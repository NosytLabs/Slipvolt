"""Scenario math, not an executable quote or an investment-return forecast."""
from decimal import Decimal, InvalidOperation
from .security import decode_address

WGNK = '0x972a7a92d92796a98801a8818bcf91f1648f2f68'
RESEARCH_DATE = '2026-09-19'

def number(value, *, positive=False, maximum='1000000000'):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Expected a finite decimal number') from exc
    if not n.is_finite() or n < 0 or (positive and n == 0) or n > Decimal(maximum):
        raise ValueError('Number outside the permitted range')
    return n

def estimate(gnk_usd, ngonka_per_token, attempts, retail_per_million, millions):
    p, unit, retry, retail, volume = [number(x) for x in
        (gnk_usd, ngonka_per_token, attempts, retail_per_million, millions)]
    if retry < 1 or retry > 100:
        raise ValueError('Attempt multiplier must be between 1 and 100')
    # One million tokens / one billion ngonka per GNK = 0.001.
    cost_per_million = p * unit * retry / 1000
    cost, revenue = cost_per_million * volume, retail * volume
    margin = (revenue-cost)/revenue*100 if revenue else None
    return {
        'upstream_per_million_usd': float(cost_per_million),
        'cost_usd': float(cost), 'revenue_usd': float(revenue),
        'contribution_usd': float(revenue-cost),
        'margin_before_overhead_pct': float(margin) if margin is not None else None,
        'excludes': ['epoch costs', 'hosting', 'support', 'gas', 'slippage', 'taxes', 'refunds'],
        'scenario_only': True,
    }

def route_plan(source, target, amount, source_mint=None):
    if source not in ('SOL', 'USDC', 'SPL') or target not in ('GNK', 'WGNK'):
        raise ValueError('Supported destinations are official Ethereum WGNK or native Gonka GNK')
    value = number(amount, positive=True)
    if source == 'SPL':
        decode_address(source_mint)
    steps = []
    if source != 'USDC':
        steps.append({'operation':'swap_on_solana','chain':'Solana','asset':'USDC',
            'description':f'Quote {source} → native Solana USDC. Requires a real liquid market.'})
    steps += [
        {'operation':'bridge_usdc','chain':'Ethereum (chain ID 1)','asset':'USDC',
         'description':'Obtain a live Solana → Ethereum USDC route; receive into your own wallet, not the Gonka bridge.'},
        {'operation':'swap_on_ethereum','chain':'Ethereum (chain ID 1)','asset':'WGNK',
         'description':'Quote USDC → the exact official WGNK contract. Check liquidity, minimum output and ETH gas.'},
    ]
    if target == 'GNK':
        steps.append({'operation':'bridge_to_gonka','chain':'gonka-mainnet','asset':'GNK',
            'description':'Use the official Gonka dashboard to burn WGNK and release GNK to the address derived from the same signing key.'})
    return {
        'source':source,'source_mint':source_mint,'amount':str(value),'amount_unit':source,
        'target':target,'destination_contract':WGNK,'destination_decimals':9,
        'quote_status':'not_requested','executable':False,'steps':steps,
        'warnings':[
            'This is a route plan, not a live quote. No transactions are prepared or signed.',
            'There is no official GNK or WGNK mint on Solana in the reviewed Gonka documentation.',
            'Ethereum → Gonka delivery is derived from the same key, not an arbitrary recipient address. A matching seed phrase is not enough.',
            'Never direct an aggregator or exchange withdrawal straight to the Gonka bridge. Receive WGNK yourself first.',
            'Contract wallets, custodial senders and account-abstraction relayers need explicit bridge compatibility verification.',
            'Keep SOL and ETH for gas. WGNK and native GNK are not interchangeable deposit formats.',
            'For API funding, transfer native GNK to the actual OpenBroker dashboard deposit address after bridge receipt.',
            'Houdini support for this exact WGNK contract has not been verified. General chain support does not establish a route.',
        ],'verified_documents_on':RESEARCH_DATE,
    }
