"""Prepare one unsigned treasury BurnChecked instruction. Never sign or broadcast.

Binary layouts and tags follow solana-program/token and token-2022 interfaces.
Only plain tokens and reviewed metadata/immutable-owner extensions are supported.
Authority ownership is not proof that assets are legally project-owned: the
operator must separately exclude user deposits and obtain signer approval.
"""
import base64
import re
import struct
import time

from .integrations import MAINNET_GENESIS
from .security import decode_address

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
SYSTEM = '11111111111111111111111111111111'
U64_MAX = 2**64 - 1
MAX_ACCOUNT_BYTES = 8192
REVIEW_SECONDS = 60


def amount_to_raw(amount, decimals):
    """Parse token units without float/Decimal rounding or scientific notation."""
    if type(decimals) is not int or not 0 <= decimals <= 18:
        raise ValueError('Unsupported token precision')
    if not isinstance(amount, str) or len(amount) > 40 or not re.fullmatch(
            r'(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?', amount):
        raise ValueError('Use a plain positive decimal token amount')
    whole, _, fraction = amount.partition('.')
    if len(fraction) > decimals:
        raise ValueError('Amount exceeds token precision')
    raw = int(whole) * 10**decimals + int(fraction.ljust(decimals, '0') or '0')
    if not 0 < raw <= U64_MAX:
        raise ValueError('Token amount is outside the u64 range')
    return raw


def _data(account, owner):
    if (not isinstance(account, dict) or account.get('owner') != owner
            or account.get('executable') is not False):
        raise ValueError('Missing account or unexpected account program')
    encoded = account.get('data')
    if (not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != 'base64'
            or not isinstance(encoded[0], str) or len(encoded[0]) > 4*((MAX_ACCOUNT_BYTES+2)//3)):
        raise ValueError('Unsupported account data encoding or size')
    try:
        raw = base64.b64decode(encoded[0], validate=True)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid binary account data') from None
    if (len(raw) > MAX_ACCOUNT_BYTES or type(account.get('space')) is not int
            or account['space'] != len(raw)):
        raise ValueError('Account data length does not match its space')
    return raw


def _option(raw, offset):
    tag = int.from_bytes(raw[offset:offset+4], 'little')
    if tag not in (0, 1):
        raise ValueError('Invalid optional authority field')
    return bool(tag)


def _metadata(data, mint):
    # TokenMetadata = update authority, mint, three Borsh strings, key/value vector.
    if len(data) < 80 or data[32:64] != mint:
        raise ValueError('Invalid token metadata extension')
    cursor = 64

    def string():
        nonlocal cursor
        if cursor+4 > len(data):
            raise ValueError('Truncated token metadata extension')
        length = int.from_bytes(data[cursor:cursor+4], 'little'); cursor += 4
        if cursor+length > len(data):
            raise ValueError('Truncated token metadata extension')
        try:
            data[cursor:cursor+length].decode('utf-8')
        except UnicodeError:
            raise ValueError('Invalid token metadata text') from None
        cursor += length
    for _ in range(3):
        string()
    if cursor+4 > len(data):
        raise ValueError('Truncated token metadata extension')
    count = int.from_bytes(data[cursor:cursor+4], 'little'); cursor += 4
    if count > 64:
        raise ValueError('Token metadata extension exceeds reviewed bounds')
    for _ in range(count):
        string(); string()
    if cursor != len(data):
        raise ValueError('Unexpected token metadata extension bytes')


def _extensions(raw, base, kind, program, mint):
    if len(raw) == base:
        return []
    if program != TOKEN_2022 or len(raw) < 166 or len(raw) == 355:
        raise ValueError('Unsupported extension layout')
    if any(raw[base:165]) or raw[165] != kind:
        raise ValueError('Invalid extension account type or padding')
    allowed = {18: ('metadataPointer', 64), 19: ('tokenMetadata', None)} if kind == 1 else {7: ('immutableOwner', 0)}
    cursor, seen, names = 166, set(), []
    while cursor < len(raw):
        if not any(raw[cursor:]):  # Unallocated zero padding is not an extension.
            break
        if cursor+4 > len(raw):
            raise ValueError('Truncated extension header')
        tag, length = struct.unpack_from('<HH', raw, cursor); cursor += 4
        if tag not in allowed or tag in seen or cursor+length > len(raw):
            raise ValueError('Unreviewed, duplicate or truncated token extension')
        name, size = allowed[tag]
        if size is not None and length != size:
            raise ValueError('Invalid token extension length')
        if tag == 19:
            _metadata(raw[cursor:cursor+length], mint)
        names.append(name); seen.add(tag); cursor += length
    return names


def _inputs(mint, source, treasury_owner, amount, decimals):
    addresses = [decode_address(value) for value in (mint, source, treasury_owner)]
    if len(set(addresses)) != 3 or treasury_owner == SYSTEM:
        raise ValueError('Mint, source and treasury authority must be distinct')
    return addresses, amount_to_raw(amount, decimals)


def build_burn_plan(result, *, mint, source, treasury_owner, amount, decimals, now=None):
    """Validate a same-slot finalized snapshot; return an instruction, NOT a tx."""
    addresses, raw_amount = _inputs(mint, source, treasury_owner, amount, decimals)
    if not isinstance(result, dict) or not isinstance(result.get('context'), dict):
        raise ValueError('Missing account snapshot')
    slot, values = result['context'].get('slot'), result.get('value')
    if type(slot) is not int or not 0 < slot <= 2**53-1 or not isinstance(values, list) or len(values) != 3:
        raise ValueError('Invalid snapshot slot or account list')
    program = values[0].get('owner') if isinstance(values[0], dict) else None
    if program not in (TOKEN, TOKEN_2022):
        raise ValueError('Unsupported mint program')
    mint_data, source_data = _data(values[0], program), _data(values[1], program)
    if _data(values[2], SYSTEM) != b'':
        raise ValueError('Treasury must be a system-owned wallet or vault authority; SPL multisig is unsupported')
    if len(mint_data) < 82 or len(source_data) < 165:
        raise ValueError('Truncated mint or source account')
    mint_extensions = _extensions(mint_data, 82, 1, program, addresses[0])
    source_extensions = _extensions(source_data, 165, 2, program, addresses[0])
    if mint_data[44] != decimals or mint_data[45] != 1:
        raise ValueError('Mint precision or initialization does not match configuration')
    mint_authority, freeze_authority = _option(mint_data, 0), _option(mint_data, 46)
    if source_data[:32] != addresses[0] or source_data[32:64] != addresses[2]:
        raise ValueError('Source must contain the configured mint and be owned by the configured treasury')
    if source_data[108] != 1 or _option(source_data, 109):
        raise ValueError('Source must be initialized, unfrozen and non-native')
    if _option(source_data, 72) or int.from_bytes(source_data[121:129], 'little'):
        raise ValueError('Delegated source accounts are not supported')
    if _option(source_data, 129) and source_data[133:165] != addresses[2]:
        raise ValueError('Source has an unrelated close authority')
    supply = int.from_bytes(mint_data[36:44], 'little')
    balance = int.from_bytes(source_data[64:72], 'little')
    if balance > supply:
        raise ValueError('Source balance exceeds mint supply')
    if raw_amount > balance:
        raise ValueError('Burn amount exceeds the observed treasury token balance')
    timestamp = int(time.time()) if now is None else now
    if type(timestamp) is not int or not 0 <= timestamp <= 2**53-1-REVIEW_SECONDS:
        raise ValueError('Invalid review timestamp')
    warnings = [
        'Unsigned instruction only. Assemble and simulate a complete transaction in an approved wallet or multisig before signing.',
        'Treasury authority ownership does not prove legal custody or project ownership; exclude customer deposits.',
        'The local review expiry is advisory, not an on-chain expiry or replay protection. Refresh state before signing.',
        'A burn is irreversible if executed. No buyback, swap, fee collection or AI credit is included.',
        'A PDA treasury requires its authorized vault executor; this is not a directly signable transaction.',
    ]
    if mint_authority:
        warnings.append('Mint authority remains set: new issuance can offset burns. Net deflation is not established.')
    if freeze_authority:
        warnings.append('Freeze authority remains set: the source can be frozen after this snapshot.')
    return {'schema': 'holdbyte.burn-instruction.v1', 'genesis_hash': MAINNET_GENESIS,
        'mint': mint, 'source_account': source, 'treasury_owner': treasury_owner,
        'token_program': program, 'decimals': decimals, 'amount_raw': str(raw_amount),
        'source_balance_raw': str(balance), 'expected_source_remaining_raw': str(balance-raw_amount),
        'observed_supply_raw': str(supply), 'expected_supply_after_burn_raw': str(supply-raw_amount),
        'mint_authority_present': mint_authority, 'freeze_authority_present': freeze_authority,
        'mint_extensions': mint_extensions, 'source_extensions': source_extensions,
        'snapshot_slot': slot, 'created_at': timestamp, 'local_review_expires_at': timestamp+REVIEW_SECONDS,
        'unsigned': True, 'simulation_performed': False, 'transactions_sent': 0, 'credits_issued': 0,
        'instruction': {'program_id': program, 'accounts': [
            {'pubkey': source, 'is_signer': False, 'is_writable': True},
            {'pubkey': mint, 'is_signer': False, 'is_writable': True},
            {'pubkey': treasury_owner, 'is_signer': True, 'is_writable': False}],
            'data_base64': base64.b64encode(struct.pack('<BQB', 15, raw_amount, decimals)).decode('ascii')},
        'warnings': warnings}


async def prepare_burn_plan(rpc, *, mint, source, treasury_owner, amount, decimals):
    _inputs(mint, source, treasury_owner, amount, decimals)  # Reject invalid requests before RPC.
    await rpc.ensure_mainnet()
    result = await rpc.call('getMultipleAccounts', [[mint, source, treasury_owner],
        {'encoding': 'base64', 'commitment': 'finalized'}])
    return build_burn_plan(result, mint=mint, source=source, treasury_owner=treasury_owner,
        amount=amount, decimals=decimals)
