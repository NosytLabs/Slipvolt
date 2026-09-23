"""Merge regressions; provider/RPC responses below are controlled test fixtures."""
import asyncio
import csv
import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from gridraft.app import create_app
from gridraft.broker import Broker
from gridraft.membership import Membership
from gridraft.store import Store
from test_gridraft import WALLET, MODEL, BODY, login
from test_membership import member_settings, handler, make_key


def client_for(tmp_path, **settings):
    app = create_app(member_settings(**settings), str(tmp_path/'app.db'), httpx.MockTransport(handler))
    app.state.membership.allocate(10000000, 'fixture-funding')
    return app, TestClient(app)


def test_holder_summary_reads_gnk_ledger(tmp_path):
    app, client = client_for(tmp_path)
    with client as c:
        login(c)
        assert c.post('/v1/chat/completions', headers=make_key(c), json=BODY).status_code == 200
        summary = c.get('/api/usage/summary').json()
        assert summary['requests'] == 1
        assert summary['total_tokens'] == 15
        assert summary['cost_ngonka'] == 150
        assert len(summary['daily']) == 7
        assert summary['daily_timezone'] == 'UTC'
        assert 'billed_nusd' not in summary
        assert 'obk-' not in json.dumps(summary)


def test_holder_export_uses_gnk_units_and_excludes_other_wallet(tmp_path):
    app, client = client_for(tmp_path)
    with client as c:
        login(c)
        assert c.post('/v1/chat/completions', headers=make_key(c), json=BODY).status_code == 200
        app.state.store.db.execute("INSERT INTO member_usage(id,key_id,wallet,idem,model,reserved_tokens,reserved_ngonka,state,created) VALUES('other','k','other','i','secret-other-model',1,25,'reserved',?)", (time.time(),))
        response = c.get('/api/usage/export')
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert len(rows) == 1
        assert rows[0]['model'] == MODEL
        assert rows[0]['tokens'] == '15'
        assert rows[0]['cost_ngonka'] == '150'
        assert response.headers['X-Usage-Unit'] == 'ngonka'
        assert 'billed_nusd' not in response.text
        assert 'secret-other-model' not in response.text
        assert 'Hello back' not in response.text


def test_holder_account_does_not_claim_prepaid_credit_required(tmp_path):
    _, client = client_for(tmp_path)
    with client as c:
        login(c)
        data = c.get('/api/account').json()
        assert data.get('access_mode') == 'holder_allowance'
        assert 'balance_nusd' not in data
        assert 'Credits must be funded' not in data.get('notice', '')


def seeded_store(count=0, path=':memory:'):
    store = Store(path, 'x'*40)
    m = Membership(store)
    m.allocate(1000000000, 'fixture-funding')
    past = (int(time.time()//86400)-2)*86400
    with store.transaction():
        store.db.executemany("""INSERT INTO member_usage(id,key_id,wallet,idem,model,reserved_tokens,tokens,reserved_ngonka,cost_ngonka,state,created)
          VALUES(?, 'k', ?, ?, 'model', 10, 10, 250, 150, 'settled', ?)""",
          [(f'h{i}', WALLET, f'i{i}', past) for i in range(count)])
    return store, m


def op_count(db, call):
    calls = 0
    def count():
        nonlocal calls
        calls += 1
        return 0
    db.set_progress_handler(count, 1)
    try:
        result = call()
    finally:
        db.set_progress_handler(None, 0)
    return result, calls


def test_pool_checks_do_not_rescan_settled_history():
    s, m = seeded_store(10000)
    try:
        pool, steps = op_count(s.db, m.pool)
        assert pool['budget_spent_ngonka'] == 1500000
        assert pool['available_budget_ngonka'] == 998500000
        assert steps < 300, f'pool check used {steps} SQLite VM steps'
    finally:
        s.close()


def test_daily_quota_query_skips_old_settled_history():
    s, m = seeded_store(10000)
    try:
        for wallet in (None, WALLET):
            result, steps = op_count(s.db, lambda: m.totals(wallet))
            assert result['used_tokens'] == 0
            assert steps < 500, f'quota check used {steps} SQLite VM steps'
    finally:
        s.close()


def test_old_unresolved_holds_still_count_in_optimized_queries():
    s, m = seeded_store(200)
    try:
        s.db.execute("UPDATE member_usage SET state='needs_review',tokens=0,cost_ngonka=0 WHERE id='h0'")
        assert m.totals(WALLET)['reserved_tokens'] == 10
        assert m.totals()['reserved_tokens'] == 10
        pool = m.pool()
        assert pool['reconciliation_required'] is True
        assert pool['reserved_ngonka'] == 250
        assert pool['budget_spent_ngonka'] == 199*150
    finally:
        s.close()


def test_public_balance_requests_are_coalesced_but_auth_reads_stay_fresh(tmp_path):
    hits = []
    def remote(req):
        if req.url.path == '/v1/balance': hits.append(1)
        return handler(req)
    app = create_app(member_settings(public_broker_balance=True), str(tmp_path/'b.db'), httpx.MockTransport(remote))
    app.state.membership.allocate(10000000, 'fixture')
    with TestClient(app) as c:
        for _ in range(5):
            assert c.get('/api/treasury').json()['status'] == 'available'
        assert len(hits) == 1
        login(c)
        key = make_key(c)
        assert c.post('/v1/chat/completions', headers=key, json=BODY).status_code == 200
        assert c.post('/v1/chat/completions', headers=key, json=BODY).status_code == 200
        assert len(hits) == 3, 'inference must never use display-cache balance'


def test_complete_broker_read_has_deadline_even_with_regular_chunks(monkeypatch):
    import gridraft.broker as module
    monkeypatch.setattr(module, 'READ_TIMEOUT_SECONDS', 0.01, raising=False)
    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for piece in (b'{', b'"ok":', b'true}'):
                await asyncio.sleep(0.02)
                yield piece
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,stream=Drip()))) as client:
            with pytest.raises(TimeoutError):
                await Broker(client).read('/v1/models')
    asyncio.run(check())


def assert_projection_matches_rows(m):
    db = m.db
    allocated = db.execute('SELECT COALESCE(SUM(amount_ngonka),0) FROM member_funding').fetchone()[0]
    spent, held, review = db.execute("""SELECT COALESCE(SUM(cost_ngonka),0),
      COALESCE(SUM(CASE WHEN state IN ('reserved','needs_review') THEN reserved_ngonka ELSE 0 END),0),
      COALESCE(SUM(CASE WHEN state='needs_review' THEN 1 ELSE 0 END),0) FROM member_usage""").fetchone()
    pool = m.pool()
    assert pool['allocated_ngonka'] == allocated
    assert pool['budget_spent_ngonka'] == spent
    assert pool['reserved_ngonka'] == held
    assert pool['reconciliation_required'] == bool(review)
    assert pool['available_budget_ngonka'] == max(0, allocated-spent-held)


def test_existing_database_backfill_and_repeated_startup(tmp_path):
    path = str(tmp_path/'old.db')
    s, m = seeded_store(30, path)
    s.db.execute("UPDATE member_usage SET state='needs_review',cost_ngonka=0 WHERE id='h0'")
    expected = m.pool()
    # Simulate the shipped pre-optimization database, preserving source rows.
    for row in list(s.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'member_%_pool_%'")):
        s.db.execute('DROP TRIGGER '+row[0])
    s.db.execute('DROP TABLE member_pool_totals')
    s.close()
    s = Store(path, 'x'*40)
    try:
        m = Membership(s)
        assert m.pool() == expected
        assert Membership(s).pool() == expected  # no duplicate backfill or triggers
        assert s.db.execute('SELECT COUNT(*) FROM member_usage').fetchone()[0] == 30
        assert_projection_matches_rows(m)
    finally:
        s.close()


def test_projection_rolls_back_with_source_transaction():
    s, m = seeded_store(4)
    try:
        before = m.pool()
        with pytest.raises(RuntimeError):
            with s.transaction():
                s.db.execute("UPDATE member_usage SET cost_ngonka=450,state='needs_review' WHERE id='h0'")
                s.db.execute("UPDATE member_funding SET amount_ngonka=2000000000")
                assert_projection_matches_rows(m)
                raise RuntimeError('rollback')
        assert m.pool() == before
        assert_projection_matches_rows(m)
    finally:
        s.close()


def test_projection_tracks_operator_updates_and_deletes():
    s, m = seeded_store(4)
    try:
        m.allocate(123456, 'second')
        s.db.execute("UPDATE member_usage SET cost_ngonka=450,state='needs_review' WHERE id='h0'")
        assert_projection_matches_rows(m)
        m.settle('h0',12,180,'operator',evidence='test-receipt')
        before = m.pool()
        assert m.settle('h0',12,180,'operator',evidence='test-receipt') is False
        assert m.pool() == before
        s.db.execute("DELETE FROM member_funding WHERE reference='second'")
        s.db.execute("DELETE FROM member_usage WHERE id='h1'")
        assert_projection_matches_rows(m)
    finally:
        s.close()


def test_other_connection_updates_are_visible_without_cache(tmp_path):
    path = str(tmp_path/'shared.db')
    first, m1 = seeded_store(4, path)
    second = Store(path, 'x'*40)
    try:
        m2 = Membership(second)
        m2.allocate(12345, 'second-connection')
        assert m1.pool()['allocated_ngonka'] == 1000012345
        m2.review('h0')  # settled rows remain settled
        second.db.execute("UPDATE member_usage SET state='needs_review',cost_ngonka=0 WHERE id='h0'")
        assert m1.pool()['reconciliation_required'] is True
        assert_projection_matches_rows(m1)
        assert m1.pool() == m2.pool()
    finally:
        second.close(); first.close()


def test_holder_reporting_requires_session(tmp_path):
    _, client = client_for(tmp_path)
    with client as c:
        for path in ('/api/account','/api/usage/summary','/api/usage/export'):
            assert c.get(path).status_code == 401


def test_member_csv_escapes_formula_fields(tmp_path):
    app, client = client_for(tmp_path)
    with client as c:
        login(c)
        app.state.store.db.execute("""INSERT INTO member_usage(id,key_id,wallet,idem,model,reserved_tokens,cost_source,reserved_ngonka,state,created)
          VALUES('formula','k',?,'i','=bad()',1,'@bad()',25,'reserved',?)""", (WALLET,time.time()))
        rows = list(csv.DictReader(io.StringIO(c.get('/api/usage/export').text)))
        assert rows[0]['model'] == "'=bad()"
        assert rows[0]['cost_source'] == "'@bad()"


def test_public_display_cache_expires_and_cannot_turn_errors_into_zero():
    async def check():
        state = {'calls':0,'fail':False}
        def remote(req):
            state['calls'] += 1
            if state['fail']:return httpx.Response(503)
            return httpx.Response(200,json={'available_ngonka':99})
        async with httpx.AsyncClient(transport=httpx.MockTransport(remote)) as client:
            broker = Broker(client,'test-only')
            results = await asyncio.gather(*(broker.public_balance() for _ in range(10)))
            assert state['calls'] == 1
            assert all(d['available_ngonka'] == 99 for d in results)
            results[0]['available_ngonka'] = 0
            assert (await broker.public_balance())['available_ngonka'] == 99
            broker._public_balance_attempt -= 16
            state['fail'] = True
            with pytest.raises(httpx.HTTPStatusError):await broker.public_balance()
            with pytest.raises(ValueError):await broker.public_balance()
            assert state['calls'] == 2  # failed metadata reads also have a retry cooldown
            state['fail'] = False
            broker._public_balance_attempt -= 16
            assert (await broker.public_balance())['available_ngonka'] == 99
            assert state['calls'] == 3
    asyncio.run(check())


def test_ci_uses_canonical_verifier_and_verifier_includes_operator_tests():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    workflow = (root/'.github/workflows/test.yml').read_text()
    verifier = (root/'scripts/verify.sh').read_text()
    assert 'sh scripts/verify.sh' in workflow
    assert 'node --test tests/*.test.cjs' in verifier
    assert 'operator/profit-core.js' in verifier
    assert 'operator/calculate.cjs' in verifier


def test_expiry_cleanup_uses_time_indexes():
    s = Store(':memory:', 'x'*40)
    try:
        for table,column in [('rate_hits','created'),('sessions','expires'),('challenges','expires')]:
            plan = ' '.join(str(row[3]) for row in s.db.execute(f'EXPLAIN QUERY PLAN DELETE FROM {table} WHERE {column}<?', (time.time(),)))
            assert 'SEARCH' in plan, f'{table}: {plan}'
    finally:
        s.close()


def test_operator_tools_are_not_publicly_served(tmp_path):
    _, client = client_for(tmp_path)
    with client as c:
        assert c.get('/operator/profit-planner.html').status_code == 404
        assert c.get('/.env').status_code == 404
