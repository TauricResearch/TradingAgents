"""Tests for the single-source indicator registry.

The registry replaces three hand-synced copies of indicator metadata (the
yfinance ``best_ind_params`` dict, the Alpha Vantage description dict, and the
market analyst's hardcoded prompt menu). The golden test pins the prompt lines
that predate the registry so refactors can never silently drift the agent's
instructions; the wiring tests prove every registered name computes through
the yfinance window without network access.

Mirrors the no-network style of ``tests/test_zscore.py``: hand-built frames,
monkeypatched ``load_ohlcv``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import indicator_registry as reg


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


# The market analyst's indicator menu exactly as it read before the registry
# existed (agents/analysts/market_analyst.py). These lines are the contract:
# they must keep appearing verbatim, in this relative order, no matter how
# many indicators are added around them. Never paraphrase them — the agent's
# behavior is calibrated against this text.
LEGACY_PROMPT_LINES = [
    "Moving Averages:",
    "- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
    "- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
    "- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
    "MACD Related:",
    "- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
    "- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
    "- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
    "Momentum Indicators:",
    "- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
    "Volatility Indicators:",
    "- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
    "- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
    "- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
    "- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
    "Volume-Based Indicators:",
    "- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
    "Sequential / Exhaustion:",
    "- td_9: TD-9 (TD Sequential Setup): A DeMark exhaustion/reversal signal computed on three timeframes at once — weekly (Tier 1, primary), monthly (Tier 2, regime context) and daily (Tier 3, entry timing). A single td_9 call returns the current running count (signed: + buy-setup, - sell-setup) for all three tiers. Usage: a count climbing toward 9 flags approaching trend exhaustion; a completed 9 is a reversal watch. Report the current count for each timeframe even when below 9. Tips: when timeframes disagree, weight the higher tier above the lower one (weekly > monthly > daily); a daily 9 does not override a weekly setup still in progress.",
    "Mean Reversion / Stretch:",
    "- z_score: Z-Score (20-period close z-score): How far the close sits from its 20-period mean, in standard deviations, computed on three timeframes at once — weekly (Tier 1, primary), monthly (Tier 2, regime context) and daily (Tier 3, entry timing). A single z_score call returns the current reading (signed: + above mean / overbought, - below mean / oversold) for all three tiers. Usage: |z| >= 2 flags a statistically stretched price and a mean-reversion watch; near 0 is fair value. Report the reading for each timeframe. Tips: when timeframes disagree, weight the higher tier above the lower one (weekly > monthly > daily); a high z-score in a strong trend can persist, so confirm with a trend indicator before fading it.",
]


@pytest.mark.unit
class TestPromptSection:
    def test_legacy_prompt_lines_render_verbatim_and_in_order(self):
        """The anti-drift contract: every pre-registry prompt line still
        appears verbatim, and their relative order is unchanged."""
        rendered_lines = reg.render_prompt_section().splitlines()
        positions = []
        for line in LEGACY_PROMPT_LINES:
            assert line in rendered_lines, f"prompt line drifted or vanished: {line!r}"
            positions.append(rendered_lines.index(line))
        assert positions == sorted(positions), "legacy prompt lines were reordered"

    def test_section_contains_no_braces(self):
        # The system message flows through ChatPromptTemplate; stray braces in
        # a description would be parsed as template variables and crash.
        section = reg.render_prompt_section()
        assert "{" not in section and "}" not in section

    def test_every_prompt_entry_is_a_registered_name(self):
        rendered = reg.render_prompt_section()
        for line in rendered.splitlines():
            if line.startswith("- "):
                name = line[2:].split(":", 1)[0]
                assert name in reg.INDICATORS


@pytest.mark.unit
class TestRegistryLookups:
    def test_unknown_name_raises_with_supported_list(self):
        with pytest.raises(ValueError, match="not_an_indicator"):
            reg.get_spec("not_an_indicator")

    def test_snapshot_indicators_are_plain_stockstats_columns(self):
        # The snapshot computes via wrap()[column]; custom OHLCV indicators
        # cannot be in the default set.
        for name in reg.snapshot_indicators():
            assert reg.INDICATORS[name].custom is None
            assert reg.resolve_column(name)

    def test_resolve_column_defaults_to_legacy_bare_column(self):
        assert reg.resolve_column("rsi") == "rsi"
        assert reg.resolve_column("boll_ub") == "boll_ub"
        assert reg.resolve_column("close_50_sma") == "close_50_sma"

    def test_resolve_column_rejects_custom_indicators(self):
        with pytest.raises(ValueError):
            reg.resolve_column("td_9")


@pytest.mark.unit
class TestYFinanceWindowWiring:
    def test_every_stockstats_name_computes_through_the_window(self, monkeypatch):
        """Each non-custom registry name resolves to a real stockstats column
        and produces a windowed report with its registry description."""
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i % 7 for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        for name, spec in reg.INDICATORS.items():
            if spec.custom is not None:
                continue
            out = y_finance.get_stock_stats_indicators_window(
                "AAPL", name, "2026-06-04", 5
            )
            assert f"## {name} values" in out
            assert spec.description in out

    def test_custom_names_return_tiered_blocks(self, monkeypatch):
        from tradingagents.dataflows import y_finance

        frame = _ohlcv([100 + i for i in range(320)])
        monkeypatch.setattr(y_finance, "load_ohlcv", lambda symbol, curr_date: frame)

        for name in ("td_9", "z_score"):
            out = y_finance.get_stock_stats_indicators_window(
                "AAPL", name, "2026-06-04", 30
            )
            assert "Tier 1" in out and "Weekly" in out


@pytest.mark.unit
class TestSingleSourcedDescriptions:
    def test_alpha_vantage_unsupported_names_raise(self):
        """AV-unsupported names raise so route_to_vendor falls back to
        yfinance instead of treating prose as a successful result."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        for name, spec in reg.INDICATORS.items():
            if spec.av_function is None:
                with pytest.raises(ValueError):
                    av.get_indicator("AAPL", name, "2026-06-04", 30)

    def test_alpha_vantage_serves_registry_description(self, monkeypatch):
        """A (mocked) successful AV response is annotated with the same
        registry description the yfinance path uses."""
        from tradingagents.dataflows import alpha_vantage_indicator as av

        monkeypatch.setattr(
            av,
            "_make_api_request",
            lambda function, params: "time,RSI\n2026-06-04,55.5\n",
        )
        out = av.get_indicator("AAPL", "rsi", "2026-06-04", 30)
        assert "2026-06-04: 55.5" in out
        assert reg.INDICATORS["rsi"].description in out
