"""Persistent single-node ledger. All money is integer nano-USD ($1 = 10^9).

Reservations are atomic and remain locked after an ambiguous upstream result.
Do not deploy on ephemeral storage or share the DB through a network filesystem.
"""
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from .security import digest

HOUSEKEEPING_INTERVAL_SECONDS = 60
HOUSEKEEPING_BATCH_SIZE = 1000

class Store:
    def __init__(self, path: str, pepper: str):
        self.pepper = pepper
        self.lock = threading.RLock()
        self._last_housekeeping = None
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(wallet TEXT PRIMARY KEY,balance_nusd INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS credits(reference TEXT PRIMARY KEY,wallet TEXT NOT NULL,amount_nusd INTEGER NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY,wallet TEXT NOT NULL,message TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,wallet TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS api_keys(id TEXT PRIMARY KEY,wallet TEXT NOT NULL,hash TEXT UNIQUE NOT NULL,prefix TEXT NOT NULL,name TEXT NOT NULL,limit_nusd INTEGER NOT NULL,spent_nusd INTEGER NOT NULL DEFAULT 0,revoked INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY,key_id TEXT NOT NULL,wallet TEXT NOT NULL,idem TEXT NOT NULL,model TEXT NOT NULL,reserved_nusd INTEGER NOT NULL,billed_nusd INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL,prompt_tokens INTEGER,completion_tokens INTEGER,upstream_id TEXT,created REAL NOT NULL,UNIQUE(key_id,idem));
        CREATE TABLE IF NOT EXISTS reconciliations(request_id TEXT PRIMARY KEY,billed_nusd INTEGER NOT NULL,evidence TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS rate_hits(bucket TEXT NOT NULL,created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS usage_time ON usage(created);
        CREATE INDEX IF NOT EXISTS usage_wallet ON usage(wallet,created);
        CREATE INDEX IF NOT EXISTS usage_state ON usage(state);
        CREATE INDEX IF NOT EXISTS usage_wallet_state ON usage(wallet,state);
        CREATE INDEX IF NOT EXISTS rate_time ON rate_hits(bucket,created);
        CREATE INDEX IF NOT EXISTS rate_expiry ON rate_hits(created);
        CREATE INDEX IF NOT EXISTS session_expiry ON sessions(expires);
        CREATE INDEX IF NOT EXISTS sessions_wallet ON sessions(wallet);
        CREATE INDEX IF NOT EXISTS challenge_expiry ON challenges(expires);
        CREATE TABLE IF NOT EXISTS operator_settings(key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS user_admin(wallet TEXT PRIMARY KEY,disabled INTEGER NOT NULL DEFAULT 0,daily_tokens_override INTEGER,note TEXT NOT NULL DEFAULT '',updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS business_entries(reference TEXT PRIMARY KEY,category TEXT NOT NULL,amount_nusd INTEGER NOT NULL,note TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS business_time ON business_entries(created);
        CREATE TABLE IF NOT EXISTS admin_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,target TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS admin_audit_time ON admin_audit(created);
        CREATE INDEX IF NOT EXISTS api_keys_wallet_active ON api_keys(wallet,revoked);

        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.execute('COMMIT')
            except BaseException:
                # Interrupted maintenance must not leave the shared connection locked.
                if self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise

    def close(self):
        with self.lock: self.db.close()

    def throttle(self, bucket, limit, seconds=60):
        now = time.time()
        # The lock also protects the in-process housekeeping schedule. Expiry and
        # rate admission are still checked on EVERY request, independently of GC.
        with self.lock:
            monotonic_now = time.monotonic()
            due = (self._last_housekeeping is None or
                   monotonic_now - self._last_housekeeping >= HOUSEKEEPING_INTERVAL_SECONDS)
            with self.transaction():
                if due:
                    for table, column, cutoff in (
                        ('rate_hits', 'created', now - 7200),
                        ('challenges', 'expires', now),
                        ('sessions', 'expires', now),
                    ):
                        # Fixed identifiers only; bound each pass to avoid long
                        # writer locks when starting with a large expired backlog.
                        self.db.execute(
                            f'DELETE FROM {table} WHERE rowid IN '
                            f'(SELECT rowid FROM {table} WHERE {column}<? LIMIT ?)',
                            (cutoff, HOUSEKEEPING_BATCH_SIZE))
                count = self.db.execute(
                    'SELECT COUNT(*) FROM rate_hits WHERE bucket=? AND created>?',
                    (bucket, now - seconds)).fetchone()[0]
                rejected = count >= limit
                if not rejected:
                    self.db.execute('INSERT INTO rate_hits VALUES(?,?)', (bucket, now))
            if due:
                self._last_housekeeping = monotonic_now
        # Commit housekeeping even when denying admission; never insert a hit for
        # a rejected request and never change the configured rate limit.
        if rejected:
            raise ValueError('rate_limit')

    def ensure_account(self, wallet):
        with self.lock: self.db.execute('INSERT OR IGNORE INTO accounts(wallet) VALUES(?)',(wallet,))

    def account(self, wallet):
        with self.lock:
            row=self.db.execute('SELECT * FROM accounts WHERE wallet=?',(wallet,)).fetchone()
            return dict(row) if row else None

    def credit(self, wallet, amount, reference):
        if type(amount) is not int or not 0 <= amount <= 10**15 or not 1 <= len(reference) <= 200:
            raise ValueError('Invalid credit or reference')
        with self.transaction():
            old=self.db.execute('SELECT wallet,amount_nusd FROM credits WHERE reference=?',(reference,)).fetchone()
            if old:
                if tuple(old)!=(wallet,amount): raise ValueError('Reference already exists with different details')
                return
            self.db.execute('INSERT OR IGNORE INTO accounts(wallet) VALUES(?)',(wallet,))
            current=self.db.execute('SELECT balance_nusd FROM accounts WHERE wallet=?',(wallet,)).fetchone()[0]
            if current+amount > 10**15: raise ValueError('Balance limit exceeded')
            self.db.execute('INSERT INTO credits VALUES(?,?,?,?)',(reference,wallet,amount,time.time()))
            self.db.execute('UPDATE accounts SET balance_nusd=balance_nusd+? WHERE wallet=?',(amount,wallet))


    def operator_settings(self):
        import json
        with self.lock:
            rows=self.db.execute('SELECT key,value_json FROM operator_settings').fetchall()
        result={}
        for row in rows:
            try: result[row['key']]=json.loads(row['value_json'])
            except Exception: continue
        return result

    def set_operator_settings(self, values):
        import json
        now=time.time()
        with self.transaction():
            for key,value in values.items():
                self.db.execute('INSERT INTO operator_settings(key,value_json,updated) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated=excluded.updated',
                    (key,json.dumps(value,separators=(',',':')),now))
        return self.operator_settings()

    def user_policy(self,wallet):
        with self.lock:
            row=self.db.execute('SELECT wallet,disabled,daily_tokens_override,note,updated FROM user_admin WHERE wallet=?',(wallet,)).fetchone()
        if not row:return {'wallet':wallet,'disabled':False,'daily_tokens_override':None,'note':''}
        d=dict(row);d['disabled']=bool(d['disabled']);return d

    def set_user_policy(self,wallet,disabled=False,daily_tokens_override=None,note=''):
        if type(disabled) is not bool:raise ValueError('disabled must be boolean')
        if daily_tokens_override is not None and (type(daily_tokens_override) is not int or not 1<=daily_tokens_override<=10**9):raise ValueError('Invalid daily token override')
        if not isinstance(note,str) or len(note)>500 or not note.isprintable():raise ValueError('Invalid note')
        self.ensure_account(wallet);now=time.time()
        with self.lock:
            self.db.execute('INSERT INTO user_admin(wallet,disabled,daily_tokens_override,note,updated) VALUES(?,?,?,?,?) ON CONFLICT(wallet) DO UPDATE SET disabled=excluded.disabled,daily_tokens_override=excluded.daily_tokens_override,note=excluded.note,updated=excluded.updated',
                (wallet,int(disabled),daily_tokens_override,note,now))
        return self.user_policy(wallet)

    def admin_users(self,limit=100,offset=0,q=''):
        if type(limit) is not int or not 1<=limit<=200 or type(offset) is not int or offset<0:raise ValueError('Invalid pagination')
        if not isinstance(q,str) or len(q)>64 or not q.isprintable():raise ValueError('Invalid search')
        where='WHERE a.wallet LIKE ?' if q else ''
        params=('%'+q+'%',limit,offset) if q else (limit,offset)
        with self.lock:
            rows=self.db.execute(f"""SELECT a.wallet,
              COALESCE(k.active_keys,0) active_keys,COALESCE(m.requests,0) requests,COALESCE(m.tokens,0) tokens,COALESCE(m.cost_ngonka,0) cost_ngonka,
              COALESCE(u.disabled,0) disabled,u.daily_tokens_override,COALESCE(u.note,'') note
              FROM accounts a
              LEFT JOIN (SELECT wallet,COUNT(*) active_keys FROM api_keys WHERE revoked=0 GROUP BY wallet) k ON k.wallet=a.wallet
              LEFT JOIN (SELECT wallet,COUNT(*) requests,COALESCE(SUM(tokens),0) tokens,COALESCE(SUM(cost_ngonka),0) cost_ngonka FROM member_usage GROUP BY wallet) m ON m.wallet=a.wallet
              LEFT JOIN user_admin u ON u.wallet=a.wallet
              {where}
              ORDER BY COALESCE(m.tokens,0) DESC,a.wallet LIMIT ? OFFSET ?""",params).fetchall()
        out=[]
        for row in rows:
            d=dict(row);d['disabled']=bool(d['disabled']);out.append(d)
        return out

    def audit(self,action,target,note=''):
        for value,label,maximum in ((action,'action',80),(target,'target',200),(note,'note',500)):
            if not isinstance(value,str) or len(value)>maximum or not value.isprintable():raise ValueError('Invalid audit '+label)
        if not action:raise ValueError('Invalid audit action')
        with self.lock:self.db.execute('INSERT INTO admin_audit(action,target,note,created) VALUES(?,?,?,?)',(action,target,note,time.time()))

    def audit_events(self,limit=100):
        if type(limit) is not int or not 1<=limit<=200:raise ValueError('Invalid audit limit')
        with self.lock:return [dict(r) for r in self.db.execute('SELECT id,action,target,note,created FROM admin_audit ORDER BY id DESC LIMIT ?',(limit,))]

    def add_business_entry(self,category,amount_nusd,reference,note=''):
        allowed={'creator_fee','api_revenue','subscription_revenue','hosting','rpc','support','refund','tax','developer_payout','gnk_purchase','other'}
        if category not in allowed:raise ValueError('Invalid business category')
        if type(amount_nusd) is not int or amount_nusd==0 or abs(amount_nusd)>10**18:raise ValueError('Invalid business amount')
        if not isinstance(reference,str) or not 1<=len(reference)<=200 or not reference.isprintable():raise ValueError('Invalid business reference')
        if not isinstance(note,str) or len(note)>500 or not note.isprintable():raise ValueError('Invalid business note')
        with self.lock:
            self.db.execute('INSERT INTO business_entries(reference,category,amount_nusd,note,created) VALUES(?,?,?,?,?)',(reference,category,amount_nusd,note,time.time()))

    def business_summary(self,days=30):
        if type(days) is not int or not 1<=days<=3650:raise ValueError('Invalid period')
        start=time.time()-days*86400
        with self.lock:
            row=self.db.execute('SELECT COALESCE(SUM(CASE WHEN amount_nusd>0 THEN amount_nusd ELSE 0 END),0) revenue,COALESCE(SUM(CASE WHEN amount_nusd<0 THEN -amount_nusd ELSE 0 END),0) expense,COALESCE(SUM(amount_nusd),0) net,COUNT(*) entries FROM business_entries WHERE created>=?',(start,)).fetchone()
            recent=[dict(r) for r in self.db.execute('SELECT reference,category,amount_nusd,note,created FROM business_entries WHERE created>=? ORDER BY created DESC LIMIT 100',(start,))]
        return {**dict(row),'days':days,'recent':recent}

    def challenge(self, wallet, message, challenge_id):
        with self.lock:
            self.db.execute('INSERT INTO challenges VALUES(?,?,?,?)',(challenge_id,wallet,message,time.time()+300))

    def consume_challenge(self, challenge_id):
        with self.transaction():
            row=self.db.execute('SELECT * FROM challenges WHERE id=?',(challenge_id,)).fetchone()
            self.db.execute('DELETE FROM challenges WHERE id=?',(challenge_id,))
            if not row or row['expires'] < time.time(): return None
            return dict(row)

    def new_session(self, wallet):
        token=secrets.token_urlsafe(32)
        self.ensure_account(wallet)
        with self.lock: self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token,self.pepper),wallet,time.time()+3600))
        return token

    def session_wallet(self, token):
        if not token: return None
        with self.lock:
            row=self.db.execute('SELECT wallet FROM sessions WHERE hash=? AND expires>?',(digest(token,self.pepper),time.time())).fetchone()
        return row[0] if row else None

    def logout(self, token):
        with self.lock: self.db.execute('DELETE FROM sessions WHERE hash=?',(digest(token or '',self.pepper),))

    def logout_all(self, wallet):
        with self.transaction():
            count=self.db.execute('DELETE FROM sessions WHERE wallet=?',(wallet,)).rowcount
            self.audit('wallet_sessions_revoked',wallet,str(count)+' sessions')
            return count

    def revoke_all_keys(self, wallet):
        with self.transaction():
            count=self.db.execute('UPDATE api_keys SET revoked=1 WHERE wallet=? AND revoked=0',(wallet,)).rowcount
            self.audit('wallet_keys_revoked',wallet,str(count)+' keys')
            return count

    def issue_key(self, wallet, name, limit_nusd):
        raw='sv_'+secrets.token_urlsafe(32)
        key_id=str(uuid.uuid4())
        with self.transaction():
            count=self.db.execute('SELECT COUNT(*) FROM api_keys WHERE wallet=? AND revoked=0',(wallet,)).fetchone()[0]
            if count>=10: raise ValueError('Maximum 10 active keys per wallet')
            self.db.execute('INSERT INTO api_keys(id,wallet,hash,prefix,name,limit_nusd,created) VALUES(?,?,?,?,?,?,?)',
                (key_id,wallet,digest(raw,self.pepper),raw[:12],name,limit_nusd,time.time()))
        return {'id':key_id,'key':raw,'name':name,'prefix':raw[:12],'limit_nusd':limit_nusd}

    def keys(self, wallet):
        with self.lock:
            return [dict(x) for x in self.db.execute('SELECT id,prefix,name,limit_nusd,spent_nusd,revoked,created FROM api_keys WHERE wallet=? ORDER BY created DESC',(wallet,))]

    def lookup_key(self, raw):
        if not raw or not raw.startswith(('sv_','grd_')) or len(raw)>100: return None
        with self.lock:
            row=self.db.execute('SELECT * FROM api_keys WHERE hash=? AND revoked=0',(digest(raw,self.pepper),)).fetchone()
        return dict(row) if row else None

    def revoke(self, key_id, wallet):
        with self.lock:
            return self.db.execute('UPDATE api_keys SET revoked=1 WHERE id=? AND wallet=?',(key_id,wallet)).rowcount>0

    def reserve(self,key_id,wallet,amount,idem,model,rate_limit,*,daily_budget_nusd=None,wallet_daily_budget_nusd=None):
        if type(amount) is not int or amount<=0: raise ValueError('Invalid reservation')
        now=time.time(); request_id=str(uuid.uuid4())
        with self.transaction():
            key=self.db.execute('SELECT * FROM api_keys WHERE id=? AND wallet=? AND revoked=0',(key_id,wallet)).fetchone()
            if not key: raise ValueError('invalid_key')
            if self.db.execute('SELECT 1 FROM usage WHERE key_id=? AND idem=?',(key_id,idem)).fetchone(): raise ValueError('duplicate_request')
            count=self.db.execute('SELECT COUNT(*) FROM usage WHERE wallet=? AND created>?',(wallet,now-60)).fetchone()[0]
            global_count=self.db.execute('SELECT COUNT(*) FROM usage WHERE created>?',(now-60,)).fetchone()[0]
            active=self.db.execute("SELECT COUNT(*) FROM usage WHERE wallet=? AND state='reserved'",(wallet,)).fetchone()[0]
            if count>=rate_limit or global_count>=300 or active>=3: raise ValueError('rate_limit')
            if self.db.execute("SELECT 1 FROM usage WHERE state='needs_review' LIMIT 1").fetchone():
                raise ValueError('billing_review_required')
            if daily_budget_nusd is not None and self.budget_usage()+amount>daily_budget_nusd:
                raise ValueError('daily_budget')
            if wallet_daily_budget_nusd is not None and self.budget_usage(wallet)+amount>wallet_daily_budget_nusd:
                raise ValueError('wallet_daily_budget')
            if key['spent_nusd']+amount>key['limit_nusd']: raise ValueError('key_limit')
            row=self.db.execute('SELECT balance_nusd FROM accounts WHERE wallet=?',(wallet,)).fetchone()
            if not row or row[0]<amount: raise ValueError('insufficient_credit')
            self.db.execute('UPDATE accounts SET balance_nusd=balance_nusd-? WHERE wallet=?',(amount,wallet))
            self.db.execute('UPDATE api_keys SET spent_nusd=spent_nusd+? WHERE id=?',(amount,key_id))
            self.db.execute('INSERT INTO usage(id,key_id,wallet,idem,model,reserved_nusd,state,created) VALUES(?,?,?,?,?,?,?,?)',
                (request_id,key_id,wallet,idem,model,amount,'reserved',now))
        return request_id

    def settle(self, request_id, billed, state='settled', prompt=None, completion=None, upstream_id=None, evidence=None):
        if type(billed) is not int or not 0<=billed<=10**15: raise ValueError('Invalid settlement')
        if state=='operator_settled' and (not evidence or len(evidence)>200): raise ValueError('An evidence reference of 1–200 characters is required')
        with self.transaction():
            row=self.db.execute('SELECT * FROM usage WHERE id=?',(request_id,)).fetchone()
            if not row or row['state'] not in ('reserved','needs_review'): return False
            difference=row['reserved_nusd']-billed
            self.db.execute('UPDATE accounts SET balance_nusd=balance_nusd+? WHERE wallet=?',(difference,row['wallet']))
            self.db.execute('UPDATE api_keys SET spent_nusd=spent_nusd-? WHERE id=?',(difference,row['key_id']))
            self.db.execute('UPDATE usage SET billed_nusd=?,state=?,prompt_tokens=?,completion_tokens=?,upstream_id=? WHERE id=?',
                (billed,state,prompt,completion,upstream_id,request_id))
            if evidence:
                self.db.execute('INSERT INTO reconciliations VALUES(?,?,?,?)',(request_id,billed,evidence,time.time()))
            return True

    def review(self, request_id, upstream_id=None):
        with self.lock: self.db.execute("UPDATE usage SET state='needs_review',upstream_id=? WHERE id=? AND state='reserved'",(upstream_id,request_id))

    def history(self, wallet):
        with self.lock:
            return [dict(r) for r in self.db.execute('SELECT id,model,billed_nusd,reserved_nusd,state,prompt_tokens,completion_tokens,created FROM usage WHERE wallet=? ORDER BY created DESC LIMIT 100',(wallet,))]

    def pending(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT id,wallet,model,reserved_nusd,state,upstream_id,created FROM usage WHERE state IN ('reserved','needs_review') ORDER BY created LIMIT 200")]


    def needs_review(self):
        """A conservative global circuit breaker until uncertain charges are reconciled."""
        with self.lock:
            return bool(self.db.execute("SELECT 1 FROM usage WHERE state='needs_review' LIMIT 1").fetchone())

    def budget_usage(self, wallet=None):
        """UTC-day retail spend plus active reservations, not an upstream-cost estimate."""
        start=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        sql="SELECT COALESCE(SUM(CASE WHEN state IN ('reserved','needs_review') THEN reserved_nusd ELSE billed_nusd END),0) FROM usage WHERE (created>=? OR state IN ('reserved','needs_review'))"
        params=[start]
        if wallet is not None:
            sql+=' AND wallet=?'; params.append(wallet)
        with self.lock:
            return self.db.execute(sql,params).fetchone()[0]

    def usage_summary(self, wallet):
        """All-time totals plus a seven-day UTC series. Never stores request content."""
        today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        start=(today-timedelta(days=6)).timestamp()
        with self.lock:
            total=dict(self.db.execute("""SELECT COUNT(*) AS requests,
                COALESCE(SUM(billed_nusd),0) AS billed_nusd,
                COALESCE(SUM(CASE WHEN state IN ('reserved','needs_review') THEN reserved_nusd ELSE 0 END),0) AS held_nusd,
                COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens),0) AS completion_tokens,
                COALESCE(SUM(CASE WHEN state='needs_review' THEN 1 ELSE 0 END),0) AS needs_review
                FROM usage WHERE wallet=?""",(wallet,)).fetchone())
            rows=self.db.execute("""SELECT strftime('%Y-%m-%d',created,'unixepoch') AS day,
                COUNT(*) AS requests,COALESCE(SUM(billed_nusd),0) AS billed_nusd,
                COALESCE(SUM(prompt_tokens+completion_tokens),0) AS tokens
                FROM usage WHERE wallet=? AND created>=? GROUP BY day""",(wallet,start)).fetchall()
        mapping={row['day']:dict(row) for row in rows}
        total['total_tokens']=total['prompt_tokens']+total['completion_tokens']
        total['daily']=[mapping.get((today-timedelta(days=i)).strftime('%Y-%m-%d'),
            {'day':(today-timedelta(days=i)).strftime('%Y-%m-%d'),'requests':0,'billed_nusd':0,'tokens':0}) for i in range(6,-1,-1)]
        total['period']='all_time'; total['daily_timezone']='UTC'
        return total
