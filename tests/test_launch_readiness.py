"""Regressions for unreserved multi-choice calls and missing context enforcement."""
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import create_app
from test_membership import member_settings, handler, make_key
from test_gridraft import MODEL, MINT, WALLET, ORIGIN, login


def member(tmp_path, responder=handler, **kwargs):
    app = create_app(member_settings(**kwargs), str(tmp_path/'audit.db'), httpx.MockTransport(responder))
    return app, TestClient(app)


def test_context_is_checked_before_inference(tmp_path):
    sent=[]
    def responder(req):
        if req.url.path.endswith('/chat/completions'):sent.append(req)
        return handler(req)
    app,client=member(tmp_path,responder)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget')
        r=c.post('/v1/chat/completions',headers=make_key(c),json={
            'model':MODEL,'messages':[{'role':'user','content':'x'*180_000}],'max_tokens':16_384})
        assert r.status_code == 400, r.text
        assert 'context' in r.text.lower()
        assert not sent
        assert app.state.membership.pool()['budget_spent_ngonka']==0


def test_multiple_choices_reserve_all_outputs(tmp_path):
    app,client=member(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget');headers=make_key(c)
        for n in (1,5):
            r=c.post('/v1/chat/completions',headers={**headers,'Idempotency-Key':str(n)},json={
                'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_tokens':4096,'n':n})
            assert r.status_code==200,r.text
        rows=list(app.state.store.db.execute('SELECT idem,reserved_tokens FROM member_usage ORDER BY idem'))
        assert rows[1]['reserved_tokens']-rows[0]['reserved_tokens'] >= 4*4096


@pytest.mark.parametrize('extra',[
    {'stream':'false'},
    {'tools':[{'type':'function','function':{'name':'bad name','parameters':{'type':'object'}}}]},
    {'tools':[{'type':'function','function':{'name':'f','parameters':{'$ref':'https://example.invalid'}}}]},
    {'chat_template_kwargs':{'chat_template':'{{ user_supplied }}'}},
    {'response_format':{'type':'json_object'},'structured_outputs':{'json_object':True}},
])
def test_unsafe_parameter_shapes_rejected_without_dispatch(tmp_path,extra):
    sent=[]
    def responder(req):
        if req.url.path.endswith('/chat/completions'):sent.append(req)
        return handler(req)
    app,client=member(tmp_path,responder)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget')
        r=c.post('/v1/chat/completions',headers=make_key(c),json={
            'model':MODEL,'messages':[{'role':'user','content':'hello'}],**extra})
        assert r.status_code in (400,422),r.text
        assert not sent


def test_wallet_rate_headers_after_success(tmp_path):
    app,client=member(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget')
        r=c.post('/v1/chat/completions',headers=make_key(c),json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==200,r.text
        assert r.headers.get('ratelimit-limit')=='30'
        assert r.headers.get('ratelimit-remaining')=='29'
        assert 1<=int(r.headers['ratelimit-reset'])<=60


def test_local_metadata_discloses_evidence_and_admission_method(tmp_path):
    app,client=member(tmp_path)
    with client as c:
        row=c.get('/api/models').json()['data'][0]
        assert row['openbroker_limits_verified'] is False
        assert row['context_check']=='conservative_utf8_admission'


def test_mint_program_identity_and_decimals_are_not_assumed(tmp_path):
    def responder(req):
        if req.url.host=='example.invalid':
            return httpx.Response(200,json={'result':{'context':{'slot':500},'value':[
                {'account':{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'info':{
                    'owner':WALLET,'mint':MINT,'state':'initialized','tokenAmount':{'amount':'1000000','decimals':9}
                }}}}}
            ]}})
        return handler(req)
    app,client=member(tmp_path,responder,holder_token_decimals=6)
    with client as c:
        login(c)
        assert c.post('/api/member-key',headers=ORIGIN).status_code==503


def test_admin_daily_override_is_enforced_during_dispatch(tmp_path):
    app,client=member(tmp_path)
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget');headers=make_key(c)
        app.state.store.set_user_policy(WALLET,False,100,'restricted quota')
        r=c.post('/v1/chat/completions',headers=headers,json={
            'model':MODEL,'messages':[{'role':'user','content':'hello'}],'max_tokens':10})
        assert r.status_code==429,r.text
        assert 'wallet allowance' in r.text.lower()
        assert not app.state.membership.pending()


def test_user_disabled_during_provider_balance_read_cannot_dispatch(tmp_path):
    sent=[];target={}
    def responder(req):
        if req.url.path=='/v1/balance':target['app'].state.store.set_user_policy(WALLET,True,None,'suspended')
        if req.url.path.endswith('/chat/completions'):sent.append(req)
        return handler(req)
    app,client=member(tmp_path,responder);target['app']=app
    with client as c:
        login(c);app.state.membership.allocate(100_000_000,'budget')
        r=c.post('/v1/chat/completions',headers=make_key(c),json={
            'model':MODEL,'messages':[{'role':'user','content':'hello'}]})
        assert r.status_code==403,r.text
        assert not sent


def test_cached_catalog_reflects_operator_cap_changes(tmp_path):
    app,client=member(tmp_path)
    with client as c:
        assert c.get('/api/models').json()['data'][0]['max_completion_tokens']==16384
        app.state.store.set_operator_settings({'max_output_tokens':4096})
        assert c.get('/api/models').json()['data'][0]['max_completion_tokens']==4096
        app.state.store.set_operator_settings({'max_output_tokens':16384})
        assert c.get('/api/models').json()['data'][0]['max_completion_tokens']==16384
