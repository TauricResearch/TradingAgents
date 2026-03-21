"""Tests for macro regime classifier (risk-on / transition / risk-off)."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_series(values: list[float], freq: str = "B") -> pd.Series:
    dates = pd.date_range("2025-09-01", periods=len(values), freq=freq)
    return pd.Series(values, index=dates)


def _flat_series(value: float, n: int = 100) -> pd.Series:
    return _make_series([value] * n)


def _trending_series(start: float, end: float, n: int = 100) -> pd.Series:
    return _make_series(list(np.linspace(start, end, n)))


# ---------------------------------------------------------------------------
# Individual signal tests
# ---------------------------------------------------------------------------

class TestSignalVixLevel:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_vix_level
        self.fn = _signal_vix_level

    def test_low_vix_is_risk_on(self):
        score, desc = self.fn(14.0)
        assert score == 1
        assert "risk-on" in desc

    def test_high_vix_is_risk_off(self):
        score, desc = self.fn(30.0)
        assert score == -1
        assert "risk-off" in desc

    def test_mid_vix_is_neutral(self):
        score, desc = self.fn(20.0)
        assert score == 0

    def test_none_vix_is_neutral(self):
        score, desc = self.fn(None)
        assert score == 0
        assert "unavailable" in desc

    def test_boundary_at_16(self):
        # Exactly at threshold — not below, so transition
        score, _ = self.fn(16.0)
        assert score == 0

    def test_boundary_at_25(self):
        # Exactly at threshold — not above, so transition
        score, _ = self.fn(25.0)
        assert score == 0


class TestSignalVixTrend:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_vix_trend
        self.fn = _signal_vix_trend

    def test_declining_vix_is_risk_on(self):
        # SMA5 < SMA20: VIX is falling
        vix = _trending_series(30, 15, 30)
        score, desc = self.fn(vix)
        assert score == 1
        assert "risk-on" in desc

    def test_rising_vix_is_risk_off(self):
        # SMA5 > SMA20: VIX is rising
        vix = _trending_series(10, 30, 30)
        score, desc = self.fn(vix)
        assert score == -1
        assert "risk-off" in desc

    def test_insufficient_history_is_neutral(self):
        vix = _make_series([20.0] * 4)
        score, desc = self.fn(vix)
        assert score == 0

    def test_short_history_is_neutral(self):
        vix = _make_series([20.0] * 20)
        score, desc = self.fn(vix)
        assert score == 0
        assert "insufficient history" in desc

    def test_none_series_is_neutral(self):
        score, desc = self.fn(None)
        assert score == 0


class TestSignalCreditSpread:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_credit_spread
        self.fn = _signal_credit_spread

    def test_improving_spread_is_risk_on(self):
        # HYG/LQD ratio rising by >0.5% over 1 month
        hyg = _trending_series(80, 85, 30)
        lqd = _flat_series(100, 30)
        score, desc = self.fn(hyg, lqd)
        assert score == 1

    def test_deteriorating_spread_is_risk_off(self):
        # HYG/LQD ratio falling by >0.5%
        hyg = _trending_series(85, 80, 30)
        lqd = _flat_series(100, 30)
        score, desc = self.fn(hyg, lqd)
        assert score == -1

    def test_none_data_is_neutral(self):
        score, _ = self.fn(None, None)
        assert score == 0


class TestSignalMarketBreadth:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_market_breadth
        self.fn = _signal_market_breadth

    def test_above_200sma_is_risk_on(self):
        # Flat series ending above its own 200-SMA (which equals the series mean)
        # Use upward trending — latest value > SMA
        spx = _trending_series(4000, 6000, 250)
        score, desc = self.fn(spx)
        assert score == 1
        assert "risk-on" in desc

    def test_below_200sma_is_risk_off(self):
        # Downward trending — latest value < SMA
        spx = _trending_series(6000, 4000, 250)
        score, desc = self.fn(spx)
        assert score == -1
        assert "risk-off" in desc

    def test_insufficient_history_is_neutral(self):
        spx = _make_series([5000.0] * 100)
        score, _ = self.fn(spx)
        assert score == 0  # < 200 points for SMA200


# ---------------------------------------------------------------------------
# Classify macro regime
# ---------------------------------------------------------------------------

class TestClassifyMacroRegime:
    def _mock_download(self, scenario: str):
        """Return mock yfinance download data for different scenarios."""
        n = 250

        if scenario == "risk_on":
            vix = _trending_series(30, 12, n)  # VIX falling → +1 trend AND +1 level at end
            spx = _trending_series(4000, 6000, n)  # Above 200-SMA → +1
            hyg = _trending_series(75, 90, n)   # HYG rising sharply (credit improving) → +1
            lqd = _flat_series(100, n)
            tlt = _flat_series(100, n)     # TLT flat (no flight to safety) → 0
            shy = _flat_series(100, n)
            xlu = _flat_series(60, n); xlp = _flat_series(70, n); xlv = _flat_series(80, n)
            xly = _trending_series(100, 120, n); xlk = _trending_series(100, 120, n); xli = _trending_series(100, 120, n)  # cyclicals up → +1
        elif scenario == "risk_off":
            vix = _flat_series(30.0, n)    # High VIX
            spx = _trending_series(6000, 4000, n)  # Below 200-SMA
            hyg = _trending_series(85, 80, n)   # Deteriorating credit
            lqd = _flat_series(100, n)
            tlt = _trending_series(95, 105, n)  # TLT outperforming (flight to safety)
            shy = _flat_series(100, n)
            xlu = _trending_series(60, 66, n); xlp = _trending_series(70, 77, n); xlv = _trending_series(80, 88, n)
            xly = _flat_series(150, n); xlk = _flat_series(180, n); xli = _flat_series(100, n)
        else:  # transition
            vix = _flat_series(20.0, n)    # Mid VIX
            spx = _trending_series(4900, 5100, n)  # Near 200-SMA
            hyg = _flat_series(82, n)
            lqd = _flat_series(100, n)
            tlt = _flat_series(100, n)
            shy = _flat_series(100, n)
            xlu = _flat_series(60, n); xlp = _flat_series(70, n); xlv = _flat_series(80, n)
            xly = _flat_series(150, n); xlk = _flat_series(180, n); xli = _flat_series(100, n)

        return {
            "^VIX": vix, "^GSPC": spx,
            "HYG": hyg, "LQD": lqd,
            "TLT": tlt, "SHY": shy,
            "XLU": xlu, "XLP": xlp, "XLV": xlv,
            "XLY": xly, "XLK": xlk, "XLI": xli,
        }

    def _patch_download(self, scenario: str):
        series_map = self._mock_download(scenario)

        def fake_download(symbols, **kwargs):
            if isinstance(symbols, str):
                symbols = [symbols]
            data = {s: series_map[s] for s in symbols if s in series_map}
            if not data:
                return pd.DataFrame()
            df = pd.DataFrame(data)
            return pd.concat({"Close": df}, axis=1)

        return patch("yfinance.download", side_effect=fake_download)

    def test_risk_on_regime(self):
        with self._patch_download("risk_on"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        assert result["regime"] == "risk-on"
        assert result["score"] >= 3

    def test_risk_off_regime(self):
        with self._patch_download("risk_off"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        assert result["regime"] == "risk-off"
        assert result["score"] <= -3

    def test_result_has_required_keys(self):
        with self._patch_download("transition"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        for key in ("regime", "score", "confidence", "signals", "summary"):
            assert key in result

    def test_signals_list_has_6_entries(self):
        with self._patch_download("transition"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        assert len(result["signals"]) == 6

    def test_each_signal_has_score_and_description(self):
        with self._patch_download("transition"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        for sig in result["signals"]:
            assert "score" in sig
            assert "description" in sig
            assert sig["score"] in (-1, 0, 1)

    def test_confidence_is_valid(self):
        with self._patch_download("risk_on"):
            from tradingagents.dataflows.macro_regime import classify_macro_regime
            result = classify_macro_regime()
        assert result["confidence"] in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Format macro report
# ---------------------------------------------------------------------------

class TestFormatMacroReport:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import format_macro_report
        self.format = format_macro_report

    def _sample_regime(self, regime: str) -> dict:
        return {
            "regime": regime,
            "score": 3 if regime == "risk-on" else -3 if regime == "risk-off" else 0,
            "confidence": "high",
            "vix": 14.5,
            "signals": [
                {"name": "vix_level", "score": 1, "description": "VIX low"},
                {"name": "vix_trend", "score": 1, "description": "VIX declining"},
                {"name": "credit_spread", "score": 1, "description": "Improving"},
                {"name": "yield_curve", "score": 0, "description": "Neutral"},
                {"name": "market_breadth", "score": 0, "description": "Above SMA"},
                {"name": "sector_rotation", "score": 0, "description": "Cyclicals lead"},
            ],
            "summary": f"Regime: {regime}",
        }

    def test_report_contains_regime_label(self):
        for regime in ("risk-on", "risk-off", "transition"):
            report = self.format(self._sample_regime(regime))
            assert regime.upper() in report

    def test_report_contains_signal_table(self):
        report = self.format(self._sample_regime("risk-on"))
        assert "Signal Breakdown" in report
        assert "Vix Level" in report

    def test_report_contains_trading_implications(self):
        for regime in ("risk-on", "risk-off", "transition"):
            report = self.format(self._sample_regime(regime))
            assert "What This Means for Trading" in report

    def test_risk_on_suggests_cyclicals(self):
        report = self.format(self._sample_regime("risk-on"))
        assert "cyclicals" in report.lower() or "growth" in report.lower()

    def test_risk_off_suggests_defensives(self):
        report = self.format(self._sample_regime("risk-off"))
        assert "defensive" in report.lower()


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMacroRegimeIntegration:
    def test_get_macro_regime_tool(self):
        from tradingagents.agents.utils.fundamental_data_tools import get_macro_regime
        result = get_macro_regime.invoke({"curr_date": "2026-03-17"})
        assert isinstance(result, str)
        assert len(result) > 100
        assert any(r in result.upper() for r in ("RISK-ON", "RISK-OFF", "TRANSITION"))
