"""Local operator commands. This module never moves cryptocurrency."""
import argparse
import json
import os
import re
import secrets
import sys
from pathlib import Path

from .economics import number
from .security import decode_address
from .store import Store
from .membership import Membership


def usd_to_nusd(value):
    """Exact nano-dollar accounting; never round a payment to a different amount."""
    result=number(value,maximum='1000000')*10**9
    if result!=result.to_integral_value():
        raise ValueError('Use at most nine decimal places')
    return int(result)


def load_env(path):
    """Read simple KEY=value lines literally, without shell execution/expansion."""
    path=Path(path)
    if not path.exists(): return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        key,sep,value=line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*',key.strip()):
            raise ValueError('Invalid environment file syntax')
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
            value=value[1:-1]
        os.environ.setdefault(key.strip(),value)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',default='.env')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('doctor',help='Inspect local setup without network, database writes or secret output')
    commands.add_parser('init-env',help='Create a local .env with a new pepper; refuse overwrite')
    server=commands.add_parser('serve',help='Start the pilot; no real inference unless configured')
    server.add_argument('--host',default='127.0.0.1');server.add_argument('--port',type=int,default=8000)
    credit=commands.add_parser('credit',help='Grant explicitly authorized operator-funded service credit, not a crypto transfer')
    credit.add_argument('--wallet',required=True);credit.add_argument('--usd',required=True)
    credit.add_argument('--reference',required=True,help='Unique verified receipt or operator grant reference')
    commands.add_parser('pending',help='List unresolved usage reservations')
    settle=commands.add_parser('reconcile',help='Finalize a verified reservation after upstream reconciliation')
    settle.add_argument('--request-id',required=True);settle.add_argument('--billed-usd',required=True)
    settle.add_argument('--evidence',required=True,help='Reference to the upstream evidence, not a prompt or secret')
    settle.add_argument('--acknowledge-final',action='store_true',required=True)
    allocate=commands.add_parser('allocate-gnk',help='Allocate already-funded GNK to holder usage; does NOT transfer funds')
    allocate.add_argument('--gnk',required=True);allocate.add_argument('--reference',required=True)
    allocate.add_argument('--acknowledge-funded',action='store_true',required=True)
    commands.add_parser('pending-gnk',help='List pending/uncertain GNK-funded calls')
    reconcile=commands.add_parser('reconcile-gnk',help='Finalize an uncertain holder request using verified upstream evidence')
    reconcile.add_argument('--request-id',required=True);reconcile.add_argument('--ai-tokens',type=int,required=True)
    reconcile.add_argument('--gnk',required=True);reconcile.add_argument('--evidence',required=True)
    reconcile.add_argument('--acknowledge-final',action='store_true',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='doctor':
            from .doctor import report, invalid_report
            try:
                load_env(args.env_file)
                result=report(args.env_file)
            except (ValueError,OSError):
                result=invalid_report('environment_syntax','Cannot read environment file. Check KEY=value syntax and permissions locally.')
            print(json.dumps(result,indent=2))
            return 2 if result['status']=='blocked' else 0
        if args.command=='init-env':
            contents=("APP_ENV=development\nAPP_ORIGIN=http://127.0.0.1:8000\nKEY_PEPPER="+secrets.token_hex(32)+
                "\nDATABASE_PATH=data/gridraft.db\nOPENBROKER_API_KEY=\nADMIN_API_KEY="+secrets.token_urlsafe(32)+
                "\nACCESS_MODE=holder_allowance\nHOLDER_DAILY_TOKENS=250000\nGLOBAL_DAILY_TOKENS=1000000\nALLOWANCE_NGONKA_PER_TOKEN=25\nPUBLIC_BROKER_BALANCE=false\nGONKA_TREASURY_ADDRESS=\nHOLDER_TOKEN_SYMBOL=project tokens\nHOLDER_TOKEN_DECIMALS=6\nHOLDER_MINT=\nMIN_HOLDING_RAW=1\nSOLANA_RPC_URL=\nSOLANA_WSS_URL=\nSOLANA_RPC_RPS=15\nSOLANA_RPC_CONCURRENCY=8\nMETIS_API_URL=\nZEROX_API_URL=\nRETAIL_INPUT_NUSD_PER_TOKEN=75\nRETAIL_OUTPUT_NUSD_PER_TOKEN=300\nREQUESTS_PER_MINUTE=30\nWALLET_CONCURRENCY=4\nGLOBAL_REQUESTS_PER_MINUTE=300\nGLOBAL_CONCURRENCY=50\nDEFAULT_OUTPUT_TOKENS=4096\nMAX_OUTPUT_TOKENS=16384\nMAX_REQUEST_BYTES=10485760\nUPSTREAM_TIMEOUT_SECONDS=180\nDAILY_BUDGET_NUSD=10000000000\nWALLET_DAILY_BUDGET_NUSD=2000000000\n")
            fd=os.open(args.env_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(contents)
            print('Environment file created. Keep its pepper stable and private; add upstream credentials locally.')
            return 0
        load_env(args.env_file)
        if len(os.environ.get('KEY_PEPPER',''))<32:
            raise ValueError('Run init-env first or set a stable KEY_PEPPER of at least 32 characters')
        if args.command=='serve':
            import uvicorn
            uvicorn.run('gridraft.main:app',host=args.host,port=args.port,workers=1,access_log=False,proxy_headers=False)
            return 0
        path=Path(os.environ.get('DATABASE_PATH','data/gridraft.db'));path.parent.mkdir(parents=True,exist_ok=True)
        store=Store(str(path),os.environ['KEY_PEPPER'])
        try:
            if args.command=='allocate-gnk':
                member=Membership(store);amount=usd_to_nusd(args.gnk)
                if amount<=0:raise ValueError('GNK allocation must be positive')
                changed=member.allocate(amount,args.reference)
                print(json.dumps({'allocated':changed,'pool':member.pool(),'crypto_transferred':False,
                    'notice':'Local budget only. Confirm receipt and available broker balance separately.'}))
            elif args.command=='pending-gnk':
                print(json.dumps({'pending':Membership(store).pending()},indent=2))
            elif args.command=='reconcile-gnk':
                member=Membership(store);amount=usd_to_nusd(args.gnk)
                row=next((r for r in member.pending() if r['id']==args.request_id),None)
                if not row:raise ValueError('Request is not pending; no change made')
                changed=member.settle(args.request_id,args.ai_tokens,amount,'operator_verified',
                    upstream_id=row['upstream_id'],evidence=args.evidence)
                print(json.dumps({'reconciled':changed,'request_id':args.request_id,'crypto_transferred':False}))
            elif args.command=='credit':
                decode_address(args.wallet)
                amount=usd_to_nusd(args.usd)
                if amount<=0: raise ValueError('Credit must be positive')
                store.credit(args.wallet,amount,args.reference)
                print(json.dumps({'service_credit':store.account(args.wallet),'crypto_transferred':False}))
            elif args.command=='pending':
                print(json.dumps({'pending':store.pending()},indent=2))
            else:
                amount=usd_to_nusd(args.billed_usd)
                row=next((r for r in store.pending() if r['id']==args.request_id),None)
                if not row: raise ValueError('Request is not pending; no change made')
                changed=store.settle(args.request_id,amount,state='operator_settled',evidence=args.evidence)
                print(json.dumps({'reconciled':changed,'request_id':args.request_id,'crypto_transferred':False}))
        finally: store.close()
        return 0
    except (ValueError,FileExistsError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
