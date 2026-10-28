"""Finalized Pump SOL creator-vault claim evidence, not project revenue.

The configured RPC is trusted for transaction and finality data. Pump creator
vaults may aggregate several coins, and an observed claim does not establish
project attribution, legal ownership, or the provenance of all vault funds.
"""
import json
import time

from solders.pubkey import Pubkey

from .integrations import MAINNET_GENESIS
from .security import decode_address
from .token_audit import _finalized_slot, validate_signature

# Pump's published IDL: collect_creator_fee_v2, no arguments.
PUMP = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
CLAIM_DATA = 'bdpoExJbbLb'
NATIVE_MINT = 'So11111111111111111111111111111111111111112'
TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
ASSOCIATED = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
SYSTEM = '11111111111111111111111111111111'
COMPUTE = 'ComputeBudget111111111111111111111111111111'
MAX_U64 = 2**64 - 1


def _integer(value, *, maximum=MAX_U64):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Invalid transaction quantity')
    return value


def _dict(value):
    if not isinstance(value, dict):
        raise ValueError('Incomplete transaction evidence')
    return value


def _derived_accounts(creator):
    program = Pubkey.from_string(PUMP)
    associated = Pubkey.from_string(ASSOCIATED)
    token = Pubkey.from_string(TOKEN)
    mint = Pubkey.from_string(NATIVE_MINT)
    owner = Pubkey.from_string(creator)
    vault = Pubkey.find_program_address([b'creator-vault', bytes(owner)], program)[0]
    event = Pubkey.find_program_address([b'__event_authority'], program)[0]
    def ata(authority):
        return Pubkey.find_program_address([bytes(authority), bytes(token), bytes(mint)], associated)[0]
    return str(vault), str(ata(owner)), str(ata(vault)), str(event)


def _transaction(result, status, signature):
    slot = _integer(_finalized_slot(status), maximum=2**63-1)
    result = _dict(result)
    if type(result.get('slot')) is not int or result['slot'] != slot:
        raise ValueError('Transaction and finality slots differ')
    version = result.get('version')
    if version != 'legacy' and not (type(version) is int and version == 0):
        raise ValueError('Unsupported transaction version')
    meta = _dict(result.get('meta'))
    if 'err' not in meta or meta['err'] is not None:
        raise ValueError('Transaction did not succeed')
    payload = _dict(result.get('transaction'))
    signatures = payload.get('signatures')
    if not isinstance(signatures, list) or not signatures or signatures[0] != signature:
        raise ValueError('Transaction signature mismatch')
    message = _dict(payload.get('message'))
    return result, meta, message, slot


def _claim_instruction(message, creator):
    instructions = message.get('instructions')
    if not isinstance(instructions, list) or not 1 <= len(instructions) <= 16:
        raise ValueError('Invalid transaction instructions')
    claims = []
    for item in instructions:
        item = _dict(item)
        if item.get('programId') == COMPUTE:
            continue
        if item.get('programId') != PUMP or item.get('data') != CLAIM_DATA:
            raise ValueError('Only a single direct Pump creator claim is supported')
        claims.append(item)
    if len(claims) != 1:
        raise ValueError('Exactly one Pump creator claim is required')
    accounts = claims[0].get('accounts')
    if not isinstance(accounts, list) or len(accounts) != 10:
        raise ValueError('Invalid Pump claim accounts')
    for address in accounts:
        decode_address(address)
    if (accounts[0] != creator or accounts[4:8] != [NATIVE_MINT, TOKEN, ASSOCIATED, SYSTEM]
            or accounts[9] != PUMP or accounts[2] == creator):
        raise ValueError('Claim does not match the configured creator or supported SOL route')
    vault, creator_ata, vault_ata, event = _derived_accounts(creator)
    if (accounts[2], accounts[1], accounts[3], accounts[8]) != (vault, creator_ata, vault_ata, event):
        raise ValueError('Claim contains invalid program-derived accounts')
    return accounts, len(instructions)


def _balances(meta, message, accounts):
    keys = message.get('accountKeys')
    before, after = meta.get('preBalances'), meta.get('postBalances')
    if not isinstance(keys, list) or not 1 <= len(keys) <= 256:
        raise ValueError('Invalid account keys')
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(keys) or len(after) != len(keys):
        raise ValueError('Incomplete balance evidence')
    addresses = []
    for entry in keys:
        entry = _dict(entry)
        address = entry.get('pubkey')
        decode_address(address)
        addresses.append(address)
    if len(set(addresses)) != len(addresses) or not set(accounts).issubset(addresses):
        raise ValueError('Inconsistent account keys')
    if keys[0].get('signer') is not True:
        raise ValueError('Missing transaction fee payer')
    fee = _integer(meta.get('fee'))
    deltas = {key: _integer(after[i]) - _integer(before[i]) for i, key in enumerate(addresses)}
    payer, creator, vault = addresses[0], accounts[0], accounts[2]
    if payer == vault:
        raise ValueError('Vault cannot be the fee payer')
    amount = deltas[creator] + (fee if payer == creator else 0)
    if amount <= 0 or amount > MAX_U64 or deltas[vault] != -amount:
        raise ValueError('Claim balance changes do not match')
    if payer != creator and deltas[payer] != -fee:
        raise ValueError('Fee payer balance is inconsistent')
    if any(delta != 0 for key, delta in deltas.items() if key not in (payer, creator, vault)):
        raise ValueError('Other account balances changed during the claim')
    return amount


def parse_creator_claim(result, status, creator, signature):
    decode_address(creator)
    if creator == SYSTEM:
        raise ValueError('Invalid creator')
    validate_signature(signature)
    result, meta, message, slot = _transaction(result, status, signature)
    accounts, outer_count = _claim_instruction(message, creator)
    groups = meta.get('innerInstructions')
    if not isinstance(groups, list) or len(groups) > outer_count:
        raise ValueError('Incomplete inner instruction evidence')
    seen = set()
    for group in groups:
        group = _dict(group)
        index = _integer(group.get('index'), maximum=outer_count-1)
        rows = group.get('instructions')
        if index in seen or not isinstance(rows, list) or len(rows) > 4096:
            raise ValueError('Invalid inner instruction evidence')
        seen.add(index)
    block_time = result.get('blockTime')
    if block_time is not None:
        _integer(block_time, maximum=2**63-1)
    amount = _balances(meta, message, accounts)
    return {'schema': 'holdbyte.creator-claim.v1', 'genesis_hash': MAINNET_GENESIS,
        'signature': signature, 'creator': creator, 'source_vault': accounts[2],
        'protocol': 'pump_curve_creator_claim_v2', 'asset': 'SOL',
        'amount_lamports': str(amount), 'slot': slot, 'block_time': block_time,
        'project_attribution': 'unverified', 'recognized_revenue': False}


class CreatorClaimAuditor:
    def __init__(self, rpc, creator):
        decode_address(creator)
        if creator == SYSTEM:
            raise ValueError('Invalid creator')
        self.rpc, self.creator = rpc, creator

    async def verify(self, signature):
        validate_signature(signature)
        await self.rpc.ensure_mainnet()
        status = await self.rpc.call('getSignatureStatuses', [[signature], {'searchTransactionHistory': True}])
        _finalized_slot(status)
        result = await self.rpc.call('getTransaction', [signature, {
            'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}])
        return parse_creator_claim(result, status, self.creator, signature)


class CreatorClaimLedger:
    """Deduplicated claim evidence; never credits business or allowance ledgers."""
    def __init__(self, store):
        self.store = store
        with store.transaction():
            store.db.execute('''CREATE TABLE IF NOT EXISTS creator_claim_receipts(
                genesis_hash TEXT NOT NULL, signature TEXT NOT NULL, creator TEXT NOT NULL,
                amount_lamports TEXT NOT NULL, slot INTEGER NOT NULL, evidence TEXT NOT NULL,
                checked_at INTEGER NOT NULL, PRIMARY KEY(genesis_hash,signature,creator))''')
            store.db.execute('''CREATE INDEX IF NOT EXISTS creator_claim_creator_slot
                ON creator_claim_receipts(genesis_hash,creator,slot DESC)''')

    def record(self, receipt):
        if (receipt.get('schema') != 'holdbyte.creator-claim.v1' or receipt.get('genesis_hash') != MAINNET_GENESIS
                or receipt.get('protocol') != 'pump_curve_creator_claim_v2' or receipt.get('asset') != 'SOL'
                or receipt.get('project_attribution') != 'unverified' or receipt.get('recognized_revenue') is not False):
            raise ValueError('Invalid creator claim evidence')
        validate_signature(receipt.get('signature'))
        decode_address(receipt.get('creator'))
        amount = receipt.get('amount_lamports')
        if not isinstance(amount, str) or not amount.isascii() or not amount.isdigit() or str(int(amount)) != amount or not 1 <= int(amount) <= MAX_U64:
            raise ValueError('Invalid creator claim amount')
        if _integer(receipt.get('slot'), maximum=2**63-1) == 0:
            raise ValueError('Invalid creator claim slot')
        evidence = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        key = (MAINNET_GENESIS, receipt['signature'], receipt['creator'])
        with self.store.transaction():
            changed = self.store.db.execute('''INSERT OR IGNORE INTO creator_claim_receipts
                (genesis_hash,signature,creator,amount_lamports,slot,evidence,checked_at)
                VALUES(?,?,?,?,?,?,?)''', (*key, amount, receipt['slot'], evidence, int(time.time()))).rowcount
            existing = self.store.db.execute('''SELECT evidence FROM creator_claim_receipts
                WHERE genesis_hash=? AND signature=? AND creator=?''', key).fetchone()
            if existing[0] != evidence:
                raise ValueError('Conflicting evidence for an already recorded claim')
            return bool(changed)

    def summary(self, creator):
        decode_address(creator)
        count = total = 0
        with self.store.lock:
            key = (MAINNET_GENESIS, creator)
            for row in self.store.db.execute('''SELECT amount_lamports FROM creator_claim_receipts
                    WHERE genesis_hash=? AND creator=?''', key):
                count += 1
                total += int(row['amount_lamports'])
            rows = self.store.db.execute('''SELECT evidence,checked_at FROM creator_claim_receipts
                WHERE genesis_hash=? AND creator=? ORDER BY slot DESC,signature LIMIT 100''', key).fetchall()
        return {'creator': creator, 'count': count, 'total_lamports': str(total),
            'recent': [json.loads(row['evidence']) | {'checked_at': row['checked_at']} for row in rows],
            'complete_history': False, 'project_attribution': 'unverified', 'recognized_revenue': False}
