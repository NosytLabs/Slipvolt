"""Policy changes during read-only provider work must precede local admission."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import create_app
from gridraft.request_policy import input_budget
from test_gridraft import MODEL, ORIGIN, WALLET, funded, login
from test_membership import handler, make_key, member_settings


@pytest.fixture
def admission_app(tmp_path):
    clients=[]

    def build(mode='holder'):
        state={'sent':[], 'on_balance':lambda:None, 'on_completion':lambda:None}

        def responder(request):
            if request.url.path=='/v1/balance':state['on_balance']()
            if request.url.path.endswith('/chat/completions'):
                state['sent'].append(json.loads(request.content))
                state['on_completion']()
            if state.get('estimate_cost') and request.url.path.startswith('/v1/usage/'):
                return httpx.Response(503,json={'error':'Fixture has no final cost evidence'})
            return handler(request)

        settings=member_settings(access_mode='prepaid' if mode=='prepaid' else 'holder_allowance')
        app=create_app(settings,str(tmp_path/f'{mode}.db'),httpx.MockTransport(responder))
        client=TestClient(app).__enter__();clients.append(client)
        if mode=='prepaid':
            _,headers=funded((app,client))
        else:
            login(client);app.state.membership.allocate(100_000_000,'fixture-budget')
            headers=make_key(client)
        state.update(app=app,client=client,headers={**ORIGIN,**headers},
            path='/api/preflight' if mode=='preflight' else '/v1/chat/completions')
        return state

    yield build
    for client in reversed(clients):client.__exit__(None,None,None)


def send(state):
    return state['client'].post(state['path'],headers=state['headers'],json={
        'model':MODEL,'messages':[{'role':'user','content':'hello'}],'max_tokens':256})


def usage_counts(state):
    db=state['app'].state.store.db
    return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                 for table in ('usage','member_usage'))


@pytest.mark.parametrize('mode',['holder','preflight','prepaid'])
@pytest.mark.parametrize(('change','status','message'),[
    ({'maintenance_mode':True},503,'maintenance'),
    ({'disabled_models':[MODEL]},400,'catalogue'),
    ({'max_output_tokens':1},400,'1-token limit'),
])
def test_policy_tightened_during_balance_read_denies_before_admission(admission_app,mode,change,status,message):
    state=admission_app(mode);store=state['app'].state.store
    state['on_balance']=lambda:store.set_operator_settings(change)
    response=send(state)
    assert response.status_code==status,response.text
    assert message in response.text
    assert usage_counts(state)==(0,0)
    assert not state['sent']


@pytest.mark.parametrize('mode',['holder','preflight','prepaid'])
def test_user_disabled_during_balance_read_denies_before_admission(admission_app,mode):
    state=admission_app(mode);store=state['app'].state.store
    state['on_balance']=lambda:store.set_user_policy(WALLET,True,None,'Fixture suspension')
    response=send(state)
    assert response.status_code==403,response.text
    assert usage_counts(state)==(0,0)
    assert not state['sent']


@pytest.mark.parametrize('mode',['holder','preflight'])
@pytest.mark.parametrize(('change','status','reason'),[
    ({'holder_daily_tokens':1},429,'wallet_allowance_exhausted'),
    ({'global_daily_tokens':1},429,'shared_allowance_exhausted'),
    ({'ngonka_per_token_budget':100_000},503,'allowance_pool_unfunded_or_exhausted'),
])
def test_current_allowance_and_budget_policy_controls_admission(admission_app,mode,change,status,reason):
    state=admission_app(mode);store=state['app'].state.store
    state['on_balance']=lambda:store.set_operator_settings(change)
    response=send(state)
    if mode=='preflight':
        assert response.status_code==200,response.text
        assert response.json()['allowed'] is False
        assert response.json()['reason_code']==reason
    else:
        assert response.status_code==status,response.text
    assert usage_counts(state)==(0,0)
    assert not state['sent']


@pytest.mark.parametrize('mode',['holder','preflight'])
@pytest.mark.parametrize(('setting','reason'),[
    ('wallet_rpm','wallet_rpm_limit'),('global_rpm','global_rpm_limit'),
    ('wallet_concurrency','wallet_concurrency_limit'),('global_concurrency','global_concurrency_limit'),
])
def test_current_rate_and_concurrency_policy_controls_admission(admission_app,mode,setting,reason):
    state=admission_app(mode);app=state['app'];store=app.state.store
    key=store.lookup_key(state['headers']['Authorization'][7:])
    app.state.membership.reserve(key['id'],WALLET,MODEL,'already-running',100,
        wallet_daily=250_000,global_daily=1_000_000,ngonka_per_token=25,
        upstream_available=1_000_000_000,rpm=30)
    state['on_balance']=lambda:store.set_operator_settings({setting:1})
    before=usage_counts(state);response=send(state)
    if mode=='preflight':
        assert response.status_code==200,response.text
        assert response.json()['allowed'] is False
        assert response.json()['reason_code']==reason
    else:
        assert response.status_code==429,response.text
    assert usage_counts(state)==before
    assert not state['sent']


@pytest.mark.parametrize('mode',['holder','preflight'])
def test_policy_relaxed_during_balance_read_uses_current_allowance(admission_app,mode):
    state=admission_app(mode);store=state['app'].state.store
    store.set_operator_settings({'holder_daily_tokens':1})
    state['on_balance']=lambda:store.set_operator_settings({'holder_daily_tokens':250_000,'ngonka_per_token_budget':40})
    response=send(state)
    assert response.status_code==200,response.text
    if mode=='preflight':
        result=response.json()
        assert result['allowed'] is True
        assert result['estimated_budget_ngonka']==result['estimated_ai_tokens']*40
        assert usage_counts(state)==(0,0)
        assert not state['sent']
    else:
        row=store.db.execute('SELECT * FROM member_usage').fetchone()
        assert row['reserved_ngonka']==row['reserved_tokens']*40
        assert len(state['sent'])==1


def test_holder_settlement_keeps_rate_captured_at_admission(admission_app):
    state=admission_app();store=state['app'].state.store
    state['estimate_cost']=True
    state['on_balance']=lambda:store.set_operator_settings({'ngonka_per_token_budget':40})
    state['on_completion']=lambda:store.set_operator_settings({'ngonka_per_token_budget':99,'maintenance_mode':True})
    response=send(state)
    assert response.status_code==200,response.text
    row=store.db.execute('SELECT * FROM member_usage').fetchone()
    assert row['state']=='settled'
    assert row['reserved_ngonka']==row['reserved_tokens']*40
    assert int(response.headers['X-Slipvolt-Budget-Ngonka'])==15*40
    assert len(state['sent'])==1


def test_prepaid_reservation_and_settlement_keep_rates_captured_at_admission(admission_app):
    state=admission_app('prepaid');store=state['app'].state.store
    state['on_balance']=lambda:store.set_operator_settings({'retail_input_nusd_per_token':123,'retail_output_nusd_per_token':456})
    state['on_completion']=lambda:store.set_operator_settings({'retail_input_nusd_per_token':900,'retail_output_nusd_per_token':900,'maintenance_mode':True})
    response=send(state)
    assert response.status_code==200,response.text
    row=store.db.execute('SELECT * FROM usage').fetchone()
    assert row['state']=='settled'
    assert row['reserved_nusd']==input_budget(state['sent'][0])*123+256*456
    assert int(response.headers['X-Slipvolt-Cost-NUSD'])==12*123+3*456
    assert len(state['sent'])==1


def test_prepaid_current_wallet_rate_controls_admission(admission_app):
    state=admission_app('prepaid');store=state['app'].state.store
    key=store.lookup_key(state['headers']['Authorization'][7:])
    store.reserve(key['id'],WALLET,1000,'already-running',MODEL,30)
    state['on_balance']=lambda:store.set_operator_settings({'wallet_rpm':1})
    before=usage_counts(state);response=send(state)
    assert response.status_code==429,response.text
    assert usage_counts(state)==before
    assert not state['sent']
