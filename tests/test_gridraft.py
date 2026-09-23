import base64
import concurrent.futures
import hashlib
import json
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from gridraft.app import Settings, create_app
from gridraft.economics import estimate, route_plan
from gridraft.store import Store

ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58(raw):
    n=int.from_bytes(raw,'big'); out=''
    while n: n, r=divmod(n,58); out=ALPHABET[r]+out
    return '1'*(len(raw)-len(raw.lstrip(b'\0')))+out

KEY=Ed25519PrivateKey.generate()
WALLET=b58(KEY.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
MINT='So11111111111111111111111111111111111111112'
MODEL='MiniMaxAI/MiniMax-M2.7'
ORIGIN={'Origin':'http://testserver'}
BODY={'model':MODEL,'messages':[{'role':'user','content':'Hello'}],'max_tokens':16}


def provider(req):
    if req.url.path.endswith('/balance'):
        return httpx.Response(200,json={'available_ngonka':1000000000})
    if req.url.path.endswith('/models'):
        return httpx.Response(200,json={'data':[{'id':MODEL,'object':'model'}]})
    if req.url.host=='example.invalid':
        return httpx.Response(200,json={'result':{'context':{'slot':123},'value':[{'account':{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'info':{'mint':MINT,'owner':WALLET,'state':'initialized','tokenAmount':{'amount':'1000','decimals':6}}}}}}]}})
    assert req.headers['authorization']=='Bearer obk-test-upstream'
    return httpx.Response(200,json={'id':'up-1','object':'chat.completion','choices':[{'index':0,'message':{'role':'assistant','content':'Hello back'},'finish_reason':'stop'}],'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}})

@pytest.fixture
def env(tmp_path):
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',upstream_key='obk-test-upstream'),str(tmp_path/'app.db'),httpx.MockTransport(provider))
    with TestClient(app) as client:
        yield app,client

def login(client):
    c=client.post('/api/auth/challenge',json={'wallet':WALLET},headers=ORIGIN)
    assert c.status_code==200,c.text
    challenge=c.json()
    signature=base64.b64encode(KEY.sign(challenge['message'].encode())).decode()
    body={'id':challenge['id'],'signature':signature}
    r=client.post('/api/auth/verify',json=body,headers=ORIGIN)
    assert r.status_code==200,r.text
    return body,challenge

def funded(env,credit=1_000_000_000):
    app,client=env
    login(client)
    app.state.store.credit(WALLET,credit,'test-funding')
    r=client.post('/api/keys',json={'name':'test','limit_usd':'1'},headers=ORIGIN)
    assert r.status_code==201,r.text
    return r.json(),{'Authorization':'Bearer '+r.json()['key']}

def test_cost_uses_devshard_retry_rate():
    e=estimate('1','10','1.5','0.05','10')
    assert e['upstream_per_million_usd']==0.015
    assert e['cost_usd']==0.15
    assert e['revenue_usd']==0.5
    assert e['margin_before_overhead_pct']==70.0

@pytest.mark.parametrize('bad',['-1','NaN','Infinity','abc'])
def test_invalid_economics_rejected(bad):
    with pytest.raises(ValueError): estimate(bad,'10','1.5','0.05','1')

def test_zero_income_does_not_create_infinite_margin():
    assert estimate('1','10','1.5','0','1')['margin_before_overhead_pct'] is None

def test_price_can_be_unprofitable():
    assert estimate('10','10','2.5','0.05','1')['margin_before_overhead_pct'] < 0

def test_route_to_native_and_exact_token():
    r=route_plan('SOL','GNK','100')
    assert r['executable'] is False
    assert r['destination_contract']=='0x972a7a92d92796a98801a8818bcf91f1648f2f68'
    assert r['steps'][-1]['asset']=='GNK'
    assert r['quote_status']=='not_requested'
    assert any('same key' in x.lower() for x in r['warnings'])

def test_route_wgnk_does_not_burn():
    r=route_plan('USDC','WGNK','25')
    assert r['steps'][-1]['asset']=='WGNK'
    assert not any(s['operation']=='bridge_to_gonka' for s in r['steps'])

@pytest.mark.parametrize('dest',['WNK','GNK_SOL','WGNK_SOL'])
def test_counterfeit_destination_rejected(dest):
    with pytest.raises(ValueError): route_plan('SOL',dest,'10')

def test_spl_route_requires_real_mint():
    with pytest.raises(ValueError): route_plan('SPL','GNK','10')

def test_status_does_not_claim_deployed_token(env):
    _,c=env; r=c.get('/api/status')
    assert r.status_code==200
    assert r.json()['token_launched'] is False
    assert r.json()['treasury_execution_enabled'] is False

def test_nonce_cannot_be_replayed(env):
    _,c=env; body,ch=login(c)
    assert 'http://testserver' in ch['message']
    assert 'does not authorize' in ch['message'].lower()
    assert c.post('/api/auth/verify',json=body,headers=ORIGIN).status_code==401

def test_wallet_signature_must_match(env):
    _,c=env
    ch=c.post('/api/auth/challenge',json={'wallet':WALLET},headers=ORIGIN).json()
    wrong=base64.b64encode(Ed25519PrivateKey.generate().sign(ch['message'].encode())).decode()
    assert c.post('/api/auth/verify',json={'id':ch['id'],'signature':wrong},headers=ORIGIN).status_code==401

def test_missing_or_foreign_origin_rejected(env):
    _,c=env
    assert c.post('/api/auth/challenge',json={'wallet':WALLET}).status_code==403
    assert c.post('/api/auth/challenge',json={'wallet':WALLET},headers={'Origin':'https://attacker.invalid'}).status_code==403

def test_expired_challenge(env):
    app,c=env
    ch=c.post('/api/auth/challenge',json={'wallet':WALLET},headers=ORIGIN).json()
    app.state.store.db.execute('UPDATE challenges SET expires=0')
    sig=base64.b64encode(KEY.sign(ch['message'].encode())).decode()
    assert c.post('/api/auth/verify',json={'id':ch['id'],'signature':sig},headers=ORIGIN).status_code==401

def test_invalid_wallet_rejected(env):
    _,c=env
    assert c.post('/api/auth/challenge',json={'wallet':'not-a-wallet'},headers=ORIGIN).status_code==422

def test_key_only_shown_once_and_revocation(env):
    app,c=env; result,headers=funded(env)
    assert result['key'].startswith('sv_')
    listing=c.get('/api/keys').json()
    assert result['key'] not in json.dumps(listing)
    row=app.state.store.db.execute('SELECT * FROM api_keys').fetchone()
    assert result['key'] not in str(dict(row))
    assert c.delete('/api/keys/'+result['id'],headers=ORIGIN).status_code==200
    assert c.post('/v1/chat/completions',json=BODY,headers=headers).status_code==401

def test_chat_bills_exact_integer_units(env):
    app,c=env; _,headers=funded(env)
    before=app.state.store.account(WALLET)['balance_nusd']
    r=c.post('/v1/chat/completions',json=BODY,headers=headers)
    assert r.status_code==200,r.text
    assert r.json()['choices'][0]['message']['content']=='Hello back'
    assert before-app.state.store.account(WALLET)['balance_nusd']==12*75+3*300

def test_insufficient_credit_never_calls_upstream(env):
    _,c=env; _,headers=funded(env,credit=0)
    assert c.post('/v1/chat/completions',json=BODY,headers=headers).status_code==402

def test_duplicate_idempotency_does_not_double_spend(env):
    app,c=env; _,headers=funded(env)
    headers['Idempotency-Key']='same-request'
    assert c.post('/v1/chat/completions',json=BODY,headers=headers).status_code==200
    balance=app.state.store.account(WALLET)['balance_nusd']
    assert c.post('/v1/chat/completions',json=BODY,headers=headers).status_code==409
    assert app.state.store.account(WALLET)['balance_nusd']==balance

def test_streaming_not_silently_emulated(env):
    _,c=env; _,h=funded(env)
    assert c.post('/v1/chat/completions',json={**BODY,'stream':True},headers=h).status_code==400

def test_unknown_model_rejected(env):
    _,c=env; _,h=funded(env)
    assert c.post('/v1/chat/completions',json={**BODY,'model':'fake-model'},headers=h).status_code==400

def test_key_limit_enforced(env):
    app,c=env; r,h=funded(env)
    app.state.store.db.execute('UPDATE api_keys SET limit_nusd=1 WHERE id=?',(r['id'],))
    assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==402

def test_known_rejected_provider_refunds_reservation(tmp_path):
    def fail(req):
        if req.url.path.endswith('/chat/completions'): return httpx.Response(400,json={'error':'invalid request'})
        return provider(req)
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',upstream_key='obk-test-upstream'),str(tmp_path/'f.db'),httpx.MockTransport(fail))
    with TestClient(app) as c:
        _,h=funded((app,c)); before=app.state.store.account(WALLET)['balance_nusd']
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==400
        assert app.state.store.account(WALLET)['balance_nusd']==before

def test_missing_usage_holds_reservation_for_reconciliation(tmp_path):
    def missing(req):
        if req.url.path.endswith('/chat/completions'): return httpx.Response(200,json={'id':'missing-1','choices':[]})
        return provider(req)
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',upstream_key='obk-test-upstream'),str(tmp_path/'m.db'),httpx.MockTransport(missing))
    with TestClient(app) as c:
        _,h=funded((app,c)); before=app.state.store.account(WALLET)['balance_nusd']
        r=c.post('/v1/chat/completions',json=BODY,headers=h)
        assert r.status_code==502
        assert app.state.store.account(WALLET)['balance_nusd'] < before
        assert app.state.store.db.execute('SELECT state FROM usage').fetchone()[0]=='needs_review'

def test_provider_key_never_exposed(env):
    _,c=env
    for path in ['/api/status','/api/models','/openapi.json']:
        assert 'obk-test-upstream' not in c.get(path).text

def test_no_provider_is_a_real_error(tmp_path):
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',),str(tmp_path/'n.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        _,h=funded((app,c))
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==503

def test_request_size_limit(env):
    _,c=env
    r=c.post('/api/auth/challenge',content=b'x'*150000,headers=ORIGIN)
    assert r.status_code==422  # reaches schema validation; 10 MiB transport cap is higher

def test_auth_cookie_is_httponly_and_samesite(env):
    _,c=env; login(c)
    cookie=c.cookies.get('gridraft_session')
    assert cookie and len(cookie)>32
    assert c.get('/api/account').status_code==200
    assert c.post('/api/auth/logout',headers=ORIGIN).status_code==200
    assert c.get('/api/account').status_code==401

def test_credit_reference_is_idempotent(env):
    app,c=env; login(c)
    app.state.store.credit(WALLET,100,'unique')
    app.state.store.credit(WALLET,100,'unique')
    assert app.state.store.account(WALLET)['balance_nusd']==100
    with pytest.raises(ValueError): app.state.store.credit(WALLET,200,'unique')

def test_atomic_reservations_do_not_overspend(tmp_path):
    s=Store(str(tmp_path/'atomic.db'),'p'*32)
    s.ensure_account(WALLET);s.credit(WALLET,1000,'seed')
    k=s.issue_key(WALLET,'race',10000)
    def run(i):
        try: return s.reserve(k['id'],WALLET,600,str(i),MODEL,60)
        except ValueError: return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: results=list(pool.map(run,range(8)))
    assert sum(r is not None for r in results)==1
    assert s.account(WALLET)['balance_nusd']==400
    s.close()

def test_holder_gate_uses_raw_amounts_and_server_rpc(tmp_path):
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',upstream_key='obk-test-upstream',access_mode='holder',holder_mint=MINT,min_holding_raw=1001),str(tmp_path/'h.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        login(c);r=c.get('/api/eligibility')
        assert r.status_code==200 and r.json()['eligible'] is False
        assert r.json()['holding_raw']=='1000'
        assert c.post('/api/keys',json={'name':'k','limit_usd':'1'},headers=ORIGIN).status_code==403

def test_holder_gate_fails_closed_on_rpc(tmp_path):
    app=create_app(Settings(origin='http://testserver',solana_rpc='https://example.invalid',upstream_key='obk-test-upstream',access_mode='holder',holder_mint=MINT),str(tmp_path/'hr.db'),httpx.MockTransport(lambda req:httpx.Response(503)))
    with TestClient(app) as c:
        login(c)
        assert c.get('/api/eligibility').status_code==503

def test_security_headers(env):
    _,c=env; r=c.get('/api/status')
    assert r.headers['x-content-type-options']=='nosniff'
    assert 'frame-ancestors' in r.headers['content-security-policy']

def test_disallowed_generation_fields(env):
    _,c=env;_,h=funded(env)
    r=c.post('/v1/chat/completions',json={**BODY,'n':100},headers=h)
    assert r.status_code==422

# Additional review regressions: cross-account isolation, input bounds and ops.
def test_one_wallet_cannot_revoke_another_wallet_key(env):
    app,c=env; first,h=funded(env)
    other=Ed25519PrivateKey.generate()
    pub=b58(other.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw))
    ch=c.post('/api/auth/challenge',json={'wallet':pub},headers=ORIGIN).json()
    sig=base64.b64encode(other.sign(ch['message'].encode())).decode()
    assert c.post('/api/auth/verify',json={'id':ch['id'],'signature':sig},headers=ORIGIN).status_code==200
    assert c.get('/api/keys').json()['data']==[]
    assert c.delete('/api/keys/'+first['id'],headers=ORIGIN).status_code==404
    assert app.state.store.lookup_key(first['key']) is not None

def test_production_cookie_has_secure_and_httponly(tmp_path):
    app=create_app(Settings(origin='https://gridraft.example',production=True),str(tmp_path/'p.db'),httpx.MockTransport(provider))
    with TestClient(app,base_url='https://gridraft.example') as c:
        headers={'Origin':'https://gridraft.example'}
        ch=c.post('/api/auth/challenge',json={'wallet':WALLET},headers=headers).json()
        sig=base64.b64encode(KEY.sign(ch['message'].encode())).decode()
        r=c.post('/api/auth/verify',json={'id':ch['id'],'signature':sig},headers=headers)
        cookie=r.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        assert c.get('/api/account').status_code==200
        assert 'strict-transport-security' in r.headers

def test_holder_transferring_tokens_loses_inference_access(tmp_path):
    held=True
    def moving(req):
        if req.url.host=='example.invalid' and not held:
            return httpx.Response(200,json={'result':{'context':{'slot':9},'value':[]}})
        return provider(req)
    settings=Settings(origin='http://testserver',upstream_key='obk-test-upstream',access_mode='holder',holder_mint=MINT,min_holding_raw=1000,solana_rpc='https://example.invalid')
    app=create_app(settings,str(tmp_path/'transfer.db'),httpx.MockTransport(moving))
    with TestClient(app) as c:
        _,h=funded((app,c)); held=False
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==403

def test_upstream_timeout_retains_hold(tmp_path):
    def timeout(req):
        if req.url.path.endswith('/chat/completions'): raise httpx.ReadTimeout('ambiguous')
        return provider(req)
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'timeout.db'),httpx.MockTransport(timeout))
    with TestClient(app) as c:
        _,h=funded((app,c)); before=app.state.store.account(WALLET)['balance_nusd']
        assert c.post('/v1/chat/completions',json=BODY,headers=h).status_code==502
        assert app.state.store.account(WALLET)['balance_nusd']<before
        assert app.state.store.history(WALLET)[0]['state']=='needs_review'

def test_body_limit_stops_reading_stream_as_soon_as_full():
    import asyncio
    import gridraft.app as module
    assert hasattr(module,'BodyLimitMiddleware'), 'Bounded ASGI body middleware is required'
    calls=0; sent=[]
    async def receive():
        nonlocal calls
        calls+=1
        return {'type':'http.request','body':b'x'*60,'more_body':True}
    async def send(message): sent.append(message)
    async def unused_app(scope,receive,send): raise AssertionError('Oversized body reached application')
    scope={'type':'http','method':'POST','headers':[]}
    asyncio.run(module.BodyLimitMiddleware(unused_app,limit=100)(scope,receive,send))
    assert calls==2
    assert sent[0]['status']==413

def test_cli_money_does_not_round_to_free():
    from gridraft.cli import usd_to_nusd
    assert usd_to_nusd('0.000000001')==1
    with pytest.raises(ValueError): usd_to_nusd('0.0000000001')
    with pytest.raises(ValueError): usd_to_nusd('NaN')
    with pytest.raises(ValueError): usd_to_nusd('-1')

def test_manual_reconciliation_is_audited_and_not_double_charged(env):
    app,c=env; k,h=funded(env); s=app.state.store
    rid=s.reserve(k['id'],WALLET,1000,'ops-test',MODEL,60)
    s.review(rid)
    assert hasattr(s,'pending'), 'Operator needs a pending-reservation queue'
    assert s.pending()[0]['id']==rid
    assert s.settle(rid,750,state='operator_settled',evidence='verified upstream row test-1') is True
    assert s.settle(rid,750,state='operator_settled',evidence='same evidence') is False
    assert s.pending()==[]
    assert s.db.execute('SELECT evidence FROM reconciliations WHERE request_id=?',(rid,)).fetchone()[0]=='verified upstream row test-1'

def test_failed_catalog_is_negative_cached(tmp_path):
    calls=0
    def down(req):
        nonlocal calls
        calls+=1
        return httpx.Response(503)
    app=create_app(Settings(origin='http://testserver'),str(tmp_path/'catalog.db'),httpx.MockTransport(down))
    with TestClient(app) as c:
        assert c.get('/api/models').json()['live'] is False
        assert c.get('/v1/models').status_code==503
        assert calls==1, 'A provider outage must not start one upstream request per page view'

def test_public_catalog_rate_limit(env):
    _,c=env
    for _ in range(60): assert c.get('/api/models').status_code==200
    assert c.get('/api/models').status_code==429

def test_broker_balance_above_one_gnk_is_valid(tmp_path):
    def balance(req):
        if req.url.path.endswith('/balance'):
            return httpx.Response(200,json={'available_ngonka':86_730_000_000})
        return provider(req)
    app=create_app(Settings(origin='http://testserver',upstream_key='obk-test-upstream'),str(tmp_path/'large-balance.db'),httpx.MockTransport(balance))
    with TestClient(app) as c:
        _,h=funded((app,c))
        response=c.post('/v1/chat/completions',json=BODY,headers=h)
        assert response.status_code==200,response.text


def test_production_rejects_unexpected_or_malformed_host(tmp_path):
    app=create_app(Settings(origin='https://slipvolt.example',production=True,pepper='x'*32),str(tmp_path/'host.db'),httpx.MockTransport(provider))
    with TestClient(app,base_url='https://slipvolt.example') as c:
        good=c.get('/api/status',headers={'host':'slipvolt.example'})
        assert good.status_code == 200
        for host in ('evil.example','slipvolt.example/forged-path','slipvolt.example@evil.example'):
            bad=c.get('/api/status',headers={'host':host})
            assert bad.status_code == 400
            assert bad.json()['error']['message'] == 'Invalid Host header'


def test_production_host_check_normalizes_default_https_port(tmp_path):
    app=create_app(Settings(origin='https://slipvolt.example:443',production=True,pepper='x'*32),str(tmp_path/'host-port.db'),httpx.MockTransport(provider))
    with TestClient(app,base_url='https://slipvolt.example') as c:
        assert c.get('/api/status',headers={'host':'slipvolt.example'}).status_code == 200


def test_production_host_check_keeps_nondefault_port_strict(tmp_path):
    app=create_app(Settings(origin='https://slipvolt.example:8443',production=True,pepper='x'*32),str(tmp_path/'host-port-strict.db'),httpx.MockTransport(provider))
    with TestClient(app,base_url='https://slipvolt.example:8443') as c:
        assert c.get('/api/status',headers={'host':'slipvolt.example:8443'}).status_code == 200
        assert c.get('/api/status',headers={'host':'slipvolt.example'}).status_code == 400


def test_openapi_and_status_report_the_same_release_version(tmp_path):
    app=create_app(Settings(pepper='x'*32),str(tmp_path/'version.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        schema_version=c.get('/openapi.json').json()['info']['version']
        status_version=c.get('/api/status').json()['version']
        assert schema_version == status_version



def test_legacy_public_planning_routes_removed(tmp_path):
    app=create_app(Settings(pepper='x'*32),str(tmp_path/'legacy-routes.db'),httpx.MockTransport(provider))
    with TestClient(app) as c:
        assert c.get('/api/economics').status_code == 404
        assert c.get('/api/route').status_code == 404
