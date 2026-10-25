"""Optional read-only token evidence routes for the production ASGI entry point."""
import asyncio
import sqlite3
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .integrations import SolanaRPC
from .route_support import (api_error, authenticate_admin, close_client_with_app,
                            register_api_routes, throttle_request)
from .token_audit import BurnLedger, TokenAuditor


class BurnSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signature: str = Field(min_length=64, max_length=88, strict=True)


def install_token_audit_routes(app, settings, *, transport=None):
    """Register before StaticFiles; no signing keys or public write permissions."""
    if getattr(app.state, 'token_audit_installed', False):
        raise ValueError('Token evidence routes are already installed')
    app.state.token_audit_installed = True
    store = app.state.store
    ledger = BurnLedger(store.db)
    client = httpx.AsyncClient(transport=transport, timeout=8, trust_env=False, follow_redirects=False)
    rpc = SolanaRPC(client, settings.solana_rpc, settings.rpc_rps, settings.rpc_concurrency)
    auditor = TokenAuditor(rpc, settings.holder_mint, settings.holder_token_decimals) if settings.holder_mint else None
    cache = {'at': None, 'value': None}
    lock = asyncio.Lock()
    close_client_with_app(app, client)

    def throttle(request, action, limit):
        throttle_request(request, store, settings.pepper, bucket='token-audit:' + action,
                         limit=limit, message='Token evidence rate limit reached')

    def require_admin(request):
        throttle(request, 'admin', 12)
        authenticate_admin(request, settings)

    router = APIRouter()

    @router.get('/api/token')
    async def token_evidence(request: Request):
        throttle(request, 'public', 60)
        if not auditor:
            data = {'status': 'unconfigured', 'mint': None, 'mint_state': None,
                'burns': None, 'checked_at': None}
        else:
            async with lock:
                now = time.monotonic()
                if cache['at'] is None or not 0 <= now - cache['at'] < 20:
                    value = {'status': 'unavailable', 'mint': settings.holder_mint,
                        'mint_state': None, 'checked_at': int(time.time())}
                    try:
                        async with asyncio.timeout(20):
                            snapshot = await auditor.snapshot()
                        value.update(status='available', mint_state=snapshot)
                    except Exception:
                        # Never expose credentialed endpoint URLs or upstream errors.
                        pass
                    cache.update(at=time.monotonic(), value=value)
                data = {**cache['value'], 'burns': ledger.summary(settings.holder_mint)}
        return JSONResponse({**data, 'token_symbol': settings.holder_token_symbol,
            'configured_decimals': settings.holder_token_decimals,
            'source': 'Operator-configured Solana mainnet RPC; finalized reads',
            'execution_enabled': False,
            'notice': 'Burn totals cover recorded receipts only, not all historical burns, net supply change, treasury income or user deposits.'},
            headers={'Cache-Control': 'no-store'})

    @router.post('/api/admin/token/burns')
    async def record_burn(body: BurnSubmission, request: Request):
        require_admin(request)
        if not auditor or not settings.solana_rpc:
            raise api_error(503, 'Token mint and RPC must be configured')
        try:
            async with asyncio.timeout(35):
                receipt = await auditor.verify(body.signature)
            recorded = ledger.record(receipt)
        except ValueError:
            raise api_error(422, 'Could not verify a successful finalized burn of the configured mint. No receipt was recorded.') from None
        except (httpx.HTTPError, TimeoutError, sqlite3.Error):
            raise api_error(503, 'Token evidence is unavailable. No transaction was sent; check recorded receipts before retrying.') from None
        cache['at'] = None
        return JSONResponse({'recorded': recorded, 'receipt': receipt,
            'transactions_sent': 0, 'credits_issued': 0}, headers={'Cache-Control': 'no-store'})

    register_api_routes(app, router)
