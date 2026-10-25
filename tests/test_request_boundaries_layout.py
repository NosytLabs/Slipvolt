"""Keep request/ASGI boundaries modular without changing public imports."""
import asyncio
import inspect

import pytest
from pydantic import ValidationError

import gridraft.app as legacy


def test_app_reexports_exact_request_models_from_dedicated_module():
    from gridraft import schemas
    for name in ('StrictBody', 'ChallengeInput', 'VerifyInput', 'KeyInput',
                 'Message', 'ChatInput', 'AdminConfigInput', 'AdminUserInput',
                 'AdminFundInput', 'AdminBusinessInput', 'SwapQuoteInput'):
        assert getattr(legacy, name) is getattr(schemas, name)
    # Migration must remove the old copies rather than define twins.
    source = inspect.getsource(legacy)
    assert 'class StrictBody(' not in source
    assert 'class ChatInput(' not in source
    assert 'class AdminConfigInput(' not in source


def test_extracted_models_keep_validation_and_openapi_field_names():
    from gridraft.schemas import ChatInput, Message, AdminConfigInput, KeyInput
    valid = ChatInput.model_validate({'model': 'MiniMaxAI/MiniMax-M2.7',
        'messages': [{'role': 'user', 'content': 'hello'}],
        'max_tokens': 128, 'max_completion_tokens': 128, 'n': 1})
    assert valid.max_tokens == 128 and valid.max_completion_tokens == 128
    schema = ChatInput.model_json_schema()
    assert {'model', 'messages', 'max_tokens', 'max_completion_tokens',
            'stream', 'tools', 'n'} <= set(schema['properties'])
    with pytest.raises(ValidationError, match='max_tokens and max_completion_tokens'):
        ChatInput.model_validate({'model': 'a', 'messages': [{'role': 'user', 'content': 'hello'}],
                                  'max_tokens': 128, 'max_completion_tokens': 129})
    with pytest.raises(ValidationError):
        ChatInput.model_validate({'model': 'a', 'messages': [{'role': 'user', 'content': 'hello'}],
                                  'unexpected_private_field': 'value'})
    with pytest.raises(ValidationError):
        Message.model_validate({'role': 'tool', 'content': 'ok'})
    assert KeyInput.model_validate({'name': '  test  '}).name == 'test'
    with pytest.raises(ValidationError):
        AdminConfigInput.model_validate({
            'wallet_rpm': 5, 'wallet_concurrency': 2, 'global_rpm': 5,
            'global_concurrency': 2, 'holder_daily_tokens': 100,
            'global_daily_tokens': 99, 'default_output_tokens': 1,
            'max_output_tokens': 1, 'retail_input_nusd_per_token': 1,
            'retail_output_nusd_per_token': 1,
        })


def test_body_middleware_is_reexported_without_duplicate_inline_class():
    from gridraft.body_boundary import BodyLimitMiddleware
    assert legacy.BodyLimitMiddleware is BodyLimitMiddleware
    assert 'class BodyLimitMiddleware:' not in inspect.getsource(legacy)


def test_extracted_body_middleware_rejects_nested_stream_without_dispatch():
    from gridraft.body_boundary import BodyLimitMiddleware
    calls = 0
    result = []
    async def receive():
        nonlocal calls
        calls += 1
        return {'type': 'http.request', 'body': b'[' * 33,
                'more_body': False}
    async def send(message):
        result.append(message)
    async def downstream(scope, receive, send):
        raise AssertionError('Invalid body was dispatched')
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/preflight', 'headers': []}
    asyncio.run(BodyLimitMiddleware(downstream, limit=1024)(scope, receive, send))
    assert calls == 1
    assert result[0]['status'] == 400


def test_extracted_body_middleware_keeps_non_http_passthrough():
    from gridraft.body_boundary import BodyLimitMiddleware
    observed = []
    async def downstream(scope, receive, send):
        observed.append(scope['type'])
    async def receive():
        raise AssertionError('Should not read body on websocket or GET')
    async def send(message):
        pass
    async def exercise():
        for scope in ({'type': 'websocket'},
                      {'type': 'http', 'method': 'GET'}):
            await BodyLimitMiddleware(downstream)(scope, receive, send)
    asyncio.run(exercise())
    assert observed == ['websocket', 'http']
