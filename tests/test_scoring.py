"""Unit tests for paper-fill P&L scoring."""

import pytest

from tradingagents.exchange.scoring import (
    MarketOutcome,
    classify_outcome,
    score_position,
)


def _fill(direction: str, contracts: float, filled_usd: float, fee: float = 0.0) -> dict:
    return {
        "direction": direction,
        "contracts": contracts,
        "filled_usd": filled_usd,
        "fee_estimate_if_win": fee,
    }


# ---------------------------------------------------------------------------
# classify_outcome - read gamma fields and decide PENDING / YES / NO / CANCEL
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classify_pending_when_market_open():
    out, current_yes = classify_outcome(closed=False, outcome_prices=[0.55, 0.45])
    assert out == MarketOutcome.PENDING
    assert current_yes == 0.55


@pytest.mark.unit
def test_classify_yes_wins():
    out, _ = classify_outcome(closed=True, outcome_prices=[1.0, 0.0])
    assert out == MarketOutcome.YES_WINS


@pytest.mark.unit
def test_classify_no_wins():
    out, _ = classify_outcome(closed=True, outcome_prices=[0.0, 1.0])
    assert out == MarketOutcome.NO_WINS


@pytest.mark.unit
def test_classify_canceled_5050():
    out, _ = classify_outcome(closed=True, outcome_prices=[0.5, 0.5])
    assert out == MarketOutcome.CANCELED


@pytest.mark.unit
def test_classify_data_anomaly_zero_zero():
    """Legacy markets with [0, 0] outcomePrices are data anomalies, not real outcomes."""
    out, _ = classify_outcome(closed=True, outcome_prices=[0.0, 0.0])
    assert out == MarketOutcome.UNKNOWN


@pytest.mark.unit
def test_classify_dispute_window():
    """Closed but not yet at clean resolution, UMA dispute window."""
    out, _ = classify_outcome(closed=True, outcome_prices=[0.85, 0.15])
    assert out == MarketOutcome.UNKNOWN


# ---------------------------------------------------------------------------
# score_position - P&L for each (direction, outcome) pair
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_buy_yes_yes_wins_with_fee():
    """Bought 250 YES at vwap 0.40 for $100. YES wins. Fee = 2% of $250 payout = $5."""
    fill = _fill("BUY_YES", contracts=250.0, filled_usd=100.0, fee=5.0)
    r = score_position(fill, MarketOutcome.YES_WINS, current_yes_price=None)
    assert r["status"] == "RESOLVED_WIN"
    assert r["payout_usd"] == pytest.approx(250.0)
    assert r["fee_paid"] == pytest.approx(5.0)
    assert r["pnl_usd"] == pytest.approx(250.0 - 5.0 - 100.0)
    assert r["roi"] == pytest.approx((250.0 - 5.0 - 100.0) / 100.0)


@pytest.mark.unit
def test_buy_yes_no_wins_total_loss():
    fill = _fill("BUY_YES", contracts=250.0, filled_usd=100.0, fee=5.0)
    r = score_position(fill, MarketOutcome.NO_WINS, current_yes_price=None)
    assert r["status"] == "RESOLVED_LOSS"
    assert r["payout_usd"] == 0.0
    assert r["fee_paid"] == 0.0
    assert r["pnl_usd"] == pytest.approx(-100.0)
    assert r["roi"] == pytest.approx(-1.0)


@pytest.mark.unit
def test_buy_no_no_wins_with_fee():
    fill = _fill("BUY_NO", contracts=200.0, filled_usd=100.0, fee=4.0)
    r = score_position(fill, MarketOutcome.NO_WINS, current_yes_price=None)
    assert r["status"] == "RESOLVED_WIN"
    assert r["payout_usd"] == pytest.approx(200.0)
    assert r["fee_paid"] == pytest.approx(4.0)
    assert r["pnl_usd"] == pytest.approx(200.0 - 4.0 - 100.0)


@pytest.mark.unit
def test_buy_no_yes_wins_total_loss():
    fill = _fill("BUY_NO", contracts=200.0, filled_usd=100.0, fee=4.0)
    r = score_position(fill, MarketOutcome.YES_WINS, current_yes_price=None)
    assert r["status"] == "RESOLVED_LOSS"
    assert r["pnl_usd"] == pytest.approx(-100.0)


@pytest.mark.unit
def test_canceled_refunds_at_50_cents_no_fee():
    """50-50 cancellation: each contract refunds $0.50, no fee."""
    fill = _fill("BUY_YES", contracts=250.0, filled_usd=100.0, fee=5.0)
    r = score_position(fill, MarketOutcome.CANCELED, current_yes_price=None)
    assert r["status"] == "CANCELED"
    assert r["payout_usd"] == pytest.approx(125.0)
    assert r["fee_paid"] == 0.0
    assert r["pnl_usd"] == pytest.approx(25.0)


@pytest.mark.unit
def test_pending_buy_yes_mtm_above_entry():
    """Bought 250 YES at vwap 0.40. Current price 0.50 -> MTM up $25."""
    fill = _fill("BUY_YES", contracts=250.0, filled_usd=100.0, fee=5.0)
    r = score_position(fill, MarketOutcome.PENDING, current_yes_price=0.50)
    assert r["status"] == "PENDING"
    assert r["mtm_value_usd"] == pytest.approx(125.0)
    assert r["mtm_pnl_usd"] == pytest.approx(25.0)


@pytest.mark.unit
def test_pending_buy_no_mtm_uses_no_price():
    """BUY_NO at $100, current YES price 0.30 -> NO price 0.70."""
    fill = _fill("BUY_NO", contracts=200.0, filled_usd=100.0, fee=4.0)
    r = score_position(fill, MarketOutcome.PENDING, current_yes_price=0.30)
    assert r["mtm_value_usd"] == pytest.approx(140.0)
    assert r["mtm_pnl_usd"] == pytest.approx(40.0)


@pytest.mark.unit
def test_unknown_outcome_returns_no_pnl():
    """Market closed but not yet resolved, neither realized nor MTM available."""
    fill = _fill("BUY_YES", contracts=250.0, filled_usd=100.0, fee=5.0)
    r = score_position(fill, MarketOutcome.UNKNOWN, current_yes_price=None)
    assert r["status"] == "UNRESOLVED"
    assert r["pnl_usd"] == 0.0
    assert r.get("mtm_pnl_usd") is None
