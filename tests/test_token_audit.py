"""Offline evidence tests. Fixtures are not live burn transactions."""
import asyncio
import copy
import importlib
import importlib.util
import json
import sqlite3

import httpx
import pytest

from gridraft.integrations import MAINNET_GENESIS, SolanaRPC

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'
MINT = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
OWNER = '11111111111111111111111111111111'
ACCOUNT = 'So11111111111111111111111111111111111111112'
SIGNATURE = '1' * 64  # Exactly 64 decoded bytes; fixture only.


def module():
    assert importlib.util.find_spec('gridraft.token_audit') is not None, 'Burn receipt verification is missing'
    return importlib.import_module('gridraft.token_audit')


def mint_result(program=TOKEN, supply='18446744073709551615'):
    return {'context': {'slot': 200}, 'value': {'owner': program, 'executable': False,
        'data': {'parsed': {'type': 'mint', 'info': {'decimals': 6, 'supply': supply,
            'isInitialized': True, 'mintAuthority': None, 'freezeAuthority': None}}}}}


def burn(program=TOKEN, amount='9007199254740993', checked=True):
    info = {'account': ACCOUNT, 'mint': MINT, 'authority': OWNER}
    info.update({'tokenAmount': {'amount': amount, 'decimals': 6}} if checked else {'amount': amount})
    return {'programId': program, 'parsed': {'type': 'burnChecked' if checked else 'burn', 'info': info}}


def transaction(instructions=None, inner=None):
    return {'slot': 100, 'blockTime': 1700000000, 'version': 'legacy',
        'meta': {'err': None, 'innerInstructions': inner if inner is not None else []},
        'transaction': {'signatures': [SIGNATURE], 'message': {'instructions': instructions or [burn()]}}}


def status():
    return {'context': {'slot': 201}, 'value': [{'slot': 100, 'err': None, 'confirmationStatus': 'finalized'}]}


def receipt(tx=None, stat=None, mint=None):
    m = module()
    snapshot = m.parse_mint(mint or mint_result(), MINT, 6, min_slot=100)
    return m.parse_burn_receipt(tx or transaction(), stat or status(), snapshot, SIGNATURE)


def test_preserves_exact_supply_and_authority_state():
    data = module().parse_mint(mint_result(), MINT, 6)
    assert data['supply_raw'] == '18446744073709551615'
    assert data['mint_authority'] is None and data['freeze_authority'] is None
    assert data['slot'] == 200 and data['mint'] == MINT


@pytest.mark.parametrize('program', [TOKEN, TOKEN_2022])
@pytest.mark.parametrize('checked', [True, False])
def test_verifies_exact_raw_burn_without_claiming_net_deflation(program, checked):
    r = receipt(transaction([burn(program, checked=checked)]), mint=mint_result(program))
    assert r['burned_raw'] == '9007199254740993'
    assert r['events'][0]['path'] == 'outer:0'
    assert r['token_program'] == program
    assert r['signature'] == SIGNATURE
    assert r['scope'] == 'tracked_gross_burns'
    assert r['net_supply_change_raw'] is None


def test_collects_cpi_burns_once_and_preserves_instruction_paths():
    ix = {'programId': OWNER, 'data': 'placeholder'}
    r = receipt(transaction([ix], [{'index': 0, 'instructions': [burn(amount='7'), burn(amount='8')]}]))
    assert r['burned_raw'] == '15'
    assert [v['path'] for v in r['events']] == ['inner:0:0', 'inner:0:1']


def test_dead_address_transfer_is_not_a_burn():
    ix = burn()
    ix['parsed']['type'] = 'transferChecked'
    with pytest.raises(ValueError, match='burn'):
        receipt(transaction([ix]))


@pytest.mark.parametrize('mutation', [
    lambda tx: tx['meta'].update(err={'InstructionError': [0, 'Custom']}),
    lambda tx: tx['meta'].pop('err'),
    lambda tx: tx.update(meta=None),
    lambda tx: tx.update(slot=101),
    lambda tx: tx.update(version=1),
    lambda tx: tx.update(version=True),
    lambda tx: tx['transaction'].update(signatures=['2' * 64]),
    lambda tx: tx['meta'].update(innerInstructions=None),
    lambda tx: tx['meta'].update(innerInstructions=[{'index': 0, 'instructions': []}, {'index': 0, 'instructions': []}]),
    lambda tx: tx['meta'].update(innerInstructions=[{'index': 2, 'instructions': [burn()]}]),
    lambda tx: tx['transaction']['message']['instructions'][0].update(programId=OWNER),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info'].update(mint=ACCOUNT),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info']['tokenAmount'].update(decimals=9),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info']['tokenAmount'].update(amount='0'),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info']['tokenAmount'].update(amount='01'),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info']['tokenAmount'].update(amount=4),
    lambda tx: tx['transaction']['message']['instructions'][0]['parsed']['info']['tokenAmount'].update(amount=str(2**64)),
    lambda tx: tx['transaction']['message']['instructions'][0].pop('parsed'),
])
def test_rejects_incomplete_or_untrustworthy_transaction_evidence(mutation):
    tx = transaction()
    mutation(tx)
    with pytest.raises(ValueError):
        receipt(tx)


@pytest.mark.parametrize('confirmation', ['confirmed', 'processed', None])
def test_rejects_unfinalized_status(confirmation):
    stat = status()
    stat['value'][0]['confirmationStatus'] = confirmation
    with pytest.raises(ValueError):
        receipt(stat=stat)


@pytest.mark.parametrize('mutation', [
    lambda d: d['value'][0].update(err='failed'),
    lambda d: d['value'][0].pop('err'),
    lambda d: d.update(value=[None]),
    lambda d: d.update(value=[]),
    lambda d: d['context'].update(slot=50),
])
def test_rejects_ambiguous_status(mutation):
    stat = status(); mutation(stat)
    with pytest.raises(ValueError):
        receipt(stat=stat)


@pytest.mark.parametrize('mutation', [
    lambda d: d['value'].update(owner=OWNER),
    lambda d: d['value'].update(executable=True),
    lambda d: d['value']['data']['parsed']['info'].pop('mintAuthority'),
    lambda d: d['value']['data']['parsed']['info'].update(decimals=True),
    lambda d: d['value']['data']['parsed']['info'].update(decimals=9),
    lambda d: d['value']['data']['parsed']['info'].update(supply=100),
    lambda d: d['value']['data']['parsed']['info'].update(isInitialized=False),
    lambda d: d['context'].update(slot=99),
])
def test_rejects_wrong_or_incomplete_mint_snapshot(mutation):
    d = mint_result(); mutation(d)
    with pytest.raises(ValueError):
        module().parse_mint(d, MINT, 6, min_slot=100)


def test_repeated_receipts_are_idempotent_and_conflicts_do_not_replace_evidence():
    m = module(); db = sqlite3.connect(':memory:'); ledger = m.BurnLedger(db)
    r = receipt()
    assert ledger.record(r) is True
    assert ledger.record(copy.deepcopy(r)) is False
    changed = copy.deepcopy(r); changed['burned_raw'] = '1'; changed['events'][0]['amount_raw'] = '1'
    with pytest.raises(ValueError):
        ledger.record(changed)
    summary = ledger.summary(MINT)
    assert summary['burned_raw'] == '9007199254740993'
    assert summary['receipt_count'] == 1 and summary['event_count'] == 1
    assert summary['complete_history'] is False
    assert ledger.summary(ACCOUNT)['burned_raw'] == '0'
    db.close()


def test_auditor_uses_only_bounded_finalized_reads_and_does_not_leak_client_credentials():
    m = module(); methods = []
    def handler(req):
        assert 'authorization' not in req.headers and 'cookie' not in req.headers
        body = json.loads(req.content); method = body['method']; methods.append(method)
        if method == 'getGenesisHash': value = MAINNET_GENESIS
        elif method == 'getSignatureStatuses':
            assert body['params'] == [[SIGNATURE], {'searchTransactionHistory': True}]
            value = status()
        elif method == 'getTransaction':
            assert body['params'][1] == {'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}
            value = transaction()
        elif method == 'getAccountInfo':
            assert body['params'][0] == MINT
            assert body['params'][1]['minContextSlot'] == 100
            assert body['params'][1]['commitment'] == 'finalized'
            value = mint_result()
        else: raise AssertionError(method)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': 1, 'result': value})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                headers={'Authorization': 'Bearer secret', 'Cookie': 'private=yes'}) as client:
            return await m.TokenAuditor(SolanaRPC(client, 'https://rpc.example.invalid/private', rps=100), MINT, 6).verify(SIGNATURE)
    result = asyncio.run(run())
    assert result['burned_raw'] == '9007199254740993'
    assert methods == ['getGenesisHash', 'getSignatureStatuses', 'getTransaction', 'getAccountInfo']


def test_invalid_signature_stops_before_network():
    m = module()
    class NeverRPC:
        async def ensure_mainnet(self): raise AssertionError('network called')
        async def call(self, *args): raise AssertionError('network called')
    with pytest.raises(ValueError):
        asyncio.run(m.TokenAuditor(NeverRPC(), MINT, 6).verify('invalid'))


def test_failed_finality_does_not_fetch_transaction_or_mint():
    m = module(); calls = []
    class RPC:
        async def ensure_mainnet(self): pass
        async def call(self, method, *args):
            calls.append(method)
            d = status(); d['value'][0]['confirmationStatus'] = 'confirmed'; return d
    with pytest.raises(ValueError):
        asyncio.run(m.TokenAuditor(RPC(), MINT, 6).verify(SIGNATURE))
    assert calls == ['getSignatureStatuses']


def test_ledger_sums_large_receipts_without_sqlite_float_rounding():
    m = module(); db = sqlite3.connect(':memory:'); ledger = m.BurnLedger(db)
    first = receipt(); second = copy.deepcopy(first); second['signature'] = '1' * 63 + '2'
    assert ledger.record(first) and ledger.record(second)
    summary = ledger.summary(MINT)
    assert summary['burned_raw'] == '18014398509481986'
    assert summary['receipt_count'] == 2 and summary['decimals'] == 6
    assert all('events' not in row for row in summary['recent'])
    db.close()

@pytest.mark.parametrize('bad_program', [None, {}, [], True])
def test_malformed_token_program_metadata_is_rejected_cleanly(bad_program):
    d = mint_result(); d['value']['owner'] = bad_program
    with pytest.raises(ValueError):
        module().parse_mint(d, MINT, 6)
    tx = transaction(); tx['transaction']['message']['instructions'][0]['programId'] = bad_program
    with pytest.raises(ValueError):
        receipt(tx)
