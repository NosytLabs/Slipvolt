"""Finite holder allowances, separate from legacy dollar credits.

All budget quantities are integer ngonka (1 GNK = 10**9 ngonka). This is an
operator allocation ledger, NOT a wallet, deposit verifier, or exchange.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from .ledger_totals import initialize_pool_totals


def integer(value, minimum=0, maximum=10**15):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid integer quantity')
    return value


class Membership:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        with store.lock:
            self.db.executescript('''
            CREATE TABLE IF NOT EXISTS member_funding(
              reference TEXT PRIMARY KEY, amount_ngonka INTEGER NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS member_usage(
              id TEXT PRIMARY KEY, key_id TEXT NOT NULL, wallet TEXT NOT NULL,
              idem TEXT NOT NULL, model TEXT NOT NULL, reserved_tokens INTEGER NOT NULL,
              tokens INTEGER NOT NULL DEFAULT 0, reserved_ngonka INTEGER NOT NULL,
              cost_ngonka INTEGER NOT NULL DEFAULT 0, cost_source TEXT,
              state TEXT NOT NULL, upstream_id TEXT, evidence TEXT, created REAL NOT NULL,
              UNIQUE(key_id,idem));
            CREATE INDEX IF NOT EXISTS member_usage_wallet ON member_usage(wallet,created);
            CREATE INDEX IF NOT EXISTS member_usage_state ON member_usage(state);
            CREATE INDEX IF NOT EXISTS member_usage_created ON member_usage(created);
            CREATE INDEX IF NOT EXISTS member_usage_wallet_state ON member_usage(wallet,state);
            ''')
        initialize_pool_totals(store)

    def allocate(self, amount, reference, *, upstream_available=None):
        integer(amount, 1)
        if not isinstance(reference, str) or not 1 <= len(reference) <= 150 or not reference.isprintable():
            raise ValueError('A unique non-secret deposit/accounting reference is required')
        with self.store.transaction():
            old = self.db.execute('SELECT amount_ngonka FROM member_funding WHERE reference=?',(reference,)).fetchone()
            if old:
                if old[0] != amount: raise ValueError('Reference already allocated a different amount')
                return False
            if upstream_available is not None:
                integer(upstream_available)
                if self.pool()['available_budget_ngonka']+amount>upstream_available:
                    raise ValueError('Allocation would exceed the currently spendable OpenBroker balance')
            if self.pool()['allocated_ngonka'] + amount > 10**15: raise ValueError('Budget too large')
            self.db.execute('INSERT INTO member_funding VALUES(?,?,?)',(reference,amount,time.time()))
            return True

    def pool(self):
        with self.store.lock:
            row = self.db.execute('SELECT * FROM member_pool_totals WHERE id=1').fetchone()
            if row is None:
                raise ValueError('Missing GNK budget projection; stop and repair the database')
            total, spent, held = row['allocated_ngonka'], row['spent_ngonka'], row['reserved_ngonka']
            return {'allocated_ngonka':total,'budget_spent_ngonka':spent,
                'reserved_ngonka':held,'available_budget_ngonka':max(0,total-spent-held),
                'reconciliation_required':bool(row['review_count']),
                'accounting':'Allocation budget; may include conservative cost estimates. Not a wallet balance.'}

    def totals(self, wallet=None):
        day = int(time.time() // 86400) * 86400
        used_sql='SELECT COALESCE(SUM(tokens),0) FROM member_usage WHERE created>=?'
        held_sql="SELECT COALESCE(SUM(reserved_tokens),0) FROM member_usage WHERE state IN ('reserved','needs_review')"
        used_args=[day];held_args=[]
        if wallet is not None:
            used_sql+=' AND wallet=?';held_sql+=' AND wallet=?'
            used_args.append(wallet);held_args.append(wallet)
        with self.store.lock:
            used=self.db.execute(used_sql,used_args).fetchone()[0]
            held=self.db.execute(held_sql,held_args).fetchone()[0]
        return {'used_tokens':used,'reserved_tokens':held,'resets_at':day+86400}

    def account(self,wallet,daily):
        t=self.totals(wallet)
        return {**t,'daily_tokens':daily,'remaining_tokens':max(0,daily-t['used_tokens']-t['reserved_tokens']),
            'quota_unit':'AI input + output tokens','pool':self.pool()}

    def reserve(self,*args,**kwargs):
        return self._admit(*args,**kwargs,commit=True)

    def preview(self,*args,**kwargs):
        """Run the same admission checks without inserting or charging anything."""
        try:
            self._admit(*args,**kwargs,commit=False)
            return {'allowed':True,'reason_code':None}
        except ValueError as exc:
            return {'allowed':False,'reason_code':str(exc)}

    def _admit(self,key_id,wallet,model,idem,tokens,*,wallet_daily,global_daily,ngonka_per_token,upstream_available,rpm,wallet_concurrency=2,global_rpm=300,global_concurrency=50,commit=True):
        integer(tokens,1);integer(ngonka_per_token,1,1000000);integer(upstream_available)
        amount=tokens*ngonka_per_token;integer(amount,1)
        now=time.time();rid=str(uuid.uuid4())
        with self.store.transaction():
            if key_id is not None or commit:
                key=self.db.execute('SELECT id FROM api_keys WHERE id=? AND wallet=? AND revoked=0',(key_id,wallet)).fetchone()
                if not key:raise ValueError('invalid_key')
            policy=self.store.user_policy(wallet)
            if policy['disabled']:raise ValueError('user_disabled')
            if policy.get('daily_tokens_override') is not None:wallet_daily=policy['daily_tokens_override']
            if commit and self.db.execute('SELECT 1 FROM member_usage WHERE key_id=? AND idem=?',(key_id,idem)).fetchone():
                raise ValueError('duplicate_request')
            pool=self.pool()
            if pool['reconciliation_required']:raise ValueError('reconciliation_required')
            if pool['available_budget_ngonka']<amount:raise ValueError('allowance_pool_unfunded_or_exhausted')
            # Deduct local outstanding holds too: conservative under shared-account concurrency.
            if upstream_available-pool['reserved_ngonka']<amount:raise ValueError('broker_balance_too_low')
            for who,limit,reason in [(wallet,wallet_daily,'wallet_allowance_exhausted'),(None,global_daily,'shared_allowance_exhausted')]:
                t=self.totals(who)
                if t['used_tokens']+t['reserved_tokens']+tokens>limit:raise ValueError(reason)
            count=self.db.execute('SELECT COUNT(*) FROM member_usage WHERE wallet=? AND created>?',(wallet,now-60)).fetchone()[0]
            active=self.db.execute("SELECT COUNT(*) FROM member_usage WHERE wallet=? AND state='reserved'",(wallet,)).fetchone()[0]
            global_count=self.db.execute('SELECT COUNT(*) FROM member_usage WHERE created>?',(now-60,)).fetchone()[0]
            global_active=self.db.execute("SELECT COUNT(*) FROM member_usage WHERE state='reserved'").fetchone()[0]
            if active>=wallet_concurrency:raise ValueError('wallet_concurrency_limit')
            if global_active>=global_concurrency:raise ValueError('global_concurrency_limit')
            if count>=rpm:raise ValueError('wallet_rpm_limit')
            if global_count>=global_rpm:raise ValueError('global_rpm_limit')
            if not commit:return None
            self.db.execute('INSERT INTO member_usage(id,key_id,wallet,idem,model,reserved_tokens,reserved_ngonka,state,created) VALUES(?,?,?,?,?,?,?,?,?)',
                (rid,key_id,wallet,idem,model,tokens,amount,'reserved',now))
        return rid

    def rate_headers(self,wallet,limit):
        import math
        now=time.time()
        with self.store.lock:
            row=self.db.execute('SELECT COUNT(*), MIN(created) FROM member_usage WHERE wallet=? AND created>?',(wallet,now-60)).fetchone()
        reset=max(1,min(60,math.ceil(row[1]+60-now))) if row[1] is not None else 60
        return {'RateLimit-Limit':str(limit),'RateLimit-Remaining':str(max(0,limit-row[0])),
                'RateLimit-Reset':str(reset),'X-RateLimit-Scope':'wallet'}

    def settle(self,rid,tokens,cost,source,upstream_id=None,evidence=None):
        integer(tokens,0,10**9);integer(cost)
        if not isinstance(source,str) or len(source)>100:raise ValueError('Invalid cost source')
        with self.store.transaction():
            row=self.db.execute('SELECT state FROM member_usage WHERE id=?',(rid,)).fetchone()
            if not row or row[0] not in ('reserved','needs_review'):return False
            if row[0]=='needs_review' and not evidence:raise ValueError('Reconciliation evidence required')
            if evidence is not None and (not isinstance(evidence,str) or not 1<=len(evidence)<=200):
                raise ValueError('Invalid evidence reference')
            self.db.execute("UPDATE member_usage SET tokens=?,cost_ngonka=?,cost_source=?,state='settled',upstream_id=?,evidence=? WHERE id=?",
                (tokens,cost,source,upstream_id,evidence,rid))
            return True

    def review(self,rid,upstream_id=None):
        with self.store.lock:
            self.db.execute("UPDATE member_usage SET state='needs_review',upstream_id=? WHERE id=? AND state='reserved'",(upstream_id,rid))

    def pending(self):
        with self.store.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM member_usage WHERE state IN ('reserved','needs_review') ORDER BY created LIMIT 200")]

    def history(self,wallet,limit=50):
        integer(limit,1,100)
        with self.store.lock:
            return [dict(r) for r in self.db.execute(
                'SELECT id,model,tokens,reserved_tokens,cost_ngonka,reserved_ngonka,cost_source,state,created FROM member_usage WHERE wallet=? ORDER BY created DESC LIMIT ?',
                (wallet,limit))]


    def admin_summary(self,days=30):
        integer(days,1,3650)
        today=datetime.now(timezone.utc).date();start=datetime.combine(today-timedelta(days=days-1),datetime.min.time(),tzinfo=timezone.utc).timestamp()
        with self.store.lock:
            total=dict(self.db.execute("""SELECT COUNT(*) requests,COUNT(DISTINCT wallet) users,COALESCE(SUM(tokens),0) tokens,COALESCE(SUM(cost_ngonka),0) cost_ngonka,
                COALESCE(SUM(CASE WHEN state='needs_review' THEN 1 ELSE 0 END),0) needs_review,
                COALESCE(SUM(CASE WHEN state='reserved' THEN 1 ELSE 0 END),0) in_flight
                FROM member_usage WHERE created>=?""",(start,)).fetchone())
            models=[dict(r) for r in self.db.execute("""SELECT model,COUNT(*) requests,COALESCE(SUM(tokens),0) tokens,COALESCE(SUM(cost_ngonka),0) cost_ngonka
                FROM member_usage WHERE created>=? GROUP BY model ORDER BY tokens DESC""",(start,))]
            daily=[dict(r) for r in self.db.execute("""SELECT strftime('%Y-%m-%d',created,'unixepoch') day,COUNT(*) requests,COALESCE(SUM(tokens),0) tokens,COALESCE(SUM(cost_ngonka),0) cost_ngonka
                FROM member_usage WHERE created>=? GROUP BY day ORDER BY day""",(start,))]
            keys=self.db.execute('SELECT COUNT(*) FROM api_keys WHERE revoked=0').fetchone()[0]
        mapping={row['day']:row for row in daily}
        daily=[mapping.get((today-timedelta(days=i)).strftime('%Y-%m-%d'),
            {'day':(today-timedelta(days=i)).strftime('%Y-%m-%d'),'requests':0,'tokens':0,'cost_ngonka':0}) for i in range(days-1,-1,-1)]
        return {**total,'active_keys':keys,'models':models,'daily':daily,'days':days}

    def admin_requests(self,limit=100):
        integer(limit,1,200)
        with self.store.lock:
            return [dict(r) for r in self.db.execute("""SELECT id,wallet,model,tokens,reserved_tokens,cost_ngonka,reserved_ngonka,cost_source,state,upstream_id,created
                FROM member_usage ORDER BY created DESC LIMIT ?""",(limit,))]

    def usage_summary(self,wallet):
        """Holder-only reporting in GNK units; never infer unrecorded prompt counts."""
        today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        start=(today-timedelta(days=6)).timestamp()
        with self.store.lock:
            total=dict(self.db.execute("""SELECT COUNT(*) AS requests,
                COALESCE(SUM(tokens),0) AS total_tokens,
                COALESCE(SUM(cost_ngonka),0) AS cost_ngonka,
                COALESCE(SUM(CASE WHEN state IN ('reserved','needs_review') THEN reserved_ngonka ELSE 0 END),0) AS held_ngonka,
                COALESCE(SUM(CASE WHEN state='needs_review' THEN 1 ELSE 0 END),0) AS needs_review
                FROM member_usage WHERE wallet=?""",(wallet,)).fetchone())
            rows=self.db.execute("""SELECT strftime('%Y-%m-%d',created,'unixepoch') AS day,
                COUNT(*) AS requests,COALESCE(SUM(cost_ngonka),0) AS cost_ngonka,
                COALESCE(SUM(tokens),0) AS tokens FROM member_usage
                WHERE wallet=? AND created>=? GROUP BY day""",(wallet,start)).fetchall()
        mapping={row['day']:dict(row) for row in rows}
        total['daily']=[mapping.get((today-timedelta(days=i)).strftime('%Y-%m-%d'),
            {'day':(today-timedelta(days=i)).strftime('%Y-%m-%d'),'requests':0,'cost_ngonka':0,'tokens':0}) for i in range(6,-1,-1)]
        return {**total,'period':'all_time','daily_timezone':'UTC','access_mode':'holder_allowance',
            'cost_unit':'ngonka','cost_scope':'Allocated project compute; confirmed costs or conservative estimates, not a customer bill.'}
