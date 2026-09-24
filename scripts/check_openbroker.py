"""Verify the real OpenBroker connection. Read-only unless both paid flags are supplied.

Never outputs the master key. Paid checks send ONE small fixed prompt per selected
model, with no retries. This is not a pricing or performance benchmark.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from gridraft.cli import load_env
from gridraft.broker import BASE, Broker

# Paid smoke mode checks each supported model once after confirming it is still
# present in the live catalog. No model is treated as universally reliable from
# a previous account/run, and failures are never retried automatically.
MODELS=('deepseek-ai/DeepSeek-V4-Flash-0731','zai-org/GLM-5.3-Flash','MiniMaxAI/MiniMax-M2.7')


async def check(args):
    load_env(args.env_file)
    key=os.getenv('OPENBROKER_API_KEY','')
    paid=args.allow_paid_inference and args.acknowledge_cost
    if args.allow_paid_inference != args.acknowledge_cost:
        raise ValueError('Paid calls need BOTH --allow-paid-inference and --acknowledge-cost')
    if paid and not key:raise ValueError('Set OPENBROKER_API_KEY privately in the server environment first')
    async with httpx.AsyncClient(timeout=60,follow_redirects=False) as client:
        broker=Broker(client,key)
        catalog=await broker.read('/v1/models')
        ids=[r['id'] for r in catalog.get('data',[]) if isinstance(r,dict) and isinstance(r.get('id'),str)]
        report={'mode':'paid bounded smoke test' if paid else 'read-only','catalog':ids,'inference':[],
            'balance':await broker.balance() if key else None,'credential_configured':bool(key)}
        if not paid:
            report['note']='No inference request sent. Re-run with both paid flags only after funding.'
            return report
        selected=[args.model] if args.model else list(MODELS)
        for model in selected:
            if model not in ids:
                report['inference'].append({'model':model,'sent':False,'reason':'Not in current catalog'})
                continue
            # An explicit opt-in is required above. No automatic retry on errors.
            async with client.stream('POST',BASE+'/v1/chat/completions',headers={'Authorization':'Bearer '+key},
                json={'model':model,'messages':[{'role':'user','content':'Reply with the word OK.'}],
                      'max_tokens':32,'stream':False}) as r:
                chunks=[];size=0
                async for chunk in r.aiter_bytes():
                    size+=len(chunk)
                    if size>1000000:raise ValueError('Unexpectedly large upstream response; inspect usage before retrying')
                    chunks.append(chunk)
                data=json.loads(b''.join(chunks))
                uid=data.get('id') or r.headers.get('x-request-id')
                item={'model':model,'sent':True,'http_status':r.status_code,'request_id':uid}
                if r.is_success:
                    usage=data.get('usage',{})
                    item['usage']=usage
                    content=(data.get('choices') or [{}])[0].get('message',{}).get('content')
                    item['text_preview']=content[:160] if isinstance(content,str) else None
                    item['note']='A successful bounded check is not a load/capacity guarantee.'
                else:
                    item['note']='Failure; no retry. Inspect request cost and account usage.'
                report['inference'].append(item)
        report['balance_after']=await broker.balance()
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',default='.env')
    p.add_argument('--model',choices=MODELS)
    p.add_argument('--allow-paid-inference',action='store_true')
    p.add_argument('--acknowledge-cost',action='store_true')
    args=p.parse_args()
    try:
        report=asyncio.run(check(args));print(json.dumps(report,indent=2))
        return 0 if all(x.get('http_status')==200 for x in report['inference']) else 1
    except Exception as exc:
        # Do not log request headers, auth material, or raw exception messages.
        print(json.dumps({'ok':False,'failure_type':type(exc).__name__,
            'note':'Check network, server configuration, and account funding. No automatic retry performed.'}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
