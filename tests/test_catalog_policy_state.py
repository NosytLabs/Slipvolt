"""External catalog evidence stays cached; local display policy stays current."""
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import create_app
from test_gridraft import MODEL
from test_membership import member_settings


@contextmanager
def catalog_client(tmp_path,phase=None,change=None,initial=None):
    target={};reads=[]

    def respond(request):
        if request.url.host=='proxy.gonka.gg' and request.url.path=='/v1/models':
            observed='metadata'
            data={'data':[{'id':MODEL,'context_length':10_000,'max_tokens':2048}]}
        elif request.url.path=='/v1/models':
            observed='catalog';data={'data':[{'id':MODEL}]}
        elif request.url.path=='/api/status':
            observed='health';data={'status':'healthy','models':[{'model':MODEL,'status':'healthy','routable':True}]}
        else:
            raise AssertionError(f'Unexpected provider request: {request.url.host}{request.url.path}')
        reads.append(observed)
        if observed==phase:target['app'].state.store.set_operator_settings(change)
        return httpx.Response(200,json=data)

    app=create_app(member_settings(),str(tmp_path/'catalog.db'),httpx.MockTransport(respond))
    target['app']=app
    if initial:app.state.store.set_operator_settings(initial)
    with TestClient(app) as client:yield app,client,reads


@pytest.mark.parametrize(('path','phase'),[
    ('/v1/models','catalog'),('/v1/models','metadata'),
    ('/api/models','catalog'),('/api/models','metadata'),('/api/models','health'),
])
@pytest.mark.parametrize('change',[{'disabled_models':[MODEL]},{'max_output_tokens':128}])
def test_model_list_applies_policy_changed_during_external_read(tmp_path,path,phase,change):
    with catalog_client(tmp_path,phase,change) as (_,client,reads):
        response=client.get(path)
        assert response.status_code==200,response.text
        rows=response.json()['data']
        if 'disabled_models' in change:
            assert rows==[]
        else:
            assert len(rows)==1
            assert rows[0]['max_completion_tokens']==128
            assert rows[0]['completion_limit_source']=='operator_cap'
            assert rows[0]['context_length']==10_000
            assert rows[0]['discovered_max_completion_tokens']==2048
            assert rows[0]['openbroker_limits_verified'] is False
            if path=='/api/models':assert rows[0]['default_completion_tokens']==128
        assert reads==(['catalog','metadata','health'] if path=='/api/models' else ['catalog','metadata'])


@pytest.mark.parametrize('phase',['catalog','metadata','health'])
def test_public_model_defaults_and_rates_use_policy_after_external_reads(tmp_path,phase):
    change={'default_output_tokens':96,'retail_input_nusd_per_token':123,'retail_output_nusd_per_token':456}
    with catalog_client(tmp_path,phase,change) as (_,client,reads):
        response=client.get('/api/models')
        assert response.status_code==200,response.text
        result=response.json();row=result['data'][0]
        assert row['default_completion_tokens']==96
        assert row['max_completion_tokens']==2048
        assert result['pricing']['input_per_million_usd']==0.123
        assert result['pricing']['output_per_million_usd']==0.456
        assert result['live'] is True
        assert 'separate Gonka proxy discovery metadata' in result['source']
        assert reads==['catalog','metadata','health']


@pytest.mark.parametrize(('initial','change'),[
    ({'disabled_models':[MODEL]},{'disabled_models':[]}),
    ({'max_output_tokens':128},{'max_output_tokens':512}),
])
def test_public_model_policy_can_relax_during_health_read(tmp_path,initial,change):
    with catalog_client(tmp_path,'health',change,initial) as (_,client,reads):
        response=client.get('/api/models')
        assert response.status_code==200,response.text
        row=response.json()['data'][0]
        assert row['id']==MODEL
        assert row['max_completion_tokens']==change.get('max_output_tokens',2048)
        assert row['discovered_max_completion_tokens']==2048
        assert reads==['catalog','metadata','health']


def test_policy_changes_do_not_refetch_or_replace_cached_external_evidence(tmp_path):
    with catalog_client(tmp_path) as (app,client,reads):
        first=client.get('/api/models').json()
        app.state.store.set_operator_settings({'max_output_tokens':128,'default_output_tokens':64})
        second=client.get('/api/models').json()
        assert first['data'][0]['max_completion_tokens']==2048
        assert second['data'][0]['max_completion_tokens']==128
        assert second['data'][0]['default_completion_tokens']==64
        for key in ('id','context_length','discovered_context_length','discovered_max_completion_tokens','availability','openbroker_limits_verified'):
            assert second['data'][0][key]==first['data'][0][key]
        assert second['source']==first['source']
        assert reads==['catalog','metadata','health']
