"""Regressions for model policy provenance and holder usage metering."""
import asyncio

import httpx
import pytest

from gridraft.broker import Broker
from gridraft import member_gateway
from gridraft.membership import Membership
from gridraft.app import ChatInput, Settings, validate_settings
from gridraft.model_policy import merge_upstream_metadata
from gridraft.store import Store


MODEL = 'MiniMaxAI/MiniMax-M2.7'
WALLET = 'wallet-fixture'


def test_discovery_can_tighten_but_never_raise_reviewed_model_caps():
    raised = merge_upstream_metadata(MODEL, {
        'context_length': 999_999,
        'max_completion_tokens': 99_999,
    })
    assert raised['context_length'] == 180_000
    assert raised['max_completion_tokens'] == 4_096
    assert raised['discovered_context_length'] == 999_999
    assert raised['discovered_max_completion_tokens'] == 99_999
    assert raised['context_limit_source'] == 'reviewed_policy'
    assert raised['completion_limit_source'] == 'reviewed_policy'
    assert raised['openbroker_limits_verified'] is False

    tightened = merge_upstream_metadata(MODEL, {
        'context_length': 120_000,
        'max_completion_tokens': 2_048,
    })
    assert tightened['context_length'] == 120_000
    assert tightened['max_completion_tokens'] == 2_048
    assert tightened['context_limit_source'] == 'discovery_tighter_than_reviewed_policy'
    assert tightened['completion_limit_source'] == 'discovery_tighter_than_reviewed_policy'


def test_zero_or_missing_discovery_is_unknown_without_erasing_reviewed_caps():
    row = merge_upstream_metadata(MODEL, {'context_length': 0, 'max_tokens': 0})
    assert row['context_length'] == 180_000
    assert row['max_completion_tokens'] == 4_096
    assert row['discovered_context_length'] is None
    assert row['discovered_max_completion_tokens'] is None
    assert row['discovery_limits_status'] == 'unknown'


def test_unknown_catalog_model_is_not_made_usable_by_discovery_alone():
    row = merge_upstream_metadata('unreviewed/model', {
        'context_length': 1_000_000,
        'max_completion_tokens': 100_000,
    })
    assert row['context_length'] is None
    assert row['max_completion_tokens'] is None
    assert row['discovered_context_length'] == 1_000_000
    assert row['discovered_max_completion_tokens'] == 100_000


def test_explicit_operator_override_can_raise_caps_without_claiming_verification():
    row = merge_upstream_metadata(MODEL, {
        'context_length': 120_000,
        'max_completion_tokens': 4_096,
    }, operator_cap=1_048_576, operator_override={
        'context_length': 204_800,
        'max_completion_tokens': 32_768,
    })
    assert row['context_length'] == 204_800
    assert row['max_completion_tokens'] == 32_768
    assert row['context_limit_source'] == 'operator_override_unverified'
    assert row['completion_limit_source'] == 'operator_override_unverified'
    assert row['openbroker_limits_verified'] is False
    # Separate proxy discovery remains visible but does not govern this deliberate override.
    assert row['discovered_context_length'] == 120_000
    assert row['discovered_max_completion_tokens'] == 4_096


def test_validated_settings_allow_bounded_per_model_override():
    settings = validate_settings(Settings(
        max_output_tokens=1_048_576,
        model_limit_overrides={MODEL: {
            'context_length': 204_800,
            'max_completion_tokens': 32_768,
        }},
    ))
    assert settings.model_limit_overrides[MODEL]['max_completion_tokens'] == 32_768
    body = ChatInput.model_validate({
        'model': MODEL, 'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 32_768,
    })
    assert body.max_tokens == 32_768


@pytest.mark.parametrize('overrides', [
    {'unknown/model': {'context_length': 100_000, 'max_completion_tokens': 1_000}},
    {MODEL: {'context_length': 100_000}},
    {MODEL: {'context_length': True, 'max_completion_tokens': 1}},
    {MODEL: {'context_length': 100_000, 'max_completion_tokens': 100_000}},
    {MODEL: {'context_length': 1_048_577, 'max_completion_tokens': 1_000}},
])
def test_model_limit_overrides_reject_ambiguous_or_unsafe_values(overrides):
    with pytest.raises(ValueError, match='model limit override'):
        validate_settings(Settings(max_output_tokens=1_048_576, model_limit_overrides=overrides))


def test_model_limit_overrides_are_loaded_from_json_env(monkeypatch):
    monkeypatch.setenv('MODEL_LIMIT_OVERRIDES_JSON',
        '{"MiniMaxAI/MiniMax-M2.7":{"context_length":204800,"max_completion_tokens":32768}}')
    settings = Settings.from_env()
    assert settings.model_limit_overrides == {MODEL: {
        'context_length': 204_800, 'max_completion_tokens': 32_768}}


@pytest.mark.parametrize('raw', [
    '{broken',
    '{"MiniMaxAI/MiniMax-M2.7":{"context_length":204800,"context_length":100000,"max_completion_tokens":32768}}',
    '{"MiniMaxAI/MiniMax-M2.7":{"context_length":NaN,"max_completion_tokens":32768}}',
])
def test_malformed_model_limit_override_json_has_actionable_error(monkeypatch,raw):
    monkeypatch.setenv('MODEL_LIMIT_OVERRIDES_JSON',raw)
    with pytest.raises(ValueError, match='MODEL_LIMIT_OVERRIDES_JSON'):
        Settings.from_env()


def test_proxy_model_metadata_accepts_aliases_and_uses_tightest_positive_output():
    def handler(_):
        return httpx.Response(200, json={'data': [
            {'id': MODEL, 'context_length': 180_000, 'max_tokens': 16_384},
            {'id': 'example/model', 'context_length': 100_000,
                'max_tokens': 16_384, 'max_output_length': 32_768,
                'max_completion_tokens': 8_192},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Broker(client).model_metadata()

    rows = asyncio.run(run())
    assert rows[MODEL] == {
        'id': MODEL, 'context_length': 180_000, 'max_completion_tokens': 16_384}
    assert rows['example/model']['max_completion_tokens'] == 8_192


def test_proxy_model_metadata_rejects_duplicate_ids_instead_of_overwriting():
    def handler(_):
        return httpx.Response(200, json={'data': [
            {'id': MODEL, 'max_tokens': 16_384},
            {'id': MODEL, 'max_tokens': 8_192},
        ]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await Broker(client).model_metadata()

    with pytest.raises(ValueError, match='metadata'):
        asyncio.run(run())


@pytest.mark.parametrize('bad_row', [None, {}, {'id': 'bad model id'}])
def test_proxy_model_metadata_rejects_malformed_rows(bad_row):
    def handler(_):
        return httpx.Response(200, json={'data': [bad_row]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await Broker(client).model_metadata()

    with pytest.raises(ValueError, match='metadata'):
        asyncio.run(run())


def test_usage_parser_preserves_optional_cache_and_reasoning_detail():
    usage = member_gateway.parse_usage({
        'prompt_tokens': 120,
        'completion_tokens': 30,
        'total_tokens': 150,
        'prompt_tokens_details': {'cached_tokens': 80},
        'completion_tokens_details': {'reasoning_tokens': 12},
    })
    assert usage == {
        'prompt_tokens': 120,
        'completion_tokens': 30,
        'total_tokens': 150,
        'cached_input_tokens': 80,
        'reasoning_tokens': 12,
    }


def test_usage_parser_treats_null_optional_subtotals_as_unreported():
    usage = member_gateway.parse_usage({
        'prompt_tokens': 12,
        'completion_tokens': 3,
        'total_tokens': 15,
        'prompt_tokens_details': {'cached_tokens': None},
        'completion_tokens_details': {'reasoning_tokens': None},
    })
    assert usage['cached_input_tokens'] is None
    assert usage['reasoning_tokens'] is None


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 4},
    {'prompt_tokens': 2, 'completion_tokens': 3, 'prompt_tokens_details': {'cached_tokens': 3}},
    {'prompt_tokens': 2, 'completion_tokens': 3, 'completion_tokens_details': {'reasoning_tokens': 4}},
])
def test_usage_parser_rejects_internally_inconsistent_detail(usage):
    with pytest.raises(ValueError):
        member_gateway.parse_usage(usage)


def test_holder_ledger_migrates_existing_rows_and_reports_exact_usage_detail(tmp_path):
    store = Store(str(tmp_path / 'usage.db'), 'p' * 40)
    store.ensure_account(WALLET)
    key = store.issue_key(WALLET, 'fixture', 10**9)
    # Reproduce the schema on installations created before detailed metering.
    store.db.execute('''CREATE TABLE member_usage(
        id TEXT PRIMARY KEY, key_id TEXT NOT NULL, wallet TEXT NOT NULL,
        idem TEXT NOT NULL, model TEXT NOT NULL, reserved_tokens INTEGER NOT NULL,
        tokens INTEGER NOT NULL DEFAULT 0, reserved_ngonka INTEGER NOT NULL,
        cost_ngonka INTEGER NOT NULL DEFAULT 0, cost_source TEXT,
        state TEXT NOT NULL, upstream_id TEXT, evidence TEXT, created REAL NOT NULL,
        UNIQUE(key_id,idem))''')
    ledger = Membership(store)
    ledger.allocate(100_000, 'fixture')
    rid = ledger.reserve(key['id'], WALLET, MODEL, 'one', 200,
        wallet_daily=1_000, global_daily=1_000, ngonka_per_token=25,
        upstream_available=100_000, rpm=10)
    usage = {
        'prompt_tokens': 120, 'completion_tokens': 30, 'total_tokens': 150,
        'cached_input_tokens': 80, 'reasoning_tokens': 12,
    }
    assert ledger.settle(rid, 150, 3_750, 'devshard_settled', 'up-1', usage=usage)

    history = ledger.history(WALLET)
    assert history[0]['prompt_tokens'] == 120
    assert history[0]['completion_tokens'] == 30
    assert history[0]['cached_input_tokens'] == 80
    assert history[0]['reasoning_tokens'] == 12
    assert history[0]['usage_status'] == 'reported'
    summary = ledger.usage_summary(WALLET)
    assert summary['prompt_tokens'] == 120
    assert summary['completion_tokens'] == 30
    assert summary['cached_input_tokens'] == 80
    assert summary['reasoning_tokens'] == 12
    assert summary['usage_reported_requests'] == 1
    assert summary['usage_unreported_requests'] == 0
    assert summary['cached_usage_reported_requests'] == 1
    assert summary['reasoning_usage_reported_requests'] == 1
    store.close()


def test_holder_history_uses_null_for_unreported_breakdown(tmp_path):
    store = Store(str(tmp_path / 'unknown.db'), 'p' * 40)
    store.ensure_account(WALLET)
    key = store.issue_key(WALLET, 'fixture', 10**9)
    ledger = Membership(store)
    ledger.allocate(100_000, 'fixture')
    rid = ledger.reserve(key['id'], WALLET, MODEL, 'one', 200,
        wallet_daily=1_000, global_daily=1_000, ngonka_per_token=25,
        upstream_available=100_000, rpm=10)
    ledger.settle(rid, 150, 3_750, 'operator', 'up-1')

    row = ledger.history(WALLET)[0]
    assert row['tokens'] == 150
    assert row['prompt_tokens'] is None
    assert row['completion_tokens'] is None
    assert row['cached_input_tokens'] is None
    assert row['reasoning_tokens'] is None
    assert row['usage_status'] == 'unreported'
    summary = ledger.usage_summary(WALLET)
    assert summary['prompt_tokens'] is None
    assert summary['completion_tokens'] is None
    assert summary['usage_reported_requests'] == 0
    assert summary['usage_unreported_requests'] == 1
    assert summary['cached_usage_reported_requests'] == 0
    assert summary['reasoning_usage_reported_requests'] == 0
    empty = ledger.usage_summary('empty-wallet')
    assert empty['prompt_tokens'] is None
    assert empty['completion_tokens'] is None
    assert empty['cached_input_tokens'] is None
    assert empty['reasoning_tokens'] is None
    assert empty['usage_reported_requests'] == 0
    assert empty['usage_unreported_requests'] == 0
    assert empty['cached_usage_reported_requests'] == 0
    assert empty['reasoning_usage_reported_requests'] == 0
    store.close()


def test_provider_usage_rows_keep_reported_prompt_completion_and_cache_detail():
    def handler(req):
        assert req.url.path == '/v1/usage/summary'
        return httpx.Response(200, json={
            'totals': {'requests': 1, 'errors': 0, 'prompt_tokens': 120,
                'completion_tokens': 30, 'total_tokens': 150, 'cached_input_tokens': 80,
                'reasoning_tokens': 12, 'cost_ngonka': 3_750},
            'models': [{'model': MODEL, 'requests': 1, 'errors': 0,
                'prompt_tokens': 120, 'completion_tokens': 30, 'total_tokens': 150,
                'cached_input_tokens': 80, 'reasoning_tokens': 12, 'cost_ngonka': 3_750}],
            'days': [{'date': '2026-10-24', 'model': MODEL, 'requests': 1, 'errors': 0,
                'prompt_tokens': 120, 'completion_tokens': 30, 'total_tokens': 150,
                'cached_input_tokens': 80, 'reasoning_tokens': 12, 'cost_ngonka': 3_750}],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Broker(client, 'obk-fixture').usage_summary(1)

    result = asyncio.run(run())
    assert result['models'][0]['prompt_tokens'] == 120
    assert result['models'][0]['cached_input_tokens'] == 80
    assert result['daily'][0]['completion_tokens'] == 30
    assert result['daily'][0]['reasoning_tokens'] == 12
