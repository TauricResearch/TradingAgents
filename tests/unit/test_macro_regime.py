"""Tests for macro regime classifier (risk-on / transition / risk-off)."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

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


def test_finviz_vix_scrape_uses_env_timeout(monkeypatch):
    from tradingagents.dataflows.macro_regime import _download_vix_from_finviz_vx_futures

    class _Response:
        status_code = 200
        text = "<title>VIX Futures</title>"

    monkeypatch.setenv("TRADINGAGENTS_MACRO_REGIME_FINVIZ_TIMEOUT_SEC", "11")
    with patch(
        "tradingagents.dataflows.macro_regime.requests.get", return_value=_Response()
    ) as mocked_get:
        _download_vix_from_finviz_vx_futures()

    assert mocked_get.call_args.kwargs["timeout"] == 11.0


@pytest.mark.parametrize("raw_timeout", ["0", "-1", "inf", "nan"])
def test_env_float_timeout_rejects_non_positive_or_non_finite(monkeypatch, raw_timeout):
    from tradingagents.dataflows.macro_regime import _env_float

    monkeypatch.setenv("TRADINGAGENTS_MACRO_REGIME_FINVIZ_TIMEOUT_SEC", raw_timeout)

    assert _env_float("TRADINGAGENTS_MACRO_REGIME_FINVIZ_TIMEOUT_SEC", 20.0) == 20.0


@pytest.mark.parametrize(
    "raw_date",
    [
        "today",
        "2026-03-30 12:00:00",
        "2026-03-30T00:00:00",
        "03/30/2026",
        "2026/03/30",
        "2026-02-30",
        "",
        "2026-3-30",
    ],
)
def test_parse_as_of_date_rejects_non_iso_dates(raw_date):
    from tradingagents.dataflows.macro_regime import _parse_as_of_date

    with pytest.raises(ValueError):
        _parse_as_of_date(raw_date)


def test_parse_as_of_date_accepts_strict_iso_date():
    from tradingagents.dataflows.macro_regime import _parse_as_of_date

    assert _parse_as_of_date("2026-03-30").strftime("%Y-%m-%d") == "2026-03-30"


# ---------------------------------------------------------------------------
# Helpers tests
# ---------------------------------------------------------------------------


class TestFmtPct:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _fmt_pct

        self.fn = _fmt_pct

    @pytest.mark.parametrize(
        ("val", "expected"),
        [
            (None, "N/A"),
            (1.234, "+1.2%"),
            (-1.234, "-1.2%"),
            (0.0, "+0.0%"),
        ],
    )
    def test_fmt_pct(self, val, expected):
        assert self.fn(val) == expected


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

    def test_short_history_is_neutral(self):
        hyg = _trending_series(80, 85, 21)
        lqd = _flat_series(100, 21)
        score, desc = self.fn(hyg, lqd)
        assert score == 0
        assert "insufficient history" in desc

    def test_none_data_is_neutral(self):
        score, _ = self.fn(None, None)
        assert score == 0


class TestSignalYieldCurve:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_yield_curve

        self.fn = _signal_yield_curve

    def test_flight_to_safety_is_risk_off(self):
        tlt = _trending_series(100, 110, 30)
        shy = _flat_series(100, 30)
        score, desc = self.fn(tlt, shy)
        assert score == -1

    def test_risk_appetite_is_risk_on(self):
        tlt = _trending_series(110, 100, 30)
        shy = _flat_series(100, 30)
        score, desc = self.fn(tlt, shy)
        assert score == 1

    def test_short_history_is_neutral(self):
        tlt = _trending_series(100, 110, 21)
        shy = _flat_series(100, 21)
        score, desc = self.fn(tlt, shy)
        assert score == 0
        assert "insufficient history" in desc

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

    def test_short_history_is_neutral(self):
        spx = _make_series([5000.0] * 199)
        score, desc = self.fn(spx)
        assert score == 0
        assert "insufficient history" in desc

    def test_none_data_is_neutral(self):
        score, _ = self.fn(None)
        assert score == 0


class TestSignalSectorRotation:
    def setup_method(self):
        from tradingagents.dataflows.macro_regime import _signal_sector_rotation

        self.fn = _signal_sector_rotation

    def test_defensives_leading_is_risk_off(self):
        defensives = {"XLU": _trending_series(100, 110, 30)}
        cyclicals = {"XLY": _flat_series(100, 30)}
        score, desc = self.fn(defensives, cyclicals)
        assert score == -1

    def test_cyclicals_leading_is_risk_on(self):
        defensives = {"XLU": _flat_series(100, 30)}
        cyclicals = {"XLY": _trending_series(100, 110, 30)}
        score, desc = self.fn(defensives, cyclicals)
        assert score == 1

    def test_short_history_is_neutral(self):
        defensives = {"XLU": _trending_series(100, 110, 21)}
        cyclicals = {"XLY": _flat_series(100, 21)}
        score, desc = self.fn(defensives, cyclicals)
        assert score == 0
        assert "unavailable" in desc

    def test_empty_dicts_is_neutral(self):
        score, desc = self.fn({}, {})
        assert score == 0


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
            hyg = _trending_series(75, 90, n)  # HYG rising sharply (credit improving) → +1
            lqd = _flat_series(100, n)
            tlt = _flat_series(100, n)  # TLT flat (no flight to safety) → 0
            shy = _flat_series(100, n)
            xlu = _flat_series(60, n)
            xlp = _flat_series(70, n)
            xlv = _flat_series(80, n)
            xly = _trending_series(100, 120, n)
            xlk = _trending_series(100, 120, n)
            xli = _trending_series(100, 120, n)  # cyclicals up → +1
        elif scenario == "risk_off":
            vix = _flat_series(30.0, n)  # High VIX
            spx = _trending_series(6000, 4000, n)  # Below 200-SMA
            hyg = _trending_series(85, 80, n)  # Deteriorating credit
            lqd = _flat_series(100, n)
            tlt = _trending_series(95, 105, n)  # TLT outperforming (flight to safety)
            shy = _flat_series(100, n)
            xlu = _trending_series(60, 66, n)
            xlp = _trending_series(70, 77, n)
            xlv = _trending_series(80, 88, n)
            xly = _flat_series(150, n)
            xlk = _flat_series(180, n)
            xli = _flat_series(100, n)
        else:  # transition
            vix = _flat_series(20.0, n)  # Mid VIX
            spx = _trending_series(4900, 5100, n)  # Near 200-SMA
            hyg = _flat_series(82, n)
            lqd = _flat_series(100, n)
            tlt = _flat_series(100, n)
            shy = _flat_series(100, n)
            xlu = _flat_series(60, n)
            xlp = _flat_series(70, n)
            xlv = _flat_series(80, n)
            xly = _flat_series(150, n)
            xlk = _flat_series(180, n)
            xli = _flat_series(100, n)

        return {
            "^VIX": vix,
            "^GSPC": spx,
            "HYG": hyg,
            "LQD": lqd,
            "TLT": tlt,
            "SHY": shy,
            "XLU": xlu,
            "XLP": xlp,
            "XLV": xlv,
            "XLY": xly,
            "XLK": xlk,
            "XLI": xli,
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

    def test_curr_date_uses_bounded_downloads_including_scan_date(self, monkeypatch):
        from tradingagents.dataflows import macro_regime
        from tradingagents.dataflows.macro_regime import classify_macro_regime

        calls = []
        series_map = self._mock_download("risk_on")

        def fake_safe_yf_download(symbols, start=None, end=None, **kwargs):
            calls.append({"symbols": list(symbols), "start": start, "end": end, "kwargs": kwargs})
            data = {symbol: series_map[symbol] for symbol in symbols if symbol in series_map}
            return pd.concat({"Close": pd.DataFrame(data)}, axis=1)

        monkeypatch.setattr(macro_regime, "safe_yf_download", fake_safe_yf_download)
        monkeypatch.setattr(
            macro_regime,
            "_download_vix_proxy_from_alpha_vantage",
            lambda: (_ for _ in ()).throw(AssertionError("Alpha Vantage fallback called")),
        )
        monkeypatch.setattr(
            macro_regime,
            "_download_vix_from_finviz_vx_futures",
            lambda: (_ for _ in ()).throw(AssertionError("Finviz fallback called")),
        )

        result = classify_macro_regime("2026-03-30")

        assert result["regime"] == "risk-on"
        assert {call["end"] for call in calls} == {"2026-03-31"}
        assert {"^GSPC"} in [set(call["symbols"]) for call in calls]
        market_call = next(call for call in calls if call["symbols"] == ["^GSPC"])
        assert market_call["start"] < "2026-03-30"

    def test_curr_date_fails_without_latest_only_vix_fallback(self, monkeypatch):
        from tradingagents.dataflows import macro_regime
        from tradingagents.dataflows.macro_regime import classify_macro_regime

        series_map = self._mock_download("risk_on")

        def fake_safe_yf_download(symbols, start=None, end=None, **kwargs):
            data = {
                symbol: series_map[symbol]
                for symbol in symbols
                if symbol in series_map and symbol != "^VIX"
            }
            if not data:
                return pd.DataFrame()
            return pd.concat({"Close": pd.DataFrame(data)}, axis=1)

        monkeypatch.setattr(macro_regime, "safe_yf_download", fake_safe_yf_download)
        monkeypatch.setattr(
            macro_regime,
            "_download_vix_proxy_from_alpha_vantage",
            lambda: (_ for _ in ()).throw(AssertionError("Alpha Vantage fallback called")),
        )
        monkeypatch.setattr(
            macro_regime,
            "_download_vix_from_finviz_vx_futures",
            lambda: (_ for _ in ()).throw(AssertionError("Finviz fallback called")),
        )

        with pytest.raises(RuntimeError) as exc:
            classify_macro_regime("2026-03-30")

        assert "^VIX" in str(exc.value)


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

    def test_get_macro_regime_passes_curr_date_to_report_formatter(self, monkeypatch):
        from tradingagents.agents.utils import fundamental_data_tools

        captured = {}

        def fake_classify_macro_regime(curr_date):
            captured["classify_date"] = curr_date
            return {
                "regime": "risk-on",
                "score": 3,
                "confidence": "high",
                "signals": [],
                "summary": "summary",
            }

        def fake_format_macro_report(regime_data, report_date=None):
            captured["report_date"] = report_date
            return f"report_date={report_date}"

        monkeypatch.setattr(
            fundamental_data_tools, "classify_macro_regime", fake_classify_macro_regime
        )
        monkeypatch.setattr(
            fundamental_data_tools, "format_macro_report", fake_format_macro_report
        )

        result = fundamental_data_tools.get_macro_regime.invoke({"curr_date": "2026-03-30"})

        assert result == "report_date=2026-03-30"
        assert captured == {
            "classify_date": "2026-03-30",
            "report_date": "2026-03-30",
        }

    def test_get_macro_regime_preserves_live_report_formatter_when_date_missing(self, monkeypatch):
        from tradingagents.agents.utils import fundamental_data_tools

        captured = {}

        monkeypatch.setattr(
            fundamental_data_tools,
            "classify_macro_regime",
            lambda curr_date: captured.setdefault("classify_date", curr_date) or {},
        )

        def fake_format_macro_report(regime_data, report_date=None):
            captured["report_date"] = report_date
            return "live report"

        monkeypatch.setattr(
            fundamental_data_tools, "format_macro_report", fake_format_macro_report
        )

        result = fundamental_data_tools.get_macro_regime.invoke({})

        assert result == "live report"
        assert captured == {"classify_date": None, "report_date": None}


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
