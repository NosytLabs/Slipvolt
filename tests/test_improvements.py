"""Regression tests for the Slipvolt improvement pass. No real provider traffic."""
import csv
import io
import json
import os
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import Settings, create_app
from gridraft.store import Store
from test_gridraft import provider, funded, login, WALLET, MODEL, ORIGIN, BODY

@pytest.mark.parametrize('code', [408, 500, 502, 503, 504, 307])
def test_ambiguous_http_status_retains_reservation_and_request_id(tmp_path, code):
    def unavailable(req):
        if req.url.path.endswith('/chat/completions'):
            return httpx.Response(code, headers={'X-Request-Id':'provider-ref-123'}, json={'error':'private provider detail'})
        return provider(req)
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'amb.db'),httpx.MockTransport(unavailable))
    with TestClient(app) as c:
        _,h=funded((app,c)); before=app.state.store.account(WALLET)['balance_nusd']
        r=c.post('/v1/chat/completions',json=BODY,headers=h)
        assert r.status_code==502
        assert app.state.store.account(WALLET)['balance_nusd']<before
        row=app.state.store.pending()[0]
        assert row['state']=='needs_review'
        assert row['upstream_id']=='provider-ref-123'
        assert r.headers.get('x-request-id')==row['id']
        assert r.json()['error']['request_id']==row['id']
        assert 'private provider detail' not in r.text

@pytest.mark.parametrize('code,expected', [(400,400),(401,503),(403,503),(404,503),(413,413),(422,422),(429,429)])
def test_explicit_upstream_rejection_releases_local_reservation(tmp_path, code, expected):
    def rejected(req):
        return httpx.Response(code,json={'error':'no execution'}) if req.url.path.endswith('/chat/completions') else provider(req)
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'rej.db'),httpx.MockTransport(rejected))
    with TestClient(app) as c:
        _,h=funded((app,c)); before=app.state.store.account(WALLET)['balance_nusd']
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==expected
        assert app.state.store.account(WALLET)['balance_nusd']==before


def test_review_blocks_further_dispatch_until_reconciled(tmp_path):
    calls=[]
    def broken(req):
        if req.url.path.endswith('/chat/completions'):
            calls.append(1)
            return httpx.Response(200,json={'choices':[], 'usage':{'prompt_tokens':1,'completion_tokens':1}})
        return provider(req)
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'circuit.db'),httpx.MockTransport(broken))
    with TestClient(app) as c:
        _,h=funded((app,c))
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==502
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==503
        assert len(calls)==1
        assert c.get('/api/status').json()['billing_review_required'] is True
        rid=app.state.store.pending()[0]['id']
        app.state.store.settle(rid,0,state='operator_settled',evidence='operator checked provider')
        assert c.get('/api/status').json()['billing_review_required'] is False


def test_daily_budget_is_reserved_atomically(tmp_path):
    s=Store(str(tmp_path/'cap.db'),'p'*32)
    assert hasattr(s,'budget_usage'), 'Daily budget accounting is required'
    s.credit(WALLET,10000,'credit'); k=s.issue_key(WALLET,'cap',10000)
    first=s.reserve(k['id'],WALLET,600,'1',MODEL,60,daily_budget_nusd=1000)
    with pytest.raises(ValueError,match='daily_budget'):
        s.reserve(k['id'],WALLET,600,'2',MODEL,60,daily_budget_nusd=1000)
    assert s.account(WALLET)['balance_nusd']==9400
    s.settle(first,200)
    s.reserve(k['id'],WALLET,600,'3',MODEL,60,daily_budget_nusd=1000)
    assert s.budget_usage()==800
    s.close()


def test_usage_summary_and_export_are_owner_scoped(tmp_path):
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'sum.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        assert c.get('/api/usage/summary').status_code==401
        assert c.get('/api/usage/export').status_code==401
        _,h=funded((app,c))
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==200
        r=c.get('/api/usage/summary')
        assert r.status_code==200, r.text
        data=r.json(); assert data['requests']==1 and data['total_tokens']==15
        assert data['billed_nusd']==1800 and len(data['daily'])==7
        export=c.get('/api/usage/export')
        assert export.status_code==200 and export.headers['content-type'].startswith('text/csv')
        assert 'attachment;' in export.headers['content-disposition']
        rows=list(csv.DictReader(io.StringIO(export.text)))
        assert len(rows)==1 and rows[0]['model']==MODEL
        assert 'Hello' not in export.text and 'obk-' not in export.text
        # An unrelated wallet sees no records.
        app.state.store.ensure_account('different')
        assert app.state.store.usage_summary('different')['requests']==0


def test_csv_neutralizes_formula_injection(tmp_path):
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'csv.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        k,h=funded((app,c)); s=app.state.store
        rid=s.reserve(k['id'],WALLET,1000,'formula','=IMPORTXML("secret")',60)
        s.settle(rid,100)
        export=c.get('/api/usage/export'); assert export.status_code==200
        rows=list(csv.DictReader(io.StringIO(export.text)))
        assert rows[0]['model'].startswith("'=")

@pytest.mark.parametrize('name', [' ', '\t\n', '\u200b'])
def test_blank_key_name_is_rejected(tmp_path, name):
    app=create_app(Settings(origin='http://testserver'),str(tmp_path/'name.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        login(c)
        assert c.post('/api/keys',json={'name':name,'limit_usd':'1'},headers=ORIGIN).status_code==422


def test_key_branding_and_legacy_compatibility(tmp_path):
    s=Store(str(tmp_path/'keys.db'),'p'*32);s.ensure_account(WALLET)
    new=s.issue_key(WALLET,'new',100)
    assert new['key'].startswith('sv_')
    from gridraft.security import digest
    legacy='grd_old-compatible-key'; s.db.execute('UPDATE api_keys SET hash=? WHERE id=?',(digest(legacy,'p'*32),new['id']))
    assert s.lookup_key(legacy) is not None
    s.close()


def test_public_status_price_and_capabilities_are_not_hardcoded(tmp_path):
    app=create_app(Settings(origin='http://testserver',retail_nusd_per_token=120),str(tmp_path/'status.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        d=c.get('/api/status').json()
        assert d['brand']=='Slipvolt'
        assert d['retail_per_million_usd']==0.12
        assert d['capabilities']['streaming'] is False
        assert d['capabilities']['usage_export'] is True
        assert d['billing_review_required'] is False
        assert c.get('/healthz').json()=={'ok':True}


def test_global_budget_cannot_be_oversubscribed_by_concurrent_wallets(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s=Store(str(tmp_path/'concurrent-budget.db'),'p'*32)
    entries=[]
    for i in range(10):
        wallet='test-wallet-'+str(i)
        s.credit(wallet,10000,'grant-'+str(i))
        entries.append((wallet,s.issue_key(wallet,'test',10000)['id']))
    def attempt(item):
        wallet,kid=item
        try:
            return s.reserve(kid,wallet,600,wallet,MODEL,60,daily_budget_nusd=1000)
        except ValueError as e:
            return str(e)
    with ThreadPoolExecutor(max_workers=10) as executor:
        out=list(executor.map(attempt,entries))
    assert out.count('daily_budget')==9
    assert s.budget_usage()==600
    s.close()


def test_wallet_budget_is_shared_by_all_of_its_keys(tmp_path):
    s=Store(str(tmp_path/'wallet-budget.db'),'p'*32)
    s.credit(WALLET,10000,'grant')
    a=s.issue_key(WALLET,'a',10000);b=s.issue_key(WALLET,'b',10000)
    s.reserve(a['id'],WALLET,600,'a',MODEL,60,wallet_daily_budget_nusd=1000)
    with pytest.raises(ValueError,match='wallet_daily_budget'):
        s.reserve(b['id'],WALLET,600,'b',MODEL,60,wallet_daily_budget_nusd=1000)
    assert s.budget_usage(WALLET)==600
    s.close()


def test_prior_day_unresolved_hold_is_still_budgeted(tmp_path):
    s=Store(str(tmp_path/'prior-day.db'),'p'*32)
    s.credit(WALLET,10000,'grant');k=s.issue_key(WALLET,'a',10000)
    rid=s.reserve(k['id'],WALLET,600,'a',MODEL,60)
    s.db.execute('UPDATE usage SET created=0 WHERE id=?',(rid,))
    assert s.budget_usage()==600
    s.review(rid)
    assert s.budget_usage()==600
    s.close()


def test_provider_model_substitution_pauses_billing(tmp_path):
    def substituted(req):
        r=provider(req)
        if req.url.path.endswith('/chat/completions'):
            data=r.json();data['model']='different-provider/model'
            return httpx.Response(200,json=data)
        return r
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'model.db'),httpx.MockTransport(substituted))
    with TestClient(app) as c:
        _,h=funded((app,c))
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==502
        assert app.state.store.needs_review()


def test_configured_budget_rejects_boolean(tmp_path):
    with pytest.raises(ValueError,match='Invalid daily budget'):
        create_app(Settings(origin='http://testserver',daily_budget_nusd=True),str(tmp_path/'bad.db'))


def test_env_initializer_includes_documented_budget_defaults(tmp_path):
    from gridraft.cli import main
    path=tmp_path/'pilot.env'
    assert main(['--env-file',str(path),'init-env'])==0
    lines=path.read_text().splitlines()
    assert 'DAILY_BUDGET_NUSD=10000000000' in lines
    assert 'WALLET_DAILY_BUDGET_NUSD=2000000000' in lines
    assert 'DATABASE_PATH=data/gridraft.db' in lines
    # POSIX only: Windows os.stat cannot observe the 0o600 mode from os.open.
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777==0o600
