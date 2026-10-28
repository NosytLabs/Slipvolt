"""Explicit bounded read-only usage report; no inference or fund movements."""
import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from gridraft.broker import Broker
from gridraft.cli import load_env
from gridraft.provider_reconciliation import reconcile_usage


async def check(args):
    load_env(args.env_file)
    key = os.getenv('OPENBROKER_API_KEY', '')
    if not key:
        raise ValueError('Provider credential is not configured')
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
        return await reconcile_usage(Broker(client, key), args.start, args.end,
                                     max_pages=args.max_pages)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--from', dest='start', type=date.fromisoformat, required=True)
    parser.add_argument('--to', dest='end', type=date.fromisoformat, required=True)
    parser.add_argument('--max-pages', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(check(args))
    except (ValueError, OSError, httpx.HTTPError, TimeoutError):
        print(json.dumps({'ok': False, 'notice': 'Provider usage report unavailable or incomplete. Check the private configuration and date window; no funds or local records changed.'}), file=sys.stderr)
        return 2
    print(json.dumps({'ok': True, **result}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
