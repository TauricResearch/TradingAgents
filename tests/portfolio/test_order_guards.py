"""Tests for tradingagents.portfolio.order_guards — shared buy-order guard module."""

import pytest

from tradingagents.portfolio.order_guards import buy_order_guard, resolve_buy_execution_price

# ---------------------------------------------------------------------------
# resolve_buy_execution_price
# ---------------------------------------------------------------------------


class TestResolveBuyExecutionPrice:
    def test_returns_live_price_when_present(self):
        buy = {"ticker": "MSFT", "limit_price": 305.0, "entry_price": 300.0}
        assert resolve_buy_execution_price(buy, {"MSFT": 298.0}) == 298.0

    def test_raises_when_ticker_missing_from_prices(self):
        buy = {"ticker": "MSFT"}
        with pytest.raises(RuntimeError, match="missing live price.*MSFT"):
            resolve_buy_execution_price(buy, {"AAPL": 200.0})

    def test_raises_when_price_is_zero(self):
        buy = {"ticker": "MSFT"}
        with pytest.raises(RuntimeError, match="non-positive live price"):
            resolve_buy_execution_price(buy, {"MSFT": 0.0})

    def test_raises_when_price_is_negative(self):
        buy = {"ticker": "MSFT"}
        with pytest.raises(RuntimeError, match="non-positive live price"):
            resolve_buy_execution_price(buy, {"MSFT": -1.0})

    def test_raises_when_ticker_is_empty(self):
        buy = {"ticker": ""}
        with pytest.raises(RuntimeError, match="empty ticker"):
            resolve_buy_execution_price(buy, {})

    def test_requires_live_price_for_sgov_too(self):
        """SGOV is exempt from order guards but still requires a live price."""
        buy = {"ticker": "SGOV", "sector": "Cash Equivalent"}
        with pytest.raises(RuntimeError, match="missing live price.*SGOV"):
            resolve_buy_execution_price(buy, {})

    def test_returns_sgov_live_price_when_present(self):
        buy = {"ticker": "SGOV", "sector": "Cash Equivalent"}
        assert resolve_buy_execution_price(buy, {"SGOV": 100.03}) == 100.03


# ---------------------------------------------------------------------------
# buy_order_guard — SGOV cash-sweep exemption
# ---------------------------------------------------------------------------


class TestBuyOrderGuardCashSweepExemption:
    def test_sgov_cash_equivalent_passes_regardless_of_price_levels(self):
        buy = {
            "ticker": "SGOV",
            "sector": "Cash Equivalent",
            "limit_price": 99.0,
            "max_chase_price": 99.0,
            "stop_loss": 0.0,
            "take_profit": 99.0,
            "order_type": "limit",
        }
        # live price above limit — would fail for normal buy, exempt here
        assert buy_order_guard(buy, 100.50) is None

    def test_sgov_without_cash_equivalent_sector_is_not_exempt(self):
        """If someone uses SGOV ticker but wrong sector, guard still applies."""
        buy = {
            "ticker": "SGOV",
            "sector": "Fixed Income",
            "limit_price": 99.0,
            "max_chase_price": 99.0,
        }
        assert buy_order_guard(buy, 100.50) is not None


# ---------------------------------------------------------------------------
# buy_order_guard — order_type
# ---------------------------------------------------------------------------


class TestBuyOrderGuardOrderType:
    def test_accepts_limit_order_type(self):
        buy = {"ticker": "MSFT", "order_type": "limit"}
        assert buy_order_guard(buy, 300.0) is None

    def test_rejects_market_order_type(self):
        buy = {"ticker": "MSFT", "order_type": "market"}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "order_type" in result

    def test_accepts_missing_order_type(self):
        """When order_type is absent the guard defers — schema validates presence."""
        buy = {"ticker": "MSFT"}
        assert buy_order_guard(buy, 300.0) is None


# ---------------------------------------------------------------------------
# buy_order_guard — limit_price
# ---------------------------------------------------------------------------


class TestBuyOrderGuardLimitPrice:
    def test_passes_when_live_below_limit(self):
        buy = {"ticker": "MSFT", "limit_price": 305.0, "order_type": "limit"}
        assert buy_order_guard(buy, 298.0) is None

    def test_passes_when_live_equals_limit(self):
        buy = {"ticker": "MSFT", "limit_price": 300.0, "order_type": "limit"}
        assert buy_order_guard(buy, 300.0) is None

    def test_rejects_when_live_above_limit(self):
        buy = {"ticker": "MSFT", "limit_price": 305.0, "order_type": "limit"}
        result = buy_order_guard(buy, 310.0)
        assert result is not None
        assert "limit_price violated" in result
        assert "MSFT" in result

    def test_rejects_non_positive_limit_price(self):
        buy = {"ticker": "MSFT", "limit_price": 0.0}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "limit_price must be positive" in result


# ---------------------------------------------------------------------------
# buy_order_guard — max_chase_price
# ---------------------------------------------------------------------------


class TestBuyOrderGuardMaxChasePrice:
    def test_passes_when_live_below_max_chase(self):
        buy = {"ticker": "RMAX", "max_chase_price": 10.50}
        assert buy_order_guard(buy, 9.94) is None

    def test_rejects_when_live_above_max_chase(self):
        buy = {"ticker": "RMAX", "max_chase_price": 10.25}
        result = buy_order_guard(buy, 11.29)
        assert result is not None
        assert "max_chase_price violated" in result
        assert "RMAX" in result

    def test_rejects_non_positive_max_chase(self):
        buy = {"ticker": "RMAX", "max_chase_price": -1.0}
        result = buy_order_guard(buy, 10.0)
        assert result is not None
        assert "max_chase_price must be positive" in result


# ---------------------------------------------------------------------------
# buy_order_guard — stop_loss
# ---------------------------------------------------------------------------


class TestBuyOrderGuardStopLoss:
    def test_passes_when_stop_loss_below_live(self):
        buy = {"ticker": "MSFT", "stop_loss": 270.0}
        assert buy_order_guard(buy, 300.0) is None

    def test_rejects_when_stop_loss_equals_live(self):
        buy = {"ticker": "MSFT", "stop_loss": 300.0}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "stop_loss" in result

    def test_rejects_when_stop_loss_above_live(self):
        buy = {"ticker": "MSFT", "stop_loss": 310.0}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "stop_loss" in result

    def test_skips_stop_loss_check_when_zero(self):
        """stop_loss=0 means 'not set' for cash-sweep-style orders."""
        buy = {"ticker": "MSFT", "stop_loss": 0.0}
        assert buy_order_guard(buy, 300.0) is None


# ---------------------------------------------------------------------------
# buy_order_guard — take_profit
# ---------------------------------------------------------------------------


class TestBuyOrderGuardTakeProfit:
    def test_passes_when_take_profit_above_live(self):
        buy = {"ticker": "MSFT", "take_profit": 360.0}
        assert buy_order_guard(buy, 300.0) is None

    def test_rejects_when_take_profit_equals_live(self):
        buy = {"ticker": "MSFT", "take_profit": 300.0}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "take_profit" in result

    def test_rejects_when_take_profit_below_live(self):
        buy = {"ticker": "MSFT", "take_profit": 290.0}
        result = buy_order_guard(buy, 300.0)
        assert result is not None
        assert "take_profit" in result

    def test_skips_take_profit_check_when_zero(self):
        buy = {"ticker": "MSFT", "take_profit": 0.0}
        assert buy_order_guard(buy, 300.0) is None


# ---------------------------------------------------------------------------
# buy_order_guard — combined full-order happy path
# ---------------------------------------------------------------------------


class TestBuyOrderGuardFullOrder:
    def _valid_buy(self) -> dict:
        return {
            "ticker": "RMAX",
            "shares": 300.0,
            "entry_price": 9.94,
            "limit_price": 10.25,
            "max_chase_price": 10.25,
            "order_type": "limit",
            "valid_as_of": "2026-04-28",
            "price_target": 12.92,
            "stop_loss": 8.45,
            "take_profit": 12.92,
            "sector": "Real Estate",
        }

    def test_valid_order_passes_all_guards(self):
        assert buy_order_guard(self._valid_buy(), 9.94) is None

    def test_live_at_limit_still_passes(self):
        assert buy_order_guard(self._valid_buy(), 10.25) is None

    def test_live_one_cent_above_limit_fails(self):
        result = buy_order_guard(self._valid_buy(), 10.26)
        assert result is not None
        assert "limit_price violated" in result
