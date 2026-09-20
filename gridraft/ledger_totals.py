"""Transactional lifetime GNK totals, backfilled without deleting source records.

SQLite triggers update the projection in the same transaction as its source
rows, including writes from another connection and operator reconciliation.
Authorization must not use a time-based cache of these totals.
"""


def initialize_pool_totals(store):
    columns = ('allocated_ngonka', 'spent_ngonka', 'reserved_ngonka', 'review_count')
    with store.transaction():
        store.db.execute('''CREATE TABLE IF NOT EXISTS member_pool_totals(
          id INTEGER PRIMARY KEY CHECK(id=1),
          allocated_ngonka INTEGER NOT NULL CHECK(typeof(allocated_ngonka)='integer' AND allocated_ngonka>=0),
          spent_ngonka INTEGER NOT NULL CHECK(typeof(spent_ngonka)='integer' AND spent_ngonka>=0),
          reserved_ngonka INTEGER NOT NULL CHECK(typeof(reserved_ngonka)='integer' AND reserved_ngonka>=0),
          review_count INTEGER NOT NULL CHECK(typeof(review_count)='integer' AND review_count>=0))''')
        if not store.db.execute('SELECT 1 FROM member_pool_totals WHERE id=1').fetchone():
            store.db.execute('''INSERT INTO member_pool_totals SELECT 1,
              (SELECT COALESCE(SUM(amount_ngonka),0) FROM member_funding),
              COALESCE(SUM(cost_ngonka),0),
              COALESCE(SUM(CASE WHEN state IN ('reserved','needs_review') THEN reserved_ngonka ELSE 0 END),0),
              COALESCE(SUM(CASE WHEN state='needs_review' THEN 1 ELSE 0 END),0)
              FROM member_usage''')
        # Identifiers and expressions are constants, never supplied by callers.
        for table in ('member_funding', 'member_usage'):
            def contribution(alias):
                if table == 'member_funding':
                    return (f'{alias}.amount_ngonka', '0', '0', '0')
                return ('0', f'{alias}.cost_ngonka',
                        f"CASE WHEN {alias}.state IN ('reserved','needs_review') THEN {alias}.reserved_ngonka ELSE 0 END",
                        f"CASE WHEN {alias}.state='needs_review' THEN 1 ELSE 0 END")
            for event in ('INSERT', 'UPDATE', 'DELETE'):
                old = contribution('OLD') if event != 'INSERT' else ('0',)*4
                new = contribution('NEW') if event != 'DELETE' else ('0',)*4
                updates = ', '.join(f'{column}={column}+({after})-({before})'
                                    for column, before, after in zip(columns, old, new))
                store.db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_pool_{event.lower()}
                  AFTER {event} ON {table} BEGIN
                  UPDATE member_pool_totals SET {updates} WHERE id=1; END''')
        store.db.execute('CREATE INDEX IF NOT EXISTS member_usage_created ON member_usage(created)')
        store.db.execute("""CREATE INDEX IF NOT EXISTS member_usage_active_wallet
          ON member_usage(wallet,reserved_tokens) WHERE state IN ('reserved','needs_review')""")
