"""Operator-only unsigned burn preparation; no keys, custody or broadcast RPC."""
import asyncio

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .integrations import SolanaRPC
from .security import decode_address
from .route_support import (api_error, authenticate_admin, close_client_with_app,
                            register_api_routes, throttle_request)
from .treasury_burn import prepare_burn_plan
from .treasury_accounts import discover_treasury_accounts


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
    close_client_with_app(app, client)

    def require_admin(request, *, write=False):
        action = 'plan' if write else 'config'
        throttle_request(request, app.state.store, settings.pepper, bucket='treasury:' + action,
                         limit=12 if write else 20, message='Treasury review rate limit reached')
        authenticate_admin(request, settings, require_origin=write)

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

    @router.get('/api/admin/treasury/accounts')
    async def treasury_accounts(request: Request):
        require_admin(request)
        if not (treasury_owner and settings.holder_mint and settings.solana_rpc):
            raise api_error(503, 'Configure the treasury authority, project mint and Solana RPC before loading accounts')
        try:
            async with asyncio.timeout(20):
                result = await discover_treasury_accounts(rpc, mint=settings.holder_mint,
                    treasury_owner=treasury_owner, decimals=settings.holder_token_decimals)
        except (ValueError, httpx.HTTPError, TimeoutError):
            raise api_error(503, 'Treasury account discovery is unavailable. Check RPC health, mint configuration and supported account layouts. No transaction was sent.') from None
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @router.post('/api/admin/treasury/burn-plan')
    async def burn_plan(body: BurnPlanInput, request: Request):
        require_admin(request, write=True)
        if not (treasury_owner and settings.holder_mint and settings.solana_rpc):
            raise api_error(503, 'Configure SOLANA_TREASURY_OWNER, the project mint and Solana RPC before preparing a burn')
        if body.confirm_project_owned is not True:
            raise api_error(422, 'Confirm these are project-owned tokens, not customer deposits')
        try:
            async with asyncio.timeout(20):
                plan = await prepare_burn_plan(rpc, mint=settings.holder_mint, source=body.source_account,
                    treasury_owner=treasury_owner, amount=body.amount, decimals=settings.holder_token_decimals)
        except ValueError:
            raise api_error(422, 'Unable to prepare a burn: verify the amount, configured mint and treasury owner, '
                'source balance, account state and supported token extensions. No transaction was sent.') from None
        except (httpx.HTTPError, TimeoutError):
            raise api_error(503, 'Solana evidence is unavailable. No transaction was sent; retry preparation after checking RPC health.') from None
        return JSONResponse(plan, headers={'Cache-Control': 'no-store'})

    register_api_routes(app, router)
