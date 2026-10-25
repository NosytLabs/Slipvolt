"""Operator-only unsigned burn preparation; no keys, custody or broadcast RPC."""
import asyncio
import secrets
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.routing import Mount

from .integrations import SolanaRPC
from .security import decode_address, digest
from .treasury_burn import prepare_burn_plan


class BurnPlanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_account: str = Field(strict=True, min_length=32, max_length=44)
    amount: str = Field(strict=True, min_length=1, max_length=40)
    confirm_project_owned: bool = Field(strict=True)


def install_treasury_routes(app, settings, *, treasury_owner='', transport=None):
    """Optional server-configured treasury authority; empty means planning disabled."""
    if getattr(app.state, 'treasury_routes_installed', False):
        raise ValueError('Treasury routes are already installed')
    if treasury_owner:
        decode_address(treasury_owner)
    app.state.treasury_routes_installed = True
    client = httpx.AsyncClient(transport=transport, timeout=8, trust_env=False, follow_redirects=False)
    rpc = SolanaRPC(client, settings.solana_rpc, settings.rpc_rps, settings.rpc_concurrency)
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with previous(application):
                yield
        finally:
            await client.aclose()
    app.router.lifespan_context = lifespan

    def error(status, message, **headers):
        return HTTPException(status, message, headers={'Cache-Control': 'no-store', **headers})

    def require_admin(request, *, write=False):
        peer = request.client.host if request.client else 'unknown'
        action = 'plan' if write else 'config'
        try:
            app.state.store.throttle(digest('treasury:' + action + ':' + peer, settings.pepper), 12 if write else 20)
        except ValueError:
            raise error(429, 'Treasury review rate limit reached', **{'Retry-After': '60'}) from None
        if not settings.admin_key:
            raise error(503, 'Admin API is not configured')
        header = request.headers.get('authorization', '')
        key = header[7:] if header.startswith('Bearer ') else ''
        if not key or not key.isascii() or len(key) > 512 or not secrets.compare_digest(key, settings.admin_key):
            raise error(401, 'Invalid admin credential')
        if write and request.headers.get('origin') != settings.origin:
            raise error(403, 'Origin check failed')

    router = APIRouter()

    @router.get('/api/admin/treasury')
    async def configuration(request: Request):
        require_admin(request)
        return JSONResponse({'treasury_owner': treasury_owner or None,
            'mint': settings.holder_mint or None, 'decimals': settings.holder_token_decimals,
            'planning_enabled': bool(treasury_owner and settings.holder_mint and settings.solana_rpc),
            'signing_enabled': False, 'execution_enabled': False,
            'notice': 'Server prepares unsigned instructions only. No treasury balance is a deposit invitation.'},
            headers={'Cache-Control': 'no-store'})

    @router.post('/api/admin/treasury/burn-plan')
    async def burn_plan(body: BurnPlanInput, request: Request):
        require_admin(request, write=True)
        if not (treasury_owner and settings.holder_mint and settings.solana_rpc):
            raise error(503, 'Configure SOLANA_TREASURY_OWNER, the project mint and Solana RPC before preparing a burn')
        if body.confirm_project_owned is not True:
            raise error(422, 'Confirm these are project-owned tokens, not customer deposits')
        try:
            async with asyncio.timeout(20):
                plan = await prepare_burn_plan(rpc, mint=settings.holder_mint, source=body.source_account,
                    treasury_owner=treasury_owner, amount=body.amount, decimals=settings.holder_token_decimals)
        except ValueError:
            raise error(422, 'Unable to prepare a burn: verify the amount, configured mint and treasury owner, '
                'source balance, account state and supported token extensions. No transaction was sent.') from None
        except (httpx.HTTPError, TimeoutError):
            raise error(503, 'Solana evidence is unavailable. No transaction was sent; retry preparation after checking RPC health.') from None
        return JSONResponse(plan, headers={'Cache-Control': 'no-store'})

    index = next((i for i, route in enumerate(app.router.routes)
        if isinstance(route, Mount) and route.path in ('', '/')), len(app.router.routes))
    app.router.routes[index:index] = router.routes
