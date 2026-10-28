"""Preliminary read-only mint screening; not a vault audit or launch approval."""
from .security import decode_address
from .treasury_burn import TOKEN, TOKEN_2022, _data, _extensions, _option


def _inputs(mint, decimals):
    mint_bytes = decode_address(mint)
    if type(decimals) is not int or not 0 <= decimals <= 18:
        raise ValueError('Invalid mint precision')
    return mint_bytes


def inspect_mint(result, *, mint, decimals):
    mint_bytes = _inputs(mint, decimals)
    if not isinstance(result, dict) or not isinstance(result.get('context'), dict):
        raise ValueError('Invalid finalized mint snapshot')
    slot = result['context'].get('slot')
    if type(slot) is not int or not 0 < slot <= 2**53-1:
        raise ValueError('Invalid finalized mint slot')
    value = result.get('value')
    program = value.get('owner') if isinstance(value, dict) else None
    if program not in (TOKEN, TOKEN_2022):
        raise ValueError('Unsupported mint program')
    raw = _data(value, program)
    if len(raw) < 82 or raw[44] != decimals or raw[45] != 1:
        raise ValueError('Mint precision or initialization mismatch')
    extensions = _extensions(raw, 82, 1, program, mint_bytes)
    mint_authority, freeze_authority = _option(raw, 0), _option(raw, 46)
    return {'status': 'blocked' if freeze_authority else 'review_required',
        'mint': mint, 'token_program': program, 'decimals': decimals,
        'supply_raw': str(int.from_bytes(raw[36:44], 'little')), 'snapshot_slot': slot,
        'mint_authority_present': mint_authority, 'freeze_authority_present': freeze_authority,
        'observed_extensions': extensions, 'vault_implemented': False,
        'deployment_approved': False, 'transactions_sent': 0,
        'notice': 'Preliminary mint screening only. It does not verify a vault, custody, token accounts, program upgrades, or future mint state. Independent review and local validator tests remain required.'}


async def inspect_configured_mint(rpc, *, mint, decimals):
    _inputs(mint, decimals)
    await rpc.ensure_mainnet()
    result = await rpc.call('getAccountInfo', [mint, {'encoding': 'base64', 'commitment': 'finalized'}])
    return inspect_mint(result, mint=mint, decimals=decimals)
