"""Mixed upstream detail must not become a falsely complete daily token count."""
import asyncio

import httpx

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
