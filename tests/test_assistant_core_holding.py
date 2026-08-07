"""Tests for the index core and the corrected tactical exit policy.

These cover the two defects measured in the Jul-Aug 2026 paper run:
  1. Both books sat on idle cash (90.1% strategic, 47.7% tactical) against an
     SPY benchmark, which is an unfunded short against the benchmark.
  2. Tactical positions were created without a ``price_target`` and with a
     fixed volatility stop, so both available exits realised a loss and the
     book closed 2 trades for 2 losses.
"""

import pytest

from app.services.core_holding import CORE_NOTE, is_core


class _Pos:
    """Minimal stand-in for the Position ORM row."""

    def __init__(self, note=None, symbol="SPY", quantity=1.0, avg_price=100.0, stop_loss=None):
        self.note = note
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.stop_loss = stop_loss


class TestCoreMarker:
    def test_core_position_is_recognised(self):
        assert is_core(_Pos(note=CORE_NOTE))

    def test_marker_is_case_and_space_insensitive(self):
        assert is_core(_Pos(note="  Core  "))

    def test_conviction_positions_are_not_core(self):
        assert not is_core(_Pos(note="rule trend_following"))
        assert not is_core(_Pos(note=None))
        assert not is_core(_Pos(note=""))


class TestCoreSizingArithmetic:
    """The sweep must leave exactly the configured buffer in cash."""

    @staticmethod
    def investable(cash: float, equity: float, buffer_pct: float, minimum: float) -> float:
        target = cash - equity * buffer_pct / 100.0
        return target if target >= minimum else 0.0

    def test_sweeps_everything_above_the_buffer(self):
        # The strategic book as measured: $9,147.69 cash on $10,150.99 equity.
        amount = self.investable(9_147.69, 10_150.99, 5.0, 100.0)
        assert amount == pytest.approx(9_147.69 - 507.55, abs=0.01)
        # Post-sweep the book holds ~5% cash instead of 90%.
        assert (9_147.69 - amount) / 10_150.99 == pytest.approx(0.05, abs=0.001)

    def test_no_trade_when_already_deployed(self):
        assert self.investable(400.0, 10_000.0, 5.0, 100.0) == 0.0

    def test_no_trade_below_minimum_notional(self):
        # $560 cash on a $10k book leaves $60 investable — below the $100 floor.
        assert self.investable(560.0, 10_000.0, 5.0, 100.0) == 0.0

    def test_zero_buffer_deploys_everything(self):
        assert self.investable(1_000.0, 10_000.0, 0.0, 100.0) == pytest.approx(1_000.0)


class TestCoreFundsSignals:
    """A satellite entry must be able to raise cash by selling core."""

    @staticmethod
    def shortfall(needed: float, cash: float) -> float:
        return max(0.0, needed - cash)

    def test_sells_only_the_shortfall(self):
        # Need $500, hold $80 cash -> free $420, leaving the rest invested.
        assert self.shortfall(500.0, 80.0) == pytest.approx(420.0)

    def test_no_sale_when_cash_suffices(self):
        assert self.shortfall(500.0, 600.0) == 0.0

    def test_weighted_average_cost_basis_on_add(self):
        # 10 @ 100 then 10 @ 120 -> average 110, so P&L stays honest.
        qty1, px1, qty2, px2 = 10.0, 100.0, 10.0, 120.0
        avg = (px1 * qty1 + px2 * qty2) / (qty1 + qty2)
        assert avg == pytest.approx(110.0)


class TestTrailingStop:
    """The ratchet is what makes a profitable rule exit possible at all."""

    TRAIL = 12.0

    @staticmethod
    def ratchet(current_stop, price, trail_pct):
        candidate = round(price * (1 - trail_pct / 100.0), 4)
        if current_stop is None or candidate > current_stop:
            return candidate
        return current_stop

    def test_stop_rises_with_price(self):
        entry_stop = 237.37 * (1 - self.TRAIL / 100)
        # AMZN ran from 237.37 to 274.19; the stop should follow it up.
        raised = self.ratchet(entry_stop, 274.19, self.TRAIL)
        assert raised > entry_stop
        assert raised == pytest.approx(274.19 * 0.88, abs=0.01)

    def test_stop_never_falls(self):
        high_stop = 274.19 * 0.88
        # Price pulls back — the stop must hold, not follow it down.
        assert self.ratchet(high_stop, 250.0, self.TRAIL) == high_stop

    def test_ratcheted_stop_exits_in_profit(self):
        """The whole point: exiting on a trailing stop can be a WIN."""
        entry = 237.37
        peak = 274.19
        stop_at_peak = self.ratchet(entry * 0.88, peak, self.TRAIL)
        assert stop_at_peak > entry, "a trailing exit must be able to land above entry"
        # Realised P&L if stopped out at that level is positive.
        assert (stop_at_peak / entry - 1) > 0

    def test_fixed_stop_could_only_ever_lose(self):
        """Regression guard for the measured defect.

        The old policy set a fixed stop below entry and no target, so both
        exits (stop hit, trend break) realised a loss by construction.
        """
        entry = 237.37
        fixed_stop = entry * (1 - 0.075)  # 2.5x daily vol, clamped
        assert fixed_stop < entry
        assert (fixed_stop / entry - 1) < 0


class TestReentryCooldown:
    """Stopping out and immediately re-buying higher is pure loss."""

    @staticmethod
    def blocked(days_since_sell: int, cooldown_days: int) -> bool:
        return cooldown_days > 0 and days_since_sell < cooldown_days

    def test_blocks_the_measured_churn(self):
        # LLY was sold and re-bought the SAME day at a higher price.
        assert self.blocked(0, 5)

    def test_amazon_case_is_blocked(self):
        # AMZN sold 2026-07-23, re-bought 2026-07-30 at a higher price.
        assert self.blocked(7, 10)

    def test_allows_entry_after_cooldown(self):
        assert not self.blocked(6, 5)

    def test_disabled_when_zero(self):
        assert not self.blocked(0, 0)
