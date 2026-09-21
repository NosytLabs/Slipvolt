"""Read-only Gonka RPC boundaries. All responses are fixtures; no funds used."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

import gridraft.gonka as gonka
from gridraft.integrations import SolanaRPC, MAINNET_GENESIS

ADDRESS = 'gonka1r2s0rwgskp6y4ed7qr7d25qdwjwlvpp6demv90'


def status_payload(**changes):
    sync = {'latest_block_height': '6170952', 'latest_block_hash': 'A' * 64,
            'latest_block_time': datetime.now(timezone.utc).isoformat(), 'catching_up': False}
    sync.update(changes)
    return {'jsonrpc': '2.0', 'id': -1, 'result': {
        'node_info': {'network': 'gonka-mainnet'}, 'sync_info': sync}}


def test_native_read_verifies_chain_and_never_inherits_credentials():
    calls = []
    def handle(req):
        calls.append(req)
        assert req.method == 'GET' and req.url.host == 'rpc.gonka.gg'
        assert 'authorization' not in req.headers and 'cookie' not in req.headers
        assert 'x-api-key' not in req.headers and 'secret' not in str(req.url)
        if req.url.path == '/chain-rpc/status':
            return httpx.Response(200, json=status_payload())
        return httpx.Response(200, json={'balance': {'denom': 'ngonka', 'amount': '1230000000'}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle),
                headers={'Authorization': 'Bearer secret', 'X-Api-Key': 'secret'},
                params={'api_key': 'secret'}, cookies={'session': 'secret'}, auth=('secret', 'secret')) as client:
            reader = gonka.NativeTreasury(client, ADDRESS)
            first = await reader.balance()
            assert first['chain_id'] == 'gonka-mainnet'
            assert first['amount_ngonka'] == 1230000000
            first['amount_ngonka'] = 0
            assert (await reader.balance())['amount_ngonka'] == 1230000000
    asyncio.run(run())
    assert [r.url.path for r in calls] == ['/chain-rpc/status',
        f'/chain-api/cosmos/bank/v1beta1/balances/{ADDRESS}/by_denom']


def test_unconfigured_native_wallet_does_not_make_rpc_calls():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('Unexpected RPC'))) as c:
            assert await gonka.NativeTreasury(c).balance() is None
    asyncio.run(run())


@pytest.mark.parametrize('change,expected', [
    ({'catching_up': True}, 'syncing'),
    ({'catching_up': 'false'}, 'invalid_response'),
    ({'latest_block_height': '0'}, 'invalid_response'),
    ({'latest_block_height': True}, 'invalid_response'),
    ({'latest_block_hash': 'bad'}, 'invalid_response'),
    ({'latest_block_time': '2020-01-01T00:00:00Z'}, 'stale'),
    ({'latest_block_time': 'not-a-time'}, 'invalid_response'),
    ({'latest_block_time': '2026-09-21T00:00:00'}, 'invalid_response'),
    ({'latest_block_time': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}, 'clock_skew'),
])
def test_status_is_not_healthy_for_malformed_stale_or_syncing_node(change, expected):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=status_payload(**change)))) as c:
            rpc = gonka.GonkaRPC(c)
            d = await rpc.diagnostics()
            assert d['status'] == expected and d['transactions_sent'] == 0
            assert d['ready'] is False
    asyncio.run(run())


def test_wrong_chain_never_reads_balance():
    calls = []
    def handle(req):
        calls.append(req.url.path)
        data = status_payload()
        data['result']['node_info']['network'] = 'other-chain'
        return httpx.Response(200, json=data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            with pytest.raises(ValueError):
                await gonka.NativeTreasury(c, ADDRESS).balance()
    asyncio.run(run())
    assert calls == ['/chain-rpc/status']


def test_native_failure_has_shared_cooldown_not_a_request_storm():
    calls = []
    def handle(req):
        calls.append(req.url.path)
        if req.url.path == '/chain-rpc/status':
            return httpx.Response(200, json=status_payload())
        raise httpx.ConnectError('private diagnostic detail', request=req)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            reader = gonka.NativeTreasury(c, ADDRESS)
            results = await asyncio.gather(*(reader.balance() for _ in range(12)), return_exceptions=True)
            assert all(isinstance(x, ValueError) for x in results)
            assert all('private' not in str(x) for x in results)
    asyncio.run(run())
    assert len(calls) == 2


def test_status_cache_returns_independent_values_and_retries_after_cooldown():
    calls = []
    good = False
    def handle(req):
        calls.append(req.url.path)
        return httpx.Response(200, json=status_payload()) if good else httpx.Response(503)
    async def run():
        nonlocal good
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            rpc = gonka.GonkaRPC(c)
            with patch('gridraft.gonka.time.monotonic', return_value=0):
                assert (await rpc.diagnostics())['ready'] is False
                good = True
                assert (await rpc.diagnostics())['ready'] is False
            with patch('gridraft.gonka.time.monotonic', return_value=11):
                d = await rpc.diagnostics()
                assert d['ready'] is True
                d['chain_id'] = 'tampered'
                assert (await rpc.diagnostics())['chain_id'] == 'gonka-mainnet'
    asyncio.run(run())
    assert len(calls) == 2


@pytest.mark.parametrize('data', [[], {'error': {'message': 'private upstream detail'}},
    {'result': {}}, {'jsonrpc': '2.0', 'result': {'node_info': {'network': 'gonka-testnet'}, 'sync_info': {}}}])
def test_bad_status_is_sanitized(data):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as c:
            result = await gonka.GonkaRPC(c).diagnostics()
            assert result['ready'] is False and 'private' not in str(result)
    asyncio.run(run())


def test_rpc_redirect_is_not_followed_even_with_client_redirects_enabled():
    seen = []
    def handle(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={'Location': 'https://elsewhere.test/private'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle), follow_redirects=True) as c:
            assert (await gonka.GonkaRPC(c).diagnostics())['ready'] is False
    asyncio.run(run())
    assert seen == ['https://rpc.gonka.gg/chain-rpc/status']


def test_rpc_oversized_status_is_rejected():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=' ' * 17000))) as c:
            assert (await gonka.GonkaRPC(c).diagnostics())['ready'] is False
    asyncio.run(run())


@pytest.mark.parametrize('path', ['/chain-rpc/broadcast_tx_sync', '/chain-api/cosmos/tx/v1beta1/txs',
    '/v1/chat/completions', '//evil.test/path', '/api/endpoints', '/chain-rpc/status?key=secret'])
def test_no_arbitrary_routes_transaction_or_inference_dispatch(path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('Not allowlisted'))) as c:
            with pytest.raises(ValueError):
                await gonka.GonkaRPC(c).read(path)
    asyncio.run(run())


def test_model_zero_limits_are_unknown_and_aliases_use_tighter_positive_value():
    data = {'data': [
        {'id': 'MiniMaxAI/MiniMax-M2.7', 'context_length': 0, 'max_output_length': 0},
        {'id': 'example/model', 'context_length': 100000, 'max_output_length': 8192, 'max_completion_tokens': 4096},
    ]}
    def handle(req):
        return httpx.Response(200, json=status_payload() if req.url.path == '/chain-rpc/status' else data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            result = await gonka.GonkaRPC(c).models()
            assert result['data'][0]['context_length'] is None
            assert result['data'][0]['max_completion_tokens'] is None
            assert result['data'][1]['max_completion_tokens'] == 4096
            assert result['inference_verified'] is False
    asyncio.run(run())


def test_duplicate_models_are_not_silently_overwritten():
    def handle(req):
        data = status_payload() if req.url.path == '/chain-rpc/status' else {'data': [{'id': 'same/model'}, {'id': 'same/model'}]}
        return httpx.Response(200, json=data)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            with pytest.raises(ValueError):
                await gonka.GonkaRPC(c).models()
    asyncio.run(run())


def test_solana_first_network_check_is_not_skipped_near_monotonic_zero():
    calls = []
    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={'result': MAINNET_GENESIS})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            rpc = SolanaRPC(c, 'https://solana.test')
            with patch('gridraft.integrations.time.monotonic', return_value=10):
                await rpc.ensure_mainnet()
                await rpc.ensure_mainnet()
    asyncio.run(run())
    assert len(calls) == 1


def test_operator_check_includes_models_and_keeps_native_balance_separate():
    from scripts.check_gonka import check
    paths = []
    def handle(req):
        paths.append(req.url.path)
        assert req.method == 'GET'
        if req.url.path == '/chain-rpc/status':
            data = status_payload()
        elif req.url.path == '/v1/models':
            data = {'data': [{'id': 'example/model', 'context_length': 0, 'max_output_length': 0}]}
        else:
            data = {'balance': {'denom': 'ngonka', 'amount': '123'}}
        return httpx.Response(200, json=data)
    result = asyncio.run(check(True, ADDRESS, httpx.MockTransport(handle)))
    assert result['ready'] is True
    assert result['treasury']['amount_ngonka'] == 123
    assert result['models']['data'][0]['context_length'] is None
    assert result['inference_calls'] == 0 and result['transactions_sent'] == 0
    assert len(paths) == 3


def test_operator_check_does_not_report_success_if_requested_catalog_fails():
    from scripts.check_gonka import check
    def handle(req):
        return httpx.Response(200, json=status_payload()) if req.url.path == '/chain-rpc/status' else httpx.Response(503)
    result = asyncio.run(check(True, transport=httpx.MockTransport(handle)))
    assert result['rpc']['ready'] is True and result['ready'] is False
    assert result['models']['data'] is None


def test_operator_invalid_address_is_rejected_before_rpc_request():
    from scripts.check_gonka import check
    with pytest.raises(ValueError):
        asyncio.run(check(address='../../private', transport=httpx.MockTransport(lambda _: pytest.fail('Invalid address sent'))))


def test_expired_native_cache_is_not_served_after_rpc_failure():
    good = True
    def handle(req):
        if not good:
            return httpx.Response(503)
        return httpx.Response(200, json=status_payload() if req.url.path == '/chain-rpc/status'
            else {'balance': {'denom': 'ngonka', 'amount': '5'}})
    async def run():
        nonlocal good
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            reader = gonka.NativeTreasury(c, ADDRESS)
            with patch('gridraft.gonka.time.monotonic', return_value=10):
                assert (await reader.balance())['amount_ngonka'] == 5
            good = False
            with patch('gridraft.gonka.time.monotonic', return_value=41):
                with pytest.raises(ValueError):
                    await reader.balance()
                assert reader.cached is None
    asyncio.run(run())


@pytest.mark.parametrize('balance', [{'denom': 'WGNK', 'amount': '1'}, {'denom': 'ngonka', 'amount': True}])
def test_native_rejects_wrong_asset_or_noninteger_amount(balance):
    def handle(req):
        return httpx.Response(200, json=status_payload() if req.url.path == '/chain-rpc/status' else {'balance': balance})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            with pytest.raises(ValueError):
                await gonka.NativeTreasury(c, ADDRESS).balance()
    asyncio.run(run())
