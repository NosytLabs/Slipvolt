"""Offline mint screening is preliminary and never signs or sends transactions."""
import asyncio
import importlib
import importlib.util
import json
import struct

import httpx
import pytest

from gridraft.integrations import MAINNET_GENESIS
from test_treasury_burn import MINT, TOKEN, TOKEN_2022, account, extension, fixture, raw_edit


def inspector():
    assert importlib.util.find_spec('gridraft.lock_mint_inspection') is not None, 'Read-only mint inspection is not implemented'
    return importlib.import_module('gridraft.lock_mint_inspection')


def mint_response(program=TOKEN):
    sample = fixture(program=program)
    return {'context': sample['context'], 'value': sample['value'][0]}


def test_plain_mint_screening_does_not_claim_a_vault_is_safe():
    report = inspector().inspect_mint(mint_response(), mint=MINT, decimals=6)
    assert report['status'] == 'review_required'
    assert report['mint'] == MINT and report['token_program'] == TOKEN
    assert report['freeze_authority_present'] is False
    assert report['mint_authority_present'] is False
    assert report['vault_implemented'] is False and report['deployment_approved'] is False
    assert report['transactions_sent'] == 0


def test_freeze_authority_blocks_the_preliminary_candidate():
    sample = fixture()
    raw_edit(sample, 0, 46, struct.pack('<I', 1))
    report = inspector().inspect_mint({'context': sample['context'], 'value': sample['value'][0]}, mint=MINT, decimals=6)
    assert report['status'] == 'blocked'
    assert report['freeze_authority_present'] is True
    assert report['deployment_approved'] is False


def test_token_2022_metadata_is_reported_but_never_approves_deployment():
    raw = bytearray(82)
    raw[44:46] = bytes([6, 1])
    sample = {'context': {'slot': 50}, 'value': account(extension(raw, 1, [(18, bytes(64))]), TOKEN_2022)}
    report = inspector().inspect_mint(sample, mint=MINT, decimals=6)
    assert report['observed_extensions'] == ['metadataPointer']
    assert report['status'] == 'review_required'
    assert report['deployment_approved'] is False


def test_mint_authority_is_disclosed_for_review():
    sample = fixture()
    raw_edit(sample, 0, 0, struct.pack('<I', 1))
    report = inspector().inspect_mint({'context': sample['context'], 'value': sample['value'][0]}, mint=MINT, decimals=6)
    assert report['mint_authority_present'] is True
    assert report['deployment_approved'] is False


@pytest.mark.parametrize('offset,value', [(44, bytes([9])), (45, bytes([0])), (46, struct.pack('<I', 2))])
def test_malformed_mint_fields_fail_closed(offset, value):
    sample = fixture()
    raw_edit(sample, 0, offset, value)
    with pytest.raises(ValueError):
        inspector().inspect_mint({'context': sample['context'], 'value': sample['value'][0]}, mint=MINT, decimals=6)


@pytest.mark.parametrize('tag', [1, 12, 14, 28, 999])
def test_transfer_fee_delegate_hook_pause_and_unknown_extensions_fail_closed(tag):
    raw = bytearray(82)
    raw[44:46] = bytes([6, 1])
    sample = {'context': {'slot': 50}, 'value': account(extension(raw, 1, [(tag, bytes(64))]), TOKEN_2022)}
    with pytest.raises(ValueError):
        inspector().inspect_mint(sample, mint=MINT, decimals=6)


@pytest.mark.parametrize('slot', [0, True, '50', None])
def test_invalid_finalized_snapshot_fails_closed(slot):
    sample = mint_response()
    sample['context']['slot'] = slot
    with pytest.raises(ValueError):
        inspector().inspect_mint(sample, mint=MINT, decimals=6)


def test_rpc_inspection_verifies_network_and_uses_only_finalized_read():
    class Rpc:
        def __init__(self): self.calls = []
        async def ensure_mainnet(self): self.calls.append('genesis')
        async def call(self, method, params):
            self.calls.append((method, params))
            return mint_response()
    rpc = Rpc()
    report = asyncio.run(inspector().inspect_configured_mint(rpc, mint=MINT, decimals=6))
    assert rpc.calls == ['genesis', ('getAccountInfo', [MINT, {'encoding': 'base64', 'commitment': 'finalized'}])]
    assert report['status'] == 'review_required'
    assert report['transactions_sent'] == 0


def test_wrong_network_is_rejected_before_mint_read():
    class WrongNetwork:
        async def ensure_mainnet(self): raise ValueError('wrong network')
        async def call(self, *args): raise AssertionError('must not read on wrong network')
    with pytest.raises(ValueError):
        asyncio.run(inspector().inspect_configured_mint(WrongNetwork(), mint=MINT, decimals=6))


def test_cli_only_reads_mainnet_mint_and_never_discloses_private_rpc(monkeypatch, capsys):
    import scripts.check_lock_mint as command
    original_client = httpx.AsyncClient
    requests = []
    private_url = 'https://rpc.example.invalid/private-secret-url'
    def upstream(request):
        request_data = json.loads(request.content)
        requests.append(request_data)
        assert request.method == 'POST'
        if request_data['method'] == 'getGenesisHash':
            return httpx.Response(200, json={'result': MAINNET_GENESIS})
        assert request_data['method'] == 'getAccountInfo'
        return httpx.Response(200, json={'result': mint_response()})
    monkeypatch.setenv('SOLANA_RPC_URL', private_url)
    monkeypatch.setenv('HOLDER_MINT', MINT)
    monkeypatch.setenv('HOLDER_TOKEN_DECIMALS', '6')
    monkeypatch.setattr(command, 'load_env', lambda _: None)
    def factory(**kwargs):
        kwargs['transport'] = httpx.MockTransport(upstream)
        return original_client(**kwargs)
    monkeypatch.setattr(command.httpx, 'AsyncClient', factory)
    assert command.main([]) == 0
    captured = capsys.readouterr()
    assert [row['method'] for row in requests] == ['getGenesisHash', 'getAccountInfo']
    assert private_url not in captured.out + captured.err
    assert json.loads(captured.out)['deployment_approved'] is False


def test_cli_failure_redacts_private_rpc_error(monkeypatch, capsys):
    import scripts.check_lock_mint as command
    async def failed(*args, **kwargs):
        raise ValueError('private-secret-endpoint')
    monkeypatch.setattr(command, 'load_env', lambda _: None)
    monkeypatch.setattr(command, 'check', failed)
    assert command.main(['--mint', MINT, '--decimals', '6']) == 2
    captured = capsys.readouterr()
    assert 'private-secret-endpoint' not in captured.out + captured.err
    assert json.loads(captured.err)['status'] == 'unavailable'
