from .request_policy import input_budget
"""Treasury-funded text completions. Credentials remain on the server."""
from .http_boundary import isolated_request
import asyncio
import json
import uuid
import time
from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from .membership import integer

REJECTIONS={400,401,403,404,413,422,429}


def usage_tokens(usage):
    if not isinstance(usage,dict):raise ValueError('Missing usage')
    a=integer(usage['prompt_tokens'],0,10**7);b=integer(usage['completion_tokens'],0,10**7)
    if 'total_tokens' in usage and integer(usage['total_tokens'])!=a+b:raise ValueError('Usage mismatch')
    return a+b


class MemberGateway:
    def __init__(self,settings,client,broker,ledger,runtime=None):
        self.settings,self.client,self.broker,self.ledger=settings,client,broker,ledger
        self.runtime=runtime or (lambda:{'wallet_rpm':settings.request_limit,'wallet_concurrency':2,'global_rpm':300,'global_concurrency':50,'holder_daily_tokens':settings.holder_daily_tokens,'global_daily_tokens':settings.global_daily_tokens})

    def prepare(self,body):
        """One estimator shared by preflight and the real reservation path."""
        payload=body.model_dump(exclude_none=True)
        if body.stream:
            options=payload.get('stream_options') if isinstance(payload.get('stream_options'),dict) else {}
            payload['stream_options']={**options,'include_usage':True}
        if len(json.dumps(payload,separators=(',',':')).encode())>self.settings.max_request_bytes:
            raise HTTPException(413,'Request too large')
        return payload,input_budget(payload)+body.max_tokens*body.n

    async def call(self,body,request,key):
        s=self.settings;cfg=self.runtime()
        payload,reserve_tokens=self.prepare(body)
        idem=request.headers.get('idempotency-key') or str(uuid.uuid4())
        if len(idem)>100 or not idem.isprintable():raise HTTPException(400,'Invalid Idempotency-Key')
        # Over-reserve the text request; settle real input/output tokens afterwards.
        # UTF-8/JSON bytes provide a conservative estimate, not an exact tokenizer count;
        # add chat-template headroom instead of the old 4x byte multiplier that over-reserved capacity.
        try:available=(await self.broker.balance())['available_ngonka']
        except Exception:raise HTTPException(503,'Cannot verify GNK funding. No model request was sent.')
        try:
            rid=self.ledger.reserve(key['id'],key['wallet'],body.model,idem,reserve_tokens,
                wallet_daily=cfg['holder_daily_tokens'],global_daily=cfg['global_daily_tokens'],
                ngonka_per_token=cfg.get('ngonka_per_token_budget',s.allowance_ngonka_per_token),upstream_available=available,rpm=cfg['wallet_rpm'],
                wallet_concurrency=cfg['wallet_concurrency'],global_rpm=cfg['global_rpm'],global_concurrency=cfg['global_concurrency'])
        except ValueError as e:
            text=str(e)
            if text=='invalid_key':raise HTTPException(401,'Invalid or revoked API key')
            if text=='user_disabled':raise HTTPException(403,'This wallet is disabled by the operator')
            if 'duplicate' in text:raise HTTPException(409,'Duplicate Idempotency-Key for this API key')
            if text in ('wallet_allowance_exhausted','shared_allowance_exhausted'):
                reset=max(1,int((int(time.time()//86400)+1)*86400-time.time()))
                message='Daily wallet allowance exhausted' if text.startswith('wallet_') else 'Shared daily AI allowance exhausted'
                raise HTTPException(429,message+'; allowance resets at 00:00 UTC',headers={'Retry-After':str(reset)})
            if text in ('wallet_rpm_limit','global_rpm_limit'):
                raise HTTPException(429,'Request-per-minute limit reached; retry shortly',headers={'Retry-After':'60'})
            if text in ('wallet_concurrency_limit','global_concurrency_limit'):
                raise HTTPException(429,'Concurrent request limit reached; retry after an in-flight request finishes',headers={'Retry-After':'1'})
            if text=='allowance_pool_unfunded_or_exhausted':raise HTTPException(503,'The funded AI allowance pool is currently exhausted')
            if text=='broker_balance_too_low':raise HTTPException(503,'OpenBroker GNK funding is too low for this request')
            if text=='reconciliation_required':raise HTTPException(503,'Provider billing reconciliation is required before new requests can run')
            raise HTTPException(503,'Inference capacity is temporarily unavailable')
        request.state.request_id=rid
        upstream_id=None
        try:
            req=isolated_request('POST','https://api.openbroker.gonka.gg/v1/chat/completions',
                headers={'Authorization':'Bearer '+s.upstream_key},json=payload,timeout=s.timeout)
            upstream=await self.client.send(req,stream=True,auth=None,follow_redirects=False)
            upstream_id=upstream.headers.get('x-request-id','')[:200] or None
        except asyncio.CancelledError:
            self.ledger.review(rid);raise
        except Exception:
            self.ledger.review(rid);raise HTTPException(502,'Provider result uncertain; allowance is held for review. Do not retry blindly.')
        if not upstream.is_success:
            status=upstream.status_code
            retry=upstream.headers.get('retry-after','')
            await upstream.aclose()
            if status in REJECTIONS:
                self.ledger.settle(rid,0,0,'provider_rejected',upstream_id)
                if status==429:
                    retry=retry if retry.isdigit() and 1<=int(retry)<=3600 else '5'
                    raise HTTPException(429,'OpenBroker capacity is temporarily rate limited; retry shortly.',headers={'Retry-After':retry})
                if status in (401,403):raise HTTPException(503,'Operator provider authorization is unavailable; no allowance was charged.')
                if status==404:raise HTTPException(503,'Selected model is temporarily unavailable at OpenBroker; no allowance was charged.')
                code=status if status in (400,413,422) else 400
                raise HTTPException(code,'Provider rejected the request; your local allowance hold was released.')
            self.ledger.review(rid,upstream_id)
            raise HTTPException(502,'Provider result uncertain; allowance is held for review.')
        if body.stream:
            return StreamingResponse(self.stream(upstream,rid,body.model,upstream_id,cfg.get('ngonka_per_token_budget',s.allowance_ngonka_per_token)),media_type='text/event-stream',
                headers={'X-Request-Id':rid,'Cache-Control':'no-store','X-Accel-Buffering':'no'})
        try:
            chunks=[];size=0
            async with asyncio.timeout(s.timeout):
                async for chunk in upstream.aiter_bytes():
                    size+=len(chunk)
                    if size>2_000_000:raise ValueError('Provider response too large')
                    chunks.append(chunk)
            data=json.loads(b''.join(chunks));choices=data['choices']
            if data.get('model',body.model)!=body.model:raise ValueError('Model mismatch')
            if not isinstance(choices,list) or not 1<=len(choices)<=body.n:raise ValueError('Invalid choices')
            for choice in choices:
                if not isinstance(choice,dict) or not isinstance(choice.get('message'),dict):raise ValueError('Invalid choice')
                message=choice['message']
                if message.get('role')!='assistant':raise ValueError('Invalid assistant role')
                content=message.get('content')
                tool_calls=message.get('tool_calls')
                if content is not None and not isinstance(content,str):raise ValueError('Invalid assistant content')
                if content is None and not isinstance(tool_calls,list):raise ValueError('Missing assistant content/tool call')
            tokens=usage_tokens(data['usage'])
            uid=data.get('id',upstream_id)
            if not isinstance(uid,str) or not 1<=len(uid)<=200:raise ValueError('Missing request ID')
            cost,source=await self.broker.request_cost(uid,body.model,tokens,tokens*cfg.get('ngonka_per_token_budget',s.allowance_ngonka_per_token))
            self.ledger.settle(rid,tokens,cost,source,uid)
            return JSONResponse(data,headers={'X-Request-Id':rid,'X-Slipvolt-Allowance-Tokens':str(tokens),
                'X-Slipvolt-Budget-Ngonka':str(cost),'X-Slipvolt-Cost-Source':source})
        except asyncio.CancelledError:
            self.ledger.review(rid,upstream_id);raise
        except Exception:
            self.ledger.review(rid,upstream_id)
            raise HTTPException(502,'Provider response or usage uncertain; allowance is held for review.')
        finally:await upstream.aclose()

    async def stream(self,upstream,rid,model,upstream_id,budget_rate):
        done=False;tokens=None;uid=upstream_id;response_id=None;size=0;frame=[]
        try:
            async with asyncio.timeout(self.settings.timeout):
                async for line in upstream.aiter_lines():
                    size+=len(line.encode())
                    if size>2_000_000:raise ValueError('Stream too large')
                    if line:
                        if line.startswith('data:'):frame.append(line[5:].lstrip())
                        continue
                    if not frame:continue
                    content='\n'.join(frame);frame=[]
                    if content=='[DONE]':
                        if tokens is None:raise ValueError('No usage in completed stream')
                        cost,source=await self.broker.request_cost(uid,model,tokens,tokens*budget_rate)
                        self.ledger.settle(rid,tokens,cost,source,uid)
                        done=True
                        yield 'data: [DONE]\n\n'
                        break
                    d=json.loads(content)
                    if not isinstance(d,dict) or d.get('error') or d.get('model',model)!=model:raise ValueError('Invalid stream')
                    if d.get('id'):
                        if not isinstance(d['id'],str) or len(d['id'])>200:raise ValueError('Bad stream ID')
                        if response_id is not None and response_id!=d['id']:raise ValueError('Response ID changed during stream')
                        response_id=d['id'];uid=d['id']
                    if d.get('usage') is not None:tokens=usage_tokens(d['usage'])
                    choices=d.get('choices',[])
                    if not isinstance(choices,list) or len(choices)>5:raise ValueError('Invalid choices')
                    for choice in choices:
                        delta=choice.get('delta',{})
                        if not isinstance(delta,dict):raise ValueError('Invalid delta')
                    yield 'data: '+json.dumps(d,ensure_ascii=False)+'\n\n'
                if not done:raise ValueError('Incomplete stream')
        except asyncio.CancelledError:
            raise
        except Exception:
            yield 'data: '+json.dumps({'error':{'message':'Stream incomplete; allowance retained for review. Do not retry blindly.','request_id':rid}})+'\n\n'
        finally:
            if not done:self.ledger.review(rid,uid)
            await upstream.aclose()
