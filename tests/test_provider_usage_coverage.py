"""Mixed upstream detail must not become a falsely complete daily token count."""
import asyncio

import httpx
import pytest

from gridraft.broker import Broker


def test_provider_daily_details_require_coverage_of_every_model_row():
    def respond(request):
        return httpx.Response(200, json={
            'totals': {'requests': 2, 'total_tokens': 50, 'prompt_tokens': None},
            'models': [],
            'days': [
                {'date': '2026-10-24', 'model': 'a', 'requests': 1,
                 'total_tokens': 20, 'cost_ngonka': 500, 'prompt_tokens': 10,
                 'completion_tokens': 10, 'cached_input_tokens': 0},
                {'date': '2026-10-24', 'model': 'b', 'requests': 1,
                 'total_tokens': 30, 'cost_ngonka': 750, 'prompt_tokens': None,
                 'completion_tokens': 15},
            ],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await Broker(client, 'obk-fixture').usage_summary(1)

    result = asyncio.run(run())
    row = result['daily'][0]
    assert row['total_tokens'] == 50
    assert row['cost_ngonka'] == 1250
    assert row['prompt_tokens'] is None
    assert row['cached_input_tokens'] is None
    assert row['reasoning_tokens'] is None
    assert row['completion_tokens'] == 25
    assert row['detail_model_rows'] == 2
    assert row['prompt_tokens_reported_rows'] == 1
    assert row['cached_input_tokens_reported_rows'] == 1
    assert row['completion_tokens_reported_rows'] == 2
    assert row['reasoning_tokens_reported_rows'] == 0


@pytest.mark.parametrize('field', ['requests', 'errors', 'total_tokens', 'cost_ngonka'])
@pytest.mark.parametrize('missing', [None, 'absent'])
def test_provider_core_usage_never_treats_missing_as_zero(field, missing):
    first = {'date': '2026-10-24', 'model': 'a', 'requests': 0,
             'errors': 0, 'total_tokens': 0, 'cost_ngonka': 0}
    second = {'date': '2026-10-24', 'model': 'b', 'requests': 1,
              'errors': 0, 'total_tokens': 20, 'cost_ngonka': 500}
    if missing == 'absent':
        del second[field]
    else:
        second[field] = None

    async def run():
        response = {'totals': {field: None}, 'models': [second], 'days': [first, second]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=response))) as client:
            return await Broker(client, 'obk-fixture').usage_summary(1)

    result = asyncio.run(run())
    assert result['totals'][field] is None
    assert result['models'][0][field] is None
    assert result['days'][0][field] == 0
    assert result['days'][1][field] is None
    assert result['daily'][0][field] is None
