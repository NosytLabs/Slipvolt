"""Non-spending launch checks and wallet-scoped emergency controls."""
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import Settings, create_app
from test_gridraft import WALLET, ORIGIN, BODY, login
from test_membership import member_settings, handler, make_key

ADMIN = 'test-admin-control-key-at-least-32-characters'
AH = {**ORIGIN, 'Authorization': 'Bearer ' + ADMIN}


def client_for(tmp_path, **changes):
    s = member_settings(admin_key=ADMIN, **changes)
    a = create_app(s, str(tmp_path/'controls.db'), httpx.MockTransport(handler))
    return a, TestClient(a)


def test_readiness_requires_admin(tmp_path):
    a, c = client_for(tmp_path)
    with c:
        assert c.get('/api/admin/readiness').status_code == 401


def test_readiness_shows_funding_and_threshold_blockers_without_spending(tmp_path):
    a, c = client_for(tmp_path, min_holding_raw=1, upstream_key='')
    with c:
        r=c.get('/api/admin/readiness',headers=AH)
        assert r.status_code == 200, r.text
        d=r.json()
        assert d['status']=='blocked'
        checks={x['id']:x for x in d['checks']}
        assert checks['threshold']['status']=='blocked'
        assert checks['provider']['status']=='blocked'
        assert checks['compute_fund']['status']=='blocked'
        assert d['capacity']['full_allowances_per_day']==4
        assert d['spends_funds'] is False
        assert d['launch_authorized'] is False
        assert 'obk-' not in r.text
        assert 'https://example.invalid' not in r.text
        assert not a.state.membership.pending()


def test_readiness_never_infers_live_proof_from_configuration(tmp_path):
    a, c = client_for(tmp_path, min_holding_raw=10_000_000_000)
    with c:
        a.state.membership.allocate(100_000_000,'fixture funding')
        d=c.get('/api/admin/readiness',headers=AH).json()
        assert d['status'] != 'ready'
        checks={x['id']:x for x in d['checks']}
        assert checks['live_inference']['status']=='review'
        assert checks['holder_farming']['status']=='review'
        assert checks['context_vs_allowance']['status']=='review'
        assert '7' not in str(d.get('staking_days',''))


def test_revoke_all_is_wallet_scoped_and_does_not_erase_usage(tmp_path):
    a, c = client_for(tmp_path)
    with c:
        login(c);a.state.membership.allocate(100_000_000,'fixture')
        h1=make_key(c); h2=make_key(c)
        other='11111111111111111111111111111111'
        a.state.store.ensure_account(other)
        foreign=a.state.store.issue_key(other,'not ours',1_000_000)
        assert c.post('/v1/chat/completions',headers=h1,json=BODY).status_code == 200
        r=c.post('/api/keys/revoke-all',headers=ORIGIN)
        assert r.status_code == 200, r.text
        assert r.json()['revoked_count'] == 2
        assert c.post('/api/keys/revoke-all',headers=ORIGIN).json()['revoked_count']==0
        assert c.post('/v1/chat/completions',headers=h1,json=BODY).status_code==401
        assert c.post('/v1/chat/completions',headers=h2,json=BODY).status_code==401
        assert a.state.store.lookup_key(foreign['key']) is not None
        assert a.state.membership.usage_summary(WALLET)['requests']==1


def test_revoke_all_rejects_unauthenticated_and_wrong_origin(tmp_path):
    a, c = client_for(tmp_path)
    with c:
        assert c.post('/api/keys/revoke-all',headers=ORIGIN).status_code==401
        login(c)
        assert c.post('/api/keys/revoke-all',headers={'Origin':'https://evil.invalid'}).status_code==403


def test_logout_all_sessions_scoped_to_wallet_not_keys(tmp_path):
    a, c = client_for(tmp_path)
    with c:
        login(c);h=make_key(c)
        extra=a.state.store.new_session(WALLET)
        other=a.state.store.new_session('11111111111111111111111111111111')
        r=c.post('/api/auth/logout-all',headers=ORIGIN)
        assert r.status_code==200,r.text
        assert r.json()['sessions_revoked']==2
        assert a.state.store.session_wallet(extra) is None
        assert a.state.store.session_wallet(other) is not None
        assert c.get('/api/keys').status_code==401
        assert a.state.store.lookup_key(h['Authorization'][7:]) is not None


def test_site_name_is_configurable_without_changing_key_prefix(tmp_path):
    a,c=client_for(tmp_path,site_name='OMA-AI')
    with c:
        assert c.get('/api/status').json()['brand']=='OMA-AI'
        login(c)
        assert make_key(c)['Authorization'].startswith('Bearer sv_')


@pytest.mark.parametrize('name',['','<script>bad</script>','a'*41,'bad\nname'])
def test_bad_brand_is_rejected(tmp_path,name):
    with pytest.raises(ValueError,match='site name'):
        create_app(member_settings(site_name=name),str(tmp_path/'bad.db'))
