"""Explicit read-only mint screening; no vault, signing or transaction execution."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from gridraft.cli import load_env
from gridraft.integrations import SolanaRPC, validate_endpoint
from gridraft.lock_mint_inspection import inspect_configured_mint


async def check(mint, decimals, rpc_url, *, transport=None):
    validate_endpoint(rpc_url)
    if not rpc_url:
        raise ValueError('Solana RPC is not configured')
    async with httpx.AsyncClient(transport=transport, timeout=8, trust_env=False, follow_redirects=False) as client:
        return await inspect_configured_mint(SolanaRPC(client, rpc_url), mint=mint, decimals=decimals)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--mint', help='Public mint address; defaults to HOLDER_MINT')
    parser.add_argument('--decimals', type=int, help='Expected mint precision; defaults to HOLDER_TOKEN_DECIMALS')
    args = parser.parse_args(argv)
    try:
        load_env(args.env_file)
        mint = args.mint if args.mint is not None else os.getenv('HOLDER_MINT', '')
        decimals = args.decimals if args.decimals is not None else int(os.getenv('HOLDER_TOKEN_DECIMALS', '6'))
        report = asyncio.run(check(mint, decimals, os.getenv('SOLANA_RPC_URL', '')))
        print(json.dumps(report, indent=2))
        return 2 if report['status'] == 'blocked' else 0
    except Exception:
        print(json.dumps({'status': 'unavailable', 'notice': 'Mint screening failed or found unsupported data. Check private configuration and review the mint independently. No transaction was sent.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
