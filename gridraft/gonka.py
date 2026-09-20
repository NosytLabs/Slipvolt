"""Read a configured self-custody GNK wallet; no keys, signing, or funds transfer."""
import asyncio
import json
import time
from .broker import quantity

BANK='https://rpc.gonka.gg/chain-api/cosmos/bank/v1beta1/balances/'
CHARSET='qpzry9x8gf2tvdw0s3jn54khce6mua7l'


def validate_address(address):
    """Validate a 20-byte Gonka Bech32 account and checksum; reject URI injection."""
    if not isinstance(address,str) or len(address)!=44 or not address.startswith('gonka1'):
        raise ValueError('Invalid Gonka address')
    try: data=[CHARSET.index(c) for c in address[6:]]
    except ValueError: raise ValueError('Invalid Gonka address') from None
    values=[ord(c)>>5 for c in 'gonka']+[0]+[ord(c)&31 for c in 'gonka']+data
    chk=1
    generators=[0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3]
    for v in values:
        top=chk>>25;chk=((chk&0x1ffffff)<<5)^v
        for i,g in enumerate(generators):
            if (top>>i)&1:chk^=g
    if chk!=1:raise ValueError('Invalid Gonka address checksum')
    return address


class NativeTreasury:
    def __init__(self,client,address=''):
        self.client,self.address=client,address
        if address:validate_address(address)
        self.cached=None;self.at=0;self.lock=asyncio.Lock()

    async def balance(self):
        if not self.address:return None
        async with self.lock:
            now=time.time()
            if self.cached and now-self.at<30:return self.cached
            url=BANK+self.address+'/by_denom?denom=ngonka'
            async with asyncio.timeout(8):
                async with self.client.stream('GET',url,timeout=8) as r:
                    r.raise_for_status();chunks=[];size=0
                    async for chunk in r.aiter_bytes():
                        size+=len(chunk)
                        if size>8192:raise ValueError('Gonka response too large')
                        chunks.append(chunk)
                    b=json.loads(b''.join(chunks))['balance']
                    if b['denom']!='ngonka':raise ValueError('Wrong native denomination')
                    amount=quantity(b['amount'])
            self.cached={'address':self.address,'amount_ngonka':amount,'observed_at':int(now),
                'source':url,'scope':'Configured self-custody wallet on Gonka mainnet; not broker credit'}
            self.at=now
            return self.cached
