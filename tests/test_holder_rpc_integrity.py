"""Malformed finalized RPC balances cannot establish holder eligibility."""
import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import Settings, create_app
from test_gridraft import MINT, WALLET, login, provider

ACCOUNT_1 = 'BGocb4GEpbTFm8UFV2VsDSaBXHELPfAXrvd4vtt8QWrA'
ACCOUNT_2 = '11111111111111111111111111111111'
TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'


def account(address, amount, state='initialized'):
    return {'pubkey': address, 'account': {'owner': TOKEN_PROGRAM, 'data': {'parsed': {'info': {
        'owner': WALLET, 'mint': MINT, 'state': state,
        'tokenAmount': {'amount': amount, 'decimals': 6}}}}}}


def eligibility(tmp_path, rows, slot=123):
    def upstream(request):
        if request.url.host == 'example.invalid':
            return httpx.Response(200, json={'result': {'context': {'slot': slot}, 'value': rows}})
        return provider(request)
    settings = Settings(origin='http://testserver', access_mode='holder', holder_mint=MINT,
        min_holding_raw=1000, solana_rpc='https://example.invalid')
    app = create_app(settings, str(tmp_path/'holder.db'), httpx.MockTransport(upstream))
    with TestClient(app) as client:
        login(client)
        return client.get('/api/eligibility')


def test_duplicate_account_cannot_double_a_balance_into_eligibility(tmp_path):
    row = account(ACCOUNT_1, '600')
    response = eligibility(tmp_path, [row, copy.deepcopy(row)])
    assert response.status_code == 503


@pytest.mark.parametrize('address', [None, '', 'not-an-address'])
def test_missing_or_invalid_account_identity_fails_closed(tmp_path, address):
    assert eligibility(tmp_path, [account(address, '1000')]).status_code == 503


@pytest.mark.parametrize('amount', ['01', '١٠٠٠', str(2**64), '9'*1000])
def test_invalid_raw_token_amount_fails_closed(tmp_path, amount):
    assert eligibility(tmp_path, [account(ACCOUNT_1, amount)]).status_code == 503


@pytest.mark.parametrize('slot', [0, -1, True, '123', None, 2**64])
def test_invalid_finalized_context_slot_fails_closed(tmp_path, slot):
    assert eligibility(tmp_path, [account(ACCOUNT_1, '1000')], slot).status_code == 503


def test_distinct_accounts_count_once_and_frozen_balance_is_excluded(tmp_path):
    response = eligibility(tmp_path, [account(ACCOUNT_1, '600'), account(ACCOUNT_2, '500'), account(MINT, '9999', 'frozen')])
    assert response.status_code == 200
    assert response.json()['eligible'] is True
    assert response.json()['holding_raw'] == '1100'


def test_sum_cannot_exceed_token_supply_integer_range(tmp_path):
    assert eligibility(tmp_path, [account(ACCOUNT_1, str(2**64-1)), account(ACCOUNT_2, '1')]).status_code == 503
