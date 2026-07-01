"""Tests for MFI wiring and the Alpha Vantage fallback contract.

MFI was half-wired: described in the yfinance dict but absent from the analyst
prompt, the verified snapshot and the Alpha Vantage vendor — and stockstats
computes it on a 0-1 scale while the conventional (and Alpha Vantage) scale is
0-100. These tests pin the 0-100 rescale in both the tool output and the
snapshot, and pin the vendor contract that Alpha Vantage *raises* for names it
cannot serve (returning prose would short-circuit ``route_to_vendor``'s
fallback chain, which only advances on exceptions).

No network: hand-built frames, monkeypatched ``load_ohlcv`` and
``_make_api_request``. Mirrors ``tests/test_zscore.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest
from stockstats import wrap

from tradingagents.dataflows import indicator_registry as reg


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
class TestMfiRescale:
    def test_window_values_are_stockstats_times_100(self, monkeypatch):
        """The tool reports exactly stockstats' mfi rescaled to 0-100."""
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + (i % 9) - 4 for i in range(60)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        expected = wrap(frame.copy())
        expected_last = float(expected["mfi"].iloc[-1]) * 100.0

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "mfi", "2026-06-04", 5
        )
        reported = float(out.split("2026-06-04: ")[1].splitlines()[0])
        assert reported == pytest.approx(expected_last)

    def test_rising_series_reads_overbought_on_0_100_scale(self, monkeypatch):
        """All-positive money flow saturates MFI at the top of the 0-100
        range — on the raw stockstats scale it would read 1.0."""
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(60)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        out = y_finance.get_stock_stats_indicators_window(
            "AAPL", "mfi", "2026-06-04", 5
        )
        reported = float(out.split("2026-06-04: ")[1].splitlines()[0])
        assert reported > 80  # overbought per the description's threshold

    def test_snapshot_reports_mfi_on_0_100_scale(self, monkeypatch):
        import tradingagents.dataflows.market_data_validator as validator

        frame = _ohlcv([100 + i for i in range(60)])
        monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: frame)

        snap = validator.build_verified_market_snapshot("COF", "2026-06-04")
        mfi_rows = [ln for ln in snap.splitlines() if ln.startswith("| mfi |")]
        assert len(mfi_rows) == 1
        value = float(mfi_rows[0].split("|")[2].strip())
        assert 1.0 < value <= 100.0  # rescaled, not the raw 0-1 reading

    def test_mfi_is_in_prompt_and_snapshot_defaults(self):
        assert "- mfi:" in reg.render_prompt_section()
        assert "mfi" in reg.snapshot_indicators()


@pytest.mark.unit
class TestAlphaVantageContract:
    def test_vwma_raises_so_router_falls_back(self):
        """Regression for the short-circuit bug: AV used to *return* an
        informative paragraph for vwma, which route_to_vendor treated as a
        successful result and never tried yfinance."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        with pytest.raises(ValueError):
            av.get_indicator("AAPL", "vwma", "2026-06-04", 30)

    def test_route_to_vendor_falls_back_to_yfinance_for_vwma(self, monkeypatch):
        """End-to-end: with Alpha Vantage forced primary, vwma still returns
        yfinance-computed values."""
        import copy

        from tradingagents.dataflows import interface, y_finance
        from tradingagents.dataflows.config import get_config, set_config

        frame = _ohlcv([100 + i for i in range(60)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        saved = copy.deepcopy(get_config())  # restore so global config doesn't leak
        try:
            cfg = get_config()
            cfg.setdefault("tool_vendors", {})["get_indicators"] = "alpha_vantage,yfinance"
            set_config(cfg)

            out = interface.route_to_vendor(
                "get_indicators", "AAPL", "vwma", "2026-06-04", 5
            )
            assert "## vwma values" in out
        finally:
            set_config(saved)

    def test_every_name_either_requests_or_raises(self, monkeypatch):
        """The permanent contract: for every registered name, Alpha Vantage
        either issues an API request (served names) or raises ValueError
        (unsupported names). It never returns prose without a request — that
        is exactly the short-circuit shape."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        for name, spec in reg.INDICATORS.items():
            calls = []

            def fake_request(function, params, _calls=calls, _spec=spec):
                _calls.append(function)
                return f"time,{_spec.av_column}\n2026-06-04,42\n"

            monkeypatch.setattr(av, "_make_api_request", fake_request)

            if spec.av_function is None:
                with pytest.raises(ValueError):
                    av.get_indicator("AAPL", name, "2026-06-04", 30)
                assert calls == []
            else:
                out = av.get_indicator("AAPL", name, "2026-06-04", 30)
                assert calls == [spec.av_function]
                assert f"## {name.upper()} values" in out

    def test_mfi_request_carries_time_period_without_series_type(self, monkeypatch):
        from tradingagents.dataflows import alpha_vantage_indicator as av

        captured = {}

        def fake_request(function, params):
            captured["function"] = function
            captured["params"] = params
            return "time,MFI\n2026-06-04,77.7\n"

        monkeypatch.setattr(av, "_make_api_request", fake_request)
        out = av.get_indicator("AAPL", "mfi", "2026-06-04", 30)

        assert captured["function"] == "MFI"
        assert captured["params"]["time_period"] == "14"
        assert "series_type" not in captured["params"]
        assert "2026-06-04: 77.7" in out
