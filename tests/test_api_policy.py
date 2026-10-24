import httpx
from fastapi.testclient import TestClient
from gridraft.app import Settings, create_app
from test_gridraft import MODEL, MINT, ORIGIN, WALLET, login, provider

DEEP='deepseek-ai/DeepSeek-V4-Flash-0731'
GLM='zai-org/GLM-5.3-Flash'

def holder_settings(**kw):
    s=Settings(origin='http://testserver',upstream_key='obk-test-upstream',access_mode='holder_allowance',holder_mint=MINT,min_holding_raw=1000,solana_rpc='https://example.invalid')
    for k,v in kw.items(): setattr(s,k,v)
    return s

def transport(req):
    if req.url.host=='proxy.gonka.gg' and req.url.path=='/v1/models':
        return httpx.Response(200,json={'object':'list','data':[
            {'id':MODEL,'context_length':180000,'max_tokens':16384},
            {'id':DEEP,'context_length':400000,'max_tokens':16384},
            {'id':GLM,'context_length':400000,'max_tokens':16384},
        ]})
    if req.url.path=='/v1/models':
        return httpx.Response(200,json={'data':[{'id':MODEL},{'id':DEEP},{'id':GLM}]})
    if req.url.path.startswith('/v1/usage/'):
        return httpx.Response(200,json={'response_id':'up-tools','model':MODEL,'total_tokens':15,'cost_ngonka':150,'cost_source':'devshard_settled'})
    if req.url.path.endswith('/chat/completions'):
        body=__import__('json').loads(req.content)
        assert body['max_tokens']==4096
        if body.get('tools'):
            return httpx.Response(200,json={'id':'up-tools','model':MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'weather','arguments':'{"city":"Paris"}'}}]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
        return provider(req)
    return provider(req)

def make_member(tmp_path):
    app=create_app(holder_settings(),str(tmp_path/'p.db'),httpx.MockTransport(transport))
    client=TestClient(app); client.__enter__(); login(client); app.state.membership.allocate(10_000_000,'funded')
    key=client.post('/api/member-key',headers=ORIGIN).json()['key']
    return app,client,{'Authorization':'Bearer '+key}

def test_model_metadata_exposes_local_reviewed_context_and_output_caps(tmp_path):
    app=create_app(holder_settings(),str(tmp_path/'models.db'),httpx.MockTransport(transport))
    with TestClient(app) as c:
        d=c.get('/api/models').json()['data']
        by={m['id']:m for m in d}
        assert by[MODEL]['context_length']==180000
        assert by[DEEP]['context_length']==400000
        assert by[GLM]['context_length']==400000
        assert {m['max_completion_tokens'] for m in d}=={4096}
        o=c.get('/v1/models').json()['data'][0]
        assert 'context_length' in o and 'max_completion_tokens' in o
        assert o['openbroker_limits_verified'] is False
        assert o['limits_source']
        assert o['context_limit_source']=='reviewed_policy'
        assert o['completion_limit_source']=='reviewed_policy'

def test_default_policy_rejects_4097_before_provider_dispatch_or_reservation(tmp_path):
    sent=[]
    def guarded(req):
        if req.url.path.endswith('/chat/completions'):
            sent.append(__import__('json').loads(req.content)['max_tokens'])
        return transport(req)
    app=create_app(holder_settings(),str(tmp_path/'default-cap.db'),httpx.MockTransport(guarded))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key'];h={'Authorization':'Bearer '+key}
        rejected=c.post('/v1/chat/completions',headers=h,json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_tokens':4097})
        assert rejected.status_code==400,rejected.text
        assert sent==[]
        assert app.state.membership.pending()==[]
        assert app.state.membership.history(WALLET)==[]

        accepted=c.post('/v1/chat/completions',headers=h,json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert accepted.status_code==200,accepted.text
        assert sent==[4096]

def test_function_tools_pass_through_and_are_returned(tmp_path):
    app,c,h=make_member(tmp_path)
    try:
        body={'model':MODEL,'messages':[{'role':'user','content':'weather?'}],'tools':[{'type':'function','function':{'name':'weather','description':'weather','parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}}], 'tool_choice':'auto'}
        r=c.post('/v1/chat/completions',headers=h,json=body)
        assert r.status_code==200,r.text
        assert r.json()['choices'][0]['message']['tool_calls'][0]['function']['name']=='weather'
    finally:c.__exit__(None,None,None)

def test_body_limit_tracks_gonka_10_mib_not_old_128k(tmp_path):
    app=create_app(holder_settings(),str(tmp_path/'body.db'),httpx.MockTransport(transport))
    with TestClient(app) as c:
        payload={'wallet':'1'*44,'padding':'x'*200000}
        # unknown field should fail schema, but must reach validation rather than middleware 413
        r=c.post('/api/auth/challenge',json=payload,headers=ORIGIN)
        assert r.status_code==422


def test_explicit_operator_model_override_is_effective_and_labelled_unverified(tmp_path):
    def overridden(req):
        if req.url.host=='proxy.gonka.gg' and req.url.path=='/v1/models':
            return httpx.Response(200,json={'data':[{
                'id':MODEL,'context_length':120000,'max_tokens':4096}]})
        if req.url.path.endswith('/chat/completions'):
            assert __import__('json').loads(req.content)['max_tokens']==32768
            return provider(req)
        return transport(req)
    app=create_app(holder_settings(max_output_tokens=32768,model_limit_overrides={MODEL:{
        'context_length':204800,'max_completion_tokens':32768,
    }}),str(tmp_path/'override.db'),httpx.MockTransport(overridden))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        model=c.get('/api/models').json()['data'][0]
        assert model['context_length']==204800
        assert model['max_completion_tokens']==32768
        assert model['discovered_context_length']==120000
        assert model['discovered_max_completion_tokens']==4096
        assert model['context_limit_source']=='operator_override_unverified'
        assert model['completion_limit_source']=='operator_override_unverified'
        assert model['openbroker_limits_verified'] is False
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_tokens':32768})
        assert r.status_code==200,r.text


def test_context_is_per_choice_while_allowance_reserves_every_choice(tmp_path):
    def overridden(req):
        if req.url.host=='proxy.gonka.gg' and req.url.path=='/v1/models':
            return httpx.Response(200,json={'data':[{'id':MODEL}]})
        if req.url.path.endswith('/chat/completions'):return provider(req)
        return transport(req)
    app=create_app(holder_settings(default_output_tokens=1000,max_output_tokens=1600,
        model_limit_overrides={MODEL:{'context_length':3000,'max_completion_tokens':1600}}),
        str(tmp_path/'choice-context.db'),httpx.MockTransport(overridden))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}],
            'max_tokens':1600,'n':2})
        assert r.status_code==200,r.text
        # Aggregate reservation includes both choices and can exceed a per-sequence context.
        assert app.state.membership.history(WALLET)[0]['reserved_tokens']>3000


def test_omitted_output_uses_tightened_model_cap_below_configured_default(tmp_path):
    sent=[]
    def tightened(req):
        if req.url.host=='proxy.gonka.gg' and req.url.path=='/v1/models':
            return httpx.Response(200,json={'data':[{
                'id':MODEL,'context_length':180000,'max_tokens':2048}]})
        if req.url.path=='/v1/models':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        if req.url.path.endswith('/chat/completions'):
            sent.append(__import__('json').loads(req.content)['max_tokens'])
            return provider(req)
        return transport(req)
    app=create_app(holder_settings(default_output_tokens=4096),str(tmp_path/'tight-default.db'),httpx.MockTransport(tightened))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key'];h={'Authorization':'Bearer '+key}
        assert c.post('/v1/chat/completions',headers=h,json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}]}).status_code==200
        assert sent==[2048]
        assert c.post('/v1/chat/completions',headers={**h,'Idempotency-Key':'explicit-too-high'},json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_tokens':2049}).status_code==400
        assert sent==[2048]


def test_omitted_output_uses_operator_override_below_configured_default(tmp_path):
    sent=[]
    def overridden(req):
        if req.url.path.endswith('/chat/completions'):
            sent.append(__import__('json').loads(req.content)['max_tokens'])
            return provider(req)
        return transport(req)
    app=create_app(holder_settings(default_output_tokens=4096,model_limit_overrides={MODEL:{
        'context_length':180000,'max_completion_tokens':2048,
    }}),str(tmp_path/'override-default.db'),httpx.MockTransport(overridden))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key']
        r=c.post('/v1/chat/completions',headers={'Authorization':'Bearer '+key},json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==200,r.text
        assert sent==[2048]


def test_model_sources_remain_truthful_when_discovery_metadata_fails(tmp_path):
    def no_discovery(req):
        if req.url.host=='proxy.gonka.gg':return httpx.Response(503)
        return transport(req)
    app=create_app(holder_settings(),str(tmp_path/'metadata-failed.db'),httpx.MockTransport(no_discovery))
    with TestClient(app) as c:
        public=c.get('/api/models').json()
        assert public['live'] is True
        assert public['source']=='OpenBroker live catalogue + reviewed local model policy; separate Gonka proxy discovery unavailable'
        assert all(row['discovery_limits_status']=='unknown' for row in public['data'])
        compat=c.get('/v1/models').json()['data'][0]
        assert compat['owned_by']=='openbroker'
        assert compat['openbroker_limits_verified'] is False
        assert compat['limits_source'].startswith('Conservative reviewed local policy informed by Gonka documentation')


def test_null_optional_usage_settles_nonstream_and_stream_without_review(tmp_path):
    def nullable_usage(req):
        if req.url.path.startswith('/v1/usage/'):
            uid=req.url.path.rsplit('/',1)[-1]
            return httpx.Response(200,json={'response_id':uid,'model':MODEL,'total_tokens':15,
                'cost_ngonka':150,'cost_source':'devshard_settled'})
        if req.url.path.endswith('/chat/completions'):
            body=__import__('json').loads(req.content);uid='nullable-stream' if body.get('stream') else 'nullable-json'
            usage={'prompt_tokens':12,'completion_tokens':3,'total_tokens':15,
                'prompt_tokens_details':{'cached_tokens':None},
                'completion_tokens_details':{'reasoning_tokens':None}}
            if body.get('stream'):
                rows=[{'id':uid,'model':MODEL,'choices':[{'index':0,'delta':{'content':'ok'}}]},
                    {'id':uid,'model':MODEL,'choices':[],'usage':usage}]
                text=''.join('data: '+__import__('json').dumps(row)+'\n\n' for row in rows)+'data: [DONE]\n\n'
                return httpx.Response(200,text=text,headers={'content-type':'text/event-stream'})
            return httpx.Response(200,json={'id':uid,'model':MODEL,
                'choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],
                'usage':usage})
        return transport(req)
    app=create_app(holder_settings(),str(tmp_path/'nullable-usage.db'),httpx.MockTransport(nullable_usage))
    app.state.membership.allocate(10_000_000,'funded')
    with TestClient(app) as c:
        login(c);key=c.post('/api/member-key',headers=ORIGIN).json()['key'];h={'Authorization':'Bearer '+key}
        assert c.post('/v1/chat/completions',headers=h,json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}]}).status_code==200
        streamed=c.post('/v1/chat/completions',headers={**h,'Idempotency-Key':'nullable-stream'},json={
            'model':MODEL,'messages':[{'role':'user','content':'hi'}],'stream':True})
        assert streamed.status_code==200 and '[DONE]' in streamed.text
        history=app.state.membership.history(WALLET)
        assert len(history)==2 and all(row['state']=='settled' for row in history)
        assert all(row['cached_input_tokens'] is None and row['reasoning_tokens'] is None for row in history)
        assert app.state.membership.pool()['reconciliation_required'] is False
