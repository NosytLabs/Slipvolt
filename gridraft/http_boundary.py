"""Explicit requests prevent client defaults crossing service boundaries."""
from contextlib import asynccontextmanager
import httpx


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
        await response.aclose()
