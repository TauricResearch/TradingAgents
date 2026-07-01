"""Tests for the Phase-3 indicator additions: OBV and the ADX/KDJ/StochRSI
stockstats natives.

The generic every-name-computes loop lives in ``test_indicator_registry``;
this file pins the behaviors specific to the new names: OBV's manual cumsum
math and windowed rendering, the agent-facing ``mdi`` -> stockstats ``ndi``
column mapping, and the new names' presence in the prompt menu and snapshot.

No network: hand-built frames, monkeypatched ``load_ohlcv``.
"""

from __future__ import annotations

import pandas as pd
import pytest
from stockstats import wrap

from tradingagents.dataflows import indicator_registry as reg, stockstats_utils as su


def _ohlcv(closes, end="2026-06-04", volumes=None):
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
            "Volume": volumes or [1_000_000] * len(closes),
        }
    )


@pytest.mark.unit
class TestComputeObv:
    def test_matches_manual_signed_cumsum(self):
        # up day +200, down day -300, unchanged day adds nothing
        frame = _ohlcv([10.0, 11.0, 11.0, 9.0], volumes=[100, 200, 250, 300])
        obv = su.compute_obv(frame)
        assert list(obv) == [0.0, 200.0, 200.0, -100.0]

    def test_first_bar_contributes_nothing(self):
        frame = _ohlcv([10.0], volumes=[5_000])
        assert list(su.compute_obv(frame)) == [0.0]

    def test_is_date_indexed(self):
        frame = _ohlcv([10.0, 11.0, 12.0])
        obv = su.compute_obv(frame)
        assert list(obv.index) == list(pd.DatetimeIndex(frame["Date"]))

    def test_rising_series_rises_with_price(self):
        obv = su.compute_obv(_ohlcv([100 + i for i in range(30)]))
        assert obv.iloc[-1] > obv.iloc[0]


@pytest.mark.unit
class TestObvWindowWiring:
    def test_obv_renders_as_windowed_daily_listing(self, monkeypatch):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([10.0, 11.0, 11.0, 9.0], volumes=[100, 200, 250, 300])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "obv", "2026-06-04", 3
        )
        assert "## obv values" in out
        assert "2026-06-04: -100.0" in out
        assert reg.INDICATORS["obv"].description in out


@pytest.mark.unit
class TestMdiColumnMapping:
    def test_mdi_resolves_to_stockstats_ndi(self):
        # stockstats has no `mdi` handler — the conventional agent-facing name
        # maps to its `ndi` column.
        assert reg.resolve_column("mdi") == "ndi"

    def test_mdi_window_values_are_ndi_values(self, monkeypatch):
        from tradingagents.dataflows import y_finance

        closes = [100 + ((i * 7) % 13) - 6 for i in range(120)]
        frame = _ohlcv(closes)
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        expected = float(wrap(frame.copy())["ndi"].iloc[-1])
        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "mdi", "2026-06-04", 3
        )
        reported = float(out.split("2026-06-04: ")[1].splitlines()[0])
        assert reported == pytest.approx(expected)


@pytest.mark.unit
class TestMenuAndSnapshotAdditions:
    def test_new_names_appear_in_prompt_menu(self):
        section = reg.render_prompt_section()
        for name in ("adx", "pdi", "mdi", "kdjk", "kdjd", "kdjj", "stochrsi", "obv", "supertrend", "mfi"):
            assert f"- {name}: " in section
        assert "Trend Strength:" in section
        assert "Stochastic:" in section

    def test_snapshot_gains_mfi_adx_kdjk_only(self):
        names = reg.snapshot_indicators()
        legacy = {
            "close_10_ema", "close_50_sma", "close_200_sma",
            "rsi", "boll", "boll_ub", "boll_lb",
            "macd", "macds", "macdh", "atr",
        }
        assert set(names) == legacy | {"mfi", "adx", "kdjk"}

    def test_snapshot_computes_new_indicators(self, monkeypatch):
        import tradingagents.dataflows.market_data_validator as validator

        frame = _ohlcv([100 + ((i * 7) % 13) - 6 for i in range(320)])
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: frame)

        snap = validator.build_verified_market_snapshot("COF", "2026-06-04")
        for name in ("mfi", "adx", "kdjk"):
            rows = [ln for ln in snap.splitlines() if ln.startswith(f"| {name} |")]
            assert len(rows) == 1, f"snapshot missing {name}"
            assert "N/A" not in rows[0], f"snapshot failed to compute {name}: {rows[0]}"
