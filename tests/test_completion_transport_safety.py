"""Completion transport failures must leave bounded reads and durable accounting."""
import asyncio
import json
from types import SimpleNamespace

import anyio
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from gridraft.app import ChatInput, Settings, create_app
from gridraft.member_gateway import MemberGateway
from test_gridraft import BODY, MODEL, WALLET, funded, provider
from test_membership import handler, make_key, member_settings
from test_gridraft import login


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, chunks, fail_close=False):
        self.chunks = chunks
        self.reads = 0
        self.closed = False
        self.fail_close = fail_close

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self):
        await anyio.sleep(0)
        self.closed = True
        if self.fail_close:
            raise RuntimeError('fixture transport close failed')


def prepaid_app(tmp_path, response_stream):
    def upstream(request):
        if request.url.path.endswith('/chat/completions'):
            return httpx.Response(200, stream=response_stream)
        return provider(request)
    return create_app(Settings(origin='http://testserver', access_mode='prepaid',
        upstream_key='obk-test-upstream'), str(tmp_path/'prepaid.db'),
        httpx.MockTransport(upstream))


def test_prepaid_response_limit_stops_reading_and_retains_reservation(tmp_path):
    stream = ResponseStream([b'x' * 1_000_001] * 5)
    app = prepaid_app(tmp_path, stream)
    with TestClient(app) as client:
        _, headers = funded((app, client))
        response = client.post('/v1/chat/completions', headers=headers, json=BODY)
        assert response.status_code == 502
        assert stream.reads == 2
        assert stream.closed
        assert app.state.store.history(WALLET)[0]['state'] == 'needs_review'
        assert app.state.store.needs_review()


@pytest.mark.parametrize('payload', [
    b'{broken-json',
    b'[]',
    json.dumps({'id': 'up-1', 'choices': [{'message': {
        'role': 'assistant', 'content': 'hello'}}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 1}}).encode(),
])
def test_prepaid_malformed_response_or_usage_is_not_settled(tmp_path, payload):
    stream = ResponseStream([payload])
    app = prepaid_app(tmp_path, stream)
    with TestClient(app) as client:
        _, headers = funded((app, client))
        response = client.post('/v1/chat/completions', headers=headers, json=BODY)
        assert response.status_code == 502
        assert stream.closed
        assert app.state.store.history(WALLET)[0]['state'] == 'needs_review'


@pytest.mark.parametrize('mode', ['prepaid', 'holder_allowance'])
def test_failure_while_finishing_provider_body_retains_hold(tmp_path, mode):
    data = {'id': 'up-1', 'choices': [{'index': 0, 'message': {
        'role': 'assistant', 'content': 'hello'}}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15}}
    stream = ResponseStream([json.dumps(data).encode()], fail_close=True)
    def upstream(request):
        if request.url.path.endswith('/chat/completions'):
            return httpx.Response(200, stream=stream)
        return handler(request)
    settings = member_settings() if mode == 'holder_allowance' else Settings(
        origin='http://testserver', access_mode='prepaid', upstream_key='obk-test-upstream')
    app = create_app(settings, str(tmp_path/'close.db'), httpx.MockTransport(upstream))
    with TestClient(app) as client:
        if mode == 'holder_allowance':
            app.state.membership.allocate(10_000_000, 'fixture')
            login(client)
            headers = make_key(client)
        else:
            _, headers = funded((app, client))
        response = client.post('/v1/chat/completions', headers=headers, json=BODY)
        # HTTPX closes at EOF inside body iteration. Without a clean end of
        # body, a plausible JSON prefix is not evidence of a complete response.
        assert response.status_code == 502
        assert stream.closed
        if mode == 'holder_allowance':
            assert app.state.membership.pool()['reconciliation_required']
        else:
            assert app.state.store.needs_review()


def test_stream_disconnect_closes_transport_in_cancelled_anyio_scope():
    class Upstream:
        closed = False
        async def aiter_lines(self):
            await anyio.sleep_forever()
            yield ''
        async def aclose(self):
            await anyio.sleep(0)
            self.closed = True
    class Ledger:
        reviewed = []
        def review(self, *args):
            self.reviewed.append(args)
    upstream, ledger = Upstream(), Ledger()
    gateway = MemberGateway(SimpleNamespace(timeout=30), None, None, ledger)
    async def run():
        async def consume():
            async for _ in gateway.stream(upstream, 'local-1', MODEL, 'up-1', 25, 1):
                pass
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await anyio.sleep(0)
            group.cancel_scope.cancel()
    asyncio.run(run())
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed


def test_stream_deadline_marks_review_and_emits_structured_error():
    class Upstream:
        closed = False
        async def aiter_lines(self):
            await anyio.sleep_forever()
            yield ''
        async def aclose(self):
            await anyio.sleep(0)
            self.closed = True
    class Ledger:
        reviewed = []
        def review(self, *args):
            self.reviewed.append(args)
    upstream, ledger = Upstream(), Ledger()
    gateway = MemberGateway(SimpleNamespace(timeout=0.01), None, None, ledger)
    async def run():
        return ''.join([chunk async for chunk in gateway.stream(
            upstream, 'local-1', MODEL, 'up-1', 25, 1)])
    output = asyncio.run(run())
    error = json.loads(output.removeprefix('data: '))['error']
    assert error['type'] == 'slipvolt_error'
    assert error['code'] == 502
    assert error['request_id'] == 'local-1'
    assert '[DONE]' not in output
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed


def test_provider_response_headers_have_total_deadline_and_retain_hold():
    class Client:
        async def send(self, *args, **kwargs):
            await anyio.sleep_forever()
    class Broker:
        async def balance(self):
            return {'available_ngonka': 10**9}
    class Ledger:
        reviewed = []
        def reserve(self, *args, **kwargs):
            return 'local-1'
        def review(self, *args):
            self.reviewed.append(args)
    settings = member_settings()
    settings.timeout = 0.01
    ledger = Ledger()
    gateway = MemberGateway(settings, Client(), Broker(), ledger)
    request = SimpleNamespace(headers={}, state=SimpleNamespace())
    with pytest.raises(HTTPException) as error:
        asyncio.run(gateway.call(ChatInput.model_validate(BODY), request,
            {'id': 'key-1', 'wallet': WALLET}))
    assert error.value.status_code == 502
    assert 'uncertain' in error.value.detail
    assert ledger.reviewed == [('local-1',)]
