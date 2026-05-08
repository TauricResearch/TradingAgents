"""Unit tests for paper_fill.simulate_fill and is_economic_when_correct."""

import pytest

from tradingagents.exchange.paper_fill import is_economic_when_correct, simulate_fill


@pytest.mark.unit
def test_deep_book_partial_fill_at_top():
    """Top ask has more depth than budget needs, single-level fill."""
    asks = [
        {"price": 0.40, "size": 1000.0},
        {"price": 0.41, "size": 500.0},
    ]
    result = simulate_fill(asks, budget_usd=100.0)
    assert result["filled"] is True
    assert result["levels_consumed"] == 1
    assert result["contracts"] == pytest.approx(250.0, abs=0.01)
    assert result["vwap"] == pytest.approx(0.40, abs=1e-6)
    assert result["filled_usd"] == pytest.approx(100.0, abs=1e-6)
    assert result["remaining_budget"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.unit
def test_walks_multiple_levels_when_top_too_small():
    """Top ask has 50 USDC of depth, second has plenty, two-level fill."""
    asks = [
        {"price": 0.50, "size": 100.0},
        {"price": 0.55, "size": 500.0},
    ]
    result = simulate_fill(asks, budget_usd=100.0)
    assert result["filled"] is True
    assert result["levels_consumed"] == 2
    assert result["contracts"] == pytest.approx(100.0 + 50.0 / 0.55, rel=1e-4)
    assert 0.50 < result["vwap"] < 0.55


@pytest.mark.unit
def test_thin_book_partial_fill_remaining_budget():
    """Book has only ~$40 of depth across all levels for a $100 budget."""
    asks = [
        {"price": 0.50, "size": 60.0},
        {"price": 0.60, "size": 16.667},
    ]
    result = simulate_fill(asks, budget_usd=100.0)
    assert result["filled"] is True
    assert result["levels_consumed"] == 2
    assert result["remaining_budget"] == pytest.approx(60.0, rel=1e-3)
    assert result["contracts"] == pytest.approx(60.0 + 16.667, rel=1e-3)


@pytest.mark.unit
def test_empty_book_returns_unfilled():
    """No asks at all, nothing to buy."""
    result = simulate_fill([], budget_usd=100.0)
    assert result["filled"] is False
    assert result["contracts"] == 0
    assert result["filled_usd"] == 0
    assert result["remaining_budget"] == 100.0
    assert result["levels_consumed"] == 0


@pytest.mark.unit
def test_zero_budget_returns_unfilled():
    """Zero budget can't fill anything."""
    asks = [{"price": 0.40, "size": 100.0}]
    result = simulate_fill(asks, budget_usd=0.0)
    assert result["filled"] is False
    assert result["contracts"] == 0


@pytest.mark.unit
def test_unsorted_asks_are_sorted_by_price():
    """Caller may pass asks in arbitrary order, function sorts ascending."""
    asks = [
        {"price": 0.55, "size": 100.0},
        {"price": 0.40, "size": 50.0},
        {"price": 0.50, "size": 100.0},
    ]
    result = simulate_fill(asks, budget_usd=20.0)
    assert result["filled"] is True
    assert result["levels_consumed"] == 1
    assert result["vwap"] == pytest.approx(0.40, abs=1e-6)


@pytest.mark.unit
def test_slippage_pp_reflects_vwap_minus_top():
    """Slippage = vwap minus best ask, in percentage points (0.01 = 1pp)."""
    asks = [
        {"price": 0.50, "size": 50.0},
        {"price": 0.60, "size": 1000.0},
    ]
    result = simulate_fill(asks, budget_usd=75.0)
    # Level 1: $25 at 0.50 = 50 contracts
    # Level 2: $50 at 0.60 = 83.33 contracts
    # vwap = 75 / 133.33 = 0.5625; slippage_pp = (0.5625 - 0.50) * 100 = 6.25
    assert result["slippage_pp"] == pytest.approx(6.25, abs=0.05)


@pytest.mark.unit
def test_fee_estimate_at_winning_resolution():
    """Fee is estimated against the WIN payout (per contract * $1 * fee_rate)."""
    asks = [{"price": 0.40, "size": 1000.0}]
    result = simulate_fill(asks, budget_usd=100.0, fee_rate=0.02)
    assert result["fee_estimate_if_win"] == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# is_economic_when_correct: catches the BUY at 99c trap
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_economic_when_cheap_entry_with_real_upside():
    """Healthy directional bet: cheap entry, big upside."""
    fill = {"contracts": 250.0, "filled_usd": 100.0, "fee_estimate_if_win": 5.0}
    assert is_economic_when_correct(fill) is True


@pytest.mark.unit
def test_uneconomic_when_buying_at_99_cents():
    """The trap observed live: BUY_NO at 99.9c on a near-zero YES market.
    Each contract pays $1 if we win, fee is 2c, paid 99.9c. Net = -1.9c.
    """
    fill = {"contracts": 100.1, "filled_usd": 100.0, "fee_estimate_if_win": 2.0}
    assert is_economic_when_correct(fill) is False


@pytest.mark.unit
def test_uneconomic_when_unfilled():
    """A fill with zero contracts cannot be economic by definition."""
    fill = {"contracts": 0, "filled_usd": 0, "fee_estimate_if_win": 0}
    assert is_economic_when_correct(fill) is False


@pytest.mark.unit
def test_break_even_is_treated_as_uneconomic():
    """Zero net is not positive EV. The guard requires strict > 0."""
    fill = {"contracts": 102.0, "filled_usd": 100.0, "fee_estimate_if_win": 2.0}
    assert is_economic_when_correct(fill) is False


@pytest.mark.unit
def test_economic_when_just_above_break_even():
    """Strictly positive payout-after-fee passes."""
    fill = {"contracts": 103.0, "filled_usd": 100.0, "fee_estimate_if_win": 2.0}
    assert is_economic_when_correct(fill) is True
