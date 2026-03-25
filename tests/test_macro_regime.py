from unittest.mock import patch

import pandas as pd


def _make_series(start: float, end: float, length: int = 250) -> pd.Series:
    dates = pd.date_range("2025-09-01", periods=length, freq="B")
    step = (end - start) / max(length - 1, 1)
    return pd.Series([start + step * i for i in range(length)], index=dates)


def _mock_download_for_risk_on(symbols, **_kwargs):
    if isinstance(symbols, str):
        symbols = [symbols]

    series_map = {
        "^VIX": _make_series(30, 12),
        "^GSPC": _make_series(4000, 6000),
        "HYG": _make_series(75, 90),
        "LQD": _make_series(100, 100),
        "TLT": _make_series(100, 99),
        "SHY": _make_series(100, 100),
        "XLU": _make_series(60, 61),
        "XLP": _make_series(70, 71),
        "XLV": _make_series(80, 81),
        "XLY": _make_series(100, 120),
        "XLK": _make_series(100, 125),
        "XLI": _make_series(100, 118),
    }

    frame = pd.DataFrame({symbol: series_map[symbol] for symbol in symbols})
    return pd.concat({"Close": frame}, axis=1)


def test_signal_vix_level_thresholds():
    from tradingagents.dataflows.macro_regime import _signal_vix_level

    assert _signal_vix_level(14.0)[0] == 1
    assert _signal_vix_level(30.0)[0] == -1
    assert _signal_vix_level(20.0)[0] == 0


def test_classify_macro_regime_returns_risk_on_for_mocked_risk_on_data():
    with patch("yfinance.download", side_effect=_mock_download_for_risk_on):
        from tradingagents.dataflows.macro_regime import classify_macro_regime

        regime = classify_macro_regime()

    assert regime["regime"] == "risk-on"
    assert regime["score"] >= 3


def test_classify_macro_regime_returns_required_keys_and_six_signals():
    with patch("yfinance.download", side_effect=_mock_download_for_risk_on):
        from tradingagents.dataflows.macro_regime import classify_macro_regime

        regime = classify_macro_regime()

    assert set(["regime", "score", "confidence", "signals", "summary"]).issubset(regime)
    assert len(regime["signals"]) == 6


def test_classify_macro_regime_uses_curr_date_for_download_window():
    calls = []

    def fake_download(symbols, **kwargs):
        calls.append(kwargs)
        return _mock_download_for_risk_on(symbols, **kwargs)

    with patch("yfinance.download", side_effect=fake_download):
        from tradingagents.dataflows.macro_regime import classify_macro_regime

        classify_macro_regime("2026-03-17")

    assert all(call["end"].startswith("2026-03-18") for call in calls)


def test_format_macro_report_contains_signal_breakdown_and_trading_implications():
    from tradingagents.dataflows.macro_regime import format_macro_report

    report = format_macro_report(
        {
            "regime": "risk-on",
            "score": 4,
            "confidence": "high",
            "vix": 14.5,
            "signals": [
                {"name": "vix_level", "score": 1, "description": "Low VIX"},
                {"name": "vix_trend", "score": 1, "description": "Falling VIX"},
                {"name": "credit_spread", "score": 1, "description": "Improving"},
                {"name": "yield_curve", "score": 0, "description": "Neutral"},
                {"name": "market_breadth", "score": 1, "description": "Above SMA"},
                {"name": "sector_rotation", "score": 0, "description": "Neutral"},
            ],
            "summary": "Risk-on summary",
        }
    )

    assert "Signal Breakdown" in report
    assert "What This Means for Trading" in report
    assert "RISK-ON" in report
