"""Offline binary fixtures. They do not prove mainnet signing or custody rights."""
import base64
from copy import deepcopy
from importlib import import_module, util
import struct

import pytest

from gridraft.security import ALPHABET, decode_address

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
SYSTEM = '11111111111111111111111111111111'
MAX = 2**64 - 1


def address(byte):
    raw = bytes([byte]) * 32
    n, out = int.from_bytes(raw, 'big'), ''
    while n:
        n, rem = divmod(n, 58)
        out = ALPHABET[rem] + out
    return out


MINT, SOURCE, OWNER, OTHER = [address(n) for n in (1, 2, 3, 4)]


def account(raw, program):
    return {'owner': program, 'executable': False, 'space': len(raw),
            'data': [base64.b64encode(raw).decode(), 'base64']}


def extension(raw, kind, rows):
    return raw + bytes(165-len(raw)) + bytes([kind]) + b''.join(
        struct.pack('<HH', tag, len(data)) + data for tag, data in rows)


def fixture(program=TOKEN, balance=10_000_000, supply=1_000_000_000, decimals=6):
    mint = bytearray(82)
    struct.pack_into('<Q', mint, 36, supply)
    mint[44:46] = bytes([decimals, 1])
    source = bytearray(165)
    source[:32] = decode_address(MINT)
    source[32:64] = decode_address(OWNER)
    struct.pack_into('<Q', source, 64, balance)
    source[108] = 1
    return {'context': {'slot': 500}, 'value': [account(mint, program),
        account(source, program), account(b'', SYSTEM)]}


def raw_edit(data, index, offset, value):
    raw = bytearray(base64.b64decode(data['value'][index]['data'][0]))
    raw[offset:offset+len(value)] = value
    data['value'][index] = account(raw, data['value'][index]['owner'])


def module():
    assert util.find_spec('gridraft.treasury_burn') is not None, 'Treasury burn planner is not implemented'
    return import_module('gridraft.treasury_burn')


def plan(data=None, amount='1.25', **kw):
    return module().build_burn_plan(data or fixture(), mint=MINT, source=SOURCE,
        treasury_owner=OWNER, decimals=6, amount=amount, **kw)


def test_encodes_one_unsigned_burn_checked_with_exact_account_roles():
    p = plan(now=1000)
    assert p['amount_raw'] == '1250000'
    assert p['source_balance_raw'] == '10000000'
    assert p['expected_source_remaining_raw'] == '8750000'
    assert p['expected_supply_after_burn_raw'] == '998750000'
    assert p['unsigned'] is True and p['transactions_sent'] == 0 and p['credits_issued'] == 0
    assert p['simulation_performed'] is False and p['local_review_expires_at'] == 1060
    assert p['instruction'] == {
        'program_id': TOKEN,
        'accounts': [
            {'pubkey': SOURCE, 'is_signer': False, 'is_writable': True},
            {'pubkey': MINT, 'is_signer': False, 'is_writable': True},
            {'pubkey': OWNER, 'is_signer': True, 'is_writable': False}],
        'data_base64': base64.b64encode(struct.pack('<BQB', 15, 1250000, 6)).decode()}
    assert 'signature' not in p and 'transaction' not in p
    assert 'custody' in ' '.join(p['warnings']).lower()


@pytest.mark.parametrize('amount,decimals,expected', [
    ('1', 0, 1), ('1.250000', 6, 1250000), ('0.000001', 6, 1),
    ('18446744073709.551615', 6, MAX), ('0.000000000000000001', 18, 1)])
def test_exact_decimal_conversion(amount, decimals, expected):
    assert module().amount_to_raw(amount, decimals) == expected


@pytest.mark.parametrize('amount', ['0', '-1', '+1', '01', ' 1', '1 ', '1e6', '.5', '1.',
    '1,000', 'NaN', 'Infinity', '0.0000001', '18446744073709.551616', '9'*100, 1.25, True, None])
def test_invalid_or_unrepresentable_amounts_fail(amount):
    with pytest.raises(ValueError):
        module().amount_to_raw(amount, 6)


@pytest.mark.parametrize('decimals', [True, -1, 19, 6.0, None])
def test_invalid_precision_fails(decimals):
    with pytest.raises(ValueError):
        module().amount_to_raw('1', decimals)


def test_balances_above_javascript_safe_integer_remain_strings():
    p = plan(fixture(balance=MAX, supply=MAX), amount='18446744073709.551615')
    assert p['amount_raw'] == str(MAX) and p['expected_source_remaining_raw'] == '0'


def test_token_2022_metadata_and_immutable_owner_are_supported():
    d = fixture(program=TOKEN_2022)
    mint = base64.b64decode(d['value'][0]['data'][0])
    token_metadata = bytes(32) + decode_address(MINT) + struct.pack('<IIII', 0, 0, 0, 0)
    d['value'][0] = account(extension(mint, 1, [(18, bytes(64)), (19, token_metadata)]), TOKEN_2022)
    source = base64.b64decode(d['value'][1]['data'][0])
    d['value'][1] = account(extension(source, 2, [(7, b'')]), TOKEN_2022)
    p = plan(d)
    assert p['instruction']['program_id'] == TOKEN_2022
    assert p['mint_extensions'] == ['metadataPointer', 'tokenMetadata']
    assert p['source_extensions'] == ['immutableOwner']


@pytest.mark.parametrize('index,tag', [(0, 1), (0, 12), (0, 14), (0, 28), (1, 11), (1, 999)])
def test_unreviewed_extensions_are_rejected(index, tag):
    d = fixture(program=TOKEN_2022)
    raw = base64.b64decode(d['value'][index]['data'][0])
    d['value'][index] = account(extension(raw, index+1, [(tag, bytes(64))]), TOKEN_2022)
    with pytest.raises(ValueError, match='extension'):
        plan(d)


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(value=[None, *d['value'][1:]]),
    lambda d: d.update(value=d['value'][:2]),
    lambda d: d.update(context={'slot': True}),
    lambda d: d['value'][0].update(owner=SYSTEM),
    lambda d: d['value'][1].update(owner=TOKEN_2022),
    lambda d: d['value'][0].update(executable=True),
    lambda d: d['value'][1].update(data=['not-base64', 'base64']),
    lambda d: d['value'][1].update(data=['', 'jsonParsed']),
    lambda d: d['value'][1].update(space=999),
    lambda d: d['value'][2].update(owner=TOKEN),
    lambda d: d['value'][2].update(data=['AA==', 'base64'], space=1),
    lambda d: raw_edit(d, 0, 44, bytes([9])),
    lambda d: raw_edit(d, 0, 45, bytes([0])),
    lambda d: raw_edit(d, 0, 0, struct.pack('<I', 2)),
    lambda d: raw_edit(d, 1, 0, decode_address(OTHER)),
    lambda d: raw_edit(d, 1, 32, decode_address(OTHER)),
    lambda d: raw_edit(d, 1, 108, bytes([2])),
    lambda d: raw_edit(d, 1, 109, struct.pack('<I', 1)),
    lambda d: raw_edit(d, 1, 72, struct.pack('<I', 1)),
    lambda d: raw_edit(d, 1, 121, struct.pack('<Q', 1)),
    lambda d: raw_edit(d, 1, 129, struct.pack('<I', 2)),
])
def test_malformed_or_ineligible_snapshots_fail_closed(mutation):
    d = fixture()
    mutation(d)
    with pytest.raises(ValueError):
        plan(d)


@pytest.mark.parametrize('amount', ['10.000001', '1000'])
def test_cannot_plan_above_balance(amount):
    with pytest.raises(ValueError, match='balance'):
        plan(amount=amount)


def test_rejects_inconsistent_supply_and_source_balance():
    with pytest.raises(ValueError, match='supply'):
        plan(fixture(supply=100))


def test_mint_authority_is_disclosed_without_promising_deflation():
    d = fixture()
    raw_edit(d, 0, 0, struct.pack('<I', 1) + decode_address(OTHER))
    p = plan(d)
    assert p['mint_authority_present'] is True
    assert 'mint' in ' '.join(p['warnings']).lower()


@pytest.mark.parametrize('tail', [b'\x12\x00\x40', struct.pack('<HH', 18, 64)+bytes(63),
    struct.pack('<HH', 18, 64)+bytes(64)+struct.pack('<HH', 18, 64)+bytes(64),
    struct.pack('<HH', 0, 0)+b'\x01'])
def test_malformed_extension_tlv_rejected(tail):
    d = fixture(program=TOKEN_2022)
    mint = base64.b64decode(d['value'][0]['data'][0])
    d['value'][0] = account(mint + bytes(83) + b'\x01' + tail, TOKEN_2022)
    with pytest.raises(ValueError):
        plan(d)


def test_inputs_are_not_mutated():
    d = fixture(); before = deepcopy(d)
    plan(d)
    assert d == before
