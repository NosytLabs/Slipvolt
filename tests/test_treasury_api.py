"""Authenticated, read-only workflow fixtures; no external RPC or treasury key."""
import json
from importlib import import_module, util
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from gridraft.integrations import MAINNET_GENESIS, READ_METHODS
from test_treasury_burn import fixture, MINT, SOURCE, OWNER, OTHER

ADMIN = 'adm_' + 'a'*40
ORIGIN = 'http://testserver'
HEADERS = {'Authorization': 'Bearer '+ADMIN, 'Origin': ORIGIN}
BODY = {'source_account': SOURCE, 'amount': '1.25', 'confirm_project_owned': True}


class StoreFixture:
    def __init__(self): self.calls = {}
    def throttle(self, key, limit):
        self.calls[key] = self.calls.get(key, 0)+1
        if self.calls[key] > limit: raise ValueError('rate limited')


def setup(tmp_path, *, owner=OWNER, upstream=None, rpc_url='https://rpc.example.invalid/private', admin=ADMIN):
    assert util.find_spec('gridraft.treasury_api') is not None, 'Treasury routes are not implemented'
    install = import_module('gridraft.treasury_api').install_treasury_routes
    calls = []
    def handler(request):
        payload = json.loads(request.content); calls.append((payload, dict(request.headers)))
        if upstream: return upstream(payload)
        value = MAINNET_GENESIS if payload['method']=='getGenesisHash' else fixture()
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': value})
    app = FastAPI(); app.state.store = StoreFixture()
    app.mount('/', StaticFiles(directory=tmp_path), name='public')
    settings = SimpleNamespace(admin_key=admin, origin=ORIGIN, pepper='p'*40, holder_mint=MINT,
        holder_token_decimals=6, solana_rpc=rpc_url, rpc_rps=100000, rpc_concurrency=4)
    install(app, settings, treasury_owner=owner, transport=httpx.MockTransport(handler))
    return app, calls, settings


def test_treasury_read_methods_never_allow_broadcast():
    assert 'getMultipleAccounts' in READ_METHODS
    assert not {'sendTransaction', 'sendRawTransaction', 'requestAirdrop'} & READ_METHODS


def test_burn_plan_uses_one_finalized_snapshot_and_is_unsigned(tmp_path):
    app, calls, _ = setup(tmp_path)
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY)
    assert r.status_code==200, r.text
    assert r.headers['cache-control']=='no-store'
    assert r.json()['unsigned'] is True and r.json()['amount_raw']=='1250000'
    assert r.json()['transactions_sent']==0
    assert [p['method'] for p, _ in calls]==['getGenesisHash', 'getMultipleAccounts']
    assert calls[1][0]['params']==[[MINT, SOURCE, OWNER], {'encoding':'base64','commitment':'finalized'}]
    assert all('authorization' not in h and 'cookie' not in h for _, h in calls)


def test_configuration_is_authenticated_and_never_reads_rpc(tmp_path):
    app, calls, _ = setup(tmp_path)
    with TestClient(app) as c:
        assert c.get('/api/admin/treasury').status_code==401
        r = c.get('/api/admin/treasury', headers={'Authorization':'Bearer '+ADMIN})
    assert r.status_code==200 and r.json()['treasury_owner']==OWNER
    assert r.json()['signing_enabled'] is False
    assert calls==[]


@pytest.mark.parametrize('headers', [{}, {'Authorization':'Bearer sv_'+'a'*40},
    {'Authorization':'Bearer '+ADMIN}, {**HEADERS, 'Origin':'https://evil.invalid'},
    {**HEADERS, 'Origin':ORIGIN+'/'}])
def test_authentication_and_exact_origin_fail_before_rpc(tmp_path, headers):
    app, calls, _ = setup(tmp_path)
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=headers, json=BODY)
    assert r.status_code in (401,403) and calls==[]


@pytest.mark.parametrize('change', [{'amount':'0'}, {'amount':'1e6'}, {'amount':1.25},
    {'amount':True}, {'source_account':'bad'}, {'source_account':OTHER, 'mint':OTHER},
    {'treasury_owner':OTHER}, {'confirm_project_owned':False}, {'confirm_project_owned':1},
    {'confirm_project_owned':'true'}, {'private_key':'should-not-be-accepted'}])
def test_invalid_or_custodial_input_is_not_dispatched(tmp_path, change):
    app, calls, _ = setup(tmp_path)
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json={**BODY, **change})
    assert r.status_code==422, r.text
    assert calls==[]


@pytest.mark.parametrize('config', [{'owner':''}, {'rpc_url':''}, {'admin':''}])
def test_unconfigured_service_cannot_plan(tmp_path, config):
    app, calls, _ = setup(tmp_path, **config)
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY)
    assert r.status_code==503 and calls==[]


def test_wrong_network_fails_before_account_reads(tmp_path):
    app, calls, _ = setup(tmp_path, upstream=lambda _:httpx.Response(200,json={'result':'not-mainnet'}))
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY)
    assert r.status_code==422 and len(calls)==1


def test_upstream_failure_never_leaks_private_endpoint_or_keys(tmp_path):
    app, calls, _ = setup(tmp_path, upstream=lambda _:httpx.Response(503,text='private-endpoint obk-secret'))
    with TestClient(app) as c:
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY)
    assert r.status_code==503
    assert 'private-endpoint' not in r.text and 'obk-' not in r.text and 'example.invalid' not in r.text


def test_rate_limit_bounds_rpc_work(tmp_path):
    app, calls, _ = setup(tmp_path)
    with TestClient(app) as c:
        for _ in range(12):
            assert c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY).status_code==200
        r = c.post('/api/admin/treasury/burn-plan', headers=HEADERS, json=BODY)
    assert r.status_code==429 and r.headers['retry-after']=='60'
    assert len(calls)==13  # One cached genesis read and twelve fresh account snapshots.


def test_duplicate_route_registration_is_rejected(tmp_path):
    app, _, settings = setup(tmp_path)
    with pytest.raises(ValueError):
        import_module('gridraft.treasury_api').install_treasury_routes(app, settings)


def test_bad_treasury_configuration_fails_startup(tmp_path):
    with pytest.raises(ValueError):
        setup(tmp_path, owner='invalid')


def test_production_entry_point_registers_routes_before_static(tmp_path, monkeypatch):
    # Run with the complete repository in CI; local targeted work excludes this test.
    import importlib, sys
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path/'main.db'))
    monkeypatch.setenv('KEY_PEPPER', 'p'*64)
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('APP_ORIGIN', ORIGIN)
    monkeypatch.setenv('ADMIN_API_KEY', ADMIN)
    monkeypatch.setenv('SOLANA_TREASURY_OWNER', OWNER)
    sys.modules.pop('gridraft.main', None)
    main = importlib.import_module('gridraft.main')
    with TestClient(main.app) as c:
        assert c.get('/api/admin/treasury').status_code==401
        r = c.get('/api/admin/treasury', headers={'Authorization':'Bearer '+ADMIN})
        assert r.status_code==200 and r.json()['treasury_owner']==OWNER
        assert c.get('/admin/burns/').status_code==200
    sys.modules.pop('gridraft.main', None)
