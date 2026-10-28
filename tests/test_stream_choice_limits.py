"""Streaming choice validation must match the allowance reserved for ``n``."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from gridraft.member_gateway import MemberGateway


MODEL = 'MiniMaxAI/MiniMax-M2.7'
USAGE = {'prompt_tokens': 12, 'completion_tokens': 8, 'total_tokens': 20}


class StreamFixture:
    def __init__(self, frames):
        self.frames = frames
        self.closed = False

    async def aiter_lines(self):
        for frame in self.frames:
            content = frame if frame == '[DONE]' else json.dumps(frame)
            yield 'data: ' + content
            yield ''

    async def aclose(self):
        self.closed = True


class BrokerFixture:
    async def request_cost(self, upstream_id, model, tokens, estimate):
        assert upstream_id == 'up-1'
        assert model == MODEL
        assert tokens == 20
        return estimate, 'conservative_budget_estimate'


class LedgerFixture:
    def __init__(self):
        self.settled = []
        self.reviewed = []

    def settle(self, *args, **kwargs):
        self.settled.append((args, kwargs))

    def review(self, *args):
        self.reviewed.append(args)


def frame(*choices, usage=None):
    value = {'id': 'up-1', 'model': MODEL, 'choices': list(choices)}
    if usage is not None:
        value['usage'] = usage
    return value


def choice(index, content='x'):
    return {'index': index, 'delta': {'content': content}}


def consume(frames, requested_choices):
    upstream = StreamFixture(frames)
    ledger = LedgerFixture()
    gateway = MemberGateway(SimpleNamespace(timeout=1), None, BrokerFixture(), ledger)

    async def run():
        return ''.join([chunk async for chunk in gateway.stream(
            upstream, 'local-1', MODEL, None, 25, requested_choices)])

    return asyncio.run(run()), upstream, ledger


@pytest.mark.parametrize('bad_index', [1, -1, True, '0', None])
def test_stream_rejects_choice_index_outside_reserved_n(bad_index):
    output, upstream, ledger = consume([
        frame(choice(bad_index)),
        frame(usage=USAGE),
        '[DONE]',
    ], requested_choices=1)

    assert '[DONE]' not in output
    assert 'retained for review' in output
    assert ledger.settled == []
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed is True


def test_stream_accepts_interleaved_requested_choices_and_usage_on_last_choice_frame():
    output, upstream, ledger = consume([
        frame(choice(0, 'a')),
        frame(choice(1, 'b')),
        frame(choice(0, 'c'), choice(1, 'd'), usage=USAGE),
        '[DONE]',
    ], requested_choices=2)

    assert output.endswith('data: [DONE]\n\n')
    assert len(ledger.settled) == 1
    assert ledger.settled[0][0][:5] == (
        'local-1', 20, 500, 'conservative_budget_estimate', 'up-1')
    assert ledger.settled[0][1]['usage']['total_tokens'] == 20
    assert ledger.reviewed == []
    assert upstream.closed is True


def test_stream_rejects_output_after_terminal_usage_frame():
    output, upstream, ledger = consume([
        frame(choice(0, 'before')),
        frame(usage=USAGE),
        frame(choice(0, 'after')),
        '[DONE]',
    ], requested_choices=1)

    assert '[DONE]' not in output
    assert 'retained for review' in output
    assert ledger.settled == []
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed is True


def test_stream_accepts_repeated_identical_usage():
    output, upstream, ledger = consume([
        frame(choice(0)), frame(usage=USAGE), frame(usage=USAGE), '[DONE]',
    ], requested_choices=1)
    assert output.endswith('data: [DONE]\n\n')
    assert len(ledger.settled) == 1
    assert ledger.settled[0][0][1] == 20
    assert ledger.reviewed == []
    assert upstream.closed is True


def test_stream_rejects_conflicting_details_even_when_total_matches():
    output, upstream, ledger = consume([
        frame(usage=USAGE),
        frame(usage={'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}),
        '[DONE]',
    ], requested_choices=1)
    assert '[DONE]' not in output
    assert 'retained for review' in output
    assert ledger.settled == []
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed is True


def test_stream_rejects_duplicate_choice_indexes_within_one_frame():
    output, upstream, ledger = consume([
        frame(choice(0, 'a'), choice(0, 'b')),
        frame(usage=USAGE),
        '[DONE]',
    ], requested_choices=2)

    assert '[DONE]' not in output
    assert 'retained for review' in output
    assert ledger.settled == []
    assert ledger.reviewed == [('local-1', 'up-1')]
    assert upstream.closed is True
