"""Treasury-funded access regressions. All provider/wallet responses are test fixtures."""
import concurrent.futures
import importlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import Settings, create_app
from gridraft.store import Store
from test_gridraft import WALLET, MINT, MODEL, BODY, ORIGIN, login, provider


def member_settings(**updates):
    s=Settings(origin='http://testserver',upstream_key='obk-test-upstream',
        access_mode='holder_allowance',holder_mint=MINT,min_holding_raw=1000,
        solana_rpc='https://example.invalid')
    for k,v in (dict(holder_daily_tokens=250000,global_daily_tokens=1000000,
                    allowance_ngonka_per_token=25,public_broker_balance=False) | updates).items():
        setattr(s,k,v)
    return s


def handler(req):
    if req.url.path.startswith('/v1/usage/'):
        return httpx.Response(200,json={'response_id':'up-1','model':MODEL,'total_tokens':15,
            'cost_ngonka':150,'cost_source':'devshard_settled'})
    if req.url.path=='/api/registry/brokers':
        return httpx.Response(200,json={'brokers':[{'status':'active','id':'never-expose','wallet_address':'private'}],
          'daily_usage':[{'date':'2026-09-19','requests':3,'prompt_tokens':30,'completion_tokens':4,'total_tokens':34,'cost_ngonka':510}]})
    return provider(req)

@pytest.fixture
def members(tmp_path):
    app=create_app(member_settings(),str(tmp_path/'m.db'),httpx.MockTransport(handler))
    with TestClient(app) as c:
        login(c)
        yield app,c


def make_key(c):
    r=c.post('/api/member-key',headers=ORIGIN)
    assert r.status_code==201,r.text
    return {'Authorization':'Bearer '+r.json()['key']}


def test_create_key_without_dollar_credit(members):
    app,c=members
    h=make_key(c)
    assert app.state.store.account(WALLET)['balance_nusd']==0
    assert h['Authorization'].startswith('Bearer sv_')


def test_allowance_requires_explicit_pool_allocation(members):
    app,c=members
    r=c.post('/v1/chat/completions',headers=make_key(c),json=BODY)
    assert r.status_code==503
    assert 'pool' in r.text.lower()


def test_holder_can_call_with_native_budget_and_no_prepaid_credit(members):
    app,c=members
    app.state.membership.allocate(10000000,'verified-test-deposit')
    r=c.post('/v1/chat/completions',headers=make_key(c),json=BODY)
    assert r.status_code==200,r.text
    assert r.json()['choices'][0]['message']['content']=='Hello back'
    a=c.get('/api/membership').json()
    assert a['used_tokens']==15
    assert a['remaining_tokens']==249985
    assert a['pool']['budget_spent_ngonka']==150
    assert 'obk-' not in json.dumps(a)


def test_revoked_member_key_cannot_dispatch(members):
    app,c=members
    app.state.membership.allocate(10000000,'deposit')
    h=make_key(c)
    app.state.store.revoke(app.state.store.keys(WALLET)[0]['id'],WALLET)
    assert c.post('/v1/chat/completions',headers=h,json=BODY).status_code==401


def test_public_broker_statistics_never_expose_directory(members):
    app,c=members
    r=c.get('/api/network')
    assert r.status_code==200,r.text
    d=r.json()
    assert d['scope']=='OpenBroker network; not Slipvolt usage'
    assert d['totals']['tokens']==34
    assert 'never-expose' not in r.text and 'wallet_address' not in r.text


def test_broker_balance_not_published_without_opt_in(members):
    _,c=members
    d=c.get('/api/treasury').json()
    assert d['asset']=='GNK'
    assert d['broker_balance'] is None


def ledger():
    mod=importlib.import_module('gridraft.membership')
    store=Store(':memory:','x'*40);store.ensure_account(WALLET)
    k=store.issue_key(WALLET,'first',1_000_000_000)
    return store,mod.Membership(store),k


def reserve(m,k,idem='1',tokens=100,wallet=WALLET,**updates):
    p=dict(wallet_daily=1000,global_daily=10000,ngonka_per_token=25,upstream_available=10000000,rpm=60)
    p.update(updates)
    return m.reserve(k['id'],wallet,MODEL,idem,tokens,**p)


def test_duplicate_budget_allocation_is_idempotent():
    store,m,k=ledger();m.allocate(10000,'a');m.allocate(10000,'a')
    assert m.pool()['allocated_ngonka']==10000
    with pytest.raises(ValueError):m.allocate(10001,'a')
    store.close()


def test_wallet_daily_quota_shared_across_keys():
    store,m,k=ledger();m.allocate(1000000,'a');r=reserve(m,k,tokens=900)
    m.settle(r,900,22500,'budget_estimate',upstream_id='up')
    k2=store.issue_key(WALLET,'second',1_000_000_000)
    with pytest.raises(ValueError,match='wallet_allowance'):reserve(m,k2,tokens=101)
    store.close()


def test_pool_budget_atomic_under_concurrency():
    store,m,k=ledger();m.allocate(2500,'a')
    def run(i):
        try:reserve(m,k,str(i));return True
        except ValueError:return False
    with concurrent.futures.ThreadPoolExecutor() as ex:results=list(ex.map(run,range(8)))
    assert sum(results)==1
    store.close()


def test_uncertain_request_keeps_hold_and_stops_new_dispatch():
    store,m,k=ledger();m.allocate(100000,'a');rid=reserve(m,k)
    m.review(rid,'upstream-123')
    assert m.pool()['reserved_ngonka']==2500
    with pytest.raises(ValueError,match='reconciliation'):reserve(m,k,'2')
    store.close()


def test_prior_day_unresolved_hold_counts_today():
    store,m,k=ledger();m.allocate(100000,'a');rid=reserve(m,k,tokens=900)
    store.db.execute('UPDATE member_usage SET created=? WHERE id=?',(time.time()-172800,rid))
    with pytest.raises(ValueError,match='wallet_allowance'):reserve(m,k,'2',tokens=101)
    store.close()


def test_no_duplicate_request_dispatch():
    store,m,k=ledger();m.allocate(100000,'a');reserve(m,k)
    with pytest.raises(ValueError,match='duplicate'):reserve(m,k)
    store.close()


def test_settlement_refunds_unused_reservation_once():
    store,m,k=ledger();m.allocate(100000,'a');rid=reserve(m,k)
    assert m.settle(rid,15,375,'budget_estimate') is True
    assert m.settle(rid,15,375,'budget_estimate') is False
    assert m.pool()['available_budget_ngonka']==99625
    store.close()
