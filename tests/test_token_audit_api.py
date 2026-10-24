"""Read-only token routes, with bounded mocked RPC responses."""
import copy
import importlib
import importlib.util
import json
import sqlite3
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from test_token_audit import MINT, MAINNET_GENESIS, SIGNATURE, mint_result, transaction, status

ADMIN = 'admin-' + 'x' * 40
ORIGIN = 'http://testserver'


class Store:
    def __init__(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.calls = []
    def throttle(self, bucket, limit):
        self.calls.append((bucket, limit))


def settings(**kw):
    return SimpleNamespace(**dict({'holder_mint': MINT, 'holder_token_decimals': 6,
        'holder_token_symbol': 'HBYTE', 'solana_rpc': 'https://rpc.example.invalid/private-key',
        'rpc_rps': 100, 'rpc_concurrency': 2, 'admin_key': ADMIN,
        'origin': ORIGIN, 'pepper': 'p' * 40}, **kw))


def build(tmp_path, override=None, **kw):
    assert importlib.util.find_spec('gridraft.token_audit_api') is not None, 'Token evidence routes are missing'
    mod = importlib.import_module('gridraft.token_audit_api')
    calls = []
    def handler(req):
        body = json.loads(req.content); calls.append(body['method'])
        if override:
            answer = override(body)
            if answer is not None:
                return answer
        value = {'getGenesisHash': MAINNET_GENESIS, 'getAccountInfo': mint_result(),
                 'getSignatureStatuses': status(), 'getTransaction': transaction()}[body['method']]
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': value})
    app = FastAPI(); app.state.store = Store()
    app.mount('/', StaticFiles(directory=tmp_path), name='public')
    mod.install_token_audit_routes(app, settings(**kw), transport=httpx.MockTransport(handler))
    return app, calls


def auth():
    return {'Authorization': 'Bearer ' + ADMIN, 'Origin': ORIGIN}


def test_public_route_precedes_static_mount_and_keeps_large_amounts_exact(tmp_path):
    app, calls = build(tmp_path)
    with TestClient(app) as c:
        r = c.get('/api/token')
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['status'] == 'available'
        assert data['mint_state']['supply_raw'] == '18446744073709551615'
        assert data['burns']['burned_raw'] == '0'
        assert data['burns']['complete_history'] is False
        assert data['execution_enabled'] is False
        assert 'private-key' not in r.text and ADMIN not in r.text
        assert r.headers['cache-control'] == 'no-store'
        assert c.get('/api/token').json()['status'] == 'available'
        assert calls.count('getAccountInfo') == 1
    app.state.store.db.close()


def test_prelaunch_returns_unknown_instead_of_invented_zero_supply(tmp_path):
    app, calls = build(tmp_path, holder_mint='')
    with TestClient(app) as c:
        data = c.get('/api/token').json()
        assert data['status'] == 'unconfigured'
        assert data['mint_state'] is None and data['burns'] is None
        assert calls == []
    app.state.store.db.close()


def test_rpc_failure_is_redacted_and_negative_cached(tmp_path):
    def bad(body): return httpx.Response(503, text='private-key-and-provider-debug')
    app, calls = build(tmp_path, bad)
    with TestClient(app) as c:
        first = c.get('/api/token'); second = c.get('/api/token')
        assert first.json()['status'] == second.json()['status'] == 'unavailable'
        assert first.json()['mint_state'] is None
        assert 'private-key' not in first.text
        assert len(calls) == 1
    app.state.store.db.close()


def test_record_requires_admin_and_same_origin_then_deduplicates(tmp_path):
    app, calls = build(tmp_path)
    with TestClient(app) as c:
        body = {'signature': SIGNATURE}
        assert c.post('/api/admin/token/burns', json=body).status_code == 401
        assert c.post('/api/admin/token/burns', json=body, headers={'Authorization': 'Bearer ' + ADMIN}).status_code == 403
        assert calls == []
        a = c.post('/api/admin/token/burns', json=body, headers=auth())
        b = c.post('/api/admin/token/burns', json=body, headers=auth())
        assert a.status_code == b.status_code == 200, a.text
        assert a.json()['recorded'] is True and b.json()['recorded'] is False
        assert a.json()['transactions_sent'] == 0
        public = c.get('/api/token').json()
        assert public['burns']['receipt_count'] == 1
        assert public['burns']['burned_raw'] == '9007199254740993'
        tables = {r[0] for r in app.state.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {'token_burn_receipts'}  # No account credit or cash ledger.
    app.state.store.db.close()


def test_incomplete_receipt_is_not_recorded(tmp_path):
    def partial(body):
        if body['method'] == 'getSignatureStatuses':
            d = status(); d['value'][0]['confirmationStatus'] = 'confirmed'
            return httpx.Response(200, json={'result': d})
    app, calls = build(tmp_path, partial)
    with TestClient(app) as c:
        r = c.post('/api/admin/token/burns', json={'signature': SIGNATURE}, headers=auth())
        assert r.status_code == 422
        assert 'getTransaction' not in calls
        assert c.get('/api/token').json()['burns']['receipt_count'] == 0
    app.state.store.db.close()


def test_admin_accepts_only_a_signature_not_arbitrary_mints_or_amounts(tmp_path):
    app, calls = build(tmp_path)
    with TestClient(app) as c:
        assert c.post('/api/admin/token/burns', json={'signature': SIGNATURE, 'amount': '999999'}, headers=auth()).status_code == 422
        assert c.post('/api/admin/token/burns', json={'signature': 'invalid'}, headers=auth()).status_code == 422
        assert calls == []
    app.state.store.db.close()


def test_actual_app_registration_preserves_security_headers_and_is_not_shadowed(tmp_path):
    # This integration runs in full-repository CI; the local audit checkout is partial.
    from gridraft.app import Settings, create_app
    from gridraft.token_audit_api import install_token_audit_routes
    config = Settings(origin=ORIGIN, pepper='p' * 40, admin_key=ADMIN)
    app = create_app(config, str(tmp_path / 'test.db'))
    install_token_audit_routes(app, config)
    with TestClient(app) as c:
        r = c.get('/api/token')
        assert r.status_code == 200 and r.json()['status'] == 'unconfigured'
        assert r.headers['x-content-type-options'] == 'nosniff'
        assert r.headers['cache-control'] == 'no-store'
        assert c.get('/').status_code == 200


def test_failed_refresh_clears_the_previous_live_snapshot(tmp_path, monkeypatch):
    import time as real_time
    import gridraft.token_audit_api as api
    clock = {'now': 1.0}; broken = {'value': False}
    monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda: clock['now'], time=real_time.time))
    def failure(body):
        if broken['value']:
            return httpx.Response(503, text='private upstream detail')
    app, calls = build(tmp_path, failure)
    with TestClient(app) as c:
        assert c.get('/api/token').json()['mint_state'] is not None
        broken['value'] = True; clock['now'] = 30.0
        data = c.get('/api/token').json()
        assert data['status'] == 'unavailable' and data['mint_state'] is None
        assert data['burns']['burned_raw'] == '0'
        before = len(calls)
        assert c.get('/api/token').json()['status'] == 'unavailable'
        assert len(calls) == before
    app.state.store.db.close()
