"""Authenticated preflight is a snapshot, not a paid call or reservation."""
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import create_app
from test_membership import member_settings, handler, make_key
from test_gridraft import MODEL, BODY, ORIGIN, WALLET, login

def setup(tmp_path,**settings):
    sent=[]
    def respond(req):sent.append((req.method,str(req.url),req.content));return handler(req)
    app=create_app(member_settings(**settings),str(tmp_path/'a.db'),httpx.MockTransport(respond))
    return app,TestClient(app),sent

def test_preflight_requires_auth_and_origin(tmp_path):
    _,client,sent=setup(tmp_path)
    with client as c:
        assert c.post('/api/preflight',json=BODY).status_code==403
        assert c.post('/api/preflight',headers=ORIGIN,json=BODY).status_code==401
        assert not sent

def test_preview_does_not_reserve_dispatch_or_echo_prompt(tmp_path):
    app,client,sent=setup(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(10_000_000,'verified');h=make_key(c)
        before=app.state.membership.pool();body={**BODY,'messages':[{'role':'user','content':'CONFIDENTIAL TEST PROMPT'}]}
        for _ in range(2):
            r=c.post('/api/preflight',headers={**ORIGIN,**h},json=body)
            assert r.status_code==200,r.text
            d=r.json();assert d['allowed'] is True and d['inference_requests']==0 and d['reservation_created'] is False
            assert d['estimated_ai_tokens']>16 and 'CONFIDENTIAL' not in r.text and 'obk-' not in r.text
        assert app.state.membership.pool()==before and app.state.membership.history(WALLET)==[]
        assert all('/chat/completions' not in u and b'CONFIDENTIAL' not in data for _,u,data in sent)

def test_cookie_preview_does_not_create_key(tmp_path):
    app,client,_=setup(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(10_000_000,'verified')
        r=c.post('/api/preflight',headers=ORIGIN,json=BODY)
        assert r.status_code==200,r.text
        assert r.json()['allowed'] and not app.state.store.keys(WALLET)

@pytest.mark.parametrize('settings,reason',[({'holder_daily_tokens':1},'wallet_allowance_exhausted'),({'global_daily_tokens':1},'shared_allowance_exhausted')])
def test_preview_explains_limits(tmp_path,settings,reason):
    app,client,_=setup(tmp_path,**settings)
    with client as c:
        login(c);app.state.membership.allocate(10_000_000,'verified')
        r=c.post('/api/preflight',headers=ORIGIN,json=BODY)
        assert r.status_code==200,r.text
        assert not r.json()['allowed'] and r.json()['reason_code']==reason
        assert not app.state.membership.history(WALLET)

def test_unfunded_preview_is_not_success(tmp_path):
    _,client,_=setup(tmp_path)
    with client as c:
        login(c);r=c.post('/api/preflight',headers=ORIGIN,json=BODY)
        assert r.status_code==200,r.text
        assert not r.json()['allowed'] and r.json()['reason_code']=='allowance_pool_unfunded_or_exhausted'

@pytest.mark.parametrize('n',[1,3,5])
def test_estimate_matches_actual_reservation(tmp_path,n):
    app,client,_=setup(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'verified');h=make_key(c);body={**BODY,'n':n,'max_tokens':100}
        r=c.post('/api/preflight',headers={**ORIGIN,**h},json=body)
        assert r.status_code==200,r.text
        estimate=r.json()['estimated_ai_tokens']
        assert c.post('/v1/chat/completions',headers=h,json=body).status_code==200
        assert app.state.membership.history(WALLET)[0]['reserved_tokens']==estimate

def test_revoked_bearer_does_not_fall_back_to_cookie(tmp_path):
    app,client,_=setup(tmp_path)
    with client as c:
        login(c);h=make_key(c);app.state.store.revoke(app.state.store.keys(WALLET)[0]['id'],WALLET)
        assert c.post('/api/preflight',headers={**ORIGIN,**h},json=BODY).status_code==401

def test_context_error_is_caught_before_generation(tmp_path):
    _,client,sent=setup(tmp_path)
    with client as c:
        login(c);r=c.post('/api/preflight',headers=ORIGIN,json={**BODY,'messages':[{'role':'user','content':'x'*200000}]})
        assert r.status_code==400,r.text
        assert all('/chat/completions' not in u for _,u,_ in sent)

def test_suspended_wallet_cannot_preflight(tmp_path):
    app,client,_=setup(tmp_path)
    with client as c:
        login(c);app.state.store.set_user_policy(WALLET,disabled=True)
        assert c.post('/api/preflight',headers=ORIGIN,json=BODY).status_code==403
