"""Safe, projection-only burn planning.

Slipvolt is prelaunch: there is no treasury signing key, no project mint and
no on-chain burn authority. This module therefore models what a burn WOULD be,
given ledgered revenue vs expenses, and records that intent in the audit log.
It never signs, never broadcasts, never moves funds and never builds a
transaction. Nothing here can reduce native supply.

Safety invariants (mirror the read-only Gonka boundary):
  * All outputs are a projection; ``executable`` is always False unless the
    operator both sets ``BURN_ENABLED=1`` AND the module has been explicitly
    flagged as having a real (human-held) treasury authorization. Even then,
    this module still only *plans* — the actual broadcast lives outside Slipvolt.
  * GNK amounts are positive-safe decimals; addresses are validated with the
    same 20-byte Bech32 rules used by ``gonka.validate_address``.
  * A burn can never exceed retained cash after configured reserves are kept.
"""
from decimal import Decimal, InvalidOperation

BURN_FLAG = "BURN_ENABLED"
BURN_SHARE_KEY = "burn_share_pct"
BURN_RESERVE_KEY = "burn_reserve_nusd"
DEFAULT_BURN_SHARE_PCT = 50        # accepts int/str/Decimal; normalized in _d
DEFAULT_RESERVE_NUSD = 0


def _d(value, *, minimum=None, maximum=None):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Expected a finite decimal number") from exc
    if not n.is_finite():
        raise ValueError("Expected a finite decimal number")
    if minimum is not None and n < Decimal(str(minimum)):
        raise ValueError("Value below permitted minimum")
    if maximum is not None and n > Decimal(str(maximum)):
        raise ValueError("Value above permitted maximum")
    return n


def burn_plan(business_summary, *, enabled=False,
              burn_share_pct=DEFAULT_BURN_SHARE_PCT,
              reserve_nusd=DEFAULT_RESERVE_NUSD, gnk_usd="1.0",
              treasury_address="") -> dict:
    """Compute the projected burn for a given ledger summary.

    ``business_summary`` is the dict returned by ``store.business_summary``
    (integer nano-USD: revenue, expense, net, days). This returns a projection
    only; it reads the ledger and never touches a chain.

    Numeric inputs (``burn_share_pct``, ``reserve_nusd``, ``gnk_usd``) accept
    ``int``, ``str`` or ``Decimal``; each is normalized safely inside.

    Args:
        business_summary: ledger summary dict from the store.
        enabled: master switch (BURN_ENABLED). Default False.
        burn_share_pct: share of retained cash earmarked for burn (0..100).
        reserve_nusd: reserve kept aside each period before burn (integer nUSD).
        gnk_usd: assumed USD price per GNK, for the projected GNK figure.
        treasury_address: optional Gonka address for the projection label.

    Returns:
        dict: {"enabled", "executable", "transactionsPrepared", "retained_cash_usd",
               "reserve_usd", "burn_usd", "burn_gnk", "gnk_price_usd",
               "treasury_address", "warnings", "scope"}
    """
    try:
        revenue = _d(business_summary.get("revenue", 0), minimum=0)
        expense = _d(business_summary.get("expense", 0), minimum=0)
        net = _d(business_summary.get("net", 0))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError("business_summary must be a dict with numeric fields") from exc

    share = _d(burn_share_pct, minimum=0, maximum=100)
    reserve = _d(reserve_nusd, minimum=0)
    price = _d(gnk_usd, minimum=0)

    if type(enabled) is not bool:
        raise ValueError("enabled must be boolean")

    if treasury_address:
        try:
            from .gonka import validate_address
            validate_address(treasury_address)
        except ValueError:
            raise ValueError("Invalid treasury address") from None

    # Retained cash = net revenue; never let a burn exceed what the ledger
    # actually shows as surplus after the configured reserve is set aside.
    retained_cash_nusd = max(0, net - reserve)
    if retained_cash_nusd == 0:
        burn_nusd = 0
        warnings = ["No surplus after reserves; projected burn is zero."]
    else:
        burn_nusd = (retained_cash_nusd * share) / 100
        burn_nusd = int(burn_nusd)  # nano-USD is integer; floor to whole nUSD
        warnings = []

    if price == 0:
        burn_gnk = None
        warnings.append("gnk_usd is 0; a GNK figure could not be projected.")
    else:
        burn_gnk = Decimal(burn_nusd) / Decimal(10**9) / price

    # executable stays False unless the operator explicitly arms the feature
    # AND a real (external, human-held) treasury authority is declared. No such
    # authority exists in Slipvolt today, so this is always a plan, never a tx.
    executable = bool(enabled and False)  # intentionally always False (safe)

    base = {
        "enabled": bool(enabled),
        "executable": executable,
        "transactionsPrepared": 0,
        "retained_cash_usd": retained_cash_nusd / 10**9,
        "reserve_usd": float(reserve) / 10**9,
        "burn_usd": burn_nusd / 10**9,
        "burn_share_pct": float(share),
        "gnk_price_usd": float(price),
        "burn_gnk": float(burn_gnk) if burn_gnk is not None else None,
        "treasury_address": treasury_address,
        "warnings": warnings,
        "scope": "Projected from ledgered revenue vs expenses. No signing, no broadcast, "
                 "no supply change. treasury_address is a label only.",
    }
    return base
