import httpx
from fastapi.testclient import TestClient
from gridraft.app import Settings, create_app
from test_gridraft import MODEL, MINT, ORIGIN, WALLET, login, provider

ADMIN='adm_'+'a'*40

def handler(req):
    if req.url.host=='proxy.gonka.gg' and req.url.path=='/v1/models':
        return httpx.Response(200,json={'data':[{'id':MODEL,'context_length':180000,'max_completion_tokens':16384}]})
    if req.url.path=='/api/status':
        return httpx.Response(200,json={'status':'ok','models':[{'model':MODEL,'status':'healthy','routable':True,'capacity_available_pct':88,'load_pct':12,'in_flight_requests':1,'effective_max_concurrency':12}]})
    if req.url.path=='/v1/usage/summary':
        return httpx.Response(200,json={'totals':{'requests':10,'errors':1,'prompt_tokens':1000,'completion_tokens':500,'total_tokens':1500,'cost_ngonka':22500},'models':[],'days':[]})
    return provider(req)

def settings(**kw):
    s=Settings(origin='http://testserver',admin_key=ADMIN,upstream_key='obk-test-upstream',access_mode='holder_allowance',holder_mint=MINT,min_holding_raw=1000,solana_rpc='https://example.invalid')
    for k,v in kw.items():setattr(s,k,v)
    return s

def auth(): return {'Authorization':'Bearer '+ADMIN}

def test_admin_requires_separate_operator_key(tmp_path):
    app=create_app(settings(),str(tmp_path/'a.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        assert c.get('/api/admin/overview').status_code==401
        assert c.get('/api/admin/overview',headers=auth()).status_code==200
        assert ADMIN not in c.get('/api/admin/overview',headers=auth()).text

def test_admin_can_persist_runtime_limits_and_pricing(tmp_path):
    app=create_app(settings(),str(tmp_path/'cfg.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        r=c.put('/api/admin/config',headers={**auth(),**ORIGIN},json={'wallet_rpm':42,'wallet_concurrency':3,'global_rpm':420,'global_concurrency':40,'holder_daily_tokens':500000,'global_daily_tokens':50000000,'default_output_tokens':4096,'max_output_tokens':16384,'retail_input_nusd_per_token':75,'retail_output_nusd_per_token':300,'maintenance_mode':False,'disabled_models':[],'gnk_usd':'0.20'})
        assert r.status_code==200,r.text
        d=c.get('/api/admin/config',headers=auth()).json()
        assert d['wallet_rpm']==42 and d['retail_input_per_million_usd']==0.075 and d['retail_output_per_million_usd']==0.30
        assert c.get('/api/status').json()['holder_daily_tokens']==500000

def test_admin_user_disable_blocks_key_creation(tmp_path):
    app=create_app(settings(),str(tmp_path/'user.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        login(c)
        r=c.put('/api/admin/users/'+WALLET,headers={**auth(),**ORIGIN},json={'disabled':True,'daily_tokens_override':None,'note':'abuse'})
        assert r.status_code==200,r.text
        assert c.post('/api/member-key',headers=ORIGIN).status_code==403
        users=c.get('/api/admin/users',headers=auth()).json()['data']
        assert any(x['wallet']==WALLET and x['disabled'] for x in users)

def test_admin_fund_allocation_never_moves_crypto_and_cannot_exceed_broker(tmp_path):
    app=create_app(settings(),str(tmp_path/'fund.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        r=c.post('/api/admin/allowance/fund',headers={**auth(),**ORIGIN},json={'gnk':'0.5','reference':'verified-topup-1','confirm_funded':True})
        assert r.status_code==200,r.text
        d=r.json();assert d['crypto_transferred'] is False and d['pool']['allocated_ngonka']==500000000
        r2=c.post('/api/admin/allowance/fund',headers={**auth(),**ORIGIN},json={'gnk':'2','reference':'too-much','confirm_funded':True})
        assert r2.status_code==400

def test_admin_business_ledger_tracks_actual_entries(tmp_path):
    app=create_app(settings(),str(tmp_path/'biz.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        a=c.post('/api/admin/business',headers={**auth(),**ORIGIN},json={'category':'creator_fee','amount_usd':'100','reference':'pump-claim-1','note':'claimed creator fees'})
        b=c.post('/api/admin/business',headers={**auth(),**ORIGIN},json={'category':'hosting','amount_usd':'-20','reference':'hosting-1','note':'monthly host'})
        assert a.status_code==201 and b.status_code==201
        d=c.get('/api/admin/overview',headers=auth()).json()['business']
        assert d['revenue_usd']==100 and d['expense_usd']==20 and d['cash_net_usd']==80


def test_duplicate_allocation_at_balance_limit_is_idempotent(tmp_path):
    app=create_app(settings(),str(tmp_path/'fund-retry.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        body={'gnk':'1','reference':'same-topup','confirm_funded':True}
        a=c.post('/api/admin/allowance/fund',headers={**auth(),**ORIGIN},json=body)
        b=c.post('/api/admin/allowance/fund',headers={**auth(),**ORIGIN},json=body)
        assert a.status_code==200,a.text
        assert b.status_code==200,b.text
        assert b.json()['allocated'] is False
        assert b.json()['pool']['allocated_ngonka']==1_000_000_000
