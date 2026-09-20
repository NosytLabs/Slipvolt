"""Read-only operator connection check. Never logs endpoints or submits transactions."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from gridraft.cli import load_env
from gridraft.integrations import SolanaRPC, validate_endpoint

async def check(priority=False):
    url=os.getenv('SOLANA_RPC_URL','')
    validate_endpoint(url)
    async with httpx.AsyncClient(follow_redirects=False,timeout=10) as client:
        rpc=SolanaRPC(client,url)
        result={'rpc':await rpc.diagnostics(),'transactions_sent':0}
        if priority:
            try:result['priority_fees']=await rpc.priority()
            except Exception:result['priority_fees']={'status':'unavailable','message':'Check installed add-on, auth and connectivity.'}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',default='.env')
    p.add_argument('--priority-fees',action='store_true',help='Also request the priority-fee read method')
    args=p.parse_args()
    try:
        load_env(args.env_file)
        result=asyncio.run(check(args.priority_fees))
        print(json.dumps(result,indent=2))
        return 0 if result['rpc']['status']=='ready' else 2
    except Exception:
        print('Connection check failed. Verify private server configuration; no transaction was sent.',file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
