"""Tests for config-driven indicator parameter overrides.

The ``indicator_params`` config key remaps an indicator's window without
changing its agent-facing name: ``{"rsi": {"window": 7}}`` keeps the name
``rsi`` in prompts and reports but computes ``rsi_7``. The override must flow
identically through the get_indicators tool window, the verified snapshot and
the Alpha Vantage request params — and an empty config must stay byte-level
on the legacy bare column names.

No network: hand-built frames, monkeypatched ``load_ohlcv`` /
``_make_api_request``, config save/restore via ``set_config`` (the pattern
from ``tests/test_zscore.py``).
"""

from __future__ import annotations

import copy

import pandas as pd
import pytest
from stockstats import wrap

from tradingagents.dataflows import indicator_registry as reg
from tradingagents.dataflows.config import get_config, set_config


def _ohlcv(closes, end="2026-06-04"):
    """OHLCV frame of ``len(closes)`` business days ending at ``end``."""
    dates = pd.bdate_range(end=end, periods=len(closes))
    closes = [float(c) for c in closes]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        }
    )


@pytest.fixture
def indicator_params():
    """Set indicator_params for one test, restoring the global config after.

    Restores by reassigning the module global rather than via ``set_config``:
    set_config merges dict keys one level deep, so it can update but never
    *remove* an override — replaying the saved config would leak the test's
    override into later tests.
    """
    from tradingagents.dataflows import config as config_module

    saved = copy.deepcopy(get_config())

    def _set(params: dict):
        cfg = get_config()
        cfg["indicator_params"] = params
        set_config(cfg)

    try:
        yield _set
    finally:
        config_module._config = saved


@pytest.mark.unit
class TestResolveColumn:
    def test_defaults_resolve_to_legacy_bare_columns(self):
        for name in ("rsi", "boll", "boll_ub", "boll_lb", "atr", "vwma", "mfi", "kdjk"):
            assert reg.resolve_column(name, reg.effective_params(name, {})) == name
        assert reg.resolve_column("close_50_sma", reg.effective_params("close_50_sma", {})) == "close_50_sma"

    def test_override_resolves_to_windowed_column(self):
        assert reg.resolve_column("rsi", {"window": 7}) == "rsi_7"
        assert reg.resolve_column("close_50_sma", {"window": 20}) == "close_20_sma"
        # stockstats appends the window suffix *after* the band suffix
        assert reg.resolve_column("boll_ub", {"window": 30}) == "boll_ub_30"
        assert reg.resolve_column("mdi", {"window": 21}) == "ndi_21"

    def test_unknown_override_keys_are_ignored(self):
        params = reg.effective_params("rsi", {"rsi": {"bogus": 99}})
        assert params == {"window": 14}
        assert reg.resolve_column("rsi", params) == "rsi"

    def test_non_parameterizable_names_keep_their_column(self):
        # adx's smoothing windows are stockstats class attributes; macd only
        # supports the awkward comma form — both stay fixed.
        assert reg.resolve_column("adx", reg.effective_params("adx", {"adx": {"window": 21}})) == "adx"
        assert reg.resolve_column("macd", reg.effective_params("macd", {})) == "macd"


@pytest.mark.unit
class TestWindowToolRespectsOverrides:
    def test_rsi_window_7_matches_direct_stockstats_rsi_7(self, monkeypatch, indicator_params):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + ((i * 7) % 13) - 6 for i in range(120)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        ss = wrap(frame.copy())
        expected_7 = float(ss["rsi_7"].iloc[-1])
        expected_14 = float(ss["rsi"].iloc[-1])

        indicator_params({"rsi": {"window": 7}})
        out = y_finance.get_stock_stats_indicators_window("AAPL", "rsi", "2026-06-04", 3)
        reported = float(out.split("2026-06-04: ")[1].splitlines()[0])

        assert reported == pytest.approx(expected_7)
        assert reported != pytest.approx(expected_14)
        assert "## rsi (window=7) values" in out  # header shows effective params

    def test_default_config_keeps_legacy_header(self, monkeypatch):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i % 7 for i in range(60)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window("AAPL", "rsi", "2026-06-04", 3)
        assert "## rsi values" in out
        assert "(window=" not in out

    def test_zscore_window_override_shows_in_block(self, monkeypatch, indicator_params):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        indicator_params({"z_score": {"window": 10}})
        out = y_finance.get_stock_stats_indicators_window("AAPL", "z_score", "2026-06-04", 30)
        assert "Z-Score (10-period close z-score)" in out

    def test_supertrend_window_override_shows_in_block(self, monkeypatch, indicator_params):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        indicator_params({"supertrend": {"window": 10}})
        out = y_finance.get_stock_stats_indicators_window("AAPL", "supertrend", "2026-06-04", 30)
        assert "SuperTrend (10-period" in out


@pytest.mark.unit
class TestSnapshotRespectsOverrides:
    def test_snapshot_rsi_uses_configured_window(self, monkeypatch, indicator_params):
        import tradingagents.dataflows.market_data_validator as validator

        frame = _ohlcv([100 + ((i * 7) % 13) - 6 for i in range(120)])
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: frame)

        ss = wrap(frame.copy())
        expected_7 = float(ss["rsi_7"].iloc[-1])

        indicator_params({"rsi": {"window": 7}})
        snap = validator.build_verified_market_snapshot("COF", "2026-06-04")
        rsi_rows = [ln for ln in snap.splitlines() if ln.startswith("| rsi |")]
        assert len(rsi_rows) == 1
        assert float(rsi_rows[0].split("|")[2].strip()) == pytest.approx(expected_7, abs=0.01)


@pytest.mark.unit
class TestAlphaVantageRespectsOverrides:
    def test_overridden_window_is_sent_as_time_period(self, monkeypatch, indicator_params):
        from tradingagents.dataflows import alpha_vantage_indicator as av

        captured = {}

        def fake_request(function, params):
            captured["params"] = params
            return "time,RSI\n2026-06-04,55.5\n"

        monkeypatch.setattr(av, "_make_api_request", fake_request)

        indicator_params({"rsi": {"window": 7}})
        av.get_indicator("AAPL", "rsi", "2026-06-04", 30)
        assert captured["params"]["time_period"] == "7"
