"""Operator-only creator-vault claim evidence; never signs or credits funds."""
import asyncio
import sqlite3

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .creator_claims import CreatorClaimAuditor, CreatorClaimLedger, SYSTEM
from .integrations import SolanaRPC
from .route_support import (api_error, authenticate_admin, close_client_with_app,
                            register_api_routes, throttle_request)
from .security import decode_address


class CreatorClaimInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signature: str = Field(strict=True, min_length=64, max_length=88)


def install_creator_claim_routes(app, settings, *, treasury_owner='', transport=None):
    if getattr(app.state, 'creator_claim_routes_installed', False):
        raise ValueError('Creator claim routes are already installed')
    if treasury_owner:
        decode_address(treasury_owner)
    app.state.creator_claim_routes_installed = True
    ledger = CreatorClaimLedger(app.state.store)
    client = httpx.AsyncClient(transport=transport, timeout=8, trust_env=False, follow_redirects=False)
    rpc = SolanaRPC(client, settings.solana_rpc, settings.rpc_rps, settings.rpc_concurrency)
    auditor = CreatorClaimAuditor(rpc, treasury_owner) if treasury_owner and treasury_owner != SYSTEM else None
    close_client_with_app(app, client)

    def require_admin(request, *, write=False):
        throttle_request(request, app.state.store, settings.pepper,
            bucket='creator-claims:write' if write else 'creator-claims:read',
            limit=12 if write else 20, message='Creator claim evidence rate limit reached')
        authenticate_admin(request, settings, require_origin=write)

    router = APIRouter()

    @router.get('/api/admin/treasury/creator-claims')
    async def list_claims(request: Request):
        require_admin(request)
        if not auditor:
            raise api_error(503, 'Configure the public treasury owner before reviewing creator claims')
        try:
            report = ledger.summary(treasury_owner)
        except (ValueError, sqlite3.Error):
            raise api_error(503, 'Creator claim evidence is unavailable') from None
        return JSONResponse(report, headers={'Cache-Control': 'no-store'})

    @router.post('/api/admin/treasury/creator-claims')
    async def record_claim(body: CreatorClaimInput, request: Request):
        require_admin(request, write=True)
        if not auditor or not settings.solana_rpc:
            raise api_error(503, 'Configure the public treasury owner and Solana RPC before verifying creator claims')
        try:
            async with asyncio.timeout(35):
                receipt = await auditor.verify(body.signature)
            recorded = ledger.record(receipt)
        except ValueError:
            raise api_error(422, 'Could not verify an unambiguous finalized Pump SOL creator claim. No receipt was recorded.') from None
        except (httpx.HTTPError, TimeoutError, sqlite3.Error):
            raise api_error(503, 'Creator claim evidence is unavailable. No transaction was sent; check recorded receipts before retrying.') from None
        return JSONResponse({'recorded': recorded, 'receipt': receipt,
            'transactions_sent': 0, 'credits_issued': 0}, headers={'Cache-Control': 'no-store'})

    register_api_routes(app, router)
