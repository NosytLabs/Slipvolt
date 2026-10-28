"""Holdbyte API: wallet login, isolated keys, holder-funded and metered text inference.

Intentionally does not sign transactions, accept customer deposits, launch a
coin, expose an upstream credential, or promise unlimited holder benefits.
"""
import asyncio
import csv
import io
import json
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .http_boundary import isolated_request
from .route_support import authenticate_admin
import httpx
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .economics import WGNK, number
from .security import decode_address, digest, verify_signature
from .store import Store
from .membership import Membership
from .request_policy import input_budget
from .readiness import readiness_report
from .integrations import SolanaRPC, MetisQuotes
from .broker import Broker
from .member_gateway import MemberGateway
from .gonka import NativeTreasury
from .model_policy import MODEL_POLICIES, REVIEWED_OUTPUT_TOKENS, MODEL_LIMIT_CEILING, MAX_MESSAGES, MAX_CHOICES, merge_upstream_metadata
from .schemas import (StrictBody as StrictBody, ChallengeInput, VerifyInput, KeyInput,
                      Message as Message, ChatInput, AdminConfigInput, AdminUserInput,
                      AdminFundInput, AdminBusinessInput, SwapQuoteInput)
from .body_boundary import BodyLimitMiddleware
from .settings import (Settings, validate_settings,
                       model_limit_overrides_from_env as model_limit_overrides_from_env)

APP_VERSION = '0.9.5'
UPSTREAM = 'https://api.openbroker.gonka.gg/v1'
SNAPSHOT = [{'id':mid, **meta} for mid,meta in MODEL_POLICIES.items()]


def canonical_host(authority, scheme):
    """Normalize an HTTP Host authority and reject userinfo/path tricks."""
    if not authority or any(ch in authority for ch in ('/','?','#','\\','\r','\n','\t',' ')):
        return None
    try:
        parsed=urlparse(f'{scheme}://{authority}')
        if parsed.username is not None or parsed.password is not None or not parsed.hostname:
            return None
        port=parsed.port
    except ValueError:
        return None
    host=parsed.hostname.lower()
    if ':' in host:
        host=f'[{host}]'
    default_port=443 if scheme=='https' else 80 if scheme=='http' else None
    return host if port in (None,default_port) else f'{host}:{port}'


def create_app(settings=None, db_path=':memory:', transport=None):
    settings=validate_settings(settings or Settings.from_env())
    store=Store(db_path,settings.pepper)
    origin_parts=urlparse(settings.origin)
    expected_host=canonical_host(origin_parts.netloc,origin_parts.scheme)

    def runtime():
        base={
            'wallet_rpm':settings.request_limit,'wallet_concurrency':settings.wallet_concurrency,
            'global_rpm':settings.global_request_limit,'global_concurrency':settings.global_concurrency,
            'holder_daily_tokens':settings.holder_daily_tokens,'global_daily_tokens':settings.global_daily_tokens,
            'default_output_tokens':settings.default_output_tokens,'max_output_tokens':settings.max_output_tokens,
            'retail_input_nusd_per_token':settings.retail_input_nusd_per_token,
            'retail_output_nusd_per_token':settings.retail_output_nusd_per_token,
            'ngonka_per_token_budget':settings.allowance_ngonka_per_token,
            'maintenance_mode':False,'disabled_models':[],'gnk_usd':None,
        }
        base.update(store.operator_settings())
        return base

    client=httpx.AsyncClient(timeout=settings.timeout,transport=transport,follow_redirects=False,trust_env=False)
    rpc=SolanaRPC(client,settings.solana_rpc,settings.rpc_rps,settings.rpc_concurrency)
    quotes=MetisQuotes(client,settings.metis_url,settings.holder_mint,settings.holder_token_decimals)
    membership=Membership(store)
    broker=Broker(client,settings.upstream_key)
    native_treasury=NativeTreasury(client,settings.gonka_treasury_address)
    member_gateway=MemberGateway(settings,client,broker,membership,runtime)
    cache={'models':None,'metadata':None,'metadata_live':False,'at':0,'live':False,'health':None}
    catalog_lock=asyncio.Lock()
    health_lock=asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()
        store.close()

    app=FastAPI(title=settings.site_name+' API',version=APP_VERSION,docs_url=None,redoc_url=None,lifespan=lifespan)
    app.state.store=store
    app.state.membership=membership
    app.add_middleware(BodyLimitMiddleware,limit=settings.max_request_bytes)

    def error(message,status=400):
        raise HTTPException(status_code=status,detail=message)

    @app.exception_handler(HTTPException)
    async def handle_error(request,exc):
        headers=dict(exc.headers or {})
        if exc.status_code==429 and 'Retry-After' not in headers:headers['Retry-After']='60'
        rid=getattr(request.state,'request_id',None)
        if rid: headers['X-Request-Id']=rid
        return JSONResponse({'error':{'message':str(exc.detail),'type':'slipvolt_error','code':exc.status_code,'request_id':rid}},status_code=exc.status_code,headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return JSONResponse({'error':{'message':'Invalid request fields. See /openapi.json for the supported schema.','code':422}},status_code=422)

    @app.middleware('http')
    async def safeguards(request,call_next):
        # Security decisions use ASGI's routed path, not a URL reconstructed from Host.
        # This also avoids malformed Host values influencing API path checks.
        path=str(request.scope.get('path') or '')
        response=None
        if settings.production:
            supplied_host=canonical_host(request.headers.get('host') or '',origin_parts.scheme)
            if not expected_host or supplied_host != expected_host:
                response=JSONResponse({'error':{'message':'Invalid Host header'}},status_code=400)
        if response is None and request.method in ('POST','PUT','PATCH'):
            try:
                if int(request.headers.get('content-length','0'))>settings.max_request_bytes:
                    response=JSONResponse({'error':{'message':'Request too large'}},status_code=413)
            except ValueError:
                response=JSONResponse({'error':{'message':'Invalid Content-Length'}},status_code=400)
        if response is None and path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('origin')!=settings.origin:
                response=JSONResponse({'error':{'message':'Origin check failed'}},status_code=403)
        if response is None:
            response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        if settings.production: response.headers['Strict-Transport-Security']='max-age=31536000'
        if path.startswith(('/api/','/v1/')): response.headers['Cache-Control']='no-store'
        rate_wallet=getattr(request.state,'rate_wallet',None)
        if rate_wallet and settings.access_mode=='holder_allowance':
            for name,value in membership.rate_headers(rate_wallet,runtime()['wallet_rpm']).items():
                response.headers[name]=value
        return response

    def session(request):
        wallet=store.session_wallet(request.cookies.get('gridraft_session'))
        if not wallet: error('Sign in with your Solana wallet',401)
        return wallet

    def throttle(request,action,limit=20):
        # Do not trust a client-provided X-Forwarded-For. Configure your reverse proxy separately.
        ip=request.client.host if request.client else 'unknown'
        try: store.throttle(digest(action+ip,settings.pepper),limit)
        except ValueError: error('Rate limit reached',429)

    def admin_auth(request):
        if not settings.admin_key:error('Admin API is not configured',503)
        throttle(request,'admin-auth',120)
        # The shared helper also protects optional treasury/token admin routes
        # against oversized and non-ASCII credential headers.
        # Main write routes retain the middleware's exact-Origin requirement.
        authenticate_admin(request, settings, require_origin=False)
        return True

    def user_policy(wallet):
        return store.user_policy(wallet)

    def require_enabled_user(wallet):
        if user_policy(wallet)['disabled']:error('This wallet is disabled by the operator',403)

    def wallet_daily_limit(wallet):
        cfg=runtime();override=user_policy(wallet).get('daily_tokens_override')
        return override or cfg['holder_daily_tokens']

    async def eligibility(wallet):
        if settings.access_mode=='holder_allowance' and not settings.holder_mint:
            return {'eligible':False,'mode':'holder_allowance','reason':'Token not configured; no purchase needed yet.',
                'holding_raw':None,'threshold_raw':None,'requires_funded_credit':False}
        if settings.access_mode=='prepaid':
            return {'eligible':True,'mode':'prepaid','holding_raw':None,'requires_funded_credit':True}
        try:
            if settings.production:await rpc.ensure_mainnet()
            result=await rpc.call('getTokenAccountsByOwner',[
                wallet,{'mint':settings.holder_mint},{'encoding':'jsonParsed','commitment':'finalized'}])
            if not isinstance(result,dict) or not isinstance(result.get('value'),list) or len(result['value'])>10000:
                raise ValueError('Unexpected token accounts response')
            slot=result['context']['slot']
            if type(slot) is not int or not 1<=slot<=2**64-1:raise ValueError('Invalid finalized slot')
            total=0;seen=set()
            for item in result['value']:
                address=item['pubkey'];decode_address(address)
                if address in seen:raise ValueError('Duplicate token account')
                seen.add(address)
                account=item['account']
                if account['owner'] not in ('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'):
                    raise ValueError('Unexpected token program')
                info=account['data']['parsed']['info']
                if info['mint']!=settings.holder_mint or info['owner']!=wallet: raise ValueError('Balance mismatch')
                amount=info['tokenAmount']['amount']
                if type(info['tokenAmount'].get('decimals')) is not int or info['tokenAmount']['decimals']!=settings.holder_token_decimals:
                    raise ValueError('Configured mint decimals do not match the chain')
                if not isinstance(amount,str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})',amount): raise ValueError('Invalid raw balance')
                raw=int(amount)
                if raw>2**64-1:raise ValueError('Invalid raw balance')
                if info.get('state')=='initialized':
                    total+=raw
                    if total>2**64-1:raise ValueError('Invalid total balance')
            return {'eligible':total>=settings.min_holding_raw,'mode':settings.access_mode,'holding_raw':str(total),
                'threshold_raw':str(settings.min_holding_raw),'mint':settings.holder_mint,
                'slot':slot,'commitment':'finalized','requires_funded_credit':settings.access_mode!='holder_allowance'}
        except Exception:
            error('Cannot verify finalized holder balance; access is closed until RPC recovers',503)

    async def catalog():
        async with catalog_lock:
            cfg=runtime();ttl=60 if cache['live'] else 10
            fresh=cache['models'] is not None and time.time()-cache['at']<ttl
            if not fresh:
                try:
                    rows=(await broker.read('/v1/models'))['data']
                    if not isinstance(rows,list) or not rows or len(rows)>1000: raise ValueError()
                    ids=list(dict.fromkeys(m['id'] for m in rows if isinstance(m,dict) and isinstance(m.get('id'),str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:+-]{0,149}',m['id'])))
                    if not ids: raise ValueError()
                    try:
                        metadata=await broker.model_metadata()
                        metadata_live=any(i in metadata for i in ids)
                    except Exception:
                        metadata={};metadata_live=False
                    models=[{'id':i} for i in ids]
                    cache.update(models=models,metadata=metadata,metadata_live=metadata_live,at=time.time(),live=True)
                except Exception:
                    models=[{'id':m['id']} for m in SNAPSHOT]
                    cache.update(models=models,metadata={},metadata_live=False,at=time.time(),live=False)
            disabled=set(cfg.get('disabled_models',[]))
            metadata=cache.get('metadata') or {}
            return [merge_upstream_metadata(m['id'],metadata.get(m['id']),cfg['max_output_tokens'],settings.model_limit_overrides.get(m['id']))
                for m in cache['models'] if m['id'] not in disabled],cache['live']

    async def provider_health(ttl=15):
        async with health_lock:
            now=time.time()
            if cache.get('health_attempt') is not None and 0<=now-cache['health_attempt']<ttl:
                return cache.get('health')
            cache.update(health=None,health_attempt=now)
            try:
                value=await broker.provider_status()
                cache.update(health=value)
                return value
            except Exception:
                # A failed refresh invalidates health claims, not a fresh catalog.
                return None

    def normalize_completion_request(body, models):
        cfg=runtime();by_id={m['id']:m for m in models}
        meta=by_id.get(body.model)
        if not meta:error('Model not in current OpenBroker catalogue',400)
        requested=body.max_completion_tokens if body.max_completion_tokens is not None else body.max_tokens
        model_cap=meta.get('max_completion_tokens')
        if not isinstance(model_cap,int) or model_cap<1:
            error('No reviewed output policy for this model; operator review is required',503)
        cap=min(cfg['max_output_tokens'],model_cap)
        if requested is None:requested=min(cfg['default_output_tokens'],cap)
        if requested>cap:error(f'max_tokens exceeds the {cap}-token limit for this model',400)
        body.max_tokens=requested;body.max_completion_tokens=None
        context=meta.get('context_length')
        if not isinstance(context,int) or context<1:
            error('No context policy for this model; operator review is required',503)
        payload,_=member_gateway.prepare(body)
        estimate=input_budget(payload)
        if estimate+requested>context:
            error(f'Request exceeds the conservative context admission budget ({context} tokens including output). Reduce input/output. UTF-8 estimation can overcount; no content was truncated.',400)
        return meta

    @app.get('/healthz')
    async def health():
        store.db.execute('SELECT 1')
        return {'ok':True}

    @app.get('/api/status')
    async def status():
        cfg=runtime()
        return {'brand':settings.site_name,'version':APP_VERSION,'stage':'pilot implementation','provider_configured':bool(settings.upstream_key),
            'billing_review_required':store.needs_review() or membership.pool()['reconciliation_required'],
            'capabilities':{'request_preflight':settings.access_mode=='holder_allowance','status_page':True,'streaming':settings.access_mode=='holder_allowance','tools':True,'usage_export':True,'wallet_auth':True,'holder_checks':settings.access_mode in ('holder','holder_allowance')},
            'daily_budget_nusd':settings.daily_budget_nusd,'wallet_daily_budget_nusd':settings.wallet_daily_budget_nusd,
            'token_launched':settings.token_launched,'holder_gate_configured':bool(settings.holder_mint),
            'token_buy_url':f'https://pump.fun/coin/{settings.holder_mint}' if settings.token_launched else None,
            'access_mode':settings.access_mode,'treasury_execution_enabled':False,'payments_enabled':False,
            'pricing':{'input_per_million_usd':cfg['retail_input_nusd_per_token']/1000,'output_per_million_usd':cfg['retail_output_nusd_per_token']/1000},
            'retail_per_million_usd':cfg['retail_input_nusd_per_token']/1000 if cfg['retail_input_nusd_per_token']==cfg['retail_output_nusd_per_token'] else None,
            'pricing_status':'configured rate card; holder allowance remains separately funded',
            'limits':{'default_output_tokens':cfg['default_output_tokens'],'max_output_tokens':cfg['max_output_tokens'],'max_request_bytes':settings.max_request_bytes,'max_messages':MAX_MESSAGES,'max_choices':MAX_CHOICES,
                      'wallet_rpm':cfg['wallet_rpm'],'wallet_concurrency':cfg['wallet_concurrency'],'global_rpm':cfg['global_rpm'],'global_concurrency':cfg['global_concurrency']},
            'supported_api':['GET /v1/models','POST /v1/chat/completions (streaming + function tools)'],
            'holder_daily_tokens':cfg['holder_daily_tokens'],'global_daily_tokens':cfg['global_daily_tokens'],
            'holder_mint':settings.holder_mint or None,'min_holding_raw':str(settings.min_holding_raw) if settings.holder_mint else None,
            'holder_token_symbol':settings.holder_token_symbol,'holder_token_decimals':settings.holder_token_decimals,
            'treasury_asset':'GNK','key_creation_requires_payment':False,'maintenance_mode':bool(cfg['maintenance_mode']),
            'research_date':'2026-09-23','wgnk_contract':WGNK}

    @app.get('/api/models')
    async def models(request:Request):
        throttle(request,'model-catalog',60)
        rows,live=await catalog();cfg=runtime();health=await provider_health() if live else None
        health_by={m.get('model'):m for m in (health or {}).get('models',[]) if isinstance(m,dict)}
        data=[]
        for row in rows:
            h=health_by.get(row['id'],{})
            availability=h.get('status') if h.get('status') in ('healthy','degraded','unavailable') else ('listed' if live else 'unverified')
            model_cap=row.get('max_completion_tokens')
            item={**row,'availability':availability,
                'default_completion_tokens':min(cfg['default_output_tokens'],model_cap) if isinstance(model_cap,int) and model_cap>0 else None}
            for key in ('routable','capacity_available_pct','capacity_lost_pct','load_pct','in_flight_requests','max_concurrency','effective_max_concurrency'):
                if key in h:item[key]=h[key]
            data.append(item)
        if live:
            source=('OpenBroker live catalogue + separate Gonka proxy discovery metadata' if cache.get('metadata_live') else
                'OpenBroker live catalogue + reviewed local model policy; separate Gonka proxy discovery unavailable')
        else:source='Reviewed local model policy snapshot; live OpenBroker catalogue unavailable'
        return {'data':data,'source':source,
            'live':live,'inference_tested':False,
            'pricing':{'input_per_million_usd':cfg['retail_input_nusd_per_token']/1000,
                       'output_per_million_usd':cfg['retail_output_nusd_per_token']/1000,
                       'status':'configured rate card; holder allowance remains separately funded'}}

    @app.get('/v1/models')
    async def openai_models(request:Request):
        throttle(request,'model-catalog',60)
        rows,live=await catalog()
        if not live: error('Live model catalogue unavailable; see /api/models for a labelled snapshot',503)
        return {'object':'list','data':[{'id':m['id'],'object':'model','created':0,'owned_by':'openbroker',
            'context_length':m.get('context_length'),'max_completion_tokens':m.get('max_completion_tokens'),
            'openbroker_limits_verified':m.get('openbroker_limits_verified',False),
            'limits_source':m.get('limits_source'),
            'context_limit_source':m.get('context_limit_source'),
            'completion_limit_source':m.get('completion_limit_source'),
            'discovered_context_length':m.get('discovered_context_length'),
            'discovered_max_completion_tokens':m.get('discovered_max_completion_tokens'),
            'discovery_limits_status':m.get('discovery_limits_status'),
            'operator_override_configured':m.get('operator_override_configured',False)} for m in rows]}


    @app.post('/api/auth/challenge')
    async def challenge(body:ChallengeInput,request:Request):
        throttle(request,'challenge')
        try: decode_address(body.wallet)
        except ValueError as exc: error(str(exc))
        challenge_id=secrets.token_urlsafe(24)
        now=datetime.now(timezone.utc).isoformat()
        message=(f'{settings.origin} requests a {settings.site_name} sign-in.\nWallet: {body.wallet}\n'
            f'Network: Solana mainnet\nNonce: {challenge_id}\nIssued at: {now}\nExpires in: 300 seconds\n'
            'Sign-in only. This does not authorize transactions, spending, token approvals or wallet access.')
        store.challenge(body.wallet,message,challenge_id)
        return {'id':challenge_id,'message':message,'expires_in':300}

    @app.post('/api/auth/verify')
    async def verify(body:VerifyInput,request:Request):
        throttle(request,'verify',30)
        row=store.consume_challenge(body.id)
        if not row: error('Expired or already used challenge',401)
        try: verify_signature(row['wallet'],row['message'],body.signature)
        except ValueError: error('Wallet signature verification failed',401)
        token=store.new_session(row['wallet'])
        response=JSONResponse({'wallet':row['wallet']})
        response.set_cookie('gridraft_session',token,httponly=True,secure=settings.production,
            samesite='strict',max_age=3600,path='/')
        return response

    @app.post('/api/auth/logout')
    async def logout(request:Request):
        store.logout(request.cookies.get('gridraft_session'))
        response=JSONResponse({'ok':True});response.delete_cookie('gridraft_session',path='/')
        return response

    @app.post('/api/auth/logout-all')
    async def logout_all(request:Request):
        wallet=session(request)
        count=store.logout_all(wallet)
        response=JSONResponse({'sessions_revoked':count,'api_keys_revoked':False})
        response.delete_cookie('gridraft_session',path='/')
        return response

    @app.get('/api/network')
    async def network(request:Request):
        throttle(request,'network',60)
        return await broker.network()

    @app.get('/api/treasury')
    async def treasury(request:Request):
        throttle(request,'treasury',30)
        balance=None
        state='not_published'
        if settings.public_broker_balance and settings.upstream_key:
            try: balance=await broker.public_balance();state='available'
            except Exception: state='unavailable'
        native=None;native_state='not_configured'
        if settings.gonka_treasury_address:
            try: native=await native_treasury.balance();native_state='available'
            except Exception: native_state='unavailable'
        return {'asset':'GNK','network':'Gonka mainnet','broker_balance':balance,'status':state,
            'self_custody_balance':native,'self_custody_status':native_state,
            'source':'https://openbroker.gonka.gg/docs','balance_scope':'OpenBroker service balance, not a self-custody treasury wallet',
            'reserve_policy':'Native GNK funds inference. WGNK is only an optional acquisition intermediate.'}

    @app.get('/api/membership')
    async def membership_account(request:Request):
        wallet=session(request);require_enabled_user(wallet);cfg=runtime();eligible=await eligibility(wallet)
        return {**membership.account(wallet,wallet_daily_limit(wallet)),'eligibility':eligible,
            'funded_allowance_mode':settings.access_mode=='holder_allowance','requires_checkout':False,
            'history':membership.history(wallet),'global_daily_tokens':cfg['global_daily_tokens']}

    @app.post('/api/member-key',status_code=201)
    async def member_key(request:Request):
        throttle(request,'member-key',10)
        wallet=session(request);require_enabled_user(wallet)
        if runtime()['maintenance_mode']:error('Inference access is temporarily paused for maintenance',503)
        if settings.access_mode!='holder_allowance':error('Holder allowance mode is not enabled',503)
        if not (await eligibility(wallet))['eligible']:error('Hold the configured project token to create a key',403)
        try:
            result=store.issue_key(wallet,'My API key',10**15)
            result.pop('limit_nusd',None)
            return {**result,'quota_shared_with_wallet':True,'daily_ai_tokens':wallet_daily_limit(wallet)}
        except ValueError as exc:error(str(exc))

    @app.get('/api/account')
    async def account(request:Request):
        wallet=session(request);require_enabled_user(wallet)
        if settings.access_mode=='holder_allowance':
            return {'wallet':wallet,'access_mode':'holder_allowance','usage':membership.history(wallet),
                'payments_enabled':False,'notice':'Eligible holders use the funded GNK allowance. No prepaid dollar balance is required.'}
        return {**store.account(wallet),'usage':store.history(wallet),'payments_enabled':False,
            'notice':'Holding does not create credit. Credits must be funded and are not redeemable treasury shares.'}

    @app.get('/api/usage/summary')
    async def usage_summary(request:Request):
        wallet=session(request)
        return membership.usage_summary(wallet) if settings.access_mode=='holder_allowance' else store.usage_summary(wallet)

    @app.get('/api/usage/export')
    async def usage_export(request:Request):
        wallet=session(request)
        throttle(request,'csv-export',20)
        output=io.StringIO(newline='')
        holder=settings.access_mode=='holder_allowance'
        fields=(['id','model','state','tokens','prompt_tokens','completion_tokens','cached_input_tokens','reasoning_tokens','usage_status',
                 'reserved_tokens','cost_ngonka','reserved_ngonka','cost_source','created_utc'] if holder else
                ['id','model','state','prompt_tokens','completion_tokens','billed_nusd','reserved_nusd','created_utc'])
        rows=membership.history(wallet,limit=100) if holder else store.history(wallet)
        writer=csv.DictWriter(output,fieldnames=fields)
        writer.writeheader()
        for row in rows:
            row['created_utc']=datetime.fromtimestamp(row.pop('created'),timezone.utc).isoformat()
            for key,value in row.items():
                if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
                    row[key]="'"+value
            writer.writerow(row)
        return Response(output.getvalue(),media_type='text/csv',headers={
            'Content-Disposition':'attachment; filename="slipvolt-usage-latest-100.csv"',
            'Cache-Control':'no-store','X-Export-Limit':'100','X-Usage-Unit':'ngonka' if holder else 'nano-USD'})

    @app.get('/api/eligibility')
    async def eligible(request:Request): return await eligibility(session(request))

    @app.get('/api/keys')
    async def keys(request:Request):
        wallet=session(request);require_enabled_user(wallet);return {'data':store.keys(wallet)}

    @app.post('/api/keys',status_code=201)
    async def new_key(body:KeyInput,request:Request):
        wallet=session(request);require_enabled_user(wallet)
        if not (await eligibility(wallet))['eligible']: error('Holder threshold is not met',403)
        try:
            limit=number(body.limit_usd,positive=True,maximum='100000')*10**9
            if limit!=limit.to_integral_value(): raise ValueError('Too many decimal places')
            return store.issue_key(wallet,body.name,int(limit))
        except ValueError as exc: error(str(exc))

    @app.delete('/api/keys/{key_id}')
    async def delete_key(key_id:str,request:Request):
        if not store.revoke(key_id,session(request)): error('Key not found',404)
        return {'revoked':True}

    @app.post('/api/keys/revoke-all')
    async def revoke_all_keys(request:Request):
        wallet=session(request)
        throttle(request,'revoke-all',10)
        return {'revoked_count':store.revoke_all_keys(wallet),
                'notice':'New calls are blocked for revoked keys. In-flight requests may finish; accounting is retained.'}

    @app.get('/api/admin/readiness')
    async def admin_readiness(request:Request):
        admin_auth(request)
        return readiness_report(settings,runtime(),membership.pool())

    @app.get('/api/admin/connections')
    async def admin_connections(request:Request):
        admin_auth(request)
        return {
            'solana_rpc':{'configured':bool(settings.solana_rpc),'rps_budget':settings.rpc_rps,'concurrency':settings.rpc_concurrency},
            'solana_websocket':{'configured':bool(settings.solana_ws),'active_subscription':False},
            'openbroker':{'configured':bool(settings.upstream_key),'paid_inference_tested':False},
            'metis':{'configured':bool(settings.metis_url),'mode':'quote_only'},
            'zeroex':{'configured':bool(settings.zeroex_url),'mode':'not_implemented','scope':'EVM swaps, not a native GNK bridge'},
            'token':{'mint':settings.holder_mint or None,'decimals':settings.holder_token_decimals,
                     'threshold_raw':str(settings.min_holding_raw) if settings.holder_mint else None},
            'payments_enabled':False,'staking_enabled':False,'treasury_execution_enabled':False,
            'credential_policy':'Credentials live in server environment only. Rotate any endpoint key shared in a chat or screenshot.'}

    @app.post('/api/admin/connections/check')
    async def admin_connections_check(request:Request):
        admin_auth(request);throttle(request,'connections-check',6)
        result=await rpc.diagnostics()
        store.audit('rpc_diagnostic','Solana',result['status'])
        return {'rpc':result,'transactions_sent':0,'websocket':'configured, not tested' if settings.solana_ws else 'unconfigured'}

    @app.post('/api/admin/connections/priority-fee')
    async def admin_priority(request:Request):
        admin_auth(request);throttle(request,'priority-check',6)
        try:return await rpc.priority()
        except Exception:error('Priority fee estimate unavailable; verify the add-on and endpoint authorization',503)

    @app.post('/api/admin/swap/quote')
    async def admin_swap_quote(body:SwapQuoteInput,request:Request):
        admin_auth(request);throttle(request,'swap-quote',12)
        try:return await quotes.quote(body.asset,body.amount,body.slippage_bps)
        except LookupError as exc:error(str(exc),503)
        except ValueError as exc:error(str(exc),400)
        except Exception:error('No validated quote is available. Check the Metis endpoint, route liquidity and slippage. No funds moved.',502)

    @app.get('/api/admin/config')
    async def admin_config(request:Request):
        admin_auth(request);cfg=runtime()
        return {**cfg,
            'retail_input_per_million_usd':cfg['retail_input_nusd_per_token']/1000,
            'retail_output_per_million_usd':cfg['retail_output_nusd_per_token']/1000,
            'reviewed_default_output_cap':REVIEWED_OUTPUT_TOKENS,
            'model_limit_configuration_ceiling':MODEL_LIMIT_CEILING,
            'max_request_bytes':settings.max_request_bytes}

    @app.put('/api/admin/config')
    async def update_admin_config(body:AdminConfigInput,request:Request):
        admin_auth(request)
        rows,_=await catalog();known={m['id'] for m in rows}|set(runtime().get('disabled_models',[]))
        if any(model not in known for model in body.disabled_models):error('Unknown model in disabled_models',400)
        values=body.model_dump()
        if values['ngonka_per_token_budget'] is None:
            values['ngonka_per_token_budget']=runtime()['ngonka_per_token_budget']
        # Names stored internally match the runtime limiter.
        values['wallet_rpm']=values.pop('wallet_rpm')
        values['global_rpm']=values.pop('global_rpm')
        store.set_operator_settings(values)
        store.audit('config_updated','runtime','admin console')
        cfg=runtime()
        return {**cfg,
            'retail_input_per_million_usd':cfg['retail_input_nusd_per_token']/1000,
            'retail_output_per_million_usd':cfg['retail_output_nusd_per_token']/1000}

    @app.get('/api/admin/users')
    async def admin_users(request:Request,limit:int=100,offset:int=0,q:str=''):
        admin_auth(request)
        try:return {'data':store.admin_users(limit,offset,q),'limit':limit,'offset':offset,'q':q}
        except ValueError as exc:error(str(exc))

    @app.put('/api/admin/users/{wallet}')
    async def update_admin_user(wallet:str,body:AdminUserInput,request:Request):
        admin_auth(request)
        try:decode_address(wallet)
        except ValueError as exc:error(str(exc))
        try:
            result=store.set_user_policy(wallet,body.disabled,body.daily_tokens_override,body.note)
            store.audit('user_policy_updated',wallet,body.note[:200])
            return result
        except ValueError as exc:error(str(exc))

    @app.get('/api/admin/users/{wallet}/keys')
    async def admin_user_keys(wallet:str,request:Request):
        admin_auth(request)
        try:decode_address(wallet)
        except ValueError as exc:error(str(exc))
        return {'data':store.keys(wallet)}

    @app.delete('/api/admin/users/{wallet}/keys/{key_id}')
    async def admin_revoke_key(wallet:str,key_id:str,request:Request):
        admin_auth(request)
        try:decode_address(wallet)
        except ValueError as exc:error(str(exc))
        if not store.revoke(key_id,wallet):error('Key not found',404)
        store.audit('key_revoked',wallet,key_id[:80])
        return {'revoked':True}

    @app.get('/api/admin/audit')
    async def admin_audit(request:Request,limit:int=100):
        admin_auth(request)
        try:return {'data':store.audit_events(limit)}
        except ValueError as exc:error(str(exc))

    @app.get('/api/admin/requests')
    async def admin_requests(request:Request,limit:int=100):
        admin_auth(request)
        try:return {'data':membership.admin_requests(limit)}
        except ValueError as exc:error(str(exc))

    @app.post('/api/admin/allowance/fund')
    async def admin_fund(body:AdminFundInput,request:Request):
        admin_auth(request)
        if not body.confirm_funded:error('Confirm that native GNK is already credited before allocating it locally',400)
        try:
            amount=number(body.gnk,positive=True,maximum='1000000')*10**9
            if amount!=amount.to_integral_value():raise ValueError('Use at most nine GNK decimal places')
            amount=int(amount)
            upstream=await broker.balance()
            changed=membership.allocate(amount,body.reference,upstream_available=upstream['available_ngonka'])
            if changed:store.audit('allowance_allocated','GNK',body.reference[:200])
            return {'allocated':changed,'pool':membership.pool(),'crypto_transferred':False,
                'broker_available_ngonka':upstream['available_ngonka'],
                'notice':'Accounting allocation only. This endpoint never transfers GNK.'}
        except HTTPException:raise
        except ValueError as exc:error(str(exc))
        except Exception:error('Could not verify OpenBroker balance; no allocation was recorded',503)

    @app.post('/api/admin/business',status_code=201)
    async def admin_business(body:AdminBusinessInput,request:Request):
        admin_auth(request)
        try:
            raw=body.amount_usd.strip()
            sign=-1 if raw.startswith('-') else 1
            unsigned=raw[1:] if sign<0 else raw
            amount=number(unsigned,positive=True,maximum='1000000000')*10**9*sign
            if amount!=amount.to_integral_value():raise ValueError('Use at most nine decimal places')
            amount=int(amount)
            revenue_categories={'creator_fee','api_revenue','subscription_revenue'}
            expense_categories={'hosting','rpc','support','refund','tax','developer_payout','gnk_purchase'}
            if body.category in revenue_categories and amount<0:error('Revenue categories require a positive amount',400)
            if body.category in expense_categories and amount>0:error('Expense/outflow categories require a negative amount',400)
            store.add_business_entry(body.category,amount,body.reference,body.note)
            store.audit('business_entry_recorded',body.category,body.reference[:200])
            return {'recorded':True,'business':_business_public(store.business_summary())}
        except ValueError as exc:error(str(exc))
        except Exception as exc:
            if 'UNIQUE constraint' in str(exc):error('Business reference already exists',409)
            raise

    def _business_public(summary):
        def usd(n):return n/10**9
        return {'days':summary['days'],'entries':summary['entries'],
            'revenue_usd':usd(summary['revenue']),'expense_usd':usd(summary['expense']),
            'cash_net_usd':usd(summary['net']),
            'daily':[{'day':row['day'],'revenue_usd':usd(row['revenue']),'expense_usd':usd(row['expense']),'net_usd':usd(row['net'])} for row in summary['daily']],
            'recent':[{**row,'amount_usd':usd(row['amount_nusd'])} for row in summary['recent']]}

    @app.get('/api/admin/overview')
    async def admin_overview(request:Request,days:int=Query(default=30,ge=1,le=90)):
        admin_auth(request);cfg=runtime()
        provider_balance=provider_usage=provider_status=None
        provider_errors=[]
        if settings.upstream_key:
            try:provider_balance=await broker.balance()
            except Exception:provider_errors.append('balance_unavailable')
            try:provider_usage=await broker.usage_summary(days)
            except Exception:provider_errors.append('usage_unavailable')
        provider_status=await provider_health()
        if provider_status is None:provider_errors.append('status_unavailable')
        local=membership.admin_summary(days);pool=membership.pool();business=_business_public(store.business_summary(days))
        totals=(provider_usage or {}).get('totals',{})
        provider_cost=totals.get('cost_ngonka')
        provider_cost_known=type(provider_cost) is int
        avg_daily_cost=provider_cost/days if provider_cost_known else 0
        available=(provider_balance or {}).get('available_ngonka')
        runway_days=(available/avg_daily_cost) if type(available) is int and avg_daily_cost>0 else None
        prompt_tokens=totals.get('prompt_tokens');completion_tokens=totals.get('completion_tokens')
        detail_known=type(prompt_tokens) is int and type(completion_tokens) is int
        metered_nusd=(prompt_tokens*cfg['retail_input_nusd_per_token']+completion_tokens*cfg['retail_output_nusd_per_token']) if detail_known else None
        economics={'metered_revenue_reference_usd':metered_nusd/10**9 if metered_nusd is not None else None,
            'provider_cost_gnk':provider_cost/10**9 if provider_cost_known else None,
            'scope':'Reference margin at configured retail rates using OpenBroker usage summary. Excludes epoch accounting, hosting, RPC, support, refunds, taxes and token/treasury costs.'}
        if cfg.get('gnk_usd') is not None:
            try:
                gnk_usd=float(number(cfg['gnk_usd'],positive=True,maximum='1000000'))
                cost_usd=economics['provider_cost_gnk']*gnk_usd if provider_cost_known else None
                economics['provider_cost_usd']=cost_usd
                contribution=(economics['metered_revenue_reference_usd']-cost_usd) if metered_nusd is not None and cost_usd is not None else None
                economics['compute_contribution_reference_usd']=contribution
                economics['compute_margin_reference_pct']=(contribution/economics['metered_revenue_reference_usd']*100) if contribution is not None and economics['metered_revenue_reference_usd'] else None
            except ValueError:pass
        budget_rate=cfg['ngonka_per_token_budget']
        local_capacity=pool['available_budget_ngonka']//budget_rate if budget_rate else 0
        fund_capacity={'budget_ngonka_per_token':budget_rate,'local_available_ai_tokens':local_capacity,
            'wallet_days_at_full_allowance':local_capacity//cfg['holder_daily_tokens'] if cfg['holder_daily_tokens'] else 0,
            'broker_available_ai_tokens':((provider_balance or {}).get('available_ngonka',0)//budget_rate) if provider_balance and budget_rate else None}
        return {'window_days':days,'local':local,'pool':pool,'fund_capacity':fund_capacity,'provider_balance':provider_balance,'provider_usage':provider_usage,
            'provider_status':provider_status,'provider_errors':provider_errors,'business':business,'economics':economics,
            'runway_days_at_recent_provider_spend':round(runway_days,1) if runway_days is not None else None,
            'config':{**cfg,'retail_input_per_million_usd':cfg['retail_input_nusd_per_token']/1000,
                'retail_output_per_million_usd':cfg['retail_output_nusd_per_token']/1000}}

    @app.post('/api/preflight')
    async def preflight(body:ChatInput, request:Request):
        throttle(request,'request-preflight',30)
        raw=request.headers.get('authorization')
        key=None
        if raw is not None:
            key=store.lookup_key(raw[7:] if raw.startswith('Bearer ') else '')
            if not key:error('Invalid or revoked API key',401)
            wallet=key['wallet']
        else:
            wallet=session(request)
        require_enabled_user(wallet)
        if settings.access_mode!='holder_allowance':error('Preflight supports holder-allowance mode',400)
        cfg=runtime()
        if cfg['maintenance_mode']:error('Inference is paused for maintenance',503)
        if not settings.upstream_key:error('OpenBroker is not configured; no inference was run',503)
        rows,live=await catalog()
        if not live:error('Cannot verify live model catalog; no inference was run',503)
        meta=normalize_completion_request(body,rows)
        health=await provider_health()
        h=next((m for m in (health or {}).get('models',[]) if isinstance(m,dict) and m.get('model')==body.model),None)
        if h and (h.get('status')=='unavailable' or h.get('routable') is False):
            error('Model currently unavailable upstream',503)
        if not (await eligibility(wallet))['eligible']:error('Holding requirement not met',403)
        require_enabled_user(wallet)
        cfg=runtime()
        if cfg['maintenance_mode']:error('Inference is paused for maintenance',503)
        _,tokens=member_gateway.prepare(body)
        estimated_input=tokens-body.max_tokens*body.n
        estimated_context=estimated_input+body.max_tokens
        context_limit=meta['context_length']
        try:available=(await broker.balance())['available_ngonka']
        except Exception:error('Cannot verify provider funding; no inference was run',503)
        result=membership.preview(key['id'] if key else None,wallet,body.model,'',tokens,
            wallet_daily=cfg['holder_daily_tokens'],global_daily=cfg['global_daily_tokens'],
            ngonka_per_token=cfg['ngonka_per_token_budget'],upstream_available=available,
            rpm=cfg['wallet_rpm'],wallet_concurrency=cfg['wallet_concurrency'],
            global_rpm=cfg['global_rpm'],global_concurrency=cfg['global_concurrency'])
        if result['reason_code']=='invalid_key':error('Invalid or revoked API key',401)
        if result['reason_code']=='user_disabled':error('This wallet is disabled',403)
        return {**result,'model':body.model,'estimated_ai_tokens':tokens,
            'estimated_input_tokens':estimated_input,
            'estimated_context_tokens':estimated_context,
            'context_limit_tokens':context_limit,
            'context_headroom_tokens':context_limit-estimated_context,
            'requested_output_tokens':body.max_tokens,'choices':body.n,
            'estimated_budget_ngonka':tokens*cfg['ngonka_per_token_budget'],
            'estimate_method':'conservative_utf8_admission','inference_requests':0,
            'context_estimate_scope':'per_choice',
            'allowance_estimate_scope':'input_once_plus_output_per_choice',
            'reservation_created':False,'checked_at':int(time.time()),
            'notice':'Snapshot only. No capacity booked. Sending rechecks all limits; actual tokenization and provider billing may differ.'}

    @app.post('/v1/chat/completions')
    async def chat(body:ChatInput,request:Request):
        throttle(request,'inference-ingress',max(120,runtime()['global_rpm']))
        raw=request.headers.get('authorization','')
        key=store.lookup_key(raw[7:] if raw.startswith('Bearer ') else '')
        if not key:error('Invalid or revoked API key',401)
        require_enabled_user(key['wallet'])
        request.state.rate_wallet=key['wallet']
        cfg=runtime()
        if cfg['maintenance_mode']:error('Inference is temporarily paused for maintenance',503)
        if not settings.upstream_key:error('Operator has not configured OpenBroker; no inference was run',503)
        rows,live=await catalog()
        if not live:error('Live model catalogue unavailable; no inference was run',503)
        normalize_completion_request(body,rows)
        health=await provider_health()
        if health:
            h=next((m for m in health.get('models',[]) if isinstance(m,dict) and m.get('model')==body.model),None)
            if h and (h.get('status')=='unavailable' or h.get('routable') is False):
                error('Model is temporarily unavailable upstream; choose another model or retry shortly',503)
        if not (await eligibility(key['wallet']))['eligible']:error('Holding requirement no longer met',403)
        if settings.access_mode=='holder_allowance':
            return await member_gateway.call(body,request,key)

        # Legacy prepaid mode. Holder allowance is the recommended production flow.
        if body.stream:error('Streaming is enabled only for holder-allowance mode in this build',400)
        if store.needs_review():error('Billing reconciliation required; new inference is paused',503)
        payload=body.model_dump(exclude_none=True);encoded=json.dumps(payload,separators=(',',':')).encode()
        if len(encoded)>settings.max_request_bytes:error('Request exceeds the configured payload limit',413)
        idem=request.headers.get('idempotency-key') or str(uuid.uuid4())
        if len(idem)>100 or not idem.isprintable():error('Invalid Idempotency-Key',400)
        input_rate=cfg['retail_input_nusd_per_token'];output_rate=cfg['retail_output_nusd_per_token']
        # Reserve a tokenizer-independent input upper bound plus the requested output.
        reserve=input_budget(payload)*input_rate + body.max_tokens*body.n*output_rate
        try:
            available=(await broker.balance())['available_ngonka']
            if available<=0:error('Operator upstream balance is unavailable',503)
        except HTTPException:raise
        except Exception:error('Cannot verify upstream funds; inference is paused',503)
        try:
            rid=store.reserve(key['id'],key['wallet'],reserve,idem,body.model,cfg['wallet_rpm'],
                daily_budget_nusd=settings.daily_budget_nusd,wallet_daily_budget_nusd=settings.wallet_daily_budget_nusd)
            request.state.request_id=rid
        except ValueError as exc:
            message=str(exc);error(message,{'invalid_key':401,'duplicate_request':409,'rate_limit':429,'daily_budget':429,'wallet_daily_budget':429,'billing_review_required':503}.get(message,402))
        try:
            upstream=await client.send(isolated_request('POST',UPSTREAM+'/chat/completions',headers={'Authorization':'Bearer '+settings.upstream_key},json=payload,timeout=settings.timeout),auth=None,follow_redirects=False)
        except Exception:
            store.review(rid);error('Upstream result uncertain; reservation retained for operator reconciliation. Do not blindly retry',502)
        if not upstream.is_success:
            status=upstream.status_code
            if status in (400,401,403,404,413,422,429):
                store.settle(rid,0,state='upstream_error')
                if status==429:
                    retry=upstream.headers.get('Retry-After','5')
                    retry=retry if retry.isdigit() and 1<=int(retry)<=3600 else '5'
                    raise HTTPException(429,'OpenBroker capacity is temporarily rate limited; retry shortly.',headers={'Retry-After':retry})
                if status in (401,403):error('Operator provider authorization is unavailable; no local credit was charged',503)
                if status==404:error('Selected model is temporarily unavailable at OpenBroker; no local credit was charged',503)
                error('Provider rejected the request; local reservation released',status if status in (400,413,422) else 400)
            store.review(rid,upstream.headers.get('X-Request-Id','')[:200] or None)
            error('Upstream result uncertain; reservation retained and inference paused for reconciliation',502)
        try:
            data=upstream.json();usage=data['usage'];choices=data.get('choices')
            if not isinstance(choices,list) or not 1<=len(choices)<=body.n:raise ValueError('Invalid completion shape')
            for choice in choices:
                message=choice.get('message',{}) if isinstance(choice,dict) else {}
                if not isinstance(message,dict) or message.get('role')!='assistant':raise ValueError('Invalid assistant response')
                content=message.get('content');tools=message.get('tool_calls')
                if content is not None and not isinstance(content,str):raise ValueError('Invalid assistant content')
                if content is None and not isinstance(tools,list):raise ValueError('Assistant response has no content or tool call')
            if data.get('model',body.model)!=body.model:raise ValueError('Upstream model substitution was not requested')
            prompt,completion=usage['prompt_tokens'],usage['completion_tokens']
            if type(prompt) is not int or type(completion) is not int or not 0<=prompt<=10**7 or not 0<=completion<=10**7:raise ValueError('Invalid usage')
            actual=prompt*input_rate+completion*output_rate
            upstream_id=str(data.get('id',''))[:200]
            store.settle(rid,actual,prompt=prompt,completion=completion,upstream_id=upstream_id)
            return JSONResponse(data,headers={'X-Request-Id':rid,'X-Slipvolt-Cost-NUSD':str(actual)})
        except HTTPException:raise
        except Exception:
            store.review(rid,upstream.headers.get('X-Request-Id','')[:200] or None)
            error('Upstream usage could not be reconciled; reservation retained for review',502)

    public=Path(__file__).resolve().parents[1]/'public'
    if public.exists(): app.mount('/',StaticFiles(directory=public,html=True),name='public')
    return app
