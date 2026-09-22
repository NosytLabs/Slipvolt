"""Documented OpenBroker reads plus a sanitized, cached public stats adapter.

The registry is used by OpenBroker's public stats UI, but is not a stable
versioned API contract. An upstream change produces unavailable, never zero.
"""
from .http_boundary import isolated_stream
from copy import deepcopy
import asyncio
import json
import re
import time
from urllib.parse import quote
from datetime import date, datetime, timezone, timedelta
from .membership import integer

BASE='https://api.openbroker.gonka.gg'
MODEL_METADATA_URL='https://proxy.gonka.gg/v1/models'
READ_TIMEOUT_SECONDS=8
PUBLIC_BALANCE_TTL_SECONDS=15
NETWORK_TTL_SECONDS=60
NETWORK_STALE_LIMIT_SECONDS=300


def quantity(value):
    if isinstance(value,str) and value.isascii() and value.isdigit() and len(value)<=16:value=int(value)
    return integer(value)


class Broker:
    def __init__(self,client,key=''):
        self.client,self.key=client,key
        self._network = None
        self._network_at = None
        self._attempt_at = None
        self._network_failed = False
        self._lock=asyncio.Lock()
        self._public_balance_lock=asyncio.Lock()
        self._public_balance=None;self._public_balance_attempt=None

    async def read(self,path,private=False,max_bytes=2_000_000):
        if not isinstance(path,str) or not path.startswith('/') or path.startswith('//') or any(x in path for x in ('\\','\r','\n','#')):
            raise ValueError('Unsupported provider route')
        headers={'Authorization':'Bearer '+self.key} if private else {}
        if private and not self.key:raise ValueError('OpenBroker key not configured')
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            async with isolated_stream(self.client,'GET',BASE+path,headers=headers,timeout=READ_TIMEOUT_SECONDS) as r:
                r.raise_for_status();chunks=[];length=0
                async for chunk in r.aiter_bytes():
                    length+=len(chunk)
                    if length>max_bytes:raise ValueError('Upstream response too large')
                    chunks.append(chunk)
                value=json.loads(b''.join(chunks))
                if not isinstance(value,dict):raise ValueError('Expected an object')
                return value

    async def read_url(self,url,max_bytes=2_000_000):
        if url!=MODEL_METADATA_URL:raise ValueError('Unsupported metadata URL')
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            async with isolated_stream(self.client,'GET',url,timeout=READ_TIMEOUT_SECONDS) as r:
                r.raise_for_status();chunks=[];length=0
                async for chunk in r.aiter_bytes():
                    length+=len(chunk)
                    if length>max_bytes:raise ValueError('Upstream response too large')
                    chunks.append(chunk)
                value=json.loads(b''.join(chunks))
                if not isinstance(value,dict):raise ValueError('Expected an object')
                return value

    async def model_metadata(self):
        d=await self.read_url(MODEL_METADATA_URL)
        rows=d.get('data')
        if not isinstance(rows,list) or len(rows)>1000:raise ValueError('Invalid model metadata')
        result={}
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str):continue
            item={'id':row['id']}
            for key in ('context_length','max_completion_tokens'):
                value=row.get(key)
                if type(value) is int and 0<value<=10**7:item[key]=value
            result[row['id']]=item
        return result

    async def provider_status(self):
        d=await self.read('/api/status',max_bytes=4_000_000)
        models=d.get('models')
        if not isinstance(models,list):return {'status':d.get('status','unknown'),'models':[],'updated_at':d.get('updated_at')}
        clean=[]
        for row in models:
            if not isinstance(row,dict) or not isinstance(row.get('model'),str):continue
            clean.append({k:row.get(k) for k in ('model','status','routable','capacity_available_pct','capacity_lost_pct','load_pct','in_flight_requests','max_concurrency','effective_max_concurrency') if k in row})
        return {'status':d.get('status','unknown'),'models':clean,'updated_at':d.get('updated_at')}

    async def usage_summary(self, days=30):
        if type(days) is not int or not 1<=days<=90:raise ValueError('Invalid usage window')
        today=datetime.now(timezone.utc).date();start=today-timedelta(days=days-1)
        path=f'/v1/usage/summary?from={start.isoformat()}&to={today.isoformat()}'
        d=await self.read(path,True,max_bytes=4_000_000)
        totals=d.get('totals')
        if not isinstance(totals,dict):raise ValueError('Invalid usage summary')
        clean={}
        for key in ('requests','errors','prompt_tokens','completion_tokens','total_tokens','cost_ngonka'):
            if key in totals:clean[key]=quantity(totals[key])
        def clean_row(row, date_key=False):
            if not isinstance(row,dict):raise ValueError('Invalid usage row')
            model=row.get('model')
            if not isinstance(model,str) or not 1<=len(model)<=200 or not model.isprintable():raise ValueError('Invalid usage model')
            out={'model':model}
            if date_key:
                day=row.get('date')
                if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('Invalid usage date')
                date.fromisoformat(day);out={'date':day,**out}
            for key in ('requests','errors','total_tokens','cost_ngonka'):
                out[key]=quantity(row.get(key,0))
            return out
        raw_models=d.get('models',[])
        raw_days=d.get('days',[])
        if not isinstance(raw_models,list) or not isinstance(raw_days,list) or len(raw_models)>500 or len(raw_days)>10000:
            raise ValueError('Invalid usage rows')
        models=[clean_row(row) for row in raw_models]
        rows=[clean_row(row,True) for row in raw_days]
        daily_map={}
        for row in rows:
            aggregate=daily_map.setdefault(row['date'],{'date':row['date'],'requests':0,'errors':0,'total_tokens':0,'cost_ngonka':0})
            for key in ('requests','errors','total_tokens','cost_ngonka'):aggregate[key]+=row[key]
        return {'totals':clean,'models':models,'days':rows,'daily':[daily_map[key] for key in sorted(daily_map)]}

    async def balance(self):
        d=await self.read('/v1/balance',True)
        result={'available_ngonka':quantity(d['available_ngonka'])}
        for key in ('balance_ngonka','reserved_ngonka','min_reserve_ngonka'):
            result[key]=quantity(d[key]) if key in d else None
        result['status']=d.get('status') if d.get('status') in ('active','pending_deposit','suspended','inactive') else 'unreported'
        if result['status'] in ('pending_deposit','suspended','inactive'):result['available_ngonka']=0
        result['observed_at']=int(time.time())
        result['source']=BASE+'/v1/balance'
        return result

    async def public_balance(self):
        """Display cache only. Funding authorization always calls balance() fresh."""
        async with self._public_balance_lock:
            now=time.monotonic()
            if self._public_balance_attempt is not None and now-self._public_balance_attempt<PUBLIC_BALANCE_TTL_SECONDS:
                if self._public_balance is None:
                    raise ValueError('Public broker balance temporarily unavailable')
                return dict(self._public_balance,cached=True)
            self._public_balance_attempt=now
            self._public_balance=None
            self._public_balance=await self.balance()
            return dict(self._public_balance,cached=False)

    async def request_cost(self,upstream_id,model,tokens,estimate):
        try:
            if not upstream_id:raise ValueError()
            d=await self.read('/v1/usage/'+quote(upstream_id,safe=''),True)
            if upstream_id not in (d.get('response_id'),d.get('x_request_id'),d.get('id')):raise ValueError()
            if d.get('model')!=model or quantity(d['total_tokens'])!=tokens:raise ValueError()
            cost=quantity(d['cost_ngonka']);source=d.get('cost_source','')
            if isinstance(source,str) and source.startswith('devshard_') and len(source)<=100:
                return cost,source
            return max(cost,estimate),'conservative_budget_estimate'
        except Exception:
            return estimate,'conservative_budget_estimate'

    async def network(self):
        async with self._lock:
            now = time.monotonic()
            if self._attempt_at is not None and now - self._attempt_at < NETWORK_TTL_SECONDS:
                return self._network_snapshot(now)
            self._attempt_at = now
            # A cancelled or failed refresh must not make old data look current.
            self._network_failed = True
            try:
                d=await self.read('/api/registry/brokers',max_bytes=4_000_000)
                brokers=d['brokers'];rows=d['daily_usage']
                if not isinstance(brokers,list) or not isinstance(rows,list) or len(rows)>30000 or len(brokers)>5000:raise ValueError()
                if not rows:raise ValueError('No observations')
                totals={'requests':0,'tokens':0,'cost_ngonka':0};dates=[];daily_map={}
                for row in rows:
                    day=row['date']
                    if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError()
                    date.fromisoformat(day)  # Regex shape alone accepts February 30.
                    dates.append(day)
                    requests=quantity(row['requests']);tokens=quantity(row['total_tokens']);cost=quantity(row['cost_ngonka'])
                    totals['requests']+=requests;totals['tokens']+=tokens;totals['cost_ngonka']+=cost
                    aggregate=daily_map.setdefault(day,{'date':day,'requests':0,'tokens':0,'cost_ngonka':0})
                    aggregate['requests']+=requests;aggregate['tokens']+=tokens;aggregate['cost_ngonka']+=cost
                self._network={'scope':'OpenBroker network; not Slipvolt usage',
                    'source':BASE+'/api/registry/brokers','source_page':'https://openbroker.gonka.gg/stats',
                    'status':'available','observed_at':int(time.time()),'window_from':min(dates),'window_to':max(dates),
                    'active_brokers':sum(b.get('status')=='active' for b in brokers if isinstance(b,dict)),
                    'totals':totals,'daily':[daily_map[key] for key in sorted(daily_map)],
                    'aggregation':'All returned registry usage rows; may differ from website filters.'}
                self._network_at = time.monotonic()
                self._network_failed = False
            except Exception:
                pass  # Keep a bounded stale display, never an authorization cache.
            return self._network_snapshot(time.monotonic())

    def _network_snapshot(self, now):
        if self._network is None or self._network_at is None:
            return self.unavailable()
        age = now - self._network_at
        if age < 0 or age > NETWORK_STALE_LIMIT_SECONDS:
            return self.unavailable()
        return dict(deepcopy(self._network),
                    stale=self._network_failed or age >= NETWORK_TTL_SECONDS)

    @staticmethod
    def unavailable():
        return {'status':'unavailable','scope':'OpenBroker network; not Slipvolt usage',
            'source_page':'https://openbroker.gonka.gg/stats','totals':None,'observed_at':None,'stale':True}
