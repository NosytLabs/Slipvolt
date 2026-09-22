"""Tests for the safe, projection-only burn planner (gridraft.burn)."""
from decimal import Decimal

import pytest

from gridraft.burn import BURN_FLAG, DEFAULT_BURN_SHARE_PCT, burn_plan


def ledger(revenue=0, expense=0):
    return {"revenue": revenue, "expense": expense, "net": revenue - expense,
            "days": 30, "entries": 0, "recent": [], "daily": []}


NADDR = "gonka1mduf068xsxrqxr0z6p63napwjurpazjr7zltn8"  # valid checksummed address


def test_burn_plan_is_never_executable_by_default():
    plan = burn_plan(ledger(revenue=500_000_000_000, expense=200_000_000_000), enabled=False)
    assert plan["enabled"] is False
    assert plan["executable"] is False
    assert plan["transactionsPrepared"] == 0


def test_burn_plan_never_executable_even_when_enabled():
    # Even with the flag on, this module is plan-only; no signing/broadcast exists.
    plan = burn_plan(ledger(revenue=500_000_000_000, expense=200_000_000_000), enabled=True)
    assert plan["enabled"] is True
    assert plan["executable"] is False


def test_retained_cash_and_burn_math():
    revenue = 500_000_000_000  # $500
    expense = 200_000_000_000   # $200
    plan = burn_plan(ledger(revenue=revenue, expense=expense), enabled=True,
                     burn_share_pct=50)
    assert plan["retained_cash_usd"] == 300.0
    assert plan["burn_usd"] == 150.0
    # $150 / $1 per GNK
    assert plan["burn_gnk"] == pytest.approx(150.0)


def test_reserve_is_kept_before_burn():
    revenue = 500_000_000_000   # $500
    expense = 200_000_000_000   # $200
    reserve = 100_000_000_000   # $100 reserve
    plan = burn_plan(ledger(revenue=revenue, expense=expense), burn_share_pct=100,
                     reserve_nusd=reserve)
    # surplus after reserve = 200 -> 100% burn = $200
    assert plan["retained_cash_usd"] == 200.0
    assert plan["burn_usd"] == 200.0


def test_zero_surplus_yields_zero_burn_and_warning():
    plan = burn_plan(ledger(revenue=100_000_000_000, expense=100_000_000_000),
                     burn_share_pct=50)
    assert plan["retained_cash_usd"] == 0.0
    assert plan["burn_usd"] == 0.0
    assert plan["burn_gnk"] == 0.0
    assert any("No surplus" in w for w in plan["warnings"])


def test_negative_net_never_burns():
    plan = burn_plan(ledger(revenue=100_000_000_000, expense=400_000_000_000),
                     burn_share_pct=50)
    assert plan["burn_usd"] == 0.0
    assert plan["retained_cash_usd"] == 0.0


def test_burn_never_exceeds_surplus_with_high_share():
    revenue = 1_000_000_000   # $1
    expense = 0
    plan = burn_plan(ledger(revenue=revenue, expense=expense), burn_share_pct=100)
    assert plan["retained_cash_usd"] == 1.0
    assert plan["burn_usd"] <= 1.0


def test_gnk_conversion_uses_price():
    revenue = 10**9 * 100      # $100
    plan = burn_plan(ledger(revenue=revenue, expense=0), burn_share_pct=50,
                     gnk_usd="2.0")
    # $50 burn / $2 per GNK = 25 GNK
    assert plan["burn_gnk"] == pytest.approx(25.0)
    assert plan["gnk_price_usd"] == 2.0


def test_zero_price_returns_none_gnk_with_warning():
    plan = burn_plan(ledger(revenue=10**9 * 100), burn_share_pct=50, gnk_usd="0")
    assert plan["burn_gnk"] is None
    assert any("gnk_usd is 0" in w for w in plan["warnings"])


def test_treasury_address_validated():
    with pytest.raises(ValueError):
        burn_plan(ledger(revenue=100), treasury_address="not-an-address")
    # valid address accepted
    plan = burn_plan(ledger(revenue=100), treasury_address=NADDR)
    assert plan["treasury_address"] == NADDR


def test_share_out_of_range_rejected():
    with pytest.raises(ValueError):
        burn_plan(ledger(revenue=100), burn_share_pct=101)
    with pytest.raises(ValueError):
        burn_plan(ledger(revenue=100), burn_share_pct=-1)


def test_enabled_must_be_bool():
    with pytest.raises(ValueError):
        burn_plan(ledger(revenue=100), enabled="yes")


def test_bad_business_summary_rejected():
    with pytest.raises(ValueError):
        burn_plan(None)
    with pytest.raises(ValueError):
        burn_plan([1, 2, 3])


def test_flags_exported():
    assert BURN_FLAG == "BURN_ENABLED"
    assert str(DEFAULT_BURN_SHARE_PCT) == "50"


# ---- store integration ----

def test_store_burn_projection_records_audit(tmp_path):
    from gridraft.store import Store
    s = Store(str(tmp_path / "b.db"), "pepper")
    s.add_business_entry("api_revenue", 300_000_000_000, "ref-1", "rev")
    plan = s.burn_projection(enabled=True, burn_share_pct=50)
    assert plan["executable"] is False
    assert plan["burn_usd"] == 150.0
    events = s.audit_events()
    assert any(e["action"] == "burn_projection" for e in events)
