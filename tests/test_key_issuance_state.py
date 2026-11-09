"""A read-only holder check cannot extend expired or revoked key authority."""
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import create_app
from test_gridraft import ORIGIN, WALLET, login
from test_membership import handler, member_settings


@contextmanager
def key_client(tmp_path):
    pending={'change':lambda:None};sent=[]

    def respond(request):
        if request.url.host=='example.invalid':pending['change']()
        if request.url.path.endswith('/chat/completions'):sent.append(request)
        return handler(request)

    app=create_app(member_settings(),str(tmp_path/'keys.db'),httpx.MockTransport(respond))
    with TestClient(app) as client:
        login(client)
        yield app,client,pending,sent


def issue(client,path):
    body={'name':'Fixture API key','limit_usd':'1'} if path=='/api/keys' else None
    return client.post(path,headers=ORIGIN,json=body)


def assert_no_issuance(app,sent):
    assert app.state.store.keys(WALLET)==[]
    for table in ('api_keys','usage','member_usage'):
        assert app.state.store.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]==0
    assert sent==[]


@pytest.mark.parametrize('path',['/api/member-key','/api/keys'])
@pytest.mark.parametrize('change',['logout','logout_all','expired'])
def test_session_invalidated_during_eligibility_cannot_issue_key(tmp_path,path,change):
    with key_client(tmp_path) as (app,client,pending,sent):
        store=app.state.store;token=client.cookies.get('gridraft_session')

        def invalidate():
            if change=='logout':store.logout(token)
            elif change=='logout_all':store.logout_all(WALLET)
            else:store.db.execute('UPDATE sessions SET expires=0')

        pending['change']=invalidate
        response=issue(client,path)
        assert response.status_code==401,response.text
        assert response.json()['error']['message']=='Sign in with your Solana wallet'
        assert store.session_wallet(token) is None
        assert_no_issuance(app,sent)


@pytest.mark.parametrize('path',['/api/member-key','/api/keys'])
def test_user_disabled_during_eligibility_cannot_issue_key(tmp_path,path):
    with key_client(tmp_path) as (app,client,pending,sent):
        pending['change']=lambda:app.state.store.set_user_policy(WALLET,True,None,'Fixture suspension')
        response=issue(client,path)
        assert response.status_code==403,response.text
        assert response.json()['error']['message']=='This wallet is disabled by the operator'
        assert_no_issuance(app,sent)


def test_maintenance_started_during_eligibility_blocks_member_key(tmp_path):
    with key_client(tmp_path) as (app,client,pending,sent):
        pending['change']=lambda:app.state.store.set_operator_settings({'maintenance_mode':True})
        response=issue(client,'/api/member-key')
        assert response.status_code==503,response.text
        assert response.json()['error']['message']=='Inference access is temporarily paused for maintenance'
        assert_no_issuance(app,sent)


@pytest.mark.parametrize('path',['/api/member-key','/api/keys'])
def test_current_session_keeps_key_contract(tmp_path,path):
    with key_client(tmp_path) as (app,client,pending,sent):
        token=client.cookies.get('gridraft_session')
        # The legacy key endpoint has never imposed a maintenance restriction.
        if path=='/api/keys':
            pending['change']=lambda:app.state.store.set_operator_settings({'maintenance_mode':True})
        response=issue(client,path)
        assert response.status_code==201,response.text
        result=response.json();store=app.state.store
        assert result['key'].startswith('sv_')
        assert store.lookup_key(result['key'])['wallet']==WALLET
        assert store.session_wallet(token)==WALLET
        assert client.cookies.get('gridraft_session')==token
        assert len(store.keys(WALLET))==1
        if path=='/api/member-key':
            assert result['quota_shared_with_wallet'] is True
            assert result['daily_ai_tokens']==250_000
            assert 'limit_nusd' not in result
        else:
            assert result['name']=='Fixture API key'
            assert result['limit_nusd']==1_000_000_000
        assert sent==[]
