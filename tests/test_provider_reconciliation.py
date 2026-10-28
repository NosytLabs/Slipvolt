"""Reconciliation uses bounded provider fixtures, never live accounts or inference."""
import asyncio
import json
from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from gridraft.broker import Broker
from gridraft.provider_reconciliation import reconcile_usage


def usage_row(identifier, source, cost):
    return {'id': identifier, 'cost_source': source, 'cost_ngonka': cost,
            'created_at': '2026-10-25T12:00:00Z'}


def fetch(rows, *, total=None, pages=None, duplicate=False):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == 'GET' and request.url.path == '/v1/usage'
        assert request.headers.get('authorization') == 'Bearer obk-private-fixture'
        query = parse_qs(request.url.query.decode())
        page = int(query['page'][0]); size = int(query['page_size'][0])
        data = rows[(page-1)*size:page*size]
        if duplicate and page == 2:
            data = [rows[0], *data[1:]]
        return httpx.Response(200, json={'data': data, 'pagination': {
            'page': page, 'page_size': size,
            'total_items': len(rows) if total is None else total,
            'total_pages': (len(rows)+size-1)//size if pages is None else pages}})
    async def run(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await reconcile_usage(Broker(client, 'obk-private-fixture'),
                date(2026,10,25), date(2026,10,25), page_size=2, **kwargs)
    return calls, run


def test_classifies_complete_bounded_pages_without_exposing_private_ids():
    rows = [usage_row('private-1', 'devshard_settled', 130),
            usage_row('private-2', 'estimated_token_price_with_retries', 100),
            usage_row('private-3', 'escrow_epoch', 7),
            usage_row('private-4', 'fallback_unbilled', 0),
            usage_row('private-5', 'unknown_provider_source', 9)]
    calls, run = fetch(rows)
    result = asyncio.run(run(max_pages=3))
    assert len(calls) == 3
    assert result['categories'] == {
        'provider_settled_requests': {'rows': 1, 'cost_ngonka': '130'},
        'estimated_requests': {'rows': 1, 'cost_ngonka': '100'},
        'epoch_adjustments': {'rows': 1, 'cost_ngonka': '7'},
        'fallback_unbilled': {'rows': 1, 'cost_ngonka': '0'},
        'other': {'rows': 1, 'cost_ngonka': '9'},
    }
    assert result['rows'] == 5 and result['pages'] == 3
    assert result['account_debits_verified'] is False
    assert 'obk-private-fixture' not in json.dumps(result)
    assert 'private-1' not in json.dumps(result)


def test_rejects_truncated_or_duplicate_pages_instead_of_reporting_partial_totals():
    rows = [usage_row(str(i), 'escrow_epoch', 1) for i in range(3)]
    calls, run = fetch(rows)
    with pytest.raises(ValueError, match='page limit'):
        asyncio.run(run(max_pages=1))
    assert len(calls) == 1
    _, run = fetch(rows, duplicate=True)
    with pytest.raises(ValueError, match='Duplicate'):
        asyncio.run(run(max_pages=2))


@pytest.mark.parametrize('value', [None, -1, True, 'bad'])
def test_unknown_or_malformed_cost_is_not_zero(value):
    _, run = fetch([usage_row('private', 'escrow_epoch', value)])
    with pytest.raises(ValueError):
        asyncio.run(run(max_pages=1))


def test_out_of_window_or_naive_provider_timestamp_fails_closed():
    for timestamp in ('2026-10-24T12:00:00Z', '2026-10-25T12:00:00'):
        row = usage_row('private', 'escrow_epoch', 1)
        row['created_at'] = timestamp
        _, run = fetch([row])
        with pytest.raises(ValueError):
            asyncio.run(run(max_pages=1))


def test_range_validation_happens_before_network_calls():
    class NoCalls:
        async def read(self, *args, **kwargs):
            raise AssertionError('Invalid date range must not call provider')
    for start, end in ((date(2026,10,26), date(2026,10,25)),
                       (date(2026,1,1), date(2026,10,25))):
        with pytest.raises(ValueError):
            asyncio.run(reconcile_usage(NoCalls(), start, end))


def test_empty_list_and_large_integer_totals_remain_exact():
    _, run = fetch([], pages=0)
    result = asyncio.run(run(max_pages=1))
    assert result['rows'] == 0
    assert result['categories']['epoch_adjustments']['cost_ngonka'] == '0'
    rows = [usage_row(str(i), 'escrow_epoch', 10**15) for i in range(10)]
    _, run = fetch(rows)
    result = asyncio.run(run(max_pages=5))
    assert result['categories']['epoch_adjustments']['cost_ngonka'] == '10000000000000000'


def test_provider_pagination_changes_fail_closed():
    class ChangingProvider:
        async def read(self, path, *args, **kwargs):
            page = int(parse_qs(path.split('?', 1)[1])['page'][0])
            return {'data': [usage_row(str(page), 'escrow_epoch', 1)],
                    'pagination': {'page': page, 'page_size': 1,
                                   'total_items': 2 if page == 1 else 3,
                                   'total_pages': 2 if page == 1 else 3}}
    with pytest.raises(ValueError, match='changed'):
        asyncio.run(reconcile_usage(ChangingProvider(), date(2026,10,25),
                                    date(2026,10,25), max_pages=3, page_size=1))


def test_cli_error_never_exposes_private_provider_details(monkeypatch, capsys):
    import scripts.reconcile_openbroker as command
    async def fail(_):
        raise ValueError('private-provider-secret')
    monkeypatch.setattr(command, 'check', fail)
    assert command.main(['--from', '2026-10-25', '--to', '2026-10-25']) == 2
    captured = capsys.readouterr()
    assert 'private-provider-secret' not in captured.out + captured.err
    assert json.loads(captured.err)['ok'] is False


def test_cli_reads_only_usage_and_emits_no_credentials(monkeypatch, capsys, tmp_path):
    import scripts.reconcile_openbroker as command
    original_client = httpx.AsyncClient
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={'data': [usage_row('private-row', 'escrow_epoch', 11)],
            'pagination': {'page': 1, 'page_size': 200, 'total_items': 1, 'total_pages': 1}})

    monkeypatch.setenv('OPENBROKER_API_KEY', 'obk-private-fixture')
    monkeypatch.setattr(command.httpx, 'AsyncClient',
                        lambda **options: original_client(transport=httpx.MockTransport(handle), **options))
    assert command.main(['--env-file', str(tmp_path/'missing.env'),
                         '--from', '2026-10-25', '--to', '2026-10-25']) == 0
    captured = capsys.readouterr()
    assert len(seen) == 1 and seen[0].method == 'GET' and seen[0].url.path == '/v1/usage'
    assert 'private' not in captured.out + captured.err
    assert json.loads(captured.out)['categories']['epoch_adjustments']['cost_ngonka'] == '11'
