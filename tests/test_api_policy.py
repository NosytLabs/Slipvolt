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
            {'id':MODEL,'context_length':180000,'max_completion_tokens':16384},
            {'id':DEEP,'context_length':400000,'max_completion_tokens':16384},
            {'id':GLM,'context_length':400000,'max_completion_tokens':16384},
        ]})
    if req.url.path=='/v1/models':
        return httpx.Response(200,json={'data':[{'id':MODEL},{'id':DEEP},{'id':GLM}]})
    if req.url.path.startswith('/v1/usage/'):
        return httpx.Response(200,json={'response_id':'up-tools','model':MODEL,'total_tokens':15,'cost_ngonka':150,'cost_source':'devshard_settled'})
    if req.url.path.endswith('/chat/completions'):
        body=__import__('json').loads(req.content)
        assert body['max_tokens'] in (4096,16384)
        if body.get('tools'):
            return httpx.Response(200,json={'id':'up-tools','model':MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'weather','arguments':'{"city":"Paris"}'}}]},'finish_reason':'tool_calls'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
        return provider(req)
    return provider(req)

def make_member(tmp_path):
    app=create_app(holder_settings(),str(tmp_path/'p.db'),httpx.MockTransport(transport))
    client=TestClient(app); client.__enter__(); login(client); app.state.membership.allocate(10_000_000,'funded')
    key=client.post('/api/member-key',headers=ORIGIN).json()['key']
    return app,client,{'Authorization':'Bearer '+key}

def test_model_metadata_has_real_context_and_output_caps(tmp_path):
    app=create_app(holder_settings(),str(tmp_path/'models.db'),httpx.MockTransport(transport))
    with TestClient(app) as c:
        d=c.get('/api/models').json()['data']
        by={m['id']:m for m in d}
        assert by[MODEL]['context_length']==180000
        assert by[DEEP]['context_length']==400000
        assert by[GLM]['context_length']==400000
        assert {m['max_completion_tokens'] for m in d}=={16384}
        o=c.get('/v1/models').json()['data'][0]
        assert 'context_length' in o and 'max_completion_tokens' in o

def test_default_output_is_4096_and_hard_cap_is_16384(tmp_path):
    app,c,h=make_member(tmp_path)
    try:
        r=c.post('/v1/chat/completions',headers=h,json={'model':MODEL,'messages':[{'role':'user','content':'hi'}]})
        assert r.status_code==200,r.text
        ok=c.post('/v1/chat/completions',headers={**h,'Idempotency-Key':'max'},json={'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_completion_tokens':16384})
        assert ok.status_code==200,ok.text
        bad=c.post('/v1/chat/completions',headers={**h,'Idempotency-Key':'too-high'},json={'model':MODEL,'messages':[{'role':'user','content':'hi'}],'max_tokens':16385})
        assert bad.status_code in (400,422)
    finally:c.__exit__(None,None,None)

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
