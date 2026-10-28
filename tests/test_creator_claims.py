"""Offline Pump claim fixtures; these do not establish a real launch or revenue."""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
import pytest

from gridraft.integrations import MAINNET_GENESIS, SolanaRPC
from gridraft.store import Store
from test_treasury_burn import address

CREATOR, PAYER = address(3), address(5)
VAULT = 'AhZUy7SEkRSq5uqCHhjETbDpoo2r9ddVQBSqrTGxqkd6'
ATA1 = 'BJLPUUmkbkQrZzyYPuiGAYhYMqwrBnZt6cdvZDTBBRaP'
ATA2 = '2fGPdz5Q1shiutRDE8q7hxYCTQu1sxTkKb1118Mkst7v'
EVENT = 'Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1'
SIGNATURE = '1' * 64
PUMP = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
SYSTEM = '11111111111111111111111111111111'
NATIVE_MINT = 'So11111111111111111111111111111111111111112'
TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
ASSOCIATED = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
COMPUTE = 'ComputeBudget111111111111111111111111111111'
DISCRIMINATOR = 'bdpoExJbbLb'


def claim(payer=PAYER, amount=125000000):
    accounts = [CREATOR, ATA1, VAULT, ATA2, NATIVE_MINT, TOKEN, ASSOCIATED, SYSTEM, EVENT, PUMP]
    keys = [payer] + [key for key in accounts if key != payer]
    balances = {key: 1000000000 for key in keys}
    balances[VAULT] = max(balances[VAULT], amount + 1000)
    before = [balances[key] for key in keys]
    balances[payer] -= 5000
    balances[CREATOR] += amount
    balances[VAULT] -= amount
    return {'slot': 100, 'blockTime': 1700000000, 'version': 'legacy',
            'meta': {'err': None, 'fee': 5000, 'preBalances': before,
                     'postBalances': [balances[key] for key in keys], 'innerInstructions': []},
            'transaction': {'signatures': [SIGNATURE], 'message': {
                'accountKeys': [{'pubkey': key, 'signer': key == payer} for key in keys],
                'instructions': [{'programId': PUMP, 'accounts': accounts, 'data': DISCRIMINATOR}]}}}


def status():
    return {'context': {'slot': 201}, 'value': [{'slot': 100, 'err': None, 'confirmationStatus': 'finalized'}]}


@pytest.mark.parametrize('payer', [PAYER, CREATOR])
def test_exact_finalized_sol_claim_is_recorded_without_revenue_attribution(tmp_path, payer):
    from gridraft.creator_claims import parse_creator_claim, CreatorClaimLedger
    tx = claim(payer=payer)
    receipt = parse_creator_claim(tx, status(), CREATOR, SIGNATURE)
    assert receipt['amount_lamports'] == '125000000'
    assert receipt['project_attribution'] == 'unverified'
    assert receipt['recognized_revenue'] is False
    store = Store(str(tmp_path/'ledger.db'), 'p'*40)
    try:
        ledger = CreatorClaimLedger(store)
        assert ledger.record(receipt) is True
        assert ledger.record(copy.deepcopy(receipt)) is False
        conflicting = copy.deepcopy(receipt); conflicting['amount_lamports'] = '1'
        with pytest.raises(ValueError, match='Conflicting'):
            ledger.record(conflicting)
        report = ledger.summary(CREATOR)
        assert report['count'] == 1 and report['total_lamports'] == '125000000'
        assert report['recognized_revenue'] is False
        assert store.business_summary()['entries'] == 0
    finally:
        store.close()


@pytest.mark.parametrize('mutate', [
    lambda tx: tx['meta'].update(err='failed'),
    lambda tx: tx['meta'].pop('err'),
    lambda tx: tx.update(slot=101),
    lambda tx: tx.update(version=True),
    lambda tx: tx['transaction'].update(signatures=['2'*64]),
    lambda tx: tx['transaction']['message']['instructions'][0].update(data='wrong'),
    lambda tx: tx['transaction']['message']['instructions'][0].update(programId=SYSTEM),
    lambda tx: tx['transaction']['message']['instructions'][0]['accounts'].__setitem__(0, PAYER),
    lambda tx: tx['transaction']['message']['instructions'][0]['accounts'].__setitem__(4, TOKEN),
    lambda tx: tx['transaction']['message']['instructions'][0]['accounts'].__setitem__(1, PAYER),
    lambda tx: tx['transaction']['message']['instructions'][0]['accounts'].__setitem__(3, PAYER),
    lambda tx: tx['transaction']['message']['instructions'][0]['accounts'].__setitem__(8, PAYER),
    lambda tx: tx['transaction']['message']['instructions'].append({'programId':SYSTEM}),
    lambda tx: tx['meta']['postBalances'].__setitem__(1, 0),
    lambda tx: tx['meta']['postBalances'].__setitem__(-1, 1000000001),
    lambda tx: tx['meta']['preBalances'].pop(),
    lambda tx: tx['meta'].update(innerInstructions=None),
    lambda tx: tx['meta'].update(innerInstructions=[{'index': 0, 'instructions': []}, {'index': 0, 'instructions': []}]),
    lambda tx: tx['meta'].update(fee=True),
    lambda tx: tx['transaction']['message']['accountKeys'][0].update(signer=False),
    lambda tx: tx['transaction']['message']['accountKeys'].append(tx['transaction']['message']['accountKeys'][0]),
])
def test_ambiguous_or_inconsistent_evidence_is_rejected(mutate):
    from gridraft.creator_claims import parse_creator_claim
    tx = claim(); mutate(tx)
    with pytest.raises(ValueError):
        parse_creator_claim(tx, status(), CREATOR, SIGNATURE)


def test_unfinalized_or_failed_status_is_rejected():
    from gridraft.creator_claims import parse_creator_claim
    s = status(); s['value'][0]['confirmationStatus'] = 'confirmed'
    with pytest.raises(ValueError):
        parse_creator_claim(claim(), s, CREATOR, SIGNATURE)


def test_unrepresentable_slot_fails_before_receipt_is_recorded():
    from gridraft.creator_claims import parse_creator_claim
    tx, finality = claim(), status()
    tx['slot'] = 2**63
    finality['value'][0]['slot'] = 2**63
    finality['context']['slot'] = 2**63
    with pytest.raises(ValueError):
        parse_creator_claim(tx, finality, CREATOR, SIGNATURE)


def test_large_claim_stays_exact_and_compute_budget_is_permitted():
    from gridraft.creator_claims import parse_creator_claim
    tx = claim(amount=9007199254740993)
    tx['transaction']['message']['instructions'].insert(0, {'programId': COMPUTE, 'data': 'fixture'})
    receipt = parse_creator_claim(tx, status(), CREATOR, SIGNATURE)
    assert receipt['amount_lamports'] == '9007199254740993'


def test_concurrent_duplicate_claims_across_connections_record_once(tmp_path):
    from gridraft.creator_claims import parse_creator_claim, CreatorClaimLedger
    path = str(tmp_path/'shared.db')
    stores = [Store(path, 'p'*40), Store(path, 'p'*40)]
    try:
        ledgers = [CreatorClaimLedger(store) for store in stores]
        receipt = parse_creator_claim(claim(), status(), CREATOR, SIGNATURE)
        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(lambda i: ledgers[i % 2].record(receipt), range(20)))
        assert sum(results) == 1
        report = ledgers[0].summary(CREATOR)
        assert report['count'] == 1 and report['total_lamports'] == '125000000'
        assert stores[0].business_summary()['entries'] == 0
    finally:
        for store in stores:
            store.close()


def test_claim_ledger_upgrade_preserves_existing_keys_sessions_and_tables(tmp_path):
    from gridraft.creator_claims import CreatorClaimLedger
    path, pepper = str(tmp_path/'existing.db'), 'stable-fixture-pepper-'+'p'*32
    original = Store(path, pepper)
    token = original.new_session(CREATOR)
    key = original.issue_key(CREATOR, 'existing', 10**9)
    existing = {row['name']: row['sql'] for row in original.db.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='table'")}
    original.close()
    upgraded = Store(path, pepper)
    try:
        CreatorClaimLedger(upgraded)
        assert upgraded.session_wallet(token) == CREATOR
        assert upgraded.lookup_key(key['key'])['wallet'] == CREATOR
        after = {row['name']: row['sql'] for row in upgraded.db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table'")}
        assert all(after[name] == sql for name, sql in existing.items())
        assert set(after) == set(existing) | {'creator_claim_receipts'}
    finally:
        upgraded.close()


def test_auditor_makes_only_read_only_finalized_rpc_calls():
    from gridraft.creator_claims import CreatorClaimAuditor
    seen = []
    def handle(request):
        body = json.loads(request.content); seen.append(body)
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        method = body['method']
        result = MAINNET_GENESIS if method == 'getGenesisHash' else status() if method == 'getSignatureStatuses' else claim()
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': result})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            rpc = SolanaRPC(client, 'https://rpc.example.invalid', rps=1000, concurrency=2)
            return await CreatorClaimAuditor(rpc, CREATOR).verify(SIGNATURE)
    assert asyncio.run(run())['amount_lamports'] == '125000000'
    assert [item['method'] for item in seen] == ['getGenesisHash', 'getSignatureStatuses', 'getTransaction']
    assert seen[-1]['params'][1]['commitment'] == 'finalized'


def test_authenticated_routes_deduplicate_evidence_without_crediting_funds(tmp_path):
    from fastapi.testclient import TestClient
    from gridraft.app import Settings, create_app
    from gridraft.creator_claims_api import install_creator_claim_routes
    admin = 'admin-fixture-secret-' + 'x'*32
    settings = Settings(origin='http://testserver', admin_key=admin, access_mode='prepaid',
                        solana_rpc='https://rpc.example.invalid/private')
    calls = []
    def handle(request):
        body = json.loads(request.content); calls.append(body['method'])
        result = MAINNET_GENESIS if body['method'] == 'getGenesisHash' else status() if body['method'] == 'getSignatureStatuses' else claim()
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': result})
    app = create_app(settings, str(tmp_path/'route.db'))
    install_creator_claim_routes(app, settings, treasury_owner=CREATOR, transport=httpx.MockTransport(handle))
    headers = {'Authorization': 'Bearer '+admin, 'Origin': 'http://testserver'}
    with TestClient(app) as client:
        path = '/api/admin/treasury/creator-claims'
        assert client.get(path).status_code == 401
        assert client.post(path, headers={'Authorization': 'Bearer '+admin}, json={'signature': SIGNATURE}).status_code == 403
        assert calls == []
        assert client.post(path, headers=headers, json={'signature': 'I'*64}).status_code == 422
        assert calls == []
        first = client.post(path, headers=headers, json={'signature': SIGNATURE})
        assert first.status_code == 200 and first.json()['recorded'] is True
        assert first.headers['cache-control'] == 'no-store'
        second = client.post(path, headers=headers, json={'signature': SIGNATURE})
        assert second.json()['recorded'] is False
        report = client.get(path, headers={'Authorization': 'Bearer '+admin}).json()
        assert report['count'] == 1 and report['total_lamports'] == '125000000'
        assert report['recognized_revenue'] is False
        assert app.state.store.business_summary()['entries'] == 0
        assert app.state.membership.pool()['allocated_ngonka'] == 0
        assert calls == ['getGenesisHash', 'getSignatureStatuses', 'getTransaction',
                         'getSignatureStatuses', 'getTransaction']


def test_creator_claim_routes_are_disabled_without_public_owner(tmp_path):
    from fastapi.testclient import TestClient
    from gridraft.app import Settings, create_app
    from gridraft.creator_claims_api import install_creator_claim_routes
    settings = Settings(origin='http://testserver', admin_key='admin', access_mode='prepaid')
    app = create_app(settings, str(tmp_path/'disabled.db'))
    install_creator_claim_routes(app, settings)
    with TestClient(app) as client:
        response = client.get('/api/admin/treasury/creator-claims', headers={'Authorization': 'Bearer admin'})
        assert response.status_code == 503


def test_conflicting_claim_evidence_cannot_replace_or_duplicate_receipt(tmp_path):
    from fastapi.testclient import TestClient
    from gridraft.app import Settings, create_app
    from gridraft.creator_claims_api import install_creator_claim_routes
    settings = Settings(origin='http://testserver', admin_key='admin', access_mode='prepaid',
                        solana_rpc='https://rpc.example.invalid/private')
    amounts = [125000000]
    def handle(request):
        body = json.loads(request.content)
        result = MAINNET_GENESIS if body['method'] == 'getGenesisHash' else status() if body['method'] == 'getSignatureStatuses' else claim(amount=amounts[0])
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': result})
    app = create_app(settings, str(tmp_path/'conflict.db'))
    install_creator_claim_routes(app, settings, treasury_owner=CREATOR, transport=httpx.MockTransport(handle))
    headers = {'Authorization': 'Bearer admin', 'Origin': 'http://testserver'}
    path = '/api/admin/treasury/creator-claims'
    with TestClient(app) as client:
        assert client.post(path, headers=headers, json={'signature': SIGNATURE}).status_code == 200
        amounts[0] = 200000000
        assert client.post(path, headers=headers, json={'signature': SIGNATURE}).status_code == 422
        report = client.get(path, headers={'Authorization': 'Bearer admin'}).json()
        assert report['count'] == 1 and report['total_lamports'] == '125000000'


def test_existing_system_treasury_setting_does_not_prevent_app_startup(tmp_path, monkeypatch):
    import importlib
    import sys
    from fastapi.testclient import TestClient
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path/'main.db'))
    monkeypatch.setenv('KEY_PEPPER', 'p'*64)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('APP_ORIGIN', 'http://testserver')
    monkeypatch.setenv('ADMIN_API_KEY', 'admin')
    monkeypatch.setenv('SOLANA_TREASURY_OWNER', SYSTEM)
    sys.modules.pop('gridraft.main', None)
    try:
        main = importlib.import_module('gridraft.main')
        with TestClient(main.app) as client:
            response = client.get('/api/admin/treasury/creator-claims', headers={'Authorization': 'Bearer admin'})
            assert response.status_code == 503
    finally:
        sys.modules.pop('gridraft.main', None)
