"""Shared bounded JSON parsing for trusted, read-only HTTP adapters.

Fixtures exercise actual HTTPX streaming transports; no live RPC/provider calls.
"""
import asyncio
import json

import httpx
import pytest

from gridraft.broker import MODEL_METADATA_URL, Broker
from gridraft.gonka import GonkaRPC, RPCError
from gridraft.integrations import SolanaRPC, bounded_json
from gridraft.http_boundary import read_bounded_json


def run(coro):
    return asyncio.run(coro)


def attached_response(**kwargs):
    # Real HTTPX transport responses always have the request that
    # raise_for_status uses; construct unit responses with one too.
    return httpx.Response(200, request=httpx.Request('GET', 'https://fixture.invalid/json'),
                          **kwargs)


@pytest.mark.parametrize("payload,max_bytes", [
    (b'{"ok":true}', 11),
    (b'{"ok":true}', 12),
    (b'{}', 2),
])
def test_bounded_reader_accepts_json_at_or_below_limit(payload, max_bytes):
    response = attached_response(content=payload)
    assert run(read_bounded_json(response, maximum=max_bytes)) == (
        {"ok": True} if payload != b'{}' else {})


@pytest.mark.parametrize("response,maximum,problem", [
    (attached_response(content=b'{"ok":true}'), 10, "Response too large"),
    (attached_response(content=b'not-json'), 64, None),
])
def test_bounded_reader_rejects_oversize_and_invalid_json(response, maximum, problem):
    with pytest.raises(ValueError if problem else json.JSONDecodeError) as caught:
        run(read_bounded_json(response, maximum=maximum))
    if problem:
        assert problem in str(caught.value)


def test_existing_solana_reader_keeps_bounded_json_signature():
    assert run(bounded_json(attached_response(json={"result": 1}), maximum=20)) == {"result": 1}
    with pytest.raises(ValueError, match="Response too large"):
        run(bounded_json(attached_response(json={"result": 1}), maximum=2))


@pytest.mark.parametrize("destination,private", [
    ("/v1/models", False),
    ("/v1/balance", True),
    (MODEL_METADATA_URL, False),
])
def test_broker_readers_keep_isolated_gets_and_same_body_limits(destination, private):
    seen = []
    payload = b'{"ok":true}'
    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=payload)
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            headers={"Authorization": "Bearer WRONG", "X-Api-Key": "PRIVATE"},
            cookies={"wallet": "PRIVATE"}, params={"secret": "PRIVATE"},
            auth=("PRIVATE", "PRIVATE"), follow_redirects=True,
        ) as client:
            broker = Broker(client, "obk-fixture")
            async def invoke(limit):
                if destination == MODEL_METADATA_URL:
                    return await broker.read_url(destination, max_bytes=limit)
                return await broker.read(destination, private=private, max_bytes=limit)
            assert await invoke(len(payload)) == {"ok": True}
            with pytest.raises(ValueError, match="Upstream response too large"):
                await invoke(len(payload)-1)
    run(exercise())
    assert len(seen) == 2
    for request in seen:
        assert request.method == "GET"
        assert request.url.query == b""
        assert request.url.host == ("proxy.gonka.gg" if destination == MODEL_METADATA_URL
                                    else "api.openbroker.gonka.gg")
        assert "cookie" not in request.headers and "x-api-key" not in request.headers
        assert request.headers.get("authorization") == (
            "Bearer obk-fixture" if private else None)


def test_json_refactor_keeps_gonka_rpc_failure_codes():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text='{"long":"' + 'x' * 200 + '"}')
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            headers={"Authorization": "Bearer PRIVATE"}, cookies={"wallet": "PRIVATE"},
            params={"secret": "PRIVATE"}, follow_redirects=True,
        ) as client:
            with pytest.raises(RPCError) as error:
                await GonkaRPC(client).read("/v1/models", max_bytes=20)
            assert error.value.code == "response_too_large"
    run(exercise())
    assert len(requests) == 1
    assert requests[0].url.host == "rpc.gonka.gg"
    assert "authorization" not in requests[0].headers
    assert "cookie" not in requests[0].headers
    assert requests[0].url.query == b""


def test_shared_reader_preserves_solana_rpc_result_and_error_checks():
    async def exercise():
        def respond_ok(_):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "ok"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond_ok)) as client:
            assert await SolanaRPC(client, "https://solana.invalid").call("getHealth") == "ok"
        def respond_error(_):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1,
                                             "error": {"message": "PRIVATE PROVIDER DETAIL"}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond_error)) as client:
            with pytest.raises(ValueError, match="RPC call did not return a result"):
                await SolanaRPC(client, "https://solana.invalid").call("getHealth")
    run(exercise())


def test_readers_release_stream_after_invalid_json():
    observed = []
    def respond(request):
        response = httpx.Response(200, content=b"{broken")
        observed.append(response)
        return response
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ValueError):
                await Broker(client).read("/v1/models")
            with pytest.raises(RPCError):
                await GonkaRPC(client).read("/v1/models")
    run(exercise())
    assert len(observed) == 2
    assert all(response.is_closed for response in observed)
