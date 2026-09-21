import asyncio
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from gridraft.broker import Broker, MODEL_METADATA_URL
from gridraft.integrations import SolanaRPC
from gridraft.app import create_app
from test_membership import member_settings, handler
from test_gridraft import MODEL

@pytest.mark.parametrize('private',[False,True])
def test_broker_requests_do_not_inherit_shared_client_credentials(private):
    seen=[]
    async def run():
        async with httpx.AsyncClient(headers={'Authorization':'Bearer WRONG','X-Api-Key':'SECRET'},
              cookies={'session':'SECRET'},params={'token':'SECRET'},auth=('u','p'),
              transport=httpx.MockTransport(lambda req:(seen.append(req) or httpx.Response(200,json={})))) as c:
            await Broker(c,'obk-TEST').read('/v1/balance' if private else '/v1/models',private)
    asyncio.run(run());req=seen[0]
    assert req.headers.get('authorization')==('Bearer obk-TEST' if private else None)
    assert 'cookie' not in req.headers and 'x-api-key' not in req.headers and not req.url.query

def test_metadata_and_solana_requests_do_not_inherit_credentials():
    seen=[]
    async def run():
        async with httpx.AsyncClient(headers={'Authorization':'Bearer WRONG'},cookies={'s':'SECRET'},params={'token':'SECRET'},
              transport=httpx.MockTransport(lambda req:(seen.append(req) or httpx.Response(200,json={'result':'ok'})))) as c:
            await Broker(c).read_url(MODEL_METADATA_URL)
            await SolanaRPC(c,'https://example.invalid').call('getHealth')
    asyncio.run(run())
    for req in seen:assert 'authorization' not in req.headers and 'cookie' not in req.headers and not req.url.query

@pytest.mark.parametrize('url',['https://elsewhere.invalid/models',MODEL_METADATA_URL+'?token=x',MODEL_METADATA_URL+'#frag'])
def test_metadata_destination_is_allowlisted(url):
    seen=[]
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:(seen.append(r) or httpx.Response(200,json={})))) as c:
            with pytest.raises(ValueError):await Broker(c).read_url(url)
    asyncio.run(run());assert not seen

def test_redirect_not_followed_even_if_shared_client_allows_it():
    seen=[]
    async def run():
        async with httpx.AsyncClient(follow_redirects=True,transport=httpx.MockTransport(
             lambda r:(seen.append(r) or httpx.Response(302,headers={'location':'https://elsewhere.invalid/'})))) as c:
            with pytest.raises(Exception):await Broker(c,'obk-TEST').balance()
    asyncio.run(run());assert len(seen)==1

def test_health_failure_removes_stale_healthy_claim(tmp_path,monkeypatch):
    ticks=[1000.];calls=[]
    async def health(self):
        calls.append(1)
        if len(calls)>1:raise ValueError('unavailable')
        return {'models':[{'model':MODEL,'status':'healthy','routable':True}]}
    monkeypatch.setattr(Broker,'provider_status',health)
    import gridraft.app as mod
    monkeypatch.setattr(mod.time,'time',lambda:ticks[0])
    with TestClient(create_app(member_settings(),str(tmp_path/'a.db'),httpx.MockTransport(handler))) as c:
        assert c.get('/api/models').json()['data'][0]['availability']=='healthy'
        ticks[0]+=20
        row=c.get('/api/models').json()['data'][0]
        assert row['availability']=='listed' and 'routable' not in row
        c.get('/api/models');assert len(calls)==2

def test_network_caller_cannot_mutate_cached_totals():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            b=Broker(c);one=await b.network();one['totals']['requests']=99999
            assert (await b.network())['totals']['requests']==3
    asyncio.run(run())

def test_docker_contains_gonka_diagnostic():
    assert 'scripts/check_gonka.py' in Path('Dockerfile').read_text()
