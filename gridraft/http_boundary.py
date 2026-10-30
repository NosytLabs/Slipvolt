"""Explicit requests prevent client defaults crossing service boundaries.

The bounded JSON reader is shared by read-only providers; callers retain
their allowlisted destinations, deadlines and error handling.
"""
from contextlib import asynccontextmanager
import json
import httpx
import anyio


async def close_response(response):
    """Close even inside a cancelled streaming response task.

    Cleanup must not replace a durable settlement or its original error. Bound
    it so a broken transport cannot indefinitely delay client disconnects.
    """
    with anyio.move_on_after(5, shield=True):
        try:
            await response.aclose()
        except Exception:
            pass


def isolated_request(method, url, *, headers=None, params=None, json=None, timeout=8):
    return httpx.Request(method, url, headers={'Accept': 'application/json', **(headers or {})},
        params=params, json=json,
        extensions={'timeout': dict(connect=timeout, read=timeout, write=timeout, pool=timeout)})


@asynccontextmanager
async def isolated_stream(client, method, url, **kwargs):
    response = await client.send(isolated_request(method, url, **kwargs),
                                 stream=True, auth=None, follow_redirects=False)
    try:
        yield response
    finally:
        await close_response(response)


async def read_bounded_json(response, maximum=2_000_000, *,
                            too_large_message='Response too large'):
    """Parse only a bounded HTTP response, without trusting Content-Length.

    Caller must close the response (e.g. through isolated_stream) and validate
    the expected JSON shape. This helper never follows redirects or opens URLs.
    """
    if type(maximum) is not int or maximum < 1:
        raise ValueError('Invalid JSON response size limit')
    response.raise_for_status()
    chunks, size = [], 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > maximum:
            raise ValueError(too_large_message)
        chunks.append(chunk)
    return json.loads(b''.join(chunks))
