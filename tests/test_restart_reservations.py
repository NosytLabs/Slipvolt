"""Startup does not treat an unfinished provider request as free."""
import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import Settings, create_app
from gridraft.membership import Membership
from gridraft.store import Store
from test_gridraft import BODY, MODEL, WALLET, provider
from test_membership import handler, member_settings


@pytest.mark.parametrize('holder', [False, True])
@pytest.mark.parametrize('other_instance_finishes', [False, True])
def test_startup_holds_existing_reservations_without_mutating_them(tmp_path, holder, other_instance_finishes):
    settings = member_settings() if holder else Settings(origin='http://testserver', upstream_key='obk-test-upstream')
    path = str(tmp_path/'restart.db')
    old = Store(path, settings.pepper)
    old.ensure_account(WALLET)
    key = old.issue_key(WALLET, 'existing', 10**9)
    member = Membership(old)
    if holder:
        member.allocate(10_000_000, 'fixture-funding')
        request_id = member.reserve(key['id'], WALLET, MODEL, 'old', 100,
            wallet_daily=250000, global_daily=1000000, ngonka_per_token=25,
            upstream_available=10_000_000, rpm=30)
    else:
        old.credit(WALLET, 1_000_000_000, 'fixture-credit')
        request_id = old.reserve(key['id'], WALLET, 10000, 'old', MODEL, 30)
    if not other_instance_finishes:
        old.close()

    sent = []
    def upstream(request):
        if request.url.path.endswith('/chat/completions'):
            sent.append(1)
        return handler(request) if holder else provider(request)

    app = create_app(settings, path, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer ' + key['key']}
        assert client.get('/api/status').json()['billing_review_required'] is True
        response = client.post('/v1/chat/completions', headers=headers, json=BODY)
        assert response.status_code == 503
        assert sent == []
        pending = app.state.membership.pending() if holder else app.state.store.pending()
        assert pending[0]['id'] == request_id and pending[0]['state'] == 'reserved'

        # The preexisting request may still complete in another process. Startup
        # must not change its state or prevent that process from settling it.
        target = (member if holder else old) if other_instance_finishes else (app.state.membership if holder else app.state.store)
        if holder:
            if other_instance_finishes:
                assert target.settle(request_id, 15, 150, 'devshard_settled', 'up-1')
            else:
                assert target.settle(request_id, 0, 0, 'operator_verified', evidence='checked fixture')
        else:
            if other_instance_finishes:
                assert target.settle(request_id, 1000)
            else:
                assert target.settle(request_id, 0, state='operator_settled', evidence='checked fixture')
        assert client.get('/api/status').json()['billing_review_required'] is False
        assert client.post('/v1/chat/completions', headers=headers, json=BODY).status_code == 200
        assert sent == [1]
    if other_instance_finishes:
        old.close()


@pytest.mark.parametrize('holder', [False, True])
def test_new_inflight_reservation_does_not_trigger_startup_pause(tmp_path, holder):
    settings = member_settings() if holder else Settings(origin='http://testserver', upstream_key='obk-test-upstream')
    app = create_app(settings, str(tmp_path/'active.db'), httpx.MockTransport(handler if holder else provider))
    store = app.state.store
    store.ensure_account(WALLET)
    key = store.issue_key(WALLET, 'existing', 10**9)
    if holder:
        app.state.membership.allocate(10_000_000, 'fixture-funding')
        app.state.membership.reserve(key['id'], WALLET, MODEL, 'active', 100,
            wallet_daily=250000, global_daily=1000000, ngonka_per_token=25,
            upstream_available=10_000_000, rpm=30)
    else:
        store.credit(WALLET, 1_000_000_000, 'fixture-credit')
        store.reserve(key['id'], WALLET, 10000, 'active', MODEL, 30)
    with TestClient(app) as client:
        assert client.get('/api/status').json()['billing_review_required'] is False
        response = client.post('/v1/chat/completions',
            headers={'Authorization': 'Bearer ' + key['key']}, json=BODY)
        assert response.status_code == 200
