"""Read-only Gonka gateway check. No API key, signed transaction or inference."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from gridraft.cli import load_env
from gridraft.gonka import BASE, GonkaRPC, NativeTreasury


async def check(include_models=False, address='', transport=None):
    async with httpx.AsyncClient(transport=transport, timeout=8, follow_redirects=False) as client:
        rpc = GonkaRPC(client)
        treasury = NativeTreasury(client, address, rpc=rpc)  # Validate before network I/O.
        result = {'rpc': await rpc.diagnostics(), 'models': {'status': 'not_requested'},
            'treasury': {'status': 'not_configured'}, 'transactions_sent': 0,
            'inference_calls': 0, 'spends_funds': False,
            'docs': {'endpoints': BASE + '/endpoints', 'agents': BASE + '/agents',
                     'catalog': BASE + '/api/endpoints'}}
        if include_models:
            try:
                result['models'] = {'status': 'available', **await rpc.models()}
            except ValueError:
                result['models'] = {'status': 'unavailable', 'data': None}
        if address:
            try:
                result['treasury'] = {'status': 'available', **await treasury.balance()}
            except ValueError:
                result['treasury'] = {'status': 'unavailable', 'amount_ngonka': None}
        result['ready'] = (result['rpc']['ready']
            and (not include_models or result['models']['status'] == 'available')
            and (not address or result['treasury']['status'] == 'available'))
        result['notice'] = 'Read-only gateway reports, not proof of provider funding or a launch approval.'
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--models', action='store_true', help='Also read the Gonka model catalog')
    parser.add_argument('--treasury-address', help='Public Gonka address; defaults to GONKA_TREASURY_ADDRESS')
    args = parser.parse_args(argv)
    try:
        load_env(args.env_file)
        address = args.treasury_address if args.treasury_address is not None else os.getenv('GONKA_TREASURY_ADDRESS', '')
        result = asyncio.run(check(args.models, address))
        print(json.dumps(result, indent=2))
        return 0 if result['ready'] else 2
    except Exception:
        print('Gonka read check failed. Check configuration and public address; no funds were moved.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
