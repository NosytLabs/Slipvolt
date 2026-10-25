"""Shared route infrastructure: no network, wallet or provider activity."""
import asyncio
from contextlib import asynccontextmanager
from importlib import import_module, util
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from gridraft.security import digest

ADMIN = 'adm_' + 'a' * 40
ORIGIN = 'https://holdbyte.example'
SETTINGS = SimpleNamespace(admin_key=ADMIN, origin=ORIGIN)


def load_support():
    assert util.find_spec('gridraft.route_support'), 'Shared route infrastructure is missing'
    return import_module('gridraft.route_support')


def request(authorization=None, origin=None, peer='127.0.0.1'):
    headers = []
    for key, value in (('authorization', authorization), ('origin', origin)):
        if value is not None:
            headers.append((key.encode(), value.encode('latin-1')))
    return Request({'type': 'http', 'method': 'POST', 'path': '/', 'headers': headers,
                    'client': (peer, 1234) if peer else None})


@pytest.mark.parametrize('key', [None, '', 'Basic '+ADMIN, 'bearer '+ADMIN,
    'Bearer ', 'Bearer sv_'+'a'*40, 'Bearer '+ADMIN+' ', 'Bearer '+'x'*513,
    'Bearer \xe9'])
def test_bad_admin_credentials_fail_closed(key):
    support = load_support()
    with pytest.raises(HTTPException) as caught:
        support.authenticate_admin(request(key, ORIGIN), SETTINGS)
    assert caught.value.status_code == 401
    assert caught.value.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('origin', [None, '', ORIGIN+'/', 'https://evil.example',
    'http://holdbyte.example', ORIGIN+':443'])
def test_writes_require_exact_origin(origin):
    support = load_support()
    with pytest.raises(HTTPException) as caught:
        support.authenticate_admin(request('Bearer '+ADMIN, origin), SETTINGS)
    assert caught.value.status_code == 403


def test_valid_admin_and_read_only_exception():
    support = load_support()
    support.authenticate_admin(request('Bearer '+ADMIN, ORIGIN), SETTINGS)
    support.authenticate_admin(request('Bearer '+ADMIN), SETTINGS, require_origin=False)
    with pytest.raises(HTTPException) as caught:
        support.authenticate_admin(request(), SETTINGS, require_origin=False)
    assert caught.value.status_code == 401


def test_disabled_admin_precedes_credential_comparison():
    support = load_support()
    with pytest.raises(HTTPException) as caught:
        support.authenticate_admin(request('Bearer '+ADMIN, ORIGIN),
                                   SimpleNamespace(admin_key='', origin=ORIGIN))
    assert caught.value.status_code == 503


class StoreFixture:
    def __init__(self):
        self.calls = []
        self.blocked = False

    def throttle(self, key, limit):
        self.calls.append((key, limit))
        if self.blocked:
            raise ValueError('private throttle implementation detail')


@pytest.mark.parametrize('bucket,limit', [('treasury:config', 20), ('treasury:plan', 12),
    ('token-audit:admin', 12), ('token-audit:public', 60)])
def test_throttle_preserves_existing_namespaces_and_limits(bucket, limit):
    support = load_support()
    store = StoreFixture()
    support.throttle_request(request(), store, 'pepper', bucket=bucket,
                             limit=limit, message='Rate limit reached')
    assert store.calls == [(digest(bucket+':127.0.0.1', 'pepper'), limit)]


def test_throttle_fallback_and_failure_are_sanitized():
    support = load_support()
    store = StoreFixture(); store.blocked = True
    with pytest.raises(HTTPException) as caught:
        support.throttle_request(request(peer=None), store, 'pepper', bucket='treasury:plan',
                                 limit=12, message='Treasury review rate limit reached')
    assert store.calls == [(digest('treasury:plan:unknown', 'pepper'), 12)]
    assert caught.value.status_code == 429
    assert caught.value.detail == 'Treasury review rate limit reached'
    assert caught.value.headers == {'Cache-Control': 'no-store', 'Retry-After': '60'}


def test_api_errors_preserve_retry_headers():
    support = load_support()
    err = support.api_error(429, 'Limit reached', **{'Retry-After': '60'})
    assert err.headers == {'Cache-Control': 'no-store', 'Retry-After': '60'}


@pytest.mark.parametrize('with_mount', [False, True])
def test_api_routes_precede_root_static_but_preserve_other_routes(tmp_path, with_mount):
    support = load_support()
    (tmp_path/'index.html').write_text('static homepage')
    app = FastAPI()
    @app.get('/existing')
    def existing(): return {'existing': True}
    original = list(app.router.routes)
    if with_mount:
        app.mount('/', StaticFiles(directory=tmp_path, html=True))
    for name in ('first', 'second'):
        router = APIRouter()
        router.add_api_route('/api/'+name, lambda: {'ok': True})
        support.register_api_routes(app, router)
    assert app.router.routes[:len(original)] == original
    with TestClient(app) as client:
        for path in ('/existing', '/api/first', '/api/second'):
            assert client.get(path).status_code == 200
        if with_mount:
            assert client.get('/').text == 'static homepage'


@pytest.mark.parametrize('failure', [None, 'startup', 'body', 'shutdown'])
def test_nested_lifespans_close_clients_even_on_failure(failure):
    support = load_support()
    events = []
    @asynccontextmanager
    async def original(_):
        events.append('startup')
        if failure == 'startup': raise RuntimeError('startup')
        try:
            yield
        finally:
            events.append('shutdown')
            if failure == 'shutdown': raise RuntimeError('shutdown')
    class Client:
        def __init__(self, name): self.name = name
        async def aclose(self): events.append(self.name)
    app = FastAPI(lifespan=original)
    support.close_client_with_app(app, Client('close-first'))
    support.close_client_with_app(app, Client('close-second'))
    async def exercise():
        async with app.router.lifespan_context(app):
            events.append('body')
            if failure == 'body': raise RuntimeError('body')
    if failure:
        with pytest.raises(RuntimeError, match=failure): asyncio.run(exercise())
    else:
        asyncio.run(exercise())
    assert events[-2:] == ['close-first', 'close-second']
    assert events.count('startup') == 1
    assert events.count('shutdown') == (0 if failure == 'startup' else 1)


def test_real_httpx_client_is_closed_at_shutdown():
    support = load_support()
    app = FastAPI()
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    support.close_client_with_app(app, client)
    async def exercise():
        async with app.router.lifespan_context(app): assert not client.is_closed
        assert client.is_closed
    asyncio.run(exercise())


@pytest.mark.parametrize('token_first', [True, False])
def test_optional_routes_compose_and_keep_error_responses_private(tmp_path, token_first):
    # Uses the actual feature modules in full-repository CI, not substitute modules.
    import sqlite3
    from gridraft.token_audit_api import install_token_audit_routes
    from gridraft.treasury_api import install_treasury_routes

    store = StoreFixture()
    store.db = sqlite3.connect(':memory:', check_same_thread=False)
    settings = SimpleNamespace(admin_key=ADMIN, origin=ORIGIN, pepper='p'*40,
        holder_mint='', holder_token_decimals=6, holder_token_symbol='project tokens',
        solana_rpc='', rpc_rps=15, rpc_concurrency=8)
    app = FastAPI(); app.state.store = store
    (tmp_path/'index.html').write_text('public fallback')
    app.mount('/', StaticFiles(directory=tmp_path, html=True))
    transport = httpx.MockTransport(lambda _: pytest.fail('Unconfigured routes must not read RPC'))
    installers = [install_token_audit_routes, install_treasury_routes]
    if not token_first: installers.reverse()
    for install in installers: install(app, settings, transport=transport)
    headers = {'Authorization': 'Bearer '+ADMIN, 'Origin': ORIGIN}
    try:
        with TestClient(app) as client:
            assert client.get('/').text == 'public fallback'
            for path in ('/api/token', '/api/admin/treasury'):
                response = client.get(path, headers=headers)
                assert response.status_code == 200
                assert response.headers['cache-control'] == 'no-store'
            body = {'signature': '1'*64}
            for auth, expected in (({}, 401), ({'Authorization': 'Bearer '+ADMIN}, 403),
                                   (headers, 503)):
                response = client.post('/api/admin/token/burns', json=body, headers=auth)
                assert response.status_code == expected
                assert response.headers['cache-control'] == 'no-store'
            store.blocked = True
            for path in ('/api/token', '/api/admin/treasury'):
                response = client.get(path, headers=headers)
                assert response.status_code == 429
                assert response.headers['retry-after'] == '60'
                assert response.headers['cache-control'] == 'no-store'
    finally:
        store.db.close()
