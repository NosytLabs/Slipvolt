"""Read-only account discovery: exact balances and no inferred custody rights."""
import asyncio
import base64
from copy import deepcopy
from importlib import import_module, util
import struct

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.security import decode_address
from test_treasury_burn import MINT, OWNER, SOURCE, OTHER, TOKEN, TOKEN_2022, MAX, account, extension, fixture, raw_edit
from test_treasury_api import ADMIN, HEADERS, setup


def module():
    assert util.find_spec('gridraft.treasury_accounts') is not None, 'Treasury account discovery is missing'
    return import_module('gridraft.treasury_accounts')


def inputs(data=None):
    d = deepcopy(data or fixture())
    listing = {'context': {'slot': 500}, 'value': [{'pubkey': SOURCE, 'account': d['value'][1]}]}
    reference = {'context': {'slot': 501}, 'value': [d['value'][0], d['value'][2]]}
    return listing, reference


def parse(listing=None, reference=None, **kwargs):
    default_listing, default_reference = inputs()
    return module().parse_treasury_accounts(listing if listing is not None else default_listing,
        reference if reference is not None else default_reference, mint=MINT, treasury_owner=OWNER,
        decimals=6, **kwargs)


def test_discovery_keeps_exact_balances_and_never_builds_transactions():
    listing, reference = inputs(fixture(balance=MAX, supply=MAX))
    result = parse(listing, reference)
    assert result['schema'] == 'holdbyte.treasury-accounts.v1'
    assert result['accounts'][0] == {'address': SOURCE, 'balance_raw': str(MAX), 'review_eligible': True, 'reason': None}
    assert result['listing_slot'] == 500 and result['reference_slot'] == 501
    assert result['transactions_sent'] == 0 and result['execution_enabled'] is False
    assert 'instruction' not in result and 'authorization' not in str(result)


def test_empty_listing_is_a_real_empty_not_an_outage():
    result = parse({'context': {'slot': 500}, 'value': []})
    assert result['accounts'] == [] and result['total_raw'] == '0'


def test_zero_balance_is_not_selectable():
    result = parse(*inputs(fixture(balance=0)))
    assert result['accounts'][0]['reason'] == 'empty'
    assert result['accounts'][0]['review_eligible'] is False


@pytest.mark.parametrize('offset,value,reason', [(108, b'\x02', 'frozen'),
    (109, struct.pack('<I', 1), 'native'), (72, struct.pack('<I', 1), 'delegated'),
    (121, struct.pack('<Q', 1), 'delegated')])
def test_unsafe_sources_are_visible_but_not_selectable(offset, value, reason):
    data = fixture(); raw_edit(data, 1, offset, value)
    row = parse(*inputs(data))['accounts'][0]
    assert row['reason'] == reason and row['review_eligible'] is False


def test_unrelated_close_authority_is_blocked():
    data = fixture(); raw_edit(data, 1, 129, struct.pack('<I', 1)); raw_edit(data, 1, 133, decode_address(OTHER))
    assert parse(*inputs(data))['accounts'][0]['reason'] == 'close_authority'


def test_token2022_unreviewed_account_extension_is_not_selectable():
    data = fixture(program=TOKEN_2022)
    raw = base64.b64decode(data['value'][1]['data'][0])
    data['value'][1] = account(extension(raw, 2, [(11, bytes(64))]), TOKEN_2022)
    assert parse(*inputs(data))['accounts'][0]['reason'] == 'unsupported_extension'


def test_token2022_immutable_owner_is_supported():
    data = fixture(program=TOKEN_2022)
    raw = base64.b64decode(data['value'][1]['data'][0])
    data['value'][1] = account(extension(raw, 2, [(7, b'')]), TOKEN_2022)
    assert parse(*inputs(data))['accounts'][0]['review_eligible'] is True


@pytest.mark.parametrize('change', ['duplicate', 'bad_address', 'wrong_program', 'wrong_owner',
    'wrong_mint', 'truncated', 'bad_state', 'bad_option', 'bad_encoding', 'missing_rows', 'over_limit', 'supply'])
def test_malformed_or_inconsistent_account_sets_are_rejected(change):
    data = fixture()
    if change == 'wrong_owner': raw_edit(data, 1, 32, decode_address(OTHER))
    if change == 'wrong_mint': raw_edit(data, 1, 0, decode_address(OTHER))
    if change == 'bad_state': raw_edit(data, 1, 108, b'\x03')
    if change == 'bad_option': raw_edit(data, 1, 72, struct.pack('<I', 2))
    listing, reference = inputs(data)
    row = listing['value'][0]
    if change == 'duplicate': listing['value'].append(deepcopy(row))
    if change == 'bad_address': row['pubkey'] = 'not-an-address'
    if change == 'wrong_program': row['account']['owner'] = TOKEN_2022
    if change == 'truncated': row['account'] = account(bytes(164), TOKEN)
    if change == 'bad_encoding': row['account']['data'][1] = 'jsonParsed'
    if change == 'missing_rows': listing.pop('value')
    if change == 'over_limit': listing['value'] *= 129
    if change == 'supply':
        d = fixture(balance=1001, supply=1000); listing, reference = inputs(d)
    with pytest.raises(ValueError): parse(listing, reference)


@pytest.mark.parametrize('slot', [None, True, 0, -1, 1.5, 2**53])
def test_invalid_slots_fail(slot):
    listing, reference = inputs(); listing['context']['slot'] = slot
    with pytest.raises(ValueError): parse(listing, reference)


def test_reference_cannot_predate_listing():
    listing, reference = inputs(); reference['context']['slot'] = 499
    with pytest.raises(ValueError): parse(listing, reference)


def test_wrong_reference_precision_or_authority_fails():
    for index, offset, value in [(0, 44, b'\x09'), (0, 45, b'\x00')]:
        data = fixture(); raw_edit(data, index, offset, value)
        with pytest.raises(ValueError): parse(*inputs(data))
    listing, reference = inputs(); reference['value'][1] = account(b'data', '11111111111111111111111111111111')
    with pytest.raises(ValueError): parse(listing, reference)


def test_rpc_discovery_uses_fixed_mint_owner_finality_and_monotonic_context():
    class RPC:
        def __init__(self): self.calls = []
        async def ensure_mainnet(self): self.calls.append(('mainnet', None))
        async def call(self, method, params):
            self.calls.append((method, params))
            return inputs()[0] if method == 'getTokenAccountsByOwner' else inputs()[1]
    rpc = RPC()
    result = asyncio.run(module().discover_treasury_accounts(rpc, mint=MINT, treasury_owner=OWNER, decimals=6))
    assert result['accounts'][0]['address'] == SOURCE
    assert rpc.calls == [('mainnet', None), ('getTokenAccountsByOwner', [OWNER, {'mint': MINT},
        {'encoding': 'base64', 'commitment': 'finalized'}]), ('getMultipleAccounts', [[MINT, OWNER],
        {'encoding': 'base64', 'commitment': 'finalized', 'minContextSlot': 500}])]


def test_api_discovery_is_authenticated_and_ignores_caller_selected_owner(tmp_path):
    def upstream(payload):
        method = payload['method']
        from gridraft.integrations import MAINNET_GENESIS
        result = MAINNET_GENESIS if method == 'getGenesisHash' else inputs()[0 if method == 'getTokenAccountsByOwner' else 1]
        return httpx.Response(200, json={'result': result})
    app, calls, _ = setup(tmp_path, upstream=upstream)
    with TestClient(app) as client:
        assert client.get('/api/admin/treasury/accounts').status_code == 401
        assert calls == []
        response = client.get('/api/admin/treasury/accounts?owner='+OTHER, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['treasury_owner'] == OWNER
    assert all('authorization' not in h and 'cookie' not in h for _, h in calls)
    assert all(p['method'] not in ('sendTransaction', 'requestAirdrop') for p, _ in calls)


def test_api_error_never_returns_empty_success_or_private_rpc_text(tmp_path):
    def upstream(payload): return httpx.Response(500, text='secret private endpoint')
    app, _, _ = setup(tmp_path, upstream=upstream)
    with TestClient(app) as client:
        response = client.get('/api/admin/treasury/accounts', headers=HEADERS)
    assert response.status_code == 503
    assert 'secret' not in response.text and 'accounts' not in response.json()


def test_api_unconfigured_discovery_makes_no_calls(tmp_path):
    app, calls, _ = setup(tmp_path, owner='')
    with TestClient(app) as client:
        assert client.get('/api/admin/treasury/accounts', headers=HEADERS).status_code == 503
    assert calls == []
