"""Verify the real OpenBroker connection. Read-only unless both paid flags are supplied.

Never outputs the master key. Paid checks send ONE small fixed prompt per selected
model, with no retries. This is not a pricing or performance benchmark.
"""
import argparse
import asyncio
import json
import os
import re
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


def _safe_id(value, secret):
    """Keep only bounded, printable identifiers; never print the upstream key."""
    if (not isinstance(value, str) or
            not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', value) or
            (secret and secret in value)):
        return None
    return value


def _usage_summary(value):
    """Only numeric, self-consistent accounting fields may prove smoke usage."""
    if not isinstance(value, dict):
        return None
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    usage = {}
    for field in fields:
        number = value.get(field)
        if type(number) is not int or not 0 <= number <= 20_000_000:
            return None
        usage[field] = number
    if usage['prompt_tokens'] + usage['completion_tokens'] != usage['total_tokens']:
        return None
    return usage


async def check(args):
    load_env(args.env_file)
    key = os.getenv('OPENBROKER_API_KEY', '')
    paid = args.allow_paid_inference and args.acknowledge_cost
    if args.allow_paid_inference != args.acknowledge_cost:
        raise ValueError('Paid calls need BOTH --allow-paid-inference and --acknowledge-cost')
    if paid and not key:
        raise ValueError('Set OPENBROKER_API_KEY privately in the server environment first')

    # Do not inherit an ambient proxy or redirect a bearer credential.
    async with httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False) as client:
        broker = Broker(client, key)
        catalog = await broker.read('/v1/models')
        rows = catalog.get('data', [])
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError('Invalid model catalog')
        ids = [row['id'] for row in rows if isinstance(row, dict) and
               isinstance(row.get('id'), str) and 0 < len(row['id']) <= 150]
        report = {
            'mode': 'paid bounded smoke test' if paid else 'read-only',
            'catalog': ids, 'inference': [],
            'balance': await broker.balance() if key else None,
            'credential_configured': bool(key),
        }
        if not paid:
            report['note'] = 'No inference request sent. Re-run with both paid flags only after funding.'
            return report

        selected = [args.model] if args.model else list(MODELS)
        for model in selected:
            if model not in ids:
                report['inference'].append({
                    'model': model, 'sent': False, 'ok': False,
                    'reason': 'Not in current catalog',
                })
                continue
            # Never assume a failed or malformed result was free. One attempted
            # request per model, no automatic retry, no raw provider error body.
            item = {'model': model, 'sent': True, 'http_status': None,
                    'request_id': None, 'ok': False}
            try:
                async with client.stream(
                    'POST', BASE + '/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + key},
                    json={'model': model,
                          'messages': [{'role': 'user', 'content': 'Reply with the word OK.'}],
                          'max_tokens': 32, 'stream': False},
                ) as response:
                    item['http_status'] = response.status_code
                    item['request_id'] = _safe_id(response.headers.get('x-request-id'), key)
                    if response.status_code != 200:
                        item['note'] = 'Provider rejected or failed this attempt. Inspect usage before retrying; no automatic retry.'
                    else:
                        chunks = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 1_000_000:
                                raise ValueError('Oversized provider response')
                            chunks.append(chunk)
                        try:
                            data = json.loads(b''.join(chunks))
                        except (ValueError, UnicodeError):
                            data = None
                        if not isinstance(data, dict):
                            item['note'] = 'Provider returned invalid JSON. Outcome and cost need manual review; no retry.'
                        elif data.get('model') not in (None, model):
                            item['note'] = 'Provider response model differs from the requested model; review before retrying.'
                        else:
                            usage = _usage_summary(data.get('usage'))
                            choices = data.get('choices')
                            first = choices[0] if isinstance(choices, list) and len(choices) == 1 else None
                            message = first.get('message') if isinstance(first, dict) else None
                            content = message.get('content') if isinstance(message, dict) else None
                            if usage is None or not isinstance(content, str):
                                item['note'] = 'Provider output or usage could not be verified. Inspect billing before retrying.'
                            else:
                                item['request_id'] = _safe_id(data.get('id'), key) or item['request_id']
                                item['usage'] = usage
                                item['text_preview'] = content[:160].replace(key, '[REDACTED]')
                                item['ok'] = True
                                item['note'] = 'One verified bounded response; not a context, capacity or billing guarantee.'
            except (httpx.HTTPError, TimeoutError, ValueError):
                item['note'] = 'Provider result uncertain after an attempted request. Check billing; no automatic retry.'
            report['inference'].append(item)

        # A post-probe balance outage must not erase the record of attempted
        # paid requests. It does, however, prevent declaring the probe healthy.
        try:
            report['balance_after'] = await broker.balance()
            report['balance_after_unavailable'] = False
        except Exception:
            report['balance_after'] = None
            report['balance_after_unavailable'] = True
            report['note'] = 'Post-probe balance unavailable; reconcile provider usage before retrying.'
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
        return 0 if (not report.get('balance_after_unavailable') and
                     all(x.get('ok') is True for x in report['inference'])) else 1
    except Exception as exc:
        # Do not log request headers, auth material, or raw exception messages.
        print(json.dumps({'ok':False,'failure_type':type(exc).__name__,
            'note':'Check network, server configuration, and account funding. No automatic retry performed.'}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
