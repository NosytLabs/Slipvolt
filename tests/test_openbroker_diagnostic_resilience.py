"""Bounded OpenBroker smoke probes must preserve trustworthy failure evidence."""
import asyncio
import json
import sys
from types import SimpleNamespace

import httpx

import scripts.check_openbroker as probe

MODEL = 'MiniMaxAI/MiniMax-M2.7'
SECRET = 'obk-private-fixture-do-not-print'


def run_probe(monkeypatch, response, *, after_failure=False):
    requests = []
    balances = {'count': 0}
    original = httpx.AsyncClient

    def handler(request):
        if request.url.path == '/v1/models':
            assert request.method == 'GET'
            assert 'authorization' not in request.headers
            return httpx.Response(200, json={'data': [{'id': MODEL}]})
        if request.url.path == '/v1/balance':
            balances['count'] += 1
            assert request.headers.get('authorization') == 'Bearer ' + SECRET
            if after_failure and balances['count'] == 2:
                raise httpx.ConnectError('PRIVATE-ENDPOINT-URL', request=request)
            return httpx.Response(200, json={'available_ngonka': 100000, 'status': 'active'})
        if request.url.path == '/v1/chat/completions':
            assert request.method == 'POST'
            assert request.headers.get('authorization') == 'Bearer ' + SECRET
            assert json.loads(request.content)['max_tokens'] == 32
            requests.append(request)
            return response
        raise AssertionError('Unexpected URL: ' + str(request.url))

    def factory(**kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv('OPENBROKER_API_KEY', SECRET)
    monkeypatch.setattr(probe, 'load_env', lambda _: None)
    monkeypatch.setattr(probe.httpx, 'AsyncClient', factory)
    args = SimpleNamespace(env_file='unused', model=MODEL,
                           allow_paid_inference=True, acknowledge_cost=True)
    result = asyncio.run(probe.check(args))
    return result, requests, balances['count']


def test_non_json_rate_limit_keeps_status_without_echoing_upstream_body(monkeypatch):
    result, requests, calls = run_probe(monkeypatch,
        httpx.Response(429, text='private-token-DO-NOT-ECHO',
                       headers={'x-request-id': 'request-429'}))
    item = result['inference'][0]
    assert len(requests) == 1 and calls == 2
    assert item['http_status'] == 429 and item['sent'] is True
    assert item['ok'] is False
    assert item['request_id'] == 'request-429'
    assert result['balance_after']['available_ngonka'] == 100000
    assert 'private-token-DO-NOT-ECHO' not in json.dumps(result)
    assert SECRET not in json.dumps(result)


def test_http_200_non_json_is_not_a_verified_paid_smoke(monkeypatch):
    result, requests, calls = run_probe(monkeypatch,
        httpx.Response(200, text='<html>provider proxy error</html>'))
    item = result['inference'][0]
    assert len(requests) == 1 and calls == 2
    assert item['http_status'] == 200 and item['ok'] is False
    assert 'usage' not in item
    assert 'provider proxy error' not in json.dumps(result)


def test_valid_paid_smoke_requires_correlated_usage_and_single_response(monkeypatch):
    result, requests, calls = run_probe(monkeypatch, httpx.Response(200, json={
        'id': 'resp-1', 'model': MODEL,
        'usage': {'prompt_tokens': 7, 'completion_tokens': 1, 'total_tokens': 8},
        'choices': [{'message': {'role': 'assistant', 'content': 'OK'}}],
    }))
    item = result['inference'][0]
    assert len(requests) == 1 and calls == 2
    assert item['http_status'] == 200 and item['ok'] is True
    assert item['usage']['total_tokens'] == 8
    assert item['text_preview'] == 'OK'


def test_paid_smoke_preserves_result_when_balance_after_is_unavailable(monkeypatch):
    result, requests, calls = run_probe(monkeypatch,
        httpx.Response(503, text='upstream unavailable'), after_failure=True)
    assert len(requests) == 1 and calls == 2
    assert result['inference'][0]['ok'] is False
    assert result['balance_after'] is None
    assert result['balance_after_unavailable'] is True


def test_main_never_reports_paid_success_from_status_200_without_verified_result(monkeypatch, capsys):
    async def unverified(_):
        return {'mode': 'paid bounded smoke test', 'inference': [
            {'model': MODEL, 'sent': True, 'http_status': 200, 'ok': False}],
            'balance_after': None, 'balance_after_unavailable': True}
    monkeypatch.setattr(probe, 'check', unverified)
    monkeypatch.setattr(sys, 'argv', ['check_openbroker.py', '--allow-paid-inference', '--acknowledge-cost'])
    assert probe.main() == 1
    assert SECRET not in capsys.readouterr().out
