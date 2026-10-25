"""Shared infrastructure for optional token and treasury API routes.

Feature modules retain their own rate-limit buckets, RPC clients and business
rules. This module never reads credentials from the environment or sends RPCs.
"""
import secrets
from contextlib import asynccontextmanager

from fastapi import HTTPException
from starlette.routing import Mount

from .security import digest


def api_error(status, message, **headers):
    """Keep operator/evidence errors out of intermediary caches."""
    return HTTPException(status, message, headers={'Cache-Control': 'no-store', **headers})


def authenticate_admin(request, settings, *, require_origin=True):
    """Check the separate admin key; write routes also require an exact Origin.

    Callers must apply their own throttle before this check. Read-only routes
    may explicitly opt out of Origin checking, never out of authentication.
    """
    if not settings.admin_key:
        raise api_error(503, 'Admin API is not configured')
    header = request.headers.get('authorization', '')
    key = header[7:] if header.startswith('Bearer ') else ''
    if not key or not key.isascii() or len(key) > 512 or not secrets.compare_digest(key, settings.admin_key):
        raise api_error(401, 'Invalid admin credential')
    if require_origin and request.headers.get('origin') != settings.origin:
        raise api_error(403, 'Origin check failed')


def throttle_request(request, store, pepper, *, bucket, limit, message):
    """Preserve caller-owned namespaces and avoid retaining raw client IPs."""
    peer = request.client.host if request.client else 'unknown'
    try:
        store.throttle(digest(bucket + ':' + peer, pepper), limit)
    except ValueError:
        raise api_error(429, message, **{'Retry-After': '60'}) from None


def close_client_with_app(app, client):
    """Compose client shutdown with the existing application lifespan."""
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with previous(application):
                yield
        finally:
            await client.aclose()
    app.router.lifespan_context = lifespan


def register_api_routes(app, router):
    """Insert routes before the root StaticFiles mount without reordering others."""
    index = next((i for i, route in enumerate(app.router.routes)
                  if isinstance(route, Mount) and route.path in ('', '/')), len(app.router.routes))
    app.router.routes[index:index] = router.routes
