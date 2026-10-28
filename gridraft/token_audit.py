"""Read-only Solana mint and burn evidence; never signs, swaps or credits usage.

Evidence is verified against an operator-configured mainnet RPC, not by running
an independent validator. Totals cover submitted receipts only, not all burns,
net supply change, treasury revenue, user deposits, or investment returns.
"""
import json
import re
import time

from .integrations import MAINNET_GENESIS
from .security import ALPHABET, decode_address

TOKEN_PROGRAMS = frozenset((
    'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',
    'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb',
))
U64_MAX = 2**64 - 1


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError('Missing or invalid ' + label)
    return value


def _integer(value, label, minimum=0, maximum=U64_MAX):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Missing or invalid ' + label)
    return value


def _raw_amount(value, positive=False):
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value):
        raise ValueError('Invalid raw token amount')
    n = int(value)
    if n > U64_MAX or (positive and n == 0):
        raise ValueError('Invalid raw token amount')
    return n


def validate_signature(value):
    if not isinstance(value, str) or not 64 <= len(value) <= 88:
        raise ValueError('Invalid transaction signature')
    n = 0
    for char in value:
        if char not in ALPHABET:
            raise ValueError('Invalid transaction signature')
        n = n * 58 + ALPHABET.index(char)
    size = len(value) - len(value.lstrip('1')) + (n.bit_length() + 7) // 8
    if size != 64:
        raise ValueError('Transaction signature must decode to 64 bytes')
    return value


def parse_mint(result, mint, decimals, min_slot=0):
    decode_address(mint)
    _integer(decimals, 'configured decimals', maximum=18)
    result = _object(result, 'mint response')
    slot = _integer(_object(result.get('context'), 'mint context').get('slot'), 'mint slot', minimum=1)
    if slot < min_slot:
        raise ValueError('Mint snapshot predates the transaction')
    account = _object(result.get('value'), 'mint account')
    program = account.get('owner')
    if not isinstance(program, str) or program not in TOKEN_PROGRAMS or account.get('executable') is not False:
        raise ValueError('Unsupported mint account owner')
    parsed = _object(_object(account.get('data'), 'mint data').get('parsed'), 'parsed mint')
    info = _object(parsed.get('info'), 'mint fields')
    if parsed.get('type') != 'mint' or info.get('isInitialized') is not True:
        raise ValueError('Account is not an initialized mint')
    actual_decimals = _integer(info.get('decimals'), 'mint decimals', maximum=18)
    if actual_decimals != decimals:
        raise ValueError('Configured decimals do not match the mint')
    supply = str(_raw_amount(info.get('supply')))
    authorities = {}
    for key, output in (('mintAuthority', 'mint_authority'), ('freezeAuthority', 'freeze_authority')):
        if key not in info:
            raise ValueError('Mint authority metadata is missing')
        value = info[key]
        if value is not None:
            decode_address(value)
        authorities[output] = value
    return {'mint': mint, 'token_program': program, 'decimals': decimals,
        'supply_raw': supply, 'slot': slot, **authorities}


def _finalized_slot(result):
    result = _object(result, 'signature status')
    values = result.get('value')
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError('Signature status is unavailable')
    item = _object(values[0], 'signature status')
    if item.get('confirmationStatus') != 'finalized' or 'err' not in item or item['err'] is not None:
        raise ValueError('Transaction is not successful and finalized')
    slot = _integer(item.get('slot'), 'transaction slot', minimum=1)
    context_slot = _integer(_object(result.get('context'), 'status context').get('slot'), 'status context slot', minimum=1)
    if context_slot < slot:
        raise ValueError('Inconsistent transaction finality')
    return slot


def parse_burn_receipt(result, status, mint_state, signature):
    """Validate jsonParsed evidence after the caller has verified mainnet identity."""
    validate_signature(signature)
    slot = _finalized_slot(status)
    result = _object(result, 'transaction')
    if type(result.get('slot')) is not int or result['slot'] != slot:
        raise ValueError('Transaction and signature-status slots differ')
    version = result.get('version')
    if version != 'legacy' and not (type(version) is int and version == 0):
        raise ValueError('Unsupported transaction version')
    if mint_state['slot'] < slot:
        raise ValueError('Mint snapshot predates the transaction')
    meta = _object(result.get('meta'), 'transaction metadata')
    if 'err' not in meta or meta['err'] is not None:
        raise ValueError('Transaction did not succeed')
    transaction = _object(result.get('transaction'), 'transaction payload')
    signatures = transaction.get('signatures')
    if not isinstance(signatures, list) or not signatures or signatures[0] != signature:
        raise ValueError('Transaction signature does not match the requested receipt')
    message = _object(transaction.get('message'), 'message')
    outer = message.get('instructions')
    inner = meta.get('innerInstructions')
    if not isinstance(outer, list) or not 1 <= len(outer) <= 256 or not isinstance(inner, list):
        raise ValueError('Complete instruction metadata is required')
    instructions = [('outer:' + str(i), ix) for i, ix in enumerate(outer)]
    seen = set()
    for group in inner:
        group = _object(group, 'inner instruction group')
        index = _integer(group.get('index'), 'inner parent', maximum=len(outer) - 1)
        rows = group.get('instructions')
        if index in seen or not isinstance(rows, list):
            raise ValueError('Duplicate or invalid inner instruction group')
        seen.add(index)
        instructions.extend((f'inner:{index}:{i}', ix) for i, ix in enumerate(rows))
    if len(instructions) > 4096:
        raise ValueError('Too many instructions')
    events = []
    for path, instruction in instructions:
        instruction = _object(instruction, 'instruction')
        program = instruction.get('programId')
        if not isinstance(program, str):
            raise ValueError('Invalid instruction program')
        if program not in TOKEN_PROGRAMS:
            continue
        # Unparsed token-program instructions could conceal burns or reminting.
        # Decline this receipt instead of treating incomplete evidence as complete.
        parsed = _object(instruction.get('parsed'), 'parsed token instruction')
        kind = parsed.get('type')
        if kind not in ('burn', 'burnChecked'):
            continue
        info = _object(parsed.get('info'), 'burn fields')
        if info.get('mint') != mint_state['mint']:
            continue
        if instruction['programId'] != mint_state['token_program']:
            raise ValueError('Burn program does not match the mint owner')
        source = info.get('account')
        decode_address(source)
        authority_fields = [k for k in ('authority', 'multisigAuthority') if k in info]
        if len(authority_fields) != 1:
            raise ValueError('Burn authority is unavailable or ambiguous')
        authority = info[authority_fields[0]]
        decode_address(authority)
        if kind == 'burnChecked':
            amount = _object(info.get('tokenAmount'), 'checked token amount')
            if type(amount.get('decimals')) is not int or amount['decimals'] != mint_state['decimals']:
                raise ValueError('Burn decimals do not match the mint')
            raw = _raw_amount(amount.get('amount'), positive=True)
        else:
            raw = _raw_amount(info.get('amount'), positive=True)
        events.append({'path': path, 'kind': kind, 'amount_raw': str(raw),
            'source_account': source, 'authority': authority,
            'authority_kind': authority_fields[0]})
    if not events:
        raise ValueError('No supported burn of the configured mint was found')
    block_time = result.get('blockTime')
    if block_time is not None:
        _integer(block_time, 'block time')
    return {'genesis_hash': MAINNET_GENESIS, 'signature': signature,
        'mint': mint_state['mint'], 'token_program': mint_state['token_program'],
        'decimals': mint_state['decimals'], 'slot': slot, 'block_time': block_time,
        'burned_raw': str(sum(int(v['amount_raw']) for v in events)), 'events': events,
        'scope': 'tracked_gross_burns', 'net_supply_change_raw': None}


class TokenAuditor:
    def __init__(self, rpc, mint, decimals):
        decode_address(mint)
        _integer(decimals, 'configured decimals', maximum=18)
        self.rpc, self.mint, self.decimals = rpc, mint, decimals

    async def snapshot(self, min_slot=0):
        await self.rpc.ensure_mainnet()
        result = await self.rpc.call('getAccountInfo', [self.mint, {
            'encoding': 'jsonParsed', 'commitment': 'finalized', 'minContextSlot': min_slot}])
        return parse_mint(result, self.mint, self.decimals, min_slot)

    async def verify(self, signature):
        validate_signature(signature)  # Fail before network access.
        await self.rpc.ensure_mainnet()
        status = await self.rpc.call('getSignatureStatuses', [[signature], {'searchTransactionHistory': True}])
        slot = _finalized_slot(status)
        result = await self.rpc.call('getTransaction', [signature, {
            'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}])
        if result is None:
            raise ValueError('Finalized transaction history is unavailable from this RPC')
        snapshot = await self.snapshot(min_slot=slot)
        return parse_burn_receipt(result, status, snapshot, signature)


class BurnLedger:
    """Append-only local evidence, isolated from allowance and cash accounting."""
    def __init__(self, db):
        self.db = db
        db.execute('''CREATE TABLE IF NOT EXISTS token_burn_receipts(
            genesis_hash TEXT NOT NULL, signature TEXT NOT NULL, mint TEXT NOT NULL,
            burned_raw TEXT NOT NULL, event_count INTEGER NOT NULL, slot INTEGER NOT NULL,
            evidence TEXT NOT NULL, checked_at INTEGER NOT NULL,
            PRIMARY KEY(genesis_hash,signature,mint))''')
        db.execute('''CREATE INDEX IF NOT EXISTS token_burn_mint_slot
            ON token_burn_receipts(genesis_hash,mint,slot DESC)''')
        db.commit()

    def record(self, receipt):
        if receipt.get('genesis_hash') != MAINNET_GENESIS:
            raise ValueError('Only verified mainnet receipts can be recorded')
        validate_signature(receipt.get('signature'))
        decode_address(receipt.get('mint'))
        events = receipt.get('events')
        if not isinstance(events, list) or not events or len(events) > 4096:
            raise ValueError('Missing burn evidence')
        total = sum(_raw_amount(v.get('amount_raw'), positive=True) for v in events)
        if receipt.get('burned_raw') != str(total):
            raise ValueError('Inconsistent burn total')
        evidence = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        key = (MAINNET_GENESIS, receipt['signature'], receipt['mint'])
        self.db.execute('SAVEPOINT token_burn_record')
        try:
            changed = self.db.execute('''INSERT OR IGNORE INTO token_burn_receipts
                (genesis_hash,signature,mint,burned_raw,event_count,slot,evidence,checked_at)
                VALUES(?,?,?,?,?,?,?,?)''', (*key, str(total), len(events), receipt['slot'], evidence, int(time.time()))).rowcount
            existing = self.db.execute('''SELECT evidence FROM token_burn_receipts
                WHERE genesis_hash=? AND signature=? AND mint=?''', key).fetchone()
            if existing[0] != evidence:
                raise ValueError('Conflicting evidence for an already recorded transaction')
            self.db.execute('RELEASE token_burn_record')
            return bool(changed)
        except BaseException:
            self.db.execute('ROLLBACK TO token_burn_record')
            self.db.execute('RELEASE token_burn_record')
            raise

    def summary(self, mint):
        decode_address(mint)
        key = (MAINNET_GENESIS, mint)
        rows = self.db.execute('''SELECT burned_raw,event_count FROM token_burn_receipts
            WHERE genesis_hash=? AND mint=?''', key)
        total = receipts = events = 0
        for amount, count in rows:
            total += int(amount); receipts += 1; events += count
        recent = self.db.execute('''SELECT evidence,checked_at FROM token_burn_receipts
            WHERE genesis_hash=? AND mint=? ORDER BY slot DESC,signature LIMIT 25''', key)
        first = self.db.execute('SELECT evidence FROM token_burn_receipts WHERE genesis_hash=? AND mint=? LIMIT 1', key).fetchone()
        decimals = json.loads(first[0])['decimals'] if first else None
        return {'burned_raw': str(total), 'receipt_count': receipts, 'event_count': events, 'decimals': decimals,
            'scope': 'tracked_gross_burns', 'complete_history': False,
            'recent': [self._public_receipt(row[0], row[1]) for row in recent]}

    @staticmethod
    def _public_receipt(evidence, checked_at):
        value = json.loads(evidence)
        return {key: value[key] for key in ('signature', 'slot', 'block_time', 'burned_raw')} | {
            'event_count': len(value['events']), 'checked_at': checked_at}
