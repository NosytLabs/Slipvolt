"""QuickNode configuration, diagnostics and read-only Metis boundary checks."""
import asyncio,json,time
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.app import create_app
from test_admin_console import settings,auth
from test_gridraft import ORIGIN,MINT

GENESIS='5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d'
SOL='So11111111111111111111111111111111111111112'
USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'


def config(**kwargs):
    s=settings(solana_rpc='https://rpc.test/private-token',solana_ws='wss://rpc.test/private-token',
        metis_url='https://metis.test/private-metis',rpc_rps=100,rpc_concurrency=4,**kwargs)
    return s


def rpc_handler(req):
    if req.method=='POST':
        b=json.loads(req.content);method=b['method']
        result={'getGenesisHash':GENESIS,'getHealth':'ok','getSlot':999,
            'qn_estimatePriorityFees':{'per_compute_unit':{'recommended':1000},'per_transaction':{'recommended':123}},
        }.get(method)
        return httpx.Response(200,json={'jsonrpc':'2.0','id':b['id'],'result':result})
    if req.url.path.endswith('/quote'):
        return httpx.Response(200,json={'inputMint':SOL,'inAmount':'1000000000','outputMint':USDC,
            'outAmount':'120000000','otherAmountThreshold':'119400000','swapMode':'ExactIn','slippageBps':50,
            'priceImpactPct':'0.001','contextSlot':999,'routePlan':[{'swapInfo':{'label':'fixture'}}]})
    return httpx.Response(404)


def app_client(tmp_path,fn=rpc_handler,**kwargs):
    app=create_app(config(**kwargs),str(tmp_path/'i.db'),httpx.MockTransport(fn))
    return app,TestClient(app)


def test_connection_config_is_authenticated_and_contains_no_urls(tmp_path):
    _,client=app_client(tmp_path)
    with client as c:
        assert c.get('/api/admin/connections').status_code==401
        r=c.get('/api/admin/connections',headers=auth())
        assert r.status_code==200,r.text
        assert r.json()['solana_rpc']['configured'] is True
        assert 'private-token' not in r.text and 'private-metis' not in r.text
        assert 'rpc.test' not in r.text
        assert c.get('/api/status').json()['payments_enabled'] is False


def test_rpc_diagnostics_checks_actual_network_identity(tmp_path):
    _,client=app_client(tmp_path)
    with client as c:
        r=c.post('/api/admin/connections/check',headers={**ORIGIN,**auth()})
        assert r.status_code==200,r.text
        assert r.json()['rpc']['mainnet_verified'] is True
        assert r.json()['rpc']['slot']==999
        assert r.json()['transactions_sent']==0


def test_wrong_chain_is_never_reported_ready(tmp_path):
    def other(req):
        if req.method=='POST' and json.loads(req.content)['method']=='getGenesisHash':
            return httpx.Response(200,json={'jsonrpc':'2.0','id':1,'result':'wrong-network'})
        return rpc_handler(req)
    _,client=app_client(tmp_path,other)
    with client as c:
        d=c.post('/api/admin/connections/check',headers={**ORIGIN,**auth()}).json()
        assert d['rpc']['mainnet_verified'] is False
        assert d['rpc']['status']=='wrong_network'


def test_rpc_failure_does_not_leak_private_url(tmp_path):
    def bad(req):raise httpx.ConnectError(str(req.url),request=req)
    _,client=app_client(tmp_path,bad)
    with client as c:
        r=c.post('/api/admin/connections/check',headers={**ORIGIN,**auth()})
        assert r.status_code==200
        assert r.json()['rpc']['status']=='unavailable'
        assert 'private-token' not in r.text and 'rpc.test' not in r.text


def test_metis_quote_cannot_move_funds_or_issue_credit(tmp_path):
    seen=[]
    def record(req):seen.append(req);return rpc_handler(req)
    app,client=app_client(tmp_path,record)
    with client as c:
        r=c.post('/api/admin/swap/quote',headers={**ORIGIN,**auth()},json={'asset':'SOL','amount':'1','slippage_bps':50})
        assert r.status_code==200,r.text
        d=r.json()
        assert d['expected_usdc']=='120'
        assert d['minimum_usdc']=='119.4'
        assert d['execution_enabled'] is False and d['credits_issued']==0
        assert d['local_expires_at']>d['quoted_at']
        assert seen[0].method=='GET' and seen[0].url.params['amount']=='1000000000'
        assert not any('/swap' in str(x.url.path) for x in seen)
        assert 'private-metis' not in r.text


@pytest.mark.parametrize('changes',[{'outputMint':SOL},{'inAmount':'2'},{'otherAmountThreshold':'-1'},
    {'slippageBps':9999},{'priceImpactPct':'NaN'},{'priceImpactPct':'0.25'},{'outAmount':'1e12'}])
def test_bad_swap_quote_is_rejected(tmp_path,changes):
    def bad(req):
        r=rpc_handler(req)
        if req.url.path.endswith('/quote'):
            d=r.json();d.update(changes);return httpx.Response(200,json=d)
        return r
    _,client=app_client(tmp_path,bad)
    with client as c:
        r=c.post('/api/admin/swap/quote',headers={**ORIGIN,**auth()},json={'asset':'SOL','amount':'1','slippage_bps':50})
        assert r.status_code==502,r.text


@pytest.mark.parametrize('body',[{'asset':'GNK','amount':'1'}, {'asset':'SOL','amount':'0'},
 {'asset':'SOL','amount':'1e9'}, {'asset':'SOL','amount':'0.0000000001'},
 {'asset':'SOL','amount':'1','slippage_bps':1000}])
def test_quote_input_bounded_and_no_gnk_on_solana(tmp_path,body):
    seen=[]
    def record(req):seen.append(req);return rpc_handler(req)
    _,client=app_client(tmp_path,record)
    with client as c:
        assert c.post('/api/admin/swap/quote',headers={**ORIGIN,**auth()},json=body).status_code in (400,422)
        assert not seen
