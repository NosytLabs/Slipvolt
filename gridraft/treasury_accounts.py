"""Discover the configured treasury's token accounts without spending permissions.

A listing is a dated balance observation, not proof of lawful custody or a burn
approval. Preparation always repeats the existing same-snapshot burn checks.
"""
from .security import decode_address
from .treasury_burn import TOKEN, TOKEN_2022, SYSTEM, _data, _extensions, _option

MAX_ACCOUNTS = 128
MAX_SLOT = 2**53 - 1


def _configuration(mint, treasury_owner, decimals):
    mint_bytes, owner_bytes = decode_address(mint), decode_address(treasury_owner)
    if mint == treasury_owner or treasury_owner == SYSTEM:
        raise ValueError('Treasury authority and mint must be distinct')
    if type(decimals) is not int or not 0 <= decimals <= 18:
        raise ValueError('Unsupported token precision')
    return mint_bytes, owner_bytes


def _slot(result):
    context = result.get('context') if isinstance(result, dict) else None
    slot = context.get('slot') if isinstance(context, dict) else None
    if type(slot) is not int or not 0 < slot <= MAX_SLOT:
        raise ValueError('Invalid finalized snapshot slot')
    return slot


def _rows(listing):
    slot = _slot(listing)
    rows = listing.get('value')
    if not isinstance(rows, list) or len(rows) > MAX_ACCOUNTS:
        raise ValueError('Token account listing exceeds supported bounds or is incomplete')
    return slot, rows


def parse_treasury_accounts(listing, reference, *, mint, treasury_owner, decimals):
    mint_bytes, owner_bytes = _configuration(mint, treasury_owner, decimals)
    listing_slot, rows = _rows(listing)
    reference_slot = _slot(reference)
    values = reference.get('value')
    if reference_slot < listing_slot or not isinstance(values, list) or len(values) != 2:
        raise ValueError('Mint and treasury reference must follow the account listing')
    program = values[0].get('owner') if isinstance(values[0], dict) else None
    if program not in (TOKEN, TOKEN_2022):
        raise ValueError('Unsupported mint program')
    mint_data = _data(values[0], program)
    if _data(values[1], SYSTEM) != b'':
        raise ValueError('Unsupported treasury authority account')
    if len(mint_data) < 82 or mint_data[44] != decimals or mint_data[45] != 1:
        raise ValueError('Invalid or mismatched mint')
    _extensions(mint_data, 82, 1, program, mint_bytes)
    _option(mint_data, 0); _option(mint_data, 46)
    supply = int.from_bytes(mint_data[36:44], 'little')
    result, seen, total = [], set(), 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid token account entry')
        address = row.get('pubkey')
        decode_address(address)
        if address in seen or address in (mint, treasury_owner):
            raise ValueError('Duplicate or inconsistent token account address')
        seen.add(address)
        data = _data(row.get('account'), program)
        if len(data) < 165 or data[:32] != mint_bytes or data[32:64] != owner_bytes:
            raise ValueError('Token account does not match the configured treasury and mint')
        state = data[108]
        if state not in (1, 2):
            raise ValueError('Invalid token account state')
        delegated, native, close = _option(data, 72), _option(data, 109), _option(data, 129)
        balance = int.from_bytes(data[64:72], 'little')
        total += balance
        if total > supply:
            raise ValueError('Account balances exceed the observed mint supply; refresh the listing')
        reason = None
        try:
            _extensions(data, 165, 2, program, mint_bytes)
        except ValueError:
            reason = 'unsupported_extension'
        if state == 2:
            reason = 'frozen'
        elif native:
            reason = 'native'
        elif delegated or int.from_bytes(data[121:129], 'little'):
            reason = 'delegated'
        elif close and data[133:165] != owner_bytes:
            reason = 'close_authority'
        elif not balance and reason is None:
            reason = 'empty'
        result.append({'address': address, 'balance_raw': str(balance),
            'review_eligible': reason is None, 'reason': reason})
    result.sort(key=lambda row: (not row['review_eligible'], -int(row['balance_raw']), row['address']))
    return {'schema': 'holdbyte.treasury-accounts.v1', 'treasury_owner': treasury_owner,
        'mint': mint, 'token_program': program, 'decimals': decimals,
        'listing_slot': listing_slot, 'reference_slot': reference_slot,
        'accounts': result, 'total_raw': str(total), 'execution_enabled': False,
        'transactions_sent': 0,
        'notice': 'Observed balances, not revenue or custody proof. Burn preparation rechecks a fresh snapshot.'}


async def discover_treasury_accounts(rpc, *, mint, treasury_owner, decimals):
    _configuration(mint, treasury_owner, decimals)
    await rpc.ensure_mainnet()
    listing = await rpc.call('getTokenAccountsByOwner', [treasury_owner, {'mint': mint},
        {'encoding': 'base64', 'commitment': 'finalized'}])
    slot, _ = _rows(listing)
    reference = await rpc.call('getMultipleAccounts', [[mint, treasury_owner],
        {'encoding': 'base64', 'commitment': 'finalized', 'minContextSlot': slot}])
    return parse_treasury_accounts(listing, reference, mint=mint,
        treasury_owner=treasury_owner, decimals=decimals)
