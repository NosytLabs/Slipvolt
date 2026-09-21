"""Keyless, read-only Gonka RPC. No signing, broadcasts, swaps or inference.

Gateway reports are not light-client proofs. Native balances are display data,
not spendable OpenBroker credit or permission to allocate customer compute.
"""
import asyncio
import json
import re
import time
from datetime import datetime

import httpx
from .broker import quantity

BASE = 'https://rpc.gonka.gg'
CHAIN_ID = 'gonka-mainnet'
BANK = BASE + '/chain-api/cosmos/bank/v1beta1/balances/'
CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
STATUS_TTL = 15
BALANCE_TTL = 30
FAILURE_TTL = 10
MAX_BLOCK_AGE = 180


def validate_address(address):
    """Validate a 20-byte Gonka Bech32 account; reject URI injection."""
    if not isinstance(address, str) or len(address) != 44 or not address.startswith('gonka1'):
        raise ValueError('Invalid Gonka address')
    try:
        data = [CHARSET.index(c) for c in address[6:]]
    except ValueError:
        raise ValueError('Invalid Gonka address') from None
    values = [ord(c) >> 5 for c in 'gonka'] + [0] + [ord(c) & 31 for c in 'gonka'] + data
    chk = 1
    generators = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i, g in enumerate(generators):
            if (top >> i) & 1:
                chk ^= g
    if chk != 1:
        raise ValueError('Invalid Gonka address checksum')
    return address


class RPCError(ValueError):
    """Only fixed, non-sensitive error codes cross the provider boundary."""
    def __init__(self, code='unavailable'):
        self.code = code
        super().__init__(f'Gonka RPC check failed ({code})')


def _fresh(block_time):
    try:
        if not isinstance(block_time, str) or len(block_time) > 64:
            raise ValueError()
        stamp = datetime.fromisoformat(block_time.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError()
        age = time.time() - stamp.timestamp()
    except (ValueError, OverflowError):
        raise RPCError('invalid_response') from None
    if age < -30:
        raise RPCError('clock_skew')
    if age > MAX_BLOCK_AGE:
        raise RPCError('stale')


class GonkaRPC:
    """Fixed public origin and a deliberately small GET-only surface.

    Discovery catalogs are documentation, never executable routing rules.
    Reuses the supplied client's transport without inheriting auth/cookies.
    The owner of the supplied AsyncClient remains responsible for closing it.
    """
    def __init__(self, client):
        self.client = client
        self._status = None
        self._status_at = None
        self._status_error = None
        self._observed_at = None
        self._lock = asyncio.Lock()

    async def read(self, path, params=None, max_bytes=2_000_000):
        if path in ('/chain-rpc/status', '/v1/models'):
            if params:
                raise RPCError('unsupported_route')
        else:
            prefix = '/chain-api/cosmos/bank/v1beta1/balances/'
            if not path.startswith(prefix) or not path.endswith('/by_denom'):
                raise RPCError('unsupported_route')
            validate_address(path[len(prefix):-len('/by_denom')])
            if params != {'denom': 'ngonka'}:
                raise RPCError('unsupported_route')
        if type(max_bytes) is not int or not 1 <= max_bytes <= 2_000_000:
            raise RPCError('invalid_response_limit')
        # Request (not build_request/stream) avoids merging client-level secrets,
        # cookies or query parameters. Explicit auth=None also disables client auth.
        request = httpx.Request('GET', BASE + path, params=params,
            headers={'Accept': 'application/json'},
            extensions={'timeout': dict(connect=8, read=8, write=8, pool=8)})
        try:
            async with asyncio.timeout(8):
                response = await self.client.send(request, stream=True, auth=None, follow_redirects=False)
                try:
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise RPCError('response_too_large')
                        chunks.append(chunk)
                    value = json.loads(b''.join(chunks))
                    if not isinstance(value, dict):
                        raise RPCError('invalid_response')
                    return value
                finally:
                    await response.aclose()
        except RPCError:
            raise
        except Exception:
            raise RPCError() from None

    async def status(self):
        async with self._lock:
            now = time.monotonic()
            ttl = FAILURE_TTL if self._status_error else STATUS_TTL
            if self._status_at is not None and 0 <= now - self._status_at < ttl:
                if self._status_error:
                    raise RPCError(self._status_error)
                _fresh(self._status['latest_block_time'])
                return dict(self._status, cached=True)
            self._status = None
            try:
                data = await self.read('/chain-rpc/status', max_bytes=16384)
                if data.get('error') is not None or data.get('jsonrpc') != '2.0':
                    raise RPCError('invalid_response')
                result = data['result']
                if result['node_info']['network'] != CHAIN_ID:
                    raise RPCError('wrong_network')
                sync = result['sync_info']
                if type(sync['catching_up']) is not bool:
                    raise RPCError('invalid_response')
                if sync['catching_up']:
                    raise RPCError('syncing')
                height, block_hash = sync['latest_block_height'], sync['latest_block_hash']
                if not isinstance(height, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', height):
                    raise RPCError('invalid_response')
                if not isinstance(block_hash, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', block_hash):
                    raise RPCError('invalid_response')
                _fresh(sync['latest_block_time'])
                self._status = {'chain_id': CHAIN_ID, 'latest_block_height': height,
                    'latest_block_time': sync['latest_block_time'], 'catching_up': False,
                    'observed_at': int(time.time()), 'source': BASE + '/chain-rpc/status',
                    'verification': 'Gateway report; not a light-client proof'}
                self._status_error = None
            except Exception as exc:
                self._status_error = exc.code if isinstance(exc, RPCError) else 'invalid_response'
                raise RPCError(self._status_error) from None
            finally:
                self._status_at = time.monotonic()
                self._observed_at = int(time.time())
            return dict(self._status, cached=False)

    async def diagnostics(self):
        try:
            return {**await self.status(), 'status': 'ready', 'ready': True, 'transactions_sent': 0}
        except RPCError as exc:
            return {'status': exc.code, 'ready': False, 'observed_at': self._observed_at,
                'source': BASE + '/chain-rpc/status', 'transactions_sent': 0,
                'message': 'Check Gonka gateway connectivity, network, sync status and server clock.'}

    async def models(self):
        await self.status()
        data = await self.read('/v1/models')
        rows = data.get('data')
        if not isinstance(rows, list) or not rows or len(rows) > 1000:
            raise RPCError('invalid_response')
        clean, seen = [], set()
        for row in rows:
            mid = row.get('id') if isinstance(row, dict) else None
            if not isinstance(mid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:+-]{0,149}', mid) or mid in seen:
                raise RPCError('invalid_response')
            seen.add(mid)
            def limit(value):
                return value if type(value) is int and 0 < value <= 10**7 else None
            # The live gateway can return 0 and uses max_output_length. Zero is
            # unknown, never unlimited and never permission to increase policy.
            outputs = [n for n in (limit(row.get('max_completion_tokens')),
                                  limit(row.get('max_output_length'))) if n is not None]
            clean.append({'id': mid, 'context_length': limit(row.get('context_length')),
                          'max_completion_tokens': min(outputs) if outputs else None})
        return {'data': clean, 'source': BASE + '/v1/models', 'observed_at': int(time.time()),
                'inference_verified': False, 'scope': 'Gonka catalog; not OpenBroker account availability'}


class NativeTreasury:
    def __init__(self, client, address='', rpc=None):
        self.client, self.address = client, address
        if address:
            validate_address(address)
        self.rpc = rpc or GonkaRPC(client)
        self.cached, self.at, self.error_code = None, None, None
        self.lock = asyncio.Lock()

    async def balance(self):
        if not self.address:
            return None
        async with self.lock:
            now = time.monotonic()
            if self.at is not None and 0 <= now - self.at < FAILURE_TTL and self.error_code:
                raise RPCError(self.error_code)
            try:
                status = await self.rpc.status()
                if self.cached is not None and self.at is not None and 0 <= now - self.at < BALANCE_TTL:
                    return dict(self.cached)
                path = '/chain-api/cosmos/bank/v1beta1/balances/' + self.address + '/by_denom'
                value = await self.rpc.read(path, params={'denom': 'ngonka'}, max_bytes=8192)
                balance = value['balance']
                if balance['denom'] != 'ngonka':
                    raise RPCError('wrong_denomination')
                amount = quantity(balance['amount'])
                self.cached = {'address': self.address, 'amount_ngonka': amount,
                    'observed_at': int(time.time()), 'source': BANK + self.address + '/by_denom?denom=ngonka',
                    'chain_id': CHAIN_ID, 'rpc_block_height': status['latest_block_height'],
                    'rpc_observed_at': status['observed_at'],
                    'scope': 'Configured self-custody wallet; not broker credit or a spendable-balance proof'}
                self.error_code = None
            except Exception as exc:
                self.cached = None
                self.error_code = exc.code if isinstance(exc, RPCError) else 'invalid_response'
                self.at = time.monotonic()
                raise RPCError(self.error_code) from None
            self.at = time.monotonic()
            return dict(self.cached)
