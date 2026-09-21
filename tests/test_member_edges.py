"""Holder-mode request and accounting edge cases; upstreams are fixtures, never paid calls."""
import json
import pytest
import httpx
from fastapi.testclient import TestClient
from gridraft.app import create_app
from gridraft.store import Store
from gridraft.membership import Membership
from gridraft.cli import main
from test_gridraft import WALLET, MODEL, BODY, ORIGIN, login
from test_membership import member_settings, handler, make_key

# Published OpenBroker operator address is a parser fixture only, NOT our treasury.
GONKA='gonka1r2s0rwgskp6y4ed7qr7d25qdwjwlvpp6demv90'


def open_client(tmp_path, override, **settings):
    app=create_app(member_settings(**settings),str(tmp_path/'a.db'),httpx.MockTransport(override))
    app.state.membership.allocate(10_000_000,'test-funded-budget')
    return app,TestClient(app)


def sse(*,usage=True,done=True,second_id=False):
    rows=[{'id':'up-1','model':MODEL,'choices':[{'index':0,'delta':{'role':'assistant','content':'Hello stream'}}]}]
    if usage:rows.append({'id':'changed' if second_id else 'up-1','model':MODEL,'choices':[], 'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}})
    return ''.join('data: '+json.dumps(r)+'\n\n' for r in rows)+('data: [DONE]\n\n' if done else '')


def test_stream_settles_reported_usage_and_cost(tmp_path):
    def upstream(r):
        if r.url.path.endswith('/chat/completions'):
            assert json.loads(r.content)['stream_options']=={'include_usage':True}
            return httpx.Response(200,text=sse(),headers={'content-type':'text/event-stream'})
        return handler(r)
    app,c=open_client(tmp_path,upstream)
    with c:
        login(c);r=c.post('/v1/chat/completions',headers=make_key(c),json={**BODY,'stream':True})
        assert r.status_code==200 and 'Hello stream' in r.text and '[DONE]' in r.text
        assert app.state.membership.pool()['budget_spent_ngonka']==150
        assert c.get('/api/membership').json()['used_tokens']==15


@pytest.mark.parametrize('options',[{'usage':False},{'done':False},{'second_id':True}])
def test_bad_stream_retains_hold_and_pauses(tmp_path,options):
    def upstream(r):
        if r.url.path.endswith('/chat/completions'):return httpx.Response(200,text=sse(**options))
        return handler(r)
    app,c=open_client(tmp_path,upstream)
    with c:
        login(c);h=make_key(c)
        r=c.post('/v1/chat/completions',headers=h,json={**BODY,'stream':True})
        assert 'held for review' in r.text or 'retained for review' in r.text
        assert '[DONE]' not in r.text
        assert app.state.membership.pool()['reserved_ngonka']>0
        assert c.get('/api/status').json()['billing_review_required'] is True
        assert c.post('/v1/chat/completions',headers=h,json=BODY).status_code==503


@pytest.mark.parametrize('status,expected,review',[(400,400,False),(401,503,False),(429,429,False),(500,502,True),(408,502,True)])
def test_rejected_vs_uncertain_dispatch(tmp_path,status,expected,review):
    def upstream(r):
        return httpx.Response(status,headers={'x-request-id':'err-id'}) if r.url.path.endswith('/chat/completions') else handler(r)
    app,c=open_client(tmp_path,upstream)
    with c:
        login(c);r=c.post('/v1/chat/completions',headers=make_key(c),json=BODY)
        assert r.status_code==expected
        p=app.state.membership.pool()
        assert p['reconciliation_required'] is review
        assert (p['reserved_ngonka']>0) is review


def test_actual_holder_sale_blocks_key_and_no_upstream_dispatch(tmp_path):
    state={'holding':True,'calls':0}
    def upstream(r):
        if r.url.host=='example.invalid' and not state['holding']:
            return httpx.Response(200,json={'result':{'context':{'slot':200},'value':[]}})
        if r.url.path.endswith('/chat/completions'):state['calls']+=1
        return handler(r)
    _,c=open_client(tmp_path,upstream)
    with c:
        login(c);h=make_key(c);state['holding']=False
        assert c.post('/v1/chat/completions',headers=h,json=BODY).status_code==403
        assert c.post('/api/member-key',headers=ORIGIN).status_code==403
        assert state['calls']==0


def test_gnka_accounting_survives_database_reopen(tmp_path):
    path=str(tmp_path/'m.db');s=Store(path,'p'*40);s.ensure_account(WALLET)
    m=Membership(s);m.allocate(9000,'funded');k=s.issue_key(WALLET,'test',10**9)
    rid=m.reserve(k['id'],WALLET,MODEL,'x',100,wallet_daily=1000,global_daily=1000,ngonka_per_token=25,upstream_available=10000,rpm=60)
    m.review(rid,'up');s.close();s=Store(path,'p'*40);m=Membership(s)
    assert m.pool()['reserved_ngonka']==2500
    assert m.pool()['reconciliation_required']
    with pytest.raises(ValueError):m.settle(rid,10,250,'operator')
    assert m.settle(rid,10,250,'operator',evidence='verified-receipt')
    assert m.pool()['available_budget_ngonka']==8750
    s.close()


def test_mismatched_usage_lookup_never_claims_confirmed_cost(tmp_path):
    def upstream(r):
        if r.url.path.startswith('/v1/usage/'):
            return httpx.Response(200,json={'id':'not-this-request','model':MODEL,'total_tokens':15,'cost_ngonka':1,'cost_source':'devshard_settled'})
        return handler(r)
    _,c=open_client(tmp_path,upstream)
    with c:
        login(c);r=c.post('/v1/chat/completions',headers=make_key(c),json=BODY)
        assert r.status_code==200
        assert r.headers['x-slipvolt-cost-source']=='conservative_budget_estimate'
        assert r.headers['x-slipvolt-budget-ngonka']=='375'


def test_native_wallet_balance_has_separate_scope(tmp_path):
    def upstream(r):
        if r.url.host=='rpc.gonka.gg':
            if r.url.path=='/chain-rpc/status':
                from datetime import datetime, timezone
                return httpx.Response(200,json={'jsonrpc':'2.0','id':-1,'result':{
                    'node_info':{'network':'gonka-mainnet'},'sync_info':{
                        'latest_block_height':'100','latest_block_hash':'A'*64,
                        'latest_block_time':datetime.now(timezone.utc).isoformat(),'catching_up':False}}})
            assert r.url.params['denom']=='ngonka'
            assert 'Authorization' not in r.headers
            return httpx.Response(200,json={'balance':{'denom':'ngonka','amount':'1230000000'}})
        return handler(r)
    _,c=open_client(tmp_path,upstream,gonka_treasury_address=GONKA)
    with c:
        r=c.get('/api/treasury').json()
        assert r['self_custody_balance']['amount_ngonka']==1230000000
        assert r['broker_balance'] is None
        assert r['self_custody_status']=='available'


def test_invalid_gonka_address_fails_startup(tmp_path):
    with pytest.raises(ValueError,match='Gonka'):
        create_app(member_settings(gonka_treasury_address=GONKA[:-1]+'q'),str(tmp_path/'m.db'))


def test_new_env_defaults_to_holder_allowance(tmp_path):
    path=tmp_path/'fresh.env'
    assert main(['--env-file',str(path),'init-env'])==0
    assert 'ACCESS_MODE=holder_allowance' in path.read_text()
    assert 'HOLDER_DAILY_TOKENS=250000' in path.read_text()


def test_gnk_pool_cli_allocation_is_not_a_crypto_transfer(tmp_path,monkeypatch,capsys):
    monkeypatch.setenv('KEY_PEPPER','x'*40);monkeypatch.setenv('DATABASE_PATH',str(tmp_path/'c.db'))
    args=['--env-file',str(tmp_path/'none'),'allocate-gnk','--gnk','0.5','--reference','verified-fund','--acknowledge-funded']
    assert main(args)==0
    d=json.loads(capsys.readouterr().out)
    assert d['crypto_transferred'] is False
    assert d['pool']['allocated_ngonka']==500000000
    assert main(args)==0
    d=json.loads(capsys.readouterr().out)
    assert d['pool']['allocated_ngonka']==500000000


def test_unsafe_upstream_model_id_is_not_offered(tmp_path):
    def upstream(r):
        if r.url.path.endswith('/models'):
            return httpx.Response(200,json={'data':[{'id':"provider/model'; touch injected; '"},{'id':MODEL}]})
        return handler(r)
    _,c=open_client(tmp_path,upstream)
    with c:
        response=c.get('/api/models')
        assert [m['id'] for m in response.json()['data']]==[MODEL]


def test_invalid_allowance_rate_boolean_rejected_at_start(tmp_path):
    with pytest.raises(ValueError,match='GNK budget rate'):
        create_app(member_settings(allowance_ngonka_per_token=True),str(tmp_path/'x.db'))


def test_cancellation_before_headers_retains_review_hold():
    import asyncio
    from types import SimpleNamespace
    from gridraft.app import ChatInput
    from gridraft.broker import Broker
    from gridraft.member_gateway import MemberGateway
    s=Store(':memory:','p'*40);s.ensure_account(WALLET)
    m=Membership(s);m.allocate(1000000,'fixture');key=s.issue_key(WALLET,'test',10**9)
    async def go():
        def upstream(r):
            if r.url.path.endswith('/chat/completions'):raise asyncio.CancelledError()
            return handler(r)
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            gateway=MemberGateway(member_settings(),client,Broker(client,'obk-test-upstream'),m)
            await gateway.call(ChatInput.model_validate(BODY),SimpleNamespace(headers={},state=SimpleNamespace()),{'id':key['id'],'wallet':WALLET})
    with pytest.raises(asyncio.CancelledError):asyncio.run(go())
    assert m.pool()['reconciliation_required'] is True
    assert m.pool()['reserved_ngonka']>0
    s.close()
