"""Cache correctness and bounded hot-path maintenance; no external services."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import gridraft.broker as broker_module
import gridraft.store as store_module
from gridraft.broker import Broker
from gridraft.store import Store


def registry(day='2026-09-20'):
    return {'brokers': [{'status': 'active'}], 'daily_usage': [
        {'date': day, 'requests': 3, 'total_tokens': 400, 'cost_ngonka': 6000}]}


def clock(monkeypatch, module):
    value = {'wall': 1800000000.0, 'mono': 1000.0}
    monkeypatch.setattr(module, 'time', SimpleNamespace(
        time=lambda: value['wall'], monotonic=lambda: value['mono']))
    return value


def test_failed_refresh_stays_stale_during_backoff(monkeypatch):
    ticks = clock(monkeypatch, broker_module)
    async def run():
        broker = Broker(None)
        broker.read = AsyncMock(side_effect=[registry(), ValueError('offline')])
        first = await broker.network()
        assert first['stale'] is False
        ticks['wall'] += 61; ticks['mono'] += 61
        assert (await broker.network())['stale'] is True
        assert (await broker.network())['stale'] is True
        assert broker.read.await_count == 2
    asyncio.run(run())


def test_network_cache_expiry_uses_monotonic_not_wall_clock(monkeypatch):
    ticks = clock(monkeypatch, broker_module)
    async def run():
        broker = Broker(None)
        broker.read = AsyncMock(side_effect=[registry(), ValueError('offline')])
        await broker.network()
        ticks['wall'] -= 3600; ticks['mono'] += 61
        assert (await broker.network())['stale'] is True
        assert broker.read.await_count == 2
    asyncio.run(run())


def test_old_failed_snapshot_becomes_unavailable(monkeypatch):
    ticks = clock(monkeypatch, broker_module)
    async def run():
        broker = Broker(None)
        broker.read = AsyncMock(side_effect=[registry(), ValueError('offline')])
        await broker.network()
        ticks['wall'] += 301; ticks['mono'] += 301
        result = await broker.network()
        assert result['status'] == 'unavailable'
        assert result['totals'] is None
    asyncio.run(run())


@pytest.mark.parametrize('day', ['2026-99-01', '2026-02-30', '2026-00-10'])
def test_network_rejects_impossible_dates(day):
    async def run():
        broker = Broker(None)
        broker.read = AsyncMock(return_value=registry(day))
        assert (await broker.network())['status'] == 'unavailable'
    asyncio.run(run())


def test_network_concurrent_reads_fetch_once_and_return_independent_data():
    async def run():
        broker = Broker(None)
        async def read(*args, **kwargs):
            await asyncio.sleep(0)
            return registry()
        broker.read = AsyncMock(side_effect=read)
        responses = await asyncio.gather(*(broker.network() for _ in range(20)))
        responses[0]['totals']['requests'] = 99999
        assert all(r['totals']['requests'] == 3 for r in responses[1:])
        assert broker.read.await_count == 1
    asyncio.run(run())


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path/'test.db'), 'test-only-stable-pepper')
    try:
        yield s
    finally:
        s.close()


def test_hot_path_housekeeping_is_amortized(store, monkeypatch):
    clock(monkeypatch, store_module)
    statements = []
    store.db.set_trace_callback(statements.append)
    for _ in range(200):
        store.throttle('one-wallet', 1000)
    deletes = [s for s in statements if s.upper().startswith('DELETE FROM')]
    assert len(deletes) == 3, '200 requests should not run 600 cleanup DELETEs'
    assert store.db.execute('SELECT COUNT(*) FROM rate_hits').fetchone()[0] == 200


def test_housekeeping_does_not_weaken_rate_limits(store, monkeypatch):
    ticks = clock(monkeypatch, store_module)
    store.throttle('one-wallet', 1)
    with pytest.raises(ValueError, match='rate_limit'):
        store.throttle('one-wallet', 1)
    assert store.db.execute('SELECT COUNT(*) FROM rate_hits').fetchone()[0] == 1
    ticks['wall'] += 61; ticks['mono'] += 61
    store.throttle('one-wallet', 1)


def test_housekeeping_prunes_only_a_bounded_batch(store, monkeypatch):
    ticks = clock(monkeypatch, store_module)
    store.db.executemany('INSERT INTO rate_hits VALUES(?,?)',
                        [('old', ticks['wall']-8000)]*2500)
    store.throttle('new', 10)
    assert store.db.execute("SELECT COUNT(*) FROM rate_hits WHERE bucket='old'").fetchone()[0] == 1500
    ticks['wall'] += 61; ticks['mono'] += 61
    store.throttle('new', 10)
    assert store.db.execute("SELECT COUNT(*) FROM rate_hits WHERE bucket='old'").fetchone()[0] == 500


def test_housekeeping_runs_even_when_admission_is_rejected(store, monkeypatch):
    ticks = clock(monkeypatch, store_module)
    store.db.execute('INSERT INTO rate_hits VALUES(?,?)', ('full', ticks['wall']))
    store.db.execute('INSERT INTO sessions VALUES(?,?,?)', ('expired', 'wallet', ticks['wall']-1))
    with pytest.raises(ValueError, match='rate_limit'):
        store.throttle('full', 1)
    assert store.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0


def test_expired_session_stays_invalid_between_cleanup_runs(store, monkeypatch):
    ticks = clock(monkeypatch, store_module)
    store.throttle('setup', 10)
    secret = store.new_session('wallet')
    ticks['wall'] += 3601  # Authorization uses wall-clock expiry, not GC cadence.
    assert store.session_wallet(secret) is None


def test_transaction_rolls_back_on_interrupt(store):
    with pytest.raises(KeyboardInterrupt):
        with store.transaction():
            store.db.execute("INSERT INTO accounts(wallet) VALUES('interrupt')")
            raise KeyboardInterrupt()
    assert not store.db.in_transaction
    assert store.account('interrupt') is None
    with store.transaction():
        store.db.execute("INSERT INTO accounts(wallet) VALUES('next')")
    assert store.account('next') is not None


def test_logout_all_uses_wallet_index(store):
    plan = ' '.join(str(r['detail']) for r in store.db.execute(
        'EXPLAIN QUERY PLAN DELETE FROM sessions WHERE wallet=?', ('wallet',)))
    assert 'SEARCH sessions' in plan
    assert 'SCAN sessions' not in plan


def test_preview_refuses_missing_styles_instead_of_shipping_a_broken_page(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path
    import scripts.package_preview as package
    shutil.copytree(Path('public'), tmp_path/'public')
    (tmp_path/'public'/'content.css').unlink()
    monkeypatch.setattr(package, 'ROOT', tmp_path)
    target = tmp_path/'preview.html'
    target.write_text('previous-good-preview')
    with pytest.raises(FileNotFoundError):
        package.build(target)
    assert target.read_text() == 'previous-good-preview'


def test_hot_usage_queries_have_targeted_indexes(store):
    from gridraft.membership import Membership
    Membership(store)
    store_indexes={row[1] for row in store.db.execute("PRAGMA index_list('usage')")}
    member_indexes={row[1] for row in store.db.execute("PRAGMA index_list('member_usage')")}
    assert {'usage_state','usage_wallet_state'} <= store_indexes
    assert {'member_usage_created','member_usage_wallet_state'} <= member_indexes


def test_verify_script_is_executable_for_documented_command():
    from pathlib import Path
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify.sh'
    assert script.stat().st_mode & 0o111, './scripts/verify.sh is documented and must be executable'


def test_runtime_security_dependencies_are_patched():
    from pathlib import Path
    pins = {}
    for line in (Path(__file__).resolve().parents[1] / 'requirements.txt').read_text().splitlines():
        if '==' in line:
            name, version = line.split('==', 1)
            pins[name.strip().lower()] = version.strip()
    assert pins.get('cryptography') == '50.0.1'
    assert pins.get('starlette') == '1.6.0'
    assert pins.get('fastapi') == '0.141.1'
    assert pins.get('pydantic') == '2.13.5'
