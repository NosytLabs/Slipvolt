import json
import httpx
from fastapi.testclient import TestClient

from gridraft.app import Settings, create_app
from test_gridraft import MODEL, MINT, ORIGIN, WALLET, login, provider
from test_membership import handler as member_handler

ADMIN='adm_'+'z'*40
DEEP='deepseek-ai/DeepSeek-V4-Flash-0731'
GLM='zai-org/GLM-5.3-Flash'


def settings(**kw):
    s=Settings(origin='http://testserver',admin_key=ADMIN,upstream_key='obk-test-upstream',
        access_mode='holder_allowance',holder_mint=MINT,min_holding_raw=1000,
        solana_rpc='https://example.invalid')
    for k,v in kw.items():setattr(s,k,v)
    return s


def auth():return {'Authorization':'Bearer '+ADMIN}


def test_chat_accepts_documented_gonka_compat_fields(tmp_path):
    seen={}
    def upstream(req):
        if req.url.host=='proxy.gonka.gg':
            return httpx.Response(200,json={'data':[{'id':MODEL,'context_length':180000,'max_completion_tokens':16384}]})
        if req.url.path.endswith('/chat/completions'):
            seen.update(json.loads(req.content))
        return member_handler(req)
    app=create_app(settings(),str(tmp_path/'compat.db'),httpx.MockTransport(upstream))
    app.state.membership.allocate(100_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        body={'model':MODEL,'messages':[{'role':'user','content':'hi'}],
          'logit_bias':{'42':-2},'logprobs':True,'top_logprobs':5,
          'structured_outputs':{'choice':['a','b']},'service_tier':'auto','store':False,
          'safety_identifier':'anon-1','prompt_cache_key':'p','cache_key':'c',
          'enable_thinking':False,'thinking_config':{'type':'disabled'},'think':False,
          'min_tokens':0,'bad_words':['nope'],'stop_token_ids':[1,2],
          'skip_special_tokens':True,'detokenize':True,'chat_template_kwargs':{'foo':'bar'}}
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json=body)
        assert r.status_code==200,r.text
        for k in body:
            if k not in ('model','messages'): assert k in seen


def test_upstream_429_stays_429_and_releases_allowance(tmp_path):
    def upstream(req):
        if req.url.path.endswith('/chat/completions'):
            return httpx.Response(429,headers={'Retry-After':'7'})
        return member_handler(req)
    app=create_app(settings(),str(tmp_path/'rate.db'),httpx.MockTransport(upstream))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        before=app.state.membership.pool()['available_budget_ngonka']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==429,r.text
        assert r.headers['retry-after']=='7'
        assert app.state.membership.pool()['available_budget_ngonka']==before
        assert app.state.membership.pool()['reconciliation_required'] is False


def test_public_models_include_live_health_without_hiding_catalog(tmp_path):
    def upstream(req):
        if req.url.host=='proxy.gonka.gg':
            return httpx.Response(200,json={'data':[
                {'id':MODEL,'context_length':180000,'max_completion_tokens':16384},
                {'id':DEEP,'context_length':400000,'max_completion_tokens':16384},
                {'id':GLM,'context_length':400000,'max_completion_tokens':16384}]})
        if req.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':MODEL},{'id':DEEP},{'id':GLM}]})
        if req.url.path=='/api/status':return httpx.Response(200,json={'status':'degraded','models':[
            {'model':MODEL,'status':'unavailable','routable':False,'capacity_available_pct':0},
            {'model':DEEP,'status':'healthy','routable':True,'capacity_available_pct':42},
            {'model':GLM,'status':'healthy','routable':True,'capacity_available_pct':70}]})
        return provider(req)
    app=create_app(settings(),str(tmp_path/'health.db'),httpx.MockTransport(upstream))
    with TestClient(app) as c:
        d=c.get('/api/models').json()['data'];by={x['id']:x for x in d}
        assert set(by)=={MODEL,DEEP,GLM}
        assert by[MODEL]['availability']=='unavailable'
        assert by[MODEL]['routable'] is False
        assert by[DEEP]['availability']=='healthy'
        assert by[DEEP]['capacity_available_pct']==42


def test_admin_can_tune_conservative_ngonka_reserve_rate(tmp_path):
    app=create_app(settings(),str(tmp_path/'budget-rate.db'),httpx.MockTransport(member_handler))
    with TestClient(app) as c:
        cfg=c.get('/api/admin/config',headers=auth()).json()
        assert cfg['ngonka_per_token_budget']==25
        cfg={k:cfg[k] for k in ('wallet_rpm','wallet_concurrency','global_rpm','global_concurrency','holder_daily_tokens','global_daily_tokens','default_output_tokens','max_output_tokens','retail_input_nusd_per_token','retail_output_nusd_per_token','maintenance_mode','disabled_models','gnk_usd','ngonka_per_token_budget')}
        cfg['ngonka_per_token_budget']=18
        r=c.put('/api/admin/config',headers={**auth(),**ORIGIN},json=cfg)
        assert r.status_code==200,r.text
        assert r.json()['ngonka_per_token_budget']==18


def test_business_ledger_rejects_wrong_sign_for_category(tmp_path):
    app=create_app(settings(),str(tmp_path/'sign.db'),httpx.MockTransport(member_handler))
    with TestClient(app) as c:
        positive_expense=c.post('/api/admin/business',headers={**auth(),**ORIGIN},json={'category':'hosting','amount_usd':'20','reference':'bad-host','note':''})
        negative_revenue=c.post('/api/admin/business',headers={**auth(),**ORIGIN},json={'category':'api_revenue','amount_usd':'-20','reference':'bad-rev','note':''})
        assert positive_expense.status_code==400
        assert negative_revenue.status_code==400


def test_admin_user_search_key_revocation_and_audit_log(tmp_path):
    app=create_app(settings(),str(tmp_path/'ops.db'),httpx.MockTransport(member_handler))
    with TestClient(app) as c:
        login(c);created=c.post('/api/member-key',headers=ORIGIN).json();prefix=created['prefix']
        users=c.get('/api/admin/users',headers=auth(),params={'q':WALLET[:10]}).json()['data']
        assert len(users)==1 and users[0]['wallet']==WALLET
        keys=c.get('/api/admin/users/'+WALLET+'/keys',headers=auth()).json()['data']
        assert any(k['prefix']==prefix and not k['revoked'] for k in keys)
        kid=next(k['id'] for k in keys if k['prefix']==prefix)
        r=c.delete('/api/admin/users/'+WALLET+'/keys/'+kid,headers={**auth(),**ORIGIN})
        assert r.status_code==200
        assert r.json()['revoked'] is True
        events=c.get('/api/admin/audit',headers=auth()).json()['data']
        assert any(e['action']=='key_revoked' and e['target']==WALLET for e in events)


def test_admin_overview_reports_funded_capacity(tmp_path):
    app=create_app(settings(),str(tmp_path/'capacity.db'),httpx.MockTransport(member_handler))
    app.state.membership.allocate(25_000_000,'funded')
    with TestClient(app) as c:
        d=c.get('/api/admin/overview',headers=auth()).json()['fund_capacity']
        assert d['budget_ngonka_per_token']==25
        assert d['local_available_ai_tokens']==1_000_000
        assert d['wallet_days_at_full_allowance']==4

from gridraft.store import Store
from gridraft.membership import Membership

def test_rate_limiter_distinguishes_concurrency_from_rpm():
    s=Store(':memory:','x'*40);s.ensure_account(WALLET);m=Membership(s);m.allocate(1_000_000,'funded');k=s.issue_key(WALLET,'k',10**9)
    try:
        m.reserve(k['id'],WALLET,MODEL,'one',10,wallet_daily=1000,global_daily=1000,ngonka_per_token=25,upstream_available=1_000_000,rpm=10,wallet_concurrency=1,global_rpm=100,global_concurrency=100)
        try:
            m.reserve(k['id'],WALLET,MODEL,'two',10,wallet_daily=1000,global_daily=1000,ngonka_per_token=25,upstream_available=1_000_000,rpm=10,wallet_concurrency=1,global_rpm=100,global_concurrency=100)
            assert False,'expected concurrency limit'
        except ValueError as e:assert str(e)=='wallet_concurrency_limit'
    finally:s.close()

def test_unavailable_model_is_blocked_before_provider_dispatch(tmp_path):
    calls={'chat':0}
    def upstream(req):
        if req.url.host=='proxy.gonka.gg':
            return httpx.Response(200,json={'data':[{'id':MODEL,'context_length':180000,'max_completion_tokens':16384}]})
        if req.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        if req.url.path=='/api/status':return httpx.Response(200,json={'status':'degraded','models':[{'model':MODEL,'status':'unavailable','routable':False,'capacity_available_pct':0}]})
        if req.url.path.endswith('/chat/completions'):calls['chat']+=1
        return provider(req)
    app=create_app(settings(),str(tmp_path/'unavailable.db'),httpx.MockTransport(upstream))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==503,r.text
        assert calls['chat']==0


def test_admin_overview_respects_requested_window(tmp_path):
    seen=[]
    def upstream(req):
        if req.url.path=='/v1/usage/summary':
            seen.append(str(req.url))
            return httpx.Response(200,json={'totals':{'requests':1,'errors':0,'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,'cost_ngonka':180},'models':[],'days':[]})
        return member_handler(req)
    app=create_app(settings(),str(tmp_path/'window.db'),httpx.MockTransport(upstream))
    with TestClient(app) as c:
        r=c.get('/api/admin/overview?days=7',headers=auth())
        assert r.status_code==200,r.text
        assert r.json()['window_days']==7
        assert any('from=' in u and 'to=' in u for u in seen)
        assert c.get('/api/admin/overview?days=91',headers=auth()).status_code==422

def test_request_nesting_over_32_is_rejected_before_dispatch(tmp_path):
    calls={'chat':0}
    def upstream(req):
        if req.url.path.endswith('/chat/completions'):calls['chat']+=1
        return member_handler(req)
    app=create_app(settings(),str(tmp_path/'nesting.db'),httpx.MockTransport(upstream))
    app.state.membership.allocate(10_000_000,'funded')
    nested='leaf'
    for _ in range(40):nested={'x':nested}
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={'model':MODEL,'messages':[{'role':'user','content':'hi'}],'metadata':nested})
        assert r.status_code==400,r.text
        assert 'nesting' in r.text.lower()
        assert calls['chat']==0

def test_admin_overview_daily_series_is_exact_utc_window_with_zero_days(tmp_path):
    app=create_app(settings(),str(tmp_path/'daily-window.db'),httpx.MockTransport(member_handler))
    with TestClient(app) as c:
        d=c.get('/api/admin/overview?days=7',headers=auth()).json()
        assert len(d['local']['daily'])==7
        assert len(d['business']['daily'])==7
        assert all(set(row)=={'day','requests','tokens','cost_ngonka'} for row in d['local']['daily'])
        assert all(row['requests']==0 and row['tokens']==0 for row in d['local']['daily'])
