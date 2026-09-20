"""Server-only, read-only QuickNode adapters. Never signs or sends transactions.

Only operator-configured endpoints are used. Diagnostics redact URLs and upstream
errors because RPC/Metis credentials often live in URL paths.
"""
import asyncio
import json
import re
import time
from decimal import Decimal
from urllib.parse import urlparse

MAINNET_GENESIS='5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d'
SOL_MINT='So11111111111111111111111111111111111111112'
USDC_MINT='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
READ_METHODS={'getGenesisHash','getHealth','getSlot','getAccountInfo','getTokenAccountsByOwner','qn_estimatePriorityFees'}


def validate_endpoint(value,scheme='https'):
    if not value:return
    p=urlparse(value)
    if p.scheme!=scheme or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('Use a full server-side endpoint URL with no query, userinfo or fragment')
    if p.hostname in ('localhost','127.0.0.1','::1'):
        raise ValueError('Local RPC endpoints are not allowed in this configuration')


async def bounded_json(response,maximum=2_000_000):
    response.raise_for_status();parts=[];size=0
    async for chunk in response.aiter_bytes():
        size+=len(chunk)
        if size>maximum:raise ValueError('Response too large')
        parts.append(chunk)
    return json.loads(b''.join(parts))


class SolanaRPC:
    def __init__(self,client,url,rps=15,concurrency=8):
        self.client,self.url=client,url
        self.rps=rps;self.slots=asyncio.Semaphore(concurrency)
        self.gate=asyncio.Lock();self.last=0.0
        self.genesis_lock=asyncio.Lock();self.genesis_at=0.0

    async def call(self,method,params=None):
        if method not in READ_METHODS:raise ValueError('Only allowlisted read-only RPC methods are supported')
        if not self.url:raise ValueError('RPC is not configured')
        async with asyncio.timeout(10):
            async with self.slots:
                async with self.gate:
                    wait=1/self.rps-(time.monotonic()-self.last)
                    if wait>0:await asyncio.sleep(wait)
                    self.last=time.monotonic()
                async with self.client.stream('POST',self.url,json={
                    'jsonrpc':'2.0','id':1,'method':method,'params':params or []},timeout=8) as response:
                    data=await bounded_json(response)
                if not isinstance(data,dict) or data.get('error') or 'result' not in data:
                    raise ValueError('RPC call did not return a result')
                return data['result']

    async def ensure_mainnet(self):
        async with self.genesis_lock:
            if time.monotonic()-self.genesis_at<300:return
            if await self.call('getGenesisHash')!=MAINNET_GENESIS:raise ValueError('Wrong RPC network')
            self.genesis_at=time.monotonic()

    async def diagnostics(self):
        result={'status':'unconfigured','mainnet_verified':False,'checked_at':int(time.time())}
        if not self.url:return result
        try:
            if await self.call('getGenesisHash')!=MAINNET_GENESIS:
                return {**result,'status':'wrong_network'}
            result['mainnet_verified']=True
            health=await self.call('getHealth')
            slot=await self.call('getSlot',[{'commitment':'finalized'}])
            if health!='ok' or type(slot) is not int or slot<1:raise ValueError('Invalid health or slot')
            return {**result,'status':'ready','slot':slot}
        except Exception:
            return {**result,'status':'unavailable','message':'RPC read failed. Check server connectivity, endpoint authorization and provider status.'}

    async def priority(self):
        # Fee units are NOT interchangeable: compute-unit rate is micro-lamports/CU.
        value=await self.call('qn_estimatePriorityFees',[{'last_n_blocks':100,'api_version':2}])
        if not isinstance(value,dict):raise ValueError('Invalid fee response')
        output={}
        for section,unit in (('per_compute_unit','micro_lamports_per_compute_unit'),('per_transaction','lamports')):
            obj=value.get(section,{})
            if isinstance(obj,dict):
                n=obj.get('recommended')
                if isinstance(n,(int,float)) and not isinstance(n,bool) and 0<=n<=10**12:
                    output[section]={'recommended':n,'unit':unit}
        if not output:raise ValueError('No fee recommendations in response')
        return {'estimates':output,'transactions_sent':0,'checked_at':int(time.time())}


class MetisQuotes:
    def __init__(self,client,url,holder_mint='',decimals=6):
        self.client,self.url,self.holder_mint,self.decimals=client,url,holder_mint,decimals

    async def quote(self,asset,amount,slippage):
        if asset=='SOL':mint,decimals=SOL_MINT,9
        elif asset=='PROJECT' and self.holder_mint:mint,decimals=self.holder_mint,self.decimals
        else:raise ValueError('Only SOL or the configured project token can be quoted to native Solana USDC')
        if not isinstance(amount,str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,18})?',amount):
            raise ValueError('Use a plain positive decimal amount')
        value=Decimal(amount);raw=value*10**decimals
        if value<=0 or raw!=raw.to_integral_value() or raw>2**64-1:raise ValueError('Amount is outside the token precision or range')
        if not self.url:raise LookupError('Metis API endpoint is not configured; the dashboard URL is not an API endpoint')
        params={'inputMint':mint,'outputMint':USDC_MINT,'amount':str(int(raw)),
                'slippageBps':str(slippage),'swapMode':'ExactIn','restrictIntermediateTokens':'true'}
        async with asyncio.timeout(10):
            async with self.client.stream('GET',self.url.rstrip('/')+'/quote',params=params,timeout=8) as r:
                d=await bounded_json(r,maximum=512000)
        try:
            if not isinstance(d,dict) or d.get('inputMint')!=mint or d.get('outputMint')!=USDC_MINT:
                raise ValueError('Mismatched quote mints')
            if d.get('inAmount')!=str(int(raw)) or d.get('swapMode')!='ExactIn' or d.get('slippageBps')!=slippage:
                raise ValueError('Mismatched quote terms')
            def integer_string(v):
                if not isinstance(v,str) or not re.fullmatch(r'[0-9]{1,20}',v):raise ValueError('Invalid quote amount')
                return int(v)
            out=integer_string(d.get('outAmount'));minimum=integer_string(d.get('otherAmountThreshold'))
            impact=Decimal(str(d.get('priceImpactPct','NaN')))
            if not impact.is_finite() or abs(impact)>Decimal('0.03'):raise ValueError('Price impact exceeds 3%')
            if not 0<minimum<=out or minimum*10000<out*(10000-slippage)-10000:
                raise ValueError('Minimum output exceeds configured slippage')
            if type(d.get('contextSlot')) is not int or d['contextSlot']<1:raise ValueError('Missing quote slot')
            if not isinstance(d.get('routePlan'),list) or not d['routePlan']:raise ValueError('No liquidity route')
        except Exception as e:raise RuntimeError('Swap provider returned invalid or unsafe quote terms') from e
        now=int(time.time())
        def human(n):return format(Decimal(n)/10**6,'f').rstrip('0').rstrip('.') if n%10**6 else str(n//10**6)
        # Only explicitly allowed fields leave this boundary; no upstream URLs,
        # token metadata, tx payloads, or API credentials are forwarded to clients.
        return {'asset':asset,'input_mint':mint,'output_mint':USDC_MINT,'input_amount':amount,
                'expected_usdc':human(out),'minimum_usdc':human(minimum),'minimum_raw':str(minimum),
                'slippage_bps':slippage,'price_impact_pct':str(impact),'context_slot':d['contextSlot'],
                'quoted_at':now,'local_expires_at':now+15,'execution_enabled':False,'credits_issued':0,
                'notice':'Indicative read-only quote. The 15-second expiry is our display policy, not a guaranteed fill. No transaction was built or sent.'}
