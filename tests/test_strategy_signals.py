"""Tests for the quantitative strategy signals framework (task 8).

Verifies: signal computation, format output, graceful fallback on missing data.
"""

import unittest

import numpy as np
import pandas as pd

from tradingagents.strategies.base import BaseStrategy, StrategySignal
from tradingagents.strategies.registry import (
    compute_signals,
    format_signals_for_role,
    get_strategies,

)
from tradingagents.strategies.scorecard import compute_scorecard, scorecard_summary


# ---------------------------------------------------------------------------
# Helpers — synthetic data builders
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300, start: float = 100.0, trend: float = 0.001) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with *n* rows."""
    dates = pd.bdate_range(end="2025-01-15", periods=n)
    rng = np.random.RandomState(42)
    close = start * np.cumprod(1 + trend + rng.randn(n) * 0.01)
    return pd.DataFrame({
        "Open": close * 0.999,
        "High": close * 1.005,
        "Low": close * 0.995,
        "Close": close,
        "Volume": rng.randint(1_000_000, 10_000_000, n),
    }, index=dates)


def _make_info(**overrides: object) -> dict:
    """Return a minimal yfinance-style info dict."""
    base = {
        "priceToBook": 3.0,
        "trailingPE": 20.0,
        "marketCap": 2_000_000_000_000,
        "freeCashflow": 80_000_000_000,
        "trailingEps": 6.0,
        "forwardEps": 7.0,
        "returnOnEquity": 0.35,
        "sector": "Technology",
        "impliedVolatility": 0.25,
    }
    base.update(overrides)
    return base


def _ctx(**kw: object) -> dict:
    """Build a context dict with ohlcv and/or info."""
    ctx: dict = {}
    if "ohlcv" not in kw:
        ctx["ohlcv"] = _make_ohlcv()
    if "info" not in kw:
        ctx["info"] = _make_info()
    ctx.update(kw)
    return ctx


# ---------------------------------------------------------------------------
# 1. Signal computation — individual strategies with synthetic data
# ---------------------------------------------------------------------------

class TestSignalComputation(unittest.TestCase):
    """Each strategy returns a valid StrategySignal from synthetic data."""

    def setUp(self) -> None:
        pass

    def _assert_valid_signal(self, sig: StrategySignal | None, *, allow_none: bool = False) -> None:
        if sig is None:
            if allow_none:
                return
            self.fail("Expected a signal, got None")
        self.assertIn("name", sig)
        self.assertIn("ticker", sig)
        self.assertIn("date", sig)
        self.assertIn("value", sig)
        self.assertIn("direction", sig)
        self.assertIn("detail", sig)
        self.assertIn(sig["direction"], ("SUPPORTS", "CONTRADICTS", "NEUTRAL"))
        self.assertGreaterEqual(sig["value"], -1.0)
        self.assertLessEqual(sig["value"], 1.0)

    def test_momentum(self) -> None:
        from tradingagents.strategies.momentum import MomentumStrategy
        sig = MomentumStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_mean_reversion(self) -> None:
        from tradingagents.strategies.mean_reversion import MeanReversionStrategy
        sig = MeanReversionStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_value(self) -> None:
        from tradingagents.strategies.value import ValueStrategy
        sig = ValueStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_volatility(self) -> None:
        from tradingagents.strategies.volatility import VolatilityStrategy
        sig = VolatilityStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_moving_average(self) -> None:
        from tradingagents.strategies.moving_average import MovingAverageStrategy
        sig = MovingAverageStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_support_resistance(self) -> None:
        from tradingagents.strategies.support_resistance import SupportResistanceStrategy
        sig = SupportResistanceStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_earnings_momentum(self) -> None:
        from tradingagents.strategies.earnings_momentum import EarningsMomentumStrategy
        sig = EarningsMomentumStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_multifactor(self) -> None:
        from tradingagents.strategies.multifactor import MultifactorStrategy
        sig = MultifactorStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_trend_following(self) -> None:
        from tradingagents.strategies.trend_following import TrendFollowingStrategy
        sig = TrendFollowingStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_alpha_combo(self) -> None:
        from tradingagents.strategies.alpha_combo import AlphaComboStrategy
        sig = AlphaComboStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_vol_targeting(self) -> None:
        from tradingagents.strategies.vol_targeting import VolTargetingStrategy
        sig = VolTargetingStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_tax_optimization_with_drawdown(self) -> None:
        """Tax optimization needs a drawdown > 5% to produce a signal."""
        from tradingagents.strategies.tax_optimization import TaxOptimizationStrategy
        # Build OHLCV with a big drop at the end
        df = _make_ohlcv(300, start=100.0, trend=0.001)
        df.iloc[-1, df.columns.get_loc("Close")] = float(df["Close"].max()) * 0.70  # 30% drawdown
        sig = TaxOptimizationStrategy().compute("TEST", "2025-01-15", {"ohlcv": df})
        self._assert_valid_signal(sig)
        self.assertEqual(sig["direction"], "CONTRADICTS")

    def test_implied_vol(self) -> None:
        from tradingagents.strategies.implied_vol import ImpliedVolStrategy
        sig = ImpliedVolStrategy().compute("TEST", "2025-01-15", _ctx())
        self._assert_valid_signal(sig)

    def test_event_driven_with_earnings(self) -> None:
        """Event-driven needs an upcoming event within 30 days."""
        from tradingagents.strategies.event_driven import EventDrivenStrategy
        from datetime import datetime, timedelta
        future = datetime(2025, 1, 25)  # 10 days after ref date
        info = _make_info(earningsDate=future.strftime("%Y-%m-%d"))
        sig = EventDrivenStrategy().compute("TEST", "2025-01-15", {"info": info})
        self._assert_valid_signal(sig)
        self.assertEqual(sig["direction"], "NEUTRAL")


# ---------------------------------------------------------------------------
# 2. Format output — format_signals_for_role and scorecard
# ---------------------------------------------------------------------------

class TestFormatOutput(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def _sample_signals(self) -> list[StrategySignal]:
        return [
            StrategySignal(name="Momentum (§3.1)", ticker="AAPL", date="2025-01-15",
                           value=0.45, direction="SUPPORTS", detail="12-1 month return: +18%"),
            StrategySignal(name="Mean Reversion (§3.9)", ticker="AAPL", date="2025-01-15",
                           value=-0.30, direction="CONTRADICTS", detail="Z-score: +1.8 (overbought)"),
            StrategySignal(name="Value (§3.3)", ticker="AAPL", date="2025-01-15",
                           value=0.10, direction="NEUTRAL", detail="Composite: 0.55"),
        ]

    def test_format_signals_for_role_market(self) -> None:
        """Momentum and Mean Reversion target 'market'; Value does not."""
        signals = self._sample_signals()
        out = format_signals_for_role(signals, "market")
        self.assertIn("Momentum", out)
        self.assertIn("Mean Reversion", out)
        self.assertIn("## Quantitative Strategy Signals", out)

    def test_format_signals_for_role_fundamentals(self) -> None:
        """Value targets 'fundamentals'; Momentum does not."""
        signals = self._sample_signals()
        out = format_signals_for_role(signals, "fundamentals")
        self.assertIn("Value", out)
        self.assertNotIn("Momentum", out)

    def test_format_signals_empty_role(self) -> None:
        """Role with no matching signals returns empty string."""
        signals = self._sample_signals()
        out = format_signals_for_role(signals, "social")
        self.assertEqual(out, "")

    def test_format_signals_empty_list(self) -> None:
        out = format_signals_for_role([], "market")
        self.assertEqual(out, "")

    def test_compute_scorecard(self) -> None:
        signals = self._sample_signals()
        sc = compute_scorecard(signals)
        self.assertIsNotNone(sc)
        self.assertEqual(sc["ticker"], "AAPL")
        self.assertEqual(sc["total"], 3)
        self.assertEqual(sc["SUPPORTS"], 1)
        self.assertEqual(sc["CONTRADICTS"], 1)
        self.assertEqual(sc["NEUTRAL"], 1)
        self.assertIn(sc["overall"], ("SUPPORTS", "CONTRADICTS", "NEUTRAL"))

    def test_compute_scorecard_empty(self) -> None:
        self.assertIsNone(compute_scorecard([]))

    def test_scorecard_summary(self) -> None:
        sc = compute_scorecard(self._sample_signals())
        text = scorecard_summary(sc)
        self.assertIn("Strategy Consensus Scorecard", text)
        self.assertIn("AAPL", text)

    def test_scorecard_summary_none(self) -> None:
        self.assertEqual(scorecard_summary(None), "")


# ---------------------------------------------------------------------------
# 3. Graceful fallback on missing data
# ---------------------------------------------------------------------------

class TestGracefulFallback(unittest.TestCase):
    """Strategies return None (not raise) when data is missing or insufficient."""

    def setUp(self) -> None:
        pass

    def test_momentum_insufficient_data(self) -> None:
        from tradingagents.strategies.momentum import MomentumStrategy
        short_df = _make_ohlcv(n=50)  # needs 252
        sig = MomentumStrategy().compute("TEST", "2025-01-15", {"ohlcv": short_df})
        self.assertIsNone(sig)

    def test_momentum_none_ohlcv(self) -> None:
        from tradingagents.strategies.momentum import MomentumStrategy
        sig = MomentumStrategy().compute("TEST", "2025-01-15", {"ohlcv": None})
        self.assertIsNone(sig)

    def test_value_no_info(self) -> None:
        from tradingagents.strategies.value import ValueStrategy
        sig = ValueStrategy().compute("TEST", "2025-01-15", {"info": None})
        self.assertIsNone(sig)

    def test_value_empty_info(self) -> None:
        from tradingagents.strategies.value import ValueStrategy
        sig = ValueStrategy().compute("TEST", "2025-01-15", {"info": {}})
        self.assertIsNone(sig)

    def test_earnings_momentum_missing_eps(self) -> None:
        from tradingagents.strategies.earnings_momentum import EarningsMomentumStrategy
        sig = EarningsMomentumStrategy().compute("TEST", "2025-01-15", {"info": {"trailingEps": 5.0}})
        self.assertIsNone(sig)

    def test_mean_reversion_short_data(self) -> None:
        from tradingagents.strategies.mean_reversion import MeanReversionStrategy
        sig = MeanReversionStrategy().compute("TEST", "2025-01-15", {"ohlcv": _make_ohlcv(n=10)})
        self.assertIsNone(sig)

    def test_moving_average_short_data(self) -> None:
        from tradingagents.strategies.moving_average import MovingAverageStrategy
        sig = MovingAverageStrategy().compute("TEST", "2025-01-15", {"ohlcv": _make_ohlcv(n=100)})
        self.assertIsNone(sig)

    def test_volatility_short_data(self) -> None:
        from tradingagents.strategies.volatility import VolatilityStrategy
        sig = VolatilityStrategy().compute("TEST", "2025-01-15", {"ohlcv": _make_ohlcv(n=30)})
        self.assertIsNone(sig)

    def test_implied_vol_no_iv(self) -> None:
        from tradingagents.strategies.implied_vol import ImpliedVolStrategy
        sig = ImpliedVolStrategy().compute("TEST", "2025-01-15", _ctx(info=_make_info(impliedVolatility=None)))
        self.assertIsNone(sig)

    def test_event_driven_no_events(self) -> None:
        from tradingagents.strategies.event_driven import EventDrivenStrategy
        sig = EventDrivenStrategy().compute("TEST", "2025-01-15", {"info": _make_info()})
        self.assertIsNone(sig)

    def test_tax_optimization_no_drawdown(self) -> None:
        """No signal when price is near 252d high (drawdown < 5%)."""
        from tradingagents.strategies.tax_optimization import TaxOptimizationStrategy
        sig = TaxOptimizationStrategy().compute("TEST", "2025-01-15", _ctx())
        # With uptrending synthetic data, price is near high → None
        self.assertIsNone(sig)

    def test_compute_signals_no_crash(self) -> None:
        """compute_signals never raises, even with bad context."""
        signals = compute_signals("FAKE", "2025-01-15", {"ohlcv": None, "info": None})
        self.assertIsInstance(signals, list)


# ---------------------------------------------------------------------------
# 4. Registry basics
# ---------------------------------------------------------------------------

class TestRegistry(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def test_get_strategies_returns_strategies(self) -> None:
        reg = get_strategies()
        self.assertGreater(len(reg), 0)
        for s in reg:
            self.assertIsInstance(s, BaseStrategy)
            self.assertTrue(s.name)
            self.assertIsInstance(s.roles, list)

    def test_all_18_strategies_discovered(self) -> None:
        """All 18 strategies from the spec should be auto-discovered."""
        reg = get_strategies()
        names = {s.name for s in reg}
        self.assertGreaterEqual(len(names), 18, f"Only found {len(names)} strategies: {names}")

    def test_rediscovery(self) -> None:
        """Strategies are discovered on first call."""
        reg = get_strategies()
        self.assertGreater(len(reg), 0)


if __name__ == "__main__":
    unittest.main()
