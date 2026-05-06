# Range Stats + User Research Upload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two features atop the TradingAgents multi-agent pipeline:
(1) per-day open/close/volume vs 52w/6m/3m/1m high-low range stats consumed by the `market_analyst` LLM tool, the WebUI, and the Telegram daily report; and (2) per-user research note upload (PDF/markdown/text) auto-summarized and injected as a new `user_research_report` field that the four downstream agents (bull, bear, research_manager, trader) consume.

**Architecture:** Two pure-Python compute modules (`range_stats.py`, `user_research.py`) under `tradingagents/dataflows/`. Each is consumed by three integration layers: the LangChain agents (state field + new tool), the Streamlit WebUI (cards + uploader), and the Telegram render path in `scheduler.py`/`notify.py`. Storage is per-user filesystem under existing `_user_home_for(email)` convention — no DB, no migration. Both features are backwards-compatible: empty research field → byte-identical existing flows; range-stats failures degrade gracefully without blocking analysis.

**Tech Stack:** Python 3.11+, LangGraph, LangChain, Streamlit, pandas, yfinance (existing), `pypdf>=4.0,<6` (new). pytest for tests.

**Spec:** `docs/superpowers/specs/2026-05-06-range-stats-and-research-upload-design.md`

---

## Phase 1 — Range Stats

### Task 1: Core `compute_range_stats` (pure, TDD)

**Files:**
- Create: `tradingagents/dataflows/range_stats.py`
- Test: `tests/test_range_stats.py`

**Goal:** A pure function that takes a symbol + trade_date and returns a structured dict of 4 windows × 3 metrics × 4 numbers. Pull historical OHLCV via the existing `route_to_vendor("get_stock_data", ...)` path. No formatting yet.

- [ ] **Step 1.1: Write the failing tests**

```python
# tests/test_range_stats.py
import pandas as pd
import pytest
from unittest.mock import patch

from tradingagents.dataflows.range_stats import (
    compute_range_stats,
    RangeStatsUnavailable,
)


def _fake_ohlcv(rows: int, last_date="2026-05-06") -> pd.DataFrame:
    """Build a deterministic OHLCV frame ending on `last_date`."""
    end = pd.Timestamp(last_date)
    dates = pd.bdate_range(end=end, periods=rows)
    return pd.DataFrame(
        {
            "Date": dates.strftime("%Y-%m-%d"),
            "Open": [100 + i for i in range(rows)],
            "High": [101 + i for i in range(rows)],
            "Low": [99 + i for i in range(rows)],
            "Close": [100.5 + i for i in range(rows)],
            "Volume": [1_000_000 + i * 1000 for i in range(rows)],
        }
    )


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_basic_shape_with_full_history(mock_load):
    mock_load.return_value = _fake_ohlcv(260)  # > 252 trading days
    stats = compute_range_stats("FAKE", "2026-05-06")
    assert stats["symbol"] == "FAKE"
    assert stats["trade_date"] == "2026-05-06"
    assert set(stats["metrics"].keys()) == {"open", "close", "volume"}
    for metric in ("open", "close", "volume"):
        windows = stats["metrics"][metric]
        assert set(windows.keys()) == {"52w", "6m", "3m", "1m"}
        for w in ("52w", "6m", "3m", "1m"):
            row = windows[w]
            assert set(row.keys()) == {
                "low", "high", "pct_above_low", "pct_below_high", "position_pct"
            }


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_close_percentages_against_known_window(mock_load):
    """1m window = last 21 trading days. Build a frame where close at index -1 is 110
    and the prior 20 closes range exactly 100..120."""
    df = pd.DataFrame(
        {
            "Date": pd.bdate_range(end="2026-05-06", periods=21).strftime("%Y-%m-%d"),
            "Open": [100.0] * 21,
            "High": [120.0] * 21,
            "Low": [100.0] * 21,
            "Close": list(range(100, 121)),  # 100..120, close today=120
            "Volume": [1] * 21,
        }
    )
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-06")
    m1 = stats["metrics"]["close"]["1m"]
    # close today=120, 1m low=100, 1m high=120
    assert m1["low"] == pytest.approx(100.0)
    assert m1["high"] == pytest.approx(120.0)
    assert m1["pct_above_low"] == pytest.approx(20.0)
    assert m1["pct_below_high"] == pytest.approx(0.0)
    assert m1["position_pct"] == pytest.approx(100.0)


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_partial_history_marks_only_unavailable_windows(mock_load):
    """100 trading days → 1m and 3m valid, 6m and 52w n/a."""
    mock_load.return_value = _fake_ohlcv(100)
    stats = compute_range_stats("FAKE", "2026-05-06")
    for metric in ("open", "close", "volume"):
        assert stats["metrics"][metric]["1m"]["low"] is not None
        assert stats["metrics"][metric]["3m"]["low"] is not None
        assert stats["metrics"][metric]["6m"]["low"] is None
        assert stats["metrics"][metric]["52w"]["low"] is None


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_high_equals_low_position_falls_back_to_50(mock_load):
    df = pd.DataFrame(
        {
            "Date": pd.bdate_range(end="2026-05-06", periods=21).strftime("%Y-%m-%d"),
            "Open": [100.0] * 21,
            "High": [100.0] * 21,
            "Low": [100.0] * 21,
            "Close": [100.0] * 21,
            "Volume": [0] * 21,
        }
    )
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-06")
    m1 = stats["metrics"]["close"]["1m"]
    assert m1["position_pct"] == pytest.approx(50.0)
    # volume=0 across the window → pct_above_low must be n/a (None)
    v1 = stats["metrics"]["volume"]["1m"]
    assert v1["pct_above_low"] is None


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_trade_date_on_weekend_uses_last_trading_row(mock_load):
    df = _fake_ohlcv(30, last_date="2026-05-01")  # Friday
    mock_load.return_value = df
    stats = compute_range_stats("FAKE", "2026-05-03")  # Sunday
    # Should use 2026-05-01's close, not raise
    assert stats["today"]["close"] is not None
    assert stats["today"]["effective_date"] == "2026-05-01"


@patch("tradingagents.dataflows.range_stats._load_ohlcv")
def test_no_data_at_all_raises(mock_load):
    mock_load.return_value = pd.DataFrame()
    with pytest.raises(RangeStatsUnavailable):
        compute_range_stats("NOPE", "2026-05-06")
```

- [ ] **Step 1.2: Run tests, verify they all fail**

Run: `pytest tests/test_range_stats.py -v`
Expected: 6 FAILED with `ModuleNotFoundError: tradingagents.dataflows.range_stats`

- [ ] **Step 1.3: Write the implementation**

```python
# tradingagents/dataflows/range_stats.py
"""Range-stats compute: today's open/close/volume vs 52w/6m/3m/1m high-low ranges.

Pure-ish module. The only side effect is the historical-data fetch which goes
through the configured vendor (`route_to_vendor("get_stock_data", ...)`).
Three formatters live alongside (markdown for LLMs/Telegram; dict for WebUI).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

import pandas as pd

from tradingagents.dataflows.interface import route_to_vendor


WINDOWS_TRADING_DAYS = {"52w": 252, "6m": 126, "3m": 63, "1m": 21}


class RangeStatsUnavailable(Exception):
    """Raised when no historical data is available for the symbol."""


def _load_ohlcv(symbol: str, trade_date: str) -> pd.DataFrame:
    """Fetch ~380 calendar days of OHLCV ending at trade_date.

    Returns a DataFrame with columns Date (YYYY-MM-DD str), Open, High, Low,
    Close, Volume. Empty DataFrame on failure.
    """
    end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=380)
    csv_text = route_to_vendor(
        "get_stock_data",
        symbol,
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
    )
    # Vendor outputs include header comment lines starting with '#'.
    if not isinstance(csv_text, str) or "No data" in csv_text:
        return pd.DataFrame()
    try:
        df = pd.read_csv(StringIO(csv_text), comment="#")
    except Exception:
        return pd.DataFrame()
    if df.empty or "Date" not in df.columns:
        # yfinance vendor uses index "Date"; AlphaVantage may differ. Normalize.
        if df.index.name and df.index.name.lower().startswith("date"):
            df = df.reset_index()
        else:
            return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def _window_low_high(df: pd.DataFrame, n: int, col: str) -> tuple[Optional[float], Optional[float]]:
    """Return (low, high) over the last n trading days inclusive of today.

    Returns (None, None) if fewer than n rows available.
    """
    if len(df) < n:
        return None, None
    sl = df.tail(n)
    return float(sl[col].min()), float(sl[col].max())


def _calc_metrics(current: float, low: Optional[float], high: Optional[float]) -> dict:
    if low is None or high is None:
        return {"low": None, "high": None,
                "pct_above_low": None, "pct_below_high": None, "position_pct": None}
    if low == 0:
        pct_above_low = None
    else:
        pct_above_low = (current - low) / low * 100.0
    if high == 0:
        pct_below_high = None
    else:
        pct_below_high = (current - high) / high * 100.0
    if high == low:
        position_pct = 50.0
    else:
        position_pct = (current - low) / (high - low) * 100.0
    return {
        "low": low,
        "high": high,
        "pct_above_low": pct_above_low,
        "pct_below_high": pct_below_high,
        "position_pct": position_pct,
    }


def compute_range_stats(symbol: str, trade_date: str) -> dict:
    """Compute range stats for one (symbol, trade_date).

    Returns a dict of shape:
        {
            "symbol": str,
            "trade_date": str,
            "today": {"effective_date": str, "open": float, "close": float, "volume": int},
            "metrics": {
                "open":   {"52w": {...}, "6m": {...}, "3m": {...}, "1m": {...}},
                "close":  {...},
                "volume": {...},
            },
        }
    where each window dict has keys: low, high, pct_above_low, pct_below_high, position_pct.
    None values mean "n/a" (insufficient history or degenerate divisor).

    Raises RangeStatsUnavailable when no data could be fetched at all.
    """
    df = _load_ohlcv(symbol, trade_date)
    if df.empty:
        raise RangeStatsUnavailable(f"No OHLCV data for {symbol} up to {trade_date}")

    # If trade_date is a non-trading day, use the most recent row.
    today_rows = df[df["Date"] <= trade_date]
    if today_rows.empty:
        raise RangeStatsUnavailable(f"No rows on or before {trade_date} for {symbol}")
    today_row = today_rows.iloc[-1]
    effective_date = today_row["Date"]

    today = {
        "effective_date": effective_date,
        "open": float(today_row["Open"]),
        "close": float(today_row["Close"]),
        "volume": int(today_row["Volume"]),
    }

    # Trim to rows up through effective_date (drop rows after, defensive)
    df_eff = df[df["Date"] <= effective_date].reset_index(drop=True)

    metrics: dict = {"open": {}, "close": {}, "volume": {}}
    for label, n in WINDOWS_TRADING_DAYS.items():
        for metric_name, col in (("open", "Open"), ("close", "Close"), ("volume", "Volume")):
            low, high = _window_low_high(df_eff, n, col)
            metrics[metric_name][label] = _calc_metrics(today[metric_name], low, high)

    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "today": today,
        "metrics": metrics,
    }
```

- [ ] **Step 1.4: Run tests, verify they pass**

Run: `pytest tests/test_range_stats.py -v`
Expected: 6 PASSED

- [ ] **Step 1.5: Commit**

```bash
git add tradingagents/dataflows/range_stats.py tests/test_range_stats.py
git commit -m "feat(range-stats): pure compute for open/close/volume vs 52w/6m/3m/1m ranges"
```

---

### Task 2: Range-stats formatters (markdown / WebUI / Telegram)

**Files:**
- Modify: `tradingagents/dataflows/range_stats.py`
- Modify: `tests/test_range_stats.py`

**Goal:** Three render functions on top of the same dict so the LLM tool, WebUI card, and Telegram message all use one source of truth.

- [ ] **Step 2.1: Add the failing formatter tests**

Append to `tests/test_range_stats.py`:

```python
from tradingagents.dataflows.range_stats import (
    format_range_stats_markdown,
    format_range_stats_for_webui,
    format_range_stats_telegram,
)


def _sample_stats():
    return {
        "symbol": "AAPL",
        "trade_date": "2026-05-06",
        "today": {
            "effective_date": "2026-05-06",
            "open": 189.23,
            "close": 192.15,
            "volume": 58_231_400,
        },
        "metrics": {
            "close": {
                "52w": {"low": 164.20, "high": 215.40,
                        "pct_above_low": 17.0, "pct_below_high": -10.8, "position_pct": 54.5},
                "6m":  {"low": 170.10, "high": 215.40,
                        "pct_above_low": 12.9, "pct_below_high": -10.8, "position_pct": 48.6},
                "3m":  {"low": 178.50, "high": 210.00,
                        "pct_above_low": 7.6,  "pct_below_high": -8.5,  "position_pct": 43.3},
                "1m":  {"low": 184.00, "high": 198.20,
                        "pct_above_low": 4.4,  "pct_below_high": -3.0,  "position_pct": 57.4},
            },
            "open": {
                "52w": {"low": None, "high": None,
                        "pct_above_low": None, "pct_below_high": None, "position_pct": None},
                "6m":  {"low": 170.10, "high": 215.40,
                        "pct_above_low": 11.2, "pct_below_high": -12.1, "position_pct": 42.0},
                "3m":  {"low": 178.50, "high": 210.00,
                        "pct_above_low": 6.0, "pct_below_high": -9.9, "position_pct": 34.0},
                "1m":  {"low": 184.00, "high": 198.20,
                        "pct_above_low": 2.8, "pct_below_high": -4.5, "position_pct": 36.8},
            },
            "volume": {
                "52w": {"low": 26_000_000, "high": 105_000_000,
                        "pct_above_low": 124.0, "pct_below_high": -44.5, "position_pct": 40.8},
                "6m":  {"low": 28_000_000, "high": 90_000_000,
                        "pct_above_low": 108.0, "pct_below_high": -35.3, "position_pct": 48.8},
                "3m":  {"low": 30_000_000, "high": 80_000_000,
                        "pct_above_low": 94.1, "pct_below_high": -27.2, "position_pct": 56.5},
                "1m":  {"low": 35_000_000, "high": 70_000_000,
                        "pct_above_low": 66.4, "pct_below_high": -16.8, "position_pct": 66.4},
            },
        },
    }


def test_markdown_contains_three_section_headers_and_today_line():
    md = format_range_stats_markdown(_sample_stats())
    assert "Range Stats for AAPL on 2026-05-06" in md
    assert "Today: open=189.23" in md
    assert "## Close (192.15)" in md
    assert "## Open (189.23)" in md
    assert "## Volume (58,231,400)" in md
    assert "| 52w" in md
    assert "n/a" in md  # the open 52w window has None values


def test_markdown_renders_signed_percentages_with_one_decimal():
    md = format_range_stats_markdown(_sample_stats())
    assert "+17.0%" in md
    assert "-10.8%" in md
    assert "54.5%" in md


def test_webui_dict_includes_color_hints_for_extremes():
    payload = format_range_stats_for_webui(_sample_stats())
    # close 1m position_pct = 57.4 → not extreme → no color
    close_1m = payload["metrics"]["close"]["1m"]
    assert close_1m["color"] is None
    # volume 1m position_pct = 66.4 → still no color hint (threshold is >80)
    # construct an extreme entry to verify
    extreme = {
        "low": 10, "high": 20, "pct_above_low": 100.0,
        "pct_below_high": -2.0, "position_pct": 95.0,
    }
    from tradingagents.dataflows.range_stats import _color_for_window
    assert _color_for_window(extreme) == "red"
    extreme_low = {
        "low": 10, "high": 20, "pct_above_low": 1.0,
        "pct_below_high": -50.0, "position_pct": 5.0,
    }
    assert _color_for_window(extreme_low) == "green"


def test_telegram_format_is_compact_three_lines():
    msg = format_range_stats_telegram(_sample_stats())
    # Header + 3 metric lines
    lines = [ln for ln in msg.splitlines() if ln.strip()]
    assert len(lines) == 4
    assert "AAPL" in lines[0] and "2026-05-06" in lines[0]
    assert lines[1].startswith("Close")
    assert lines[2].startswith("Open")
    assert lines[3].startswith("Vol")
    # Volume row uses readable 58.2M, not raw integer
    assert "58.2M" in lines[3]
```

- [ ] **Step 2.2: Run formatter tests, verify failure**

Run: `pytest tests/test_range_stats.py -v -k "markdown or webui or telegram"`
Expected: 4 FAILED with ImportError on the missing functions.

- [ ] **Step 2.3: Implement the formatters**

Append to `tradingagents/dataflows/range_stats.py`:

```python
def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.1f}%"


def _fmt_pos(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1f}%"


def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f}"


def _fmt_vol_short(v: int | float) -> str:
    """Render a volume as 1.2K / 58.2M / 1.4B."""
    v = float(v)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.1f}K"
    return f"{v:.0f}"


def _color_for_window(window: dict) -> Optional[str]:
    """Return 'red' near recent high, 'green' near recent low, else None."""
    pos = window.get("position_pct")
    if pos is None:
        return None
    if pos >= 80.0:
        return "red"
    if pos <= 20.0:
        return "green"
    return None


def _table_for_metric(label: str, current: float, windows: dict, *, is_volume: bool = False) -> str:
    fmt = _fmt_vol_short if is_volume else _fmt_price
    cur_str = f"{int(current):,}" if is_volume else f"{current:.2f}"
    lines = [
        f"## {label.title()} ({cur_str}) vs historical ranges",
        "| Window | Low    | High   | vs Low   | vs High  | Position |",
        "|--------|--------|--------|----------|----------|----------|",
    ]
    for w in ("52w", "6m", "3m", "1m"):
        d = windows[w]
        lines.append(
            "| {w:<6} | {lo} | {hi} | {al} | {bh} | {pos} |".format(
                w=w,
                lo=fmt(d["low"]) if d["low"] is not None else "n/a   ",
                hi=fmt(d["high"]) if d["high"] is not None else "n/a   ",
                al=_fmt_pct(d["pct_above_low"]),
                bh=_fmt_pct(d["pct_below_high"]),
                pos=_fmt_pos(d["position_pct"]),
            )
        )
    return "\n".join(lines)


def format_range_stats_markdown(stats: dict) -> str:
    """LLM-facing + Telegram-fallback markdown render."""
    today = stats["today"]
    parts = [
        f"# Range Stats for {stats['symbol']} on {stats['trade_date']}",
        f"Today: open={today['open']:.2f}  close={today['close']:.2f}  "
        f"volume={today['volume']:,}  (effective_date={today['effective_date']})",
        "",
        _table_for_metric("Close",  today["close"],  stats["metrics"]["close"]),
        "",
        _table_for_metric("Open",   today["open"],   stats["metrics"]["open"]),
        "",
        _table_for_metric("Volume", today["volume"], stats["metrics"]["volume"], is_volume=True),
    ]
    return "\n".join(parts)


def format_range_stats_for_webui(stats: dict) -> dict:
    """Returns a payload streamlit can render directly: numbers + color hints."""
    out = {
        "symbol": stats["symbol"],
        "trade_date": stats["trade_date"],
        "today": stats["today"],
        "metrics": {},
    }
    for metric, windows in stats["metrics"].items():
        out["metrics"][metric] = {
            w: {**d, "color": _color_for_window(d)} for w, d in windows.items()
        }
    return out


def format_range_stats_telegram(stats: dict) -> str:
    """Compact 4-line block: header + close, open, volume rows showing 52w and 1m."""
    sym = stats["symbol"]
    date = stats["trade_date"]
    today = stats["today"]

    def row(label: str, cur: str, windows: dict) -> str:
        w52 = windows["52w"]
        w1m = windows["1m"]
        return (
            f"{label:<5} {cur:<10} → "
            f"52w {_fmt_pct(w52['pct_above_low'])}/{_fmt_pct(w52['pct_below_high'])} "
            f"({_fmt_pos(w52['position_pct'])})  "
            f"1m {_fmt_pct(w1m['pct_above_low'])}/{_fmt_pct(w1m['pct_below_high'])} "
            f"({_fmt_pos(w1m['position_pct'])})"
        )

    return "\n".join([
        f"📊 Range Stats ({sym}, {date})",
        row("Close", f"{today['close']:.2f}", stats["metrics"]["close"]),
        row("Open",  f"{today['open']:.2f}",  stats["metrics"]["open"]),
        row("Vol",   _fmt_vol_short(today["volume"]), stats["metrics"]["volume"]),
    ])
```

- [ ] **Step 2.4: Run formatter tests, verify they pass**

Run: `pytest tests/test_range_stats.py -v`
Expected: all 10 PASSED

- [ ] **Step 2.5: Commit**

```bash
git add tradingagents/dataflows/range_stats.py tests/test_range_stats.py
git commit -m "feat(range-stats): markdown / webui / telegram formatters"
```

---

### Task 3: LangChain tool wrapper + market_analyst integration

**Files:**
- Create: `tradingagents/agents/utils/range_stats_tool.py`
- Modify: `tradingagents/agents/utils/agent_utils.py` (re-export)
- Modify: `tradingagents/agents/analysts/market_analyst.py:17-20` (add to tools), `market_analyst.py:23-49` (mention in prompt)
- Test: `tests/test_range_stats_tool.py`

- [ ] **Step 3.1: Write the failing tool tests**

```python
# tests/test_range_stats_tool.py
from unittest.mock import patch


def test_tool_returns_markdown_when_compute_succeeds():
    from tradingagents.agents.utils.range_stats_tool import get_range_stats

    fake_stats = {
        "symbol": "AAPL",
        "trade_date": "2026-05-06",
        "today": {"effective_date": "2026-05-06",
                  "open": 100.0, "close": 101.0, "volume": 1000000},
        "metrics": {
            m: {w: {"low": 90, "high": 110,
                    "pct_above_low": 12.2, "pct_below_high": -8.2, "position_pct": 55.0}
                for w in ("52w", "6m", "3m", "1m")}
            for m in ("open", "close", "volume")
        },
    }
    with patch("tradingagents.agents.utils.range_stats_tool.compute_range_stats",
               return_value=fake_stats):
        result = get_range_stats.invoke({"symbol": "AAPL", "trade_date": "2026-05-06"})
    assert "Range Stats for AAPL" in result
    assert "## Close" in result


def test_tool_returns_friendly_string_when_compute_unavailable():
    from tradingagents.agents.utils.range_stats_tool import get_range_stats
    from tradingagents.dataflows.range_stats import RangeStatsUnavailable

    with patch("tradingagents.agents.utils.range_stats_tool.compute_range_stats",
               side_effect=RangeStatsUnavailable("nope")):
        result = get_range_stats.invoke({"symbol": "ZZZ", "trade_date": "2026-05-06"})
    assert "unavailable" in result.lower()
    assert "ZZZ" in result
```

- [ ] **Step 3.2: Run, verify failure**

Run: `pytest tests/test_range_stats_tool.py -v`
Expected: 2 FAILED — module missing.

- [ ] **Step 3.3: Implement the tool**

```python
# tradingagents/agents/utils/range_stats_tool.py
"""LangChain @tool wrapper around compute_range_stats."""

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.range_stats import (
    RangeStatsUnavailable,
    compute_range_stats,
    format_range_stats_markdown,
)


@tool
def get_range_stats(
    symbol: Annotated[str, "ticker symbol of the company"],
    trade_date: Annotated[str, "current trading date in YYYY-MM-DD"],
) -> str:
    """Compute today's open / close / volume vs 52w / 6m / 3m / 1m high-low ranges
    (% above period low, % below period high, position-in-range %).

    Use this to anchor the price/volume context — e.g. assess whether the stock
    is at a 52-week high, near a one-month low, or where it sits in its recent
    range — before selecting indicators."""
    try:
        stats = compute_range_stats(symbol, trade_date)
    except RangeStatsUnavailable:
        return f"Range stats unavailable for {symbol} on {trade_date}."
    except Exception as e:  # noqa: BLE001 — defensive at boundary
        return f"Range stats error for {symbol}: {e}"
    return format_range_stats_markdown(stats)
```

- [ ] **Step 3.4: Run, verify pass**

Run: `pytest tests/test_range_stats_tool.py -v`
Expected: 2 PASSED.

- [ ] **Step 3.5: Re-export from `agent_utils.py`**

Edit `tradingagents/agents/utils/agent_utils.py`. Replace lines 1-20 (the imports block) with:

```python
from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
from tradingagents.agents.utils.range_stats_tool import (
    get_range_stats,
)
```

- [ ] **Step 3.6: Wire into `market_analyst.py`**

Edit `tradingagents/agents/analysts/market_analyst.py`.

Replace lines 2-7 (imports) with:

```python
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_range_stats,
    get_stock_data,
)
```

Replace lines 17-20 (`tools = [...]`) with:

```python
        tools = [
            get_stock_data,
            get_indicators,
            get_range_stats,
        ]
```

In the system_message string (line 23-50), insert the following sentence at the start of the second `+` block (line 48), immediately before the existing "Make sure to append a Markdown table…":

```python
            + """ Always call get_range_stats first to anchor today's open/close/volume against 52w/6m/3m/1m ranges before selecting indicators. The returned tables tell you whether the stock is at a 52-week high, near a one-month low, or somewhere mid-range — incorporate this in your trend narrative."""
```

(Concretely: split the existing `+ """ Make sure to append..."""` line so the new sentence comes between the big system_message and the table-appending instruction.)

- [ ] **Step 3.7: Run all range-stats tests**

Run: `pytest tests/test_range_stats.py tests/test_range_stats_tool.py -v`
Expected: all PASSED.

- [ ] **Step 3.8: Smoke-test the import chain**

Run: `python -c "from tradingagents.agents.analysts.market_analyst import create_market_analyst; print('ok')"`
Expected: `ok`.

- [ ] **Step 3.9: Commit**

```bash
git add tradingagents/agents/utils/range_stats_tool.py \
        tradingagents/agents/utils/agent_utils.py \
        tradingagents/agents/analysts/market_analyst.py \
        tests/test_range_stats_tool.py
git commit -m "feat(market-analyst): expose get_range_stats as a LangChain tool"
```

---

### Task 4: WebUI pre-analysis range-stats card

**Files:**
- Modify: `webui.py` (insert a new render block in the main area, after the existing page caption around line 460-470 area where `st.title(...)` and caption are rendered)
- Test: smoke import only (Streamlit UI rendering is verified manually + E2E)

**Goal:** Display a 3-column card under the page title showing close/open/volume range stats for the current ticker, BEFORE the user clicks "Start analysis", using cached data.

- [ ] **Step 4.1: Add a small render helper inline in `webui.py`**

Locate the section after the page title/caption (around the line `st.caption(T("page_caption").format(...))` near line 466). Insert immediately after it:

```python
# ════════════════════════════════════════════════════════════════════
# Range stats card (pre-analysis, cached)
# ════════════════════════════════════════════════════════════════════
def _render_range_stats_card(ticker: str, trade_date_str: str) -> None:
    """Render a 3-column close/open/volume range stats card.

    Uses st.cache_data so the same (ticker, date) tuple doesn't refetch.
    Failures degrade silently to a one-line note — never block the page.
    """
    try:
        from tradingagents.dataflows.range_stats import (
            RangeStatsUnavailable,
            compute_range_stats,
            format_range_stats_for_webui,
        )
    except Exception as e:
        st.caption(f"Range stats module unavailable: {e}")
        return

    @st.cache_data(show_spinner=False, ttl=15 * 60)
    def _cached(t: str, d: str):
        try:
            return format_range_stats_for_webui(compute_range_stats(t, d))
        except RangeStatsUnavailable:
            return None

    payload = _cached(ticker, trade_date_str)
    if payload is None:
        st.info(f"Range stats unavailable for {ticker} on {trade_date_str}.")
        return

    today = payload["today"]
    with st.expander(
        f"📊 Range Stats — {ticker} (today: open={today['open']:.2f} "
        f"close={today['close']:.2f} vol={today['volume']:,})",
        expanded=False,
    ):
        cols = st.columns(3)
        for col, (metric_label, metric_key, current_value, is_vol) in zip(
            cols,
            [
                ("Close", "close", today["close"], False),
                ("Open", "open", today["open"], False),
                ("Volume", "volume", today["volume"], True),
            ],
        ):
            with col:
                cur_str = f"{int(current_value):,}" if is_vol else f"{current_value:.2f}"
                col.markdown(f"**{metric_label}** — {cur_str}")
                rows = []
                for w in ("52w", "6m", "3m", "1m"):
                    d = payload["metrics"][metric_key][w]
                    if d["low"] is None:
                        rows.append({"window": w, "low": "n/a", "high": "n/a",
                                     "vs Low": "n/a", "vs High": "n/a", "Pos": "n/a"})
                        continue
                    rows.append({
                        "window": w,
                        "low": f"{d['low']:,.2f}" if not is_vol else f"{int(d['low']):,}",
                        "high": f"{d['high']:,.2f}" if not is_vol else f"{int(d['high']):,}",
                        "vs Low": f"{d['pct_above_low']:+.1f}%",
                        "vs High": f"{d['pct_below_high']:+.1f}%",
                        "Pos": f"{d['position_pct']:.0f}%",
                    })
                col.dataframe(rows, hide_index=True, use_container_width=True)


if ticker:
    _render_range_stats_card(ticker, str(trade_date))
```

- [ ] **Step 4.2: Smoke-test the import chain**

Run: `python -c "import ast; ast.parse(open('webui.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 4.3: Run the streamlit app once and verify the card appears**

Run: `streamlit run webui.py --server.headless=true --server.port=8501 &`
Then in another shell: `curl -s http://localhost:8501/healthz` — expect `ok`. Then open the URL manually with a real browser, sign in, type `NVDA` and confirm the "📊 Range Stats" expander shows three columns with numbers. Kill the server.

(Per memory `feedback_e2e_test_after_changes.md`, healthz alone is not enough — you must visually confirm the card.)

- [ ] **Step 4.4: Commit**

```bash
git add webui.py
git commit -m "feat(webui): pre-analysis range-stats card under page title"
```

---

### Task 5: Telegram daily report — range-stats section

**Files:**
- Modify: `scheduler.py` (the `_push_full_report` function around line 159+)
- Test: `tests/test_scheduler_range_stats.py`

**Goal:** Insert a single message block with `format_range_stats_telegram(...)` output after the per-ticker decision is rendered.

- [ ] **Step 5.1: Locate the existing render call**

Read `scheduler.py:159-240` (the `_push_full_report` body) to identify where the existing per-ticker messages are sent. The block iterates over a state and calls `notify.send_telegram(chat_id, msg)` multiple times.

- [ ] **Step 5.2: Write the failing test**

```python
# tests/test_scheduler_range_stats.py
from unittest.mock import patch, MagicMock


def test_full_report_includes_range_stats_block_when_available():
    import scheduler

    fake_stats = {
        "symbol": "AAPL", "trade_date": "2026-05-06",
        "today": {"effective_date": "2026-05-06",
                  "open": 100.0, "close": 101.0, "volume": 1_000_000},
        "metrics": {
            m: {w: {"low": 90.0, "high": 110.0,
                    "pct_above_low": 12.2, "pct_below_high": -8.2, "position_pct": 55.0}
                for w in ("52w", "6m", "3m", "1m")}
            for m in ("open", "close", "volume")
        },
    }
    sent = []

    def _capture(chat_id, msg, **_):
        sent.append(msg)
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler.compute_range_stats", return_value=fake_stats):
        scheduler._push_full_report(
            chat_id="123",
            ticker="AAPL",
            trade_date="2026-05-06",
            full_state={
                "final_trade_decision": "BUY",
                "market_report": "stub",
                "fundamentals_report": "stub",
                "sentiment_report": "stub",
                "news_report": "stub",
                "trader_investment_plan": "BUY",
                "investment_plan": "BUY",
            },
        )
    assert any("📊 Range Stats" in m for m in sent), \
        f"Expected a range-stats block in: {sent}"


def test_full_report_skips_range_stats_block_when_unavailable():
    import scheduler
    from tradingagents.dataflows.range_stats import RangeStatsUnavailable

    sent = []
    def _capture(chat_id, msg, **_):
        sent.append(msg)
        return True, "ok"

    with patch("scheduler.notify.send_telegram", side_effect=_capture), \
         patch("scheduler.compute_range_stats", side_effect=RangeStatsUnavailable("x")):
        scheduler._push_full_report(
            chat_id="123",
            ticker="AAPL",
            trade_date="2026-05-06",
            full_state={
                "final_trade_decision": "BUY",
                "market_report": "stub",
                "fundamentals_report": "stub",
                "sentiment_report": "stub",
                "news_report": "stub",
                "trader_investment_plan": "BUY",
                "investment_plan": "BUY",
            },
        )
    assert not any("📊 Range Stats" in m for m in sent), \
        f"Range-stats block should be omitted: {sent}"
```

- [ ] **Step 5.3: Run, verify failure**

Run: `pytest tests/test_scheduler_range_stats.py -v`
Expected: 2 FAILED — `_push_full_report` doesn't yet emit the block.

- [ ] **Step 5.4: Add range-stats integration to scheduler**

Edit `scheduler.py`. At the top of the file with the other imports (around line 23), add:

```python
from tradingagents.dataflows.range_stats import (
    RangeStatsUnavailable,
    compute_range_stats,
    format_range_stats_telegram,
)
```

Inside `_push_full_report`, after the decision message is sent and before the next analyst-report message, insert:

```python
    # Range stats — fail-soft, never abort the report.
    try:
        rs = compute_range_stats(ticker, trade_date)
        notify.send_telegram(chat_id, format_range_stats_telegram(rs))
    except RangeStatsUnavailable:
        pass
    except Exception as e:  # noqa: BLE001 — never let this kill a report
        _log(f"  range-stats failed for {ticker}: {e}")
```

Pick the insertion point as the line right after the function sends the headline/decision message (read the function body once and place it right after).

- [ ] **Step 5.5: Run, verify pass**

Run: `pytest tests/test_scheduler_range_stats.py -v`
Expected: 2 PASSED.

- [ ] **Step 5.6: Commit**

```bash
git add scheduler.py tests/test_scheduler_range_stats.py
git commit -m "feat(scheduler): include range-stats block in Telegram daily report"
```

---

### Task 6: End-to-end smoke for range stats

**Files:** none new; this is a manual + scripted verification.

- [ ] **Step 6.1: Run the analyst pipeline against a live ticker**

Run: `python worker.py --ticker NVDA --trade-date 2026-05-05` (use whatever invocation worker.py expects — read `worker.py:60-100` to find arg parsing). Confirm:
- The chunk stream completes without exceptions referencing `range_stats`.
- The final `market_report` contains the string `Range Stats for NVDA`.
- The market-analyst log shows `get_range_stats` being called.

- [ ] **Step 6.2: Run pytest for the whole new suite**

Run: `pytest tests/test_range_stats.py tests/test_range_stats_tool.py tests/test_scheduler_range_stats.py -v`
Expected: all PASSED.

- [ ] **Step 6.3: Render the Telegram block manually via dry-run**

Run: `python scheduler.py --dry-run` (per `scheduler.py:307` help text).
Expected: dry-run output includes the range-stats block formatted text in stdout.

- [ ] **Step 6.4: No commit needed (verification only).**

---

## Phase 2 — User Research Upload

### Task 7: PDF / text extraction module

**Files:**
- Create: `tradingagents/dataflows/user_research.py` (extraction half only)
- Test: `tests/test_user_research_extract.py`
- Modify: `requirements.txt`, `pyproject.toml`

- [ ] **Step 7.1: Add `pypdf` dependency**

Edit `requirements.txt` — append:

```
pypdf>=4.0,<6
```

Edit `pyproject.toml`. Find the `dependencies = [` block (search for it). Append within the list:

```python
    "pypdf>=4.0,<6",
```

Run: `pip install -r requirements.txt`
Expected: `pypdf` installs cleanly.

- [ ] **Step 7.2: Write the failing tests**

```python
# tests/test_user_research_extract.py
import io

import pytest


def _build_simple_pdf_bytes() -> bytes:
    """Build a tiny one-page PDF in memory using pypdf, no external assets."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # Inject a minimal text stream — pypdf doesn't directly support 'add text'
    # but we can wrap with pypdf2 or skip text and assert empty extraction.
    # For determinism we use fpdf2 if available; if not, fall back to text fixture.
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_text_from_markdown():
    from tradingagents.dataflows.user_research import _extract_text
    raw = "# Hello\n\nThis is *markdown*.".encode("utf-8")
    assert _extract_text(raw, "note.md").strip() == "# Hello\n\nThis is *markdown*.".strip()


def test_extract_text_from_txt():
    from tradingagents.dataflows.user_research import _extract_text
    raw = b"plain text content"
    assert _extract_text(raw, "note.txt").strip() == "plain text content"


def test_extract_text_from_pdf_with_text(tmp_path):
    """Build a real PDF with a known text payload using reportlab if installed,
    else use a precomposed fixture in tests/fixtures/sample.pdf."""
    pytest.importorskip("reportlab", reason="reportlab needed to synthesize a PDF in-test")
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "TradingAgents test report content marker xyzzy123")
    c.save()
    pdf_bytes = buf.getvalue()

    from tradingagents.dataflows.user_research import _extract_text
    text = _extract_text(pdf_bytes, "report.pdf")
    assert "xyzzy123" in text


def test_extract_text_unsupported_extension():
    from tradingagents.dataflows.user_research import (
        _extract_text,
        ResearchExtractionError,
    )
    with pytest.raises(ResearchExtractionError):
        _extract_text(b"bytes", "weird.docx")


def test_extract_text_corrupt_pdf_raises():
    from tradingagents.dataflows.user_research import (
        _extract_text,
        ResearchExtractionError,
    )
    with pytest.raises(ResearchExtractionError):
        _extract_text(b"not a real pdf", "broken.pdf")
```

- [ ] **Step 7.3: Run, verify failure**

Run: `pytest tests/test_user_research_extract.py -v`
Expected: FAILED — module missing.

- [ ] **Step 7.4: Implement the extractor**

```python
# tradingagents/dataflows/user_research.py
"""User-uploaded research notes: extract → summarize → persist → list/delete.

Per-user storage lives under <user_home>/research/<TICKER>/ for the long-lived
library, and <user_home>/research/_shared_for_run/<run_id>/ for one-shot uploads.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


SUPPORTED_TEXT_EXT = {".txt", ".md", ".markdown"}
SUPPORTED_PDF_EXT = {".pdf"}
MAX_SUMMARY_INPUT_CHARS = 100_000


class ResearchExtractionError(Exception):
    """Raised when a file cannot be parsed."""


def _sniff_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return ext


def _extract_text(file_bytes: bytes, filename: str) -> str:
    ext = _sniff_ext(filename)
    if ext in SUPPORTED_TEXT_EXT:
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            raise ResearchExtractionError(f"text decode failed: {e}") from e
    if ext in SUPPORTED_PDF_EXT:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            chunks = []
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
            text = "\n".join(chunks).strip()
            if not text:
                raise ResearchExtractionError("PDF contained no extractable text")
            return text
        except ResearchExtractionError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ResearchExtractionError(f"PDF parse failed: {e}") from e
    raise ResearchExtractionError(f"Unsupported file type: {ext}")
```

- [ ] **Step 7.5: Run, verify pass**

Run: `pytest tests/test_user_research_extract.py -v`
Expected: 5 PASSED (or 4 PASSED + 1 SKIPPED if reportlab not installed).

- [ ] **Step 7.6: Commit**

```bash
git add tradingagents/dataflows/user_research.py tests/test_user_research_extract.py \
        requirements.txt pyproject.toml
git commit -m "feat(research): PDF/markdown/text extraction for uploaded research notes"
```

---

### Task 8: Storage layer — paths, dedupe, list, delete

**Files:**
- Modify: `tradingagents/dataflows/user_research.py`
- Test: `tests/test_user_research_storage.py`

- [ ] **Step 8.1: Write the failing tests**

```python
# tests/test_user_research_storage.py
from pathlib import Path

import pytest


def test_save_and_list_per_ticker(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        _save,
        list_research,
    )
    user_root = tmp_path / "user42"
    saved = _save(
        file_bytes=b"# my note",
        summary_md="**summary**",
        ticker="AAPL",
        user_root=user_root,
        original_filename="goldman.md",
        run_id=None,
    )
    assert saved["path"].endswith(".md")
    assert (user_root / "research" / "AAPL").exists()
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1
    assert listed[0]["filename"] == "goldman.md"
    assert listed[0]["summary"] == "**summary**"


def test_dedupes_by_content_hash(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save, list_research
    user_root = tmp_path / "user42"
    _save(b"identical bytes", "s1", "AAPL", user_root, "a.md", None)
    _save(b"identical bytes", "s2", "AAPL", user_root, "b.md", None)
    listed = list_research(user_root, "AAPL")
    assert len(listed) == 1, "second upload with same content should de-duplicate"


def test_delete_research(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        _save, list_research, delete_research,
    )
    user_root = tmp_path / "user42"
    saved = _save(b"hello", "summary", "AAPL", user_root, "n.md", None)
    delete_research(user_root, "AAPL", saved["hash"])
    assert list_research(user_root, "AAPL") == []


def test_per_run_storage_lives_under_shared(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save
    user_root = tmp_path / "user42"
    saved = _save(b"once", "s", None, user_root, "tmp.txt", run_id="run-1")
    assert "_shared_for_run" in saved["path"]
    assert "run-1" in saved["path"]


def test_clear_run_dir(tmp_path: Path):
    from tradingagents.dataflows.user_research import _save, clear_run_dir
    user_root = tmp_path / "user42"
    _save(b"x", "s", None, user_root, "t.txt", run_id="run-1")
    clear_run_dir(user_root, "run-1")
    assert not (user_root / "research" / "_shared_for_run" / "run-1").exists()


def test_list_research_unknown_ticker_returns_empty(tmp_path: Path):
    from tradingagents.dataflows.user_research import list_research
    assert list_research(tmp_path / "user42", "ZZZ") == []
```

- [ ] **Step 8.2: Run, verify failure**

Run: `pytest tests/test_user_research_storage.py -v`
Expected: FAILED.

- [ ] **Step 8.3: Implement storage**

Append to `tradingagents/dataflows/user_research.py`:

```python
def _safe_filename(name: str) -> str:
    """Strip path separators and control chars."""
    name = os.path.basename(name)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:200] or "file"


def _research_root(user_root: Path) -> Path:
    p = user_root / "research"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save(
    file_bytes: bytes,
    summary_md: str,
    ticker: Optional[str],
    user_root: Path,
    original_filename: str,
    run_id: Optional[str],
) -> dict:
    """Persist original + summary + meta. Returns metadata dict."""
    safe_orig = _safe_filename(original_filename)
    ext = _sniff_ext(safe_orig) or ".bin"
    digest = hashlib.sha256(file_bytes).hexdigest()[:12]

    if ticker:
        target_dir = _research_root(user_root) / ticker.upper()
    else:
        if not run_id:
            raise ValueError("run_id is required when ticker is None")
        target_dir = _research_root(user_root) / "_shared_for_run" / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    original_path = target_dir / f"{digest}{ext}"
    summary_path = target_dir / f"{digest}.summary.md"
    meta_path = target_dir / f"{digest}.meta.json"

    if not original_path.exists():
        original_path.write_bytes(file_bytes)
    if not summary_path.exists():
        summary_path.write_text(summary_md, encoding="utf-8")
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps({
                "filename": original_filename,
                "uploaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "size": len(file_bytes),
                "hash": digest,
                "ticker": ticker.upper() if ticker else None,
                "run_id": run_id,
            }, indent=2),
            encoding="utf-8",
        )

    return {
        "path": str(original_path),
        "summary_path": str(summary_path),
        "meta_path": str(meta_path),
        "hash": digest,
        "filename": original_filename,
        "summary": summary_md,
    }


def list_research(user_root: Path, ticker: str) -> list[dict]:
    """List per-ticker library entries. Returns [] if none."""
    d = _research_root(user_root) / ticker.upper()
    if not d.exists():
        return []
    out: list[dict] = []
    for meta_path in sorted(d.glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        digest = meta["hash"]
        summary_path = d / f"{digest}.summary.md"
        if not summary_path.exists():
            continue
        meta["summary"] = summary_path.read_text(encoding="utf-8")
        out.append(meta)
    return out


def delete_research(user_root: Path, ticker: str, digest: str) -> None:
    """Delete the original + summary + meta for a single library entry."""
    d = _research_root(user_root) / ticker.upper()
    if not d.exists():
        return
    for f in d.glob(f"{digest}*"):
        try:
            f.unlink()
        except OSError:
            pass


def clear_run_dir(user_root: Path, run_id: str) -> None:
    """Remove a per-run directory entirely."""
    import shutil
    d = _research_root(user_root) / "_shared_for_run" / run_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 8.4: Run, verify pass**

Run: `pytest tests/test_user_research_storage.py -v`
Expected: 6 PASSED.

- [ ] **Step 8.5: Commit**

```bash
git add tradingagents/dataflows/user_research.py tests/test_user_research_storage.py
git commit -m "feat(research): per-user storage with SHA dedupe + list/delete"
```

---

### Task 9: Summarization + ingest pipeline

**Files:**
- Modify: `tradingagents/dataflows/user_research.py`
- Test: `tests/test_user_research_ingest.py`

- [ ] **Step 9.1: Write the failing tests**

```python
# tests/test_user_research_ingest.py
from pathlib import Path
from unittest.mock import MagicMock


def _fake_llm():
    """Minimal langchain-style LLM with .invoke() returning a fixed string."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="**Bottom line**\n- it goes up")
    return llm


def test_ingest_research_happy_path(tmp_path: Path):
    from tradingagents.dataflows.user_research import ingest_research
    out = ingest_research(
        file_bytes=b"# AAPL beats earnings\n\nGreat quarter.",
        filename="aapl_q4.md",
        ticker="AAPL",
        user_root=tmp_path / "user42",
        summarize_fn=_fake_llm(),
        run_id=None,
    )
    assert out["filename"] == "aapl_q4.md"
    assert "Bottom line" in out["summary"]
    assert Path(out["path"]).exists()


def test_ingest_research_truncates_large_input_before_llm(tmp_path: Path):
    from tradingagents.dataflows.user_research import (
        ingest_research,
        MAX_SUMMARY_INPUT_CHARS,
    )
    big_text = "x" * (MAX_SUMMARY_INPUT_CHARS * 2)
    llm = _fake_llm()
    ingest_research(
        file_bytes=big_text.encode(),
        filename="huge.md",
        ticker="AAPL",
        user_root=tmp_path / "u",
        summarize_fn=llm,
        run_id=None,
    )
    # llm.invoke called with a prompt — verify it carries truncated content
    invoked_prompt = llm.invoke.call_args.args[0]
    assert len(invoked_prompt) < MAX_SUMMARY_INPUT_CHARS + 5_000


def test_ingest_research_falls_back_when_summary_fails(tmp_path: Path):
    from tradingagents.dataflows.user_research import ingest_research
    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("LLM down")
    out = ingest_research(
        file_bytes=b"# important note about TSLA",
        filename="tsla.md",
        ticker="TSLA",
        user_root=tmp_path / "u",
        summarize_fn=llm,
        run_id=None,
    )
    assert "summary failed" in out["summary"].lower()
    assert "important note about TSLA" in out["summary"]
```

- [ ] **Step 9.2: Run, verify failure**

Run: `pytest tests/test_user_research_ingest.py -v`
Expected: FAILED.

- [ ] **Step 9.3: Implement summarize + ingest**

Append to `tradingagents/dataflows/user_research.py`:

```python
SUMMARY_PROMPT_TMPL = """You are summarizing a research report{ticker_clause}.
Produce a markdown summary with these sections:
- **Bottom line** (1-2 sentences)
- **Key thesis** (3-5 bullets)
- **Price targets / numbers** (if any)
- **Key risks** (3-5 bullets)
- **Notable quotes** (1-3, with page if known)

Keep total output under 1500 words.

Source:
{text}
"""


def _summarize(text: str, ticker: Optional[str], summarize_fn) -> str:
    """Call the LLM to compress the report. summarize_fn is a langchain BaseLLM
    or similar with an .invoke(prompt) -> message-with-.content interface."""
    ticker_clause = f" for ticker {ticker}" if ticker else ""
    prompt = SUMMARY_PROMPT_TMPL.format(ticker_clause=ticker_clause, text=text)
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            response = summarize_fn.invoke(prompt)
            content = getattr(response, "content", None) or str(response)
            content = content.strip()
            if content:
                return content
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.5)
    excerpt = text[:2000].strip()
    return (
        f"_(summary failed after retry: {type(last_err).__name__ if last_err else 'empty'} — "
        f"raw text excerpt below)_\n\n{excerpt}"
    )


def ingest_research(
    file_bytes: bytes,
    filename: str,
    ticker: Optional[str],
    user_root: Path,
    summarize_fn: Callable,
    run_id: Optional[str] = None,
) -> dict:
    """Extract → summarize → persist. Returns metadata dict including summary."""
    text = _extract_text(file_bytes, filename)
    text = text[:MAX_SUMMARY_INPUT_CHARS]
    summary_md = _summarize(text, ticker, summarize_fn)
    return _save(
        file_bytes=file_bytes,
        summary_md=summary_md,
        ticker=ticker,
        user_root=user_root,
        original_filename=filename,
        run_id=run_id,
    )
```

- [ ] **Step 9.4: Run, verify pass**

Run: `pytest tests/test_user_research_ingest.py -v`
Expected: 3 PASSED.

- [ ] **Step 9.5: Commit**

```bash
git add tradingagents/dataflows/user_research.py tests/test_user_research_ingest.py
git commit -m "feat(research): LLM-summarize ingest pipeline with retry + fallback"
```

---

### Task 10: AgentState field + propagation init + worker.py wiring

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py:46-73` (add field)
- Modify: `tradingagents/graph/propagation.py:18-55` (init field, accept kwarg)
- Modify: `tradingagents/graph/trading_graph.py:265,303-310` (propagate accepts user_research kwarg)
- Modify: `worker.py:106-118` (pass user_research from request)
- Test: `tests/test_state_user_research.py`

- [ ] **Step 10.1: Write the failing test**

```python
# tests/test_state_user_research.py
def test_create_initial_state_includes_user_research_default_empty():
    from tradingagents.graph.propagation import Propagator
    p = Propagator()
    s = p.create_initial_state("AAPL", "2026-05-06")
    assert s["user_research_report"] == ""


def test_create_initial_state_passes_through_user_research():
    from tradingagents.graph.propagation import Propagator
    p = Propagator()
    s = p.create_initial_state(
        "AAPL", "2026-05-06",
        user_research="## Goldman note\nThesis: ..."
    )
    assert "Goldman" in s["user_research_report"]
```

- [ ] **Step 10.2: Run, verify failure**

Run: `pytest tests/test_state_user_research.py -v`
Expected: FAILED — kwarg not accepted / key missing.

- [ ] **Step 10.3: Add the field to AgentState**

Edit `tradingagents/agents/utils/agent_states.py`. After line 73 (the `past_context` line) add:

```python
    user_research_report: Annotated[str, "User-uploaded research notes summary, joined across files"]
```

- [ ] **Step 10.4: Update Propagator**

Edit `tradingagents/graph/propagation.py`. Replace lines 18-55 (`create_initial_state` body and signature) with:

```python
    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        past_context: str = "",
        user_research: str = "",
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "user_research_report": user_research,
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "fundamentals_report": "",
            "sentiment_report": "",
            "news_report": "",
        }
```

- [ ] **Step 10.5: Update `propagate()` in `trading_graph.py`**

Edit `tradingagents/graph/trading_graph.py`. Change the `propagate` signature on line 265 from:

```python
    def propagate(self, company_name, trade_date):
```

to:

```python
    def propagate(self, company_name, trade_date, user_research: str = ""):
```

In the same function find the line that calls `self._run_graph(company_name, trade_date)` and change it to `self._run_graph(company_name, trade_date, user_research=user_research)`.

In `_run_graph` (defined right after), change its signature to accept `user_research: str = ""` and update the `create_initial_state` call to pass `user_research=user_research`. The `create_initial_state` call currently looks like:

```python
init_agent_state = self.propagator.create_initial_state(
    company_name, trade_date, past_context=past_context
)
```

Change to:

```python
init_agent_state = self.propagator.create_initial_state(
    company_name, trade_date,
    past_context=past_context,
    user_research=user_research,
)
```

- [ ] **Step 10.6: Update `worker.py`**

Edit `worker.py`. The request schema is read on line 95-101 (`req["ticker"]` etc.). After line 100 (`selected_analysts = req["selected_analysts"]`), add:

```python
        user_research = req.get("user_research", "") or ""
```

In the section around line 116 where `init_state = ta.propagator.create_initial_state(...)` is called, change to pass the new kwarg:

```python
        init_state = ta.propagator.create_initial_state(
            ticker, str(trade_date),
            past_context=past_context,
            user_research=user_research,
        )
```

- [ ] **Step 10.7: Run, verify pass**

Run: `pytest tests/test_state_user_research.py -v`
Expected: 2 PASSED.

- [ ] **Step 10.8: Smoke-test the full import chain**

Run:
```bash
python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('ok')"
python -c "import worker; print('ok')"
```
Expected: both `ok`.

- [ ] **Step 10.9: Commit**

```bash
git add tradingagents/agents/utils/agent_states.py \
        tradingagents/graph/propagation.py \
        tradingagents/graph/trading_graph.py \
        worker.py \
        tests/test_state_user_research.py
git commit -m "feat(state): add user_research_report field threaded through propagate() and worker"
```

---

### Task 11: Wire `user_research_report` into 4 downstream prompts

**Files:**
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/trader/trader.py`
- Test: `tests/test_prompts_include_research.py`

**Goal:** Each of the four downstream agents receives the `user_research_report` field and includes it (when non-empty) in its prompt as a clearly-framed user-supplied prior.

- [ ] **Step 11.1: Write the failing test**

```python
# tests/test_prompts_include_research.py
"""Verify each of bull/bear/research_manager/trader propagates user_research_report
into the prompt that gets sent to the LLM."""

from unittest.mock import MagicMock


def _fake_state(**overrides):
    base = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-06",
        "market_report": "M",
        "sentiment_report": "S",
        "news_report": "N",
        "fundamentals_report": "F",
        "user_research_report": "## Goldman bullish\nUNIQUE_MARKER_42",
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
            "judge_decision": "",
        },
        "investment_plan": "BUY",
    }
    base.update(overrides)
    return base


def _capturing_llm():
    """Returns (llm, captured_prompts: list[str])."""
    llm = MagicMock()
    captured = []
    def _inv(prompt):
        if isinstance(prompt, list):
            content = "\n".join(m.get("content", "") for m in prompt if isinstance(m, dict))
        else:
            content = str(prompt)
        captured.append(content)
        return MagicMock(content="ok")
    llm.invoke.side_effect = _inv
    llm.with_structured_output = MagicMock(return_value=llm)
    return llm, captured


def test_bull_researcher_includes_user_research():
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    llm, captured = _capturing_llm()
    node = create_bull_researcher(llm)
    node(_fake_state())
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_bear_researcher_includes_user_research():
    from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
    llm, captured = _capturing_llm()
    node = create_bear_researcher(llm)
    node(_fake_state())
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_research_manager_includes_user_research():
    from tradingagents.agents.managers.research_manager import create_research_manager
    llm, captured = _capturing_llm()
    node = create_research_manager(llm)
    try:
        node(_fake_state())
    except Exception:
        pass  # structured output path may swallow; we only care about prompt capture
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_trader_includes_user_research():
    from tradingagents.agents.trader.trader import create_trader
    llm, captured = _capturing_llm()
    node = create_trader(llm)
    try:
        node(_fake_state())
    except Exception:
        pass
    assert any("UNIQUE_MARKER_42" in c for c in captured), captured


def test_empty_research_does_not_inject_block():
    """When user_research_report == "", prompts must not contain the framing line."""
    from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
    llm, captured = _capturing_llm()
    node = create_bull_researcher(llm)
    node(_fake_state(user_research_report=""))
    assert not any("User-uploaded research" in c for c in captured), captured
```

- [ ] **Step 11.2: Run, verify failure**

Run: `pytest tests/test_prompts_include_research.py -v`
Expected: 4 FAILED (or 5 — KeyError on `user_research_report` for some).

- [ ] **Step 11.3: Update `bull_researcher.py`**

Edit `tradingagents/agents/researchers/bull_researcher.py`. Replace lines 5-34 (the `bull_node` body up to and including the prompt assignment) with:

```python
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        user_research_report = state.get("user_research_report", "")

        user_research_block = ""
        if user_research_report.strip():
            user_research_block = (
                "\nUser-uploaded research (provided by the user; treat as one expert "
                "opinion among many, NOT ground truth):\n"
                f"{user_research_report}\n"
            )

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
{user_research_block}Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
"""
        prompt += get_language_instruction()
```

- [ ] **Step 11.4: Update `bear_researcher.py`**

Edit `tradingagents/agents/researchers/bear_researcher.py`. Apply the symmetric change. Replace lines 5-36 (`bear_node` body up to the prompt assignment) with:

```python
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        user_research_report = state.get("user_research_report", "")

        user_research_block = ""
        if user_research_report.strip():
            user_research_block = (
                "\nUser-uploaded research (provided by the user; treat as one expert "
                "opinion among many, NOT ground truth):\n"
                f"{user_research_report}\n"
            )

        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
{user_research_block}Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock.
"""
        prompt += get_language_instruction()
```

- [ ] **Step 11.5: Update `research_manager.py`**

Edit `tradingagents/agents/managers/research_manager.py`. Replace lines 16-41 (`research_manager_node` body up to and including `prompt += get_language_instruction()`) with:

```python
    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        user_research_report = state.get("user_research_report", "")

        investment_debate_state = state["investment_debate_state"]

        user_research_block = ""
        if user_research_report.strip():
            user_research_block = (
                "\n---\n\n**User-uploaded research** (provided by the user; treat as one "
                "expert opinion among many, NOT ground truth):\n"
                f"{user_research_report}\n"
            )

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.

---

**Debate History:**
{history}{user_research_block}"""
        prompt += get_language_instruction()
```

- [ ] **Step 11.6: Update `trader.py`**

Edit `tradingagents/agents/trader/trader.py`. Replace lines 20-46 (the `trader_node` body up to and including `messages = [...]`) with:

```python
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        user_research_report = state.get("user_research_report", "")

        user_research_block = ""
        if user_research_report.strip():
            user_research_block = (
                "\n\nUser-uploaded research (provided by the user; treat as one expert "
                f"opinion among many, NOT ground truth):\n{user_research_report}"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make investment decisions. "
                    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                    "Anchor your reasoning in the analysts' reports and the research plan."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                    f"insights from current technical market trends, macroeconomic indicators, and "
                    f"social media sentiment. Use this plan as a foundation for evaluating your next "
                    f"trading decision.\n\nProposed Investment Plan: {investment_plan}{user_research_block}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                ),
            },
        ]
```

- [ ] **Step 11.7: Run, verify pass**

Run: `pytest tests/test_prompts_include_research.py -v`
Expected: 5 PASSED.

- [ ] **Step 11.8: Run all prompt tests + state test together**

Run: `pytest tests/test_prompts_include_research.py tests/test_state_user_research.py -v`
Expected: all PASSED.

- [ ] **Step 11.9: Commit**

```bash
git add tradingagents/agents/researchers/bull_researcher.py \
        tradingagents/agents/researchers/bear_researcher.py \
        tradingagents/agents/managers/research_manager.py \
        tradingagents/agents/trader/trader.py \
        tests/test_prompts_include_research.py
git commit -m "feat(agents): inject user_research_report into bull/bear/manager/trader prompts"
```

---

### Task 12: WebUI upload component + library manager

**Files:**
- Modify: `webui.py` (insert a new section near the existing sidebar inputs around line 397-414, AND a library manager expander)
- Test: smoke import + manual e2e (Streamlit UI)

**Goal:** Two visible UI elements:
1. A research uploader between the ticker input and the date input (sidebar) with a "Save to <TICKER> library" checkbox.
2. A "📚 <TICKER> research library" sidebar expander showing existing entries with checkboxes and delete buttons.

The submit ("Start analysis") flow must read the checked library entries + the just-uploaded per-run files, concatenate into `user_research_report`, and pass to `worker.py` via the `user_research` JSON field.

- [ ] **Step 12.1: Inspect the current submit path**

Open `webui.py` and read the area around the line `run = _run_btn_slot.button(...)` (~line 466) plus the block that builds the worker request payload (search for `subprocess.Popen(..., worker.py)` or for `req` / `stdin`). Identify the dict that's serialized to JSON and sent to worker.py over stdin.

- [ ] **Step 12.2: Insert the upload UI in the sidebar**

After the sidebar `raw_input = st.sidebar.text_input(T("ticker"), ...)` block (around line 308), and before the `trade_date = st.sidebar.date_input(...)` line, insert:

```python
# ════════════════════════════════════════════════════════════════════
# User research upload + library
# ════════════════════════════════════════════════════════════════════
from tradingagents.dataflows.user_research import (
    ingest_research,
    list_research,
    delete_research,
    clear_run_dir,
)

if "ur_per_run" not in st.session_state:
    st.session_state["ur_per_run"] = []  # list of meta dicts

if "ur_run_id" not in st.session_state:
    st.session_state["ur_run_id"] = f"run-{int(time.time())}-{os.getpid()}"

if ticker:
    _lib_count = len(list_research(USER_HOME, ticker))
    _lib_label = f"📎 Research notes (library: {_lib_count})"
else:
    _lib_label = "📎 Research notes"

with st.sidebar.expander(_lib_label, expanded=False):
    _save_to_lib = st.checkbox(
        f"Save to {ticker} library" if ticker else "Save to ticker library",
        value=True,
        disabled=not ticker,
        key="ur_save_to_lib",
    )
    _uploads = st.file_uploader(
        "Drop PDF / .md / .txt (max 20MB, up to 5 files)",
        type=["pdf", "md", "markdown", "txt"],
        accept_multiple_files=True,
        key="ur_uploader",
    )
    if _uploads and ticker:
        if len(_uploads) > 5:
            st.error("Max 5 files at once.")
        else:
            for f in _uploads:
                if f.size > 20 * 1024 * 1024:
                    st.error(f"{f.name} exceeds 20MB.")
                    continue
                # Skip already-ingested in this session
                if any(m.get("filename") == f.name for m in st.session_state["ur_per_run"]):
                    continue
                with st.spinner(f"Summarizing {f.name}…"):
                    try:
                        # Use the quick-thinking model from the user's current selection.
                        # Lazy-init via the same provider config the run will use.
                        from tradingagents.llm_clients.deepseek import DeepSeekClient  # noqa: F401
                        from tradingagents.llm_clients.factory import build_quick_llm
                        llm = build_quick_llm(provider, quick_model)
                        meta = ingest_research(
                            file_bytes=f.read(),
                            filename=f.name,
                            ticker=ticker if _save_to_lib else None,
                            user_root=USER_HOME,
                            summarize_fn=llm,
                            run_id=st.session_state["ur_run_id"] if not _save_to_lib else None,
                        )
                        if not _save_to_lib:
                            st.session_state["ur_per_run"].append(meta)
                        st.success(f"✓ {f.name} summarized")
                    except Exception as e:
                        st.error(f"Failed to ingest {f.name}: {e}")

    # Library manager
    if ticker:
        existing = list_research(USER_HOME, ticker)
        if existing:
            st.markdown("**Library**")
            for m in existing:
                cols = st.columns([1, 4, 1])
                key_base = f"ur_{ticker}_{m['hash']}"
                cols[0].checkbox(
                    "include",
                    value=True,
                    key=f"{key_base}_chk",
                    label_visibility="collapsed",
                )
                cols[1].caption(
                    f"{m['filename']} · {m['uploaded_at'][:10]}"
                )
                if cols[2].button("🗑", key=f"{key_base}_del"):
                    delete_research(USER_HOME, ticker, m["hash"])
                    st.rerun()
        else:
            st.caption("Library is empty for this ticker.")
```

(If `tradingagents.llm_clients.factory.build_quick_llm` doesn't exist, mirror the WebUI's existing approach for instantiating an LLM by `provider, quick_model` — search webui.py for how `quick_model` is used to construct a client today and reuse that path.)

- [ ] **Step 12.3: Assemble `user_research_report` at run-time and inject into worker payload**

Locate the part of `webui.py` that builds the worker request dict (search for `"selected_analysts"` in the sidebar-button section). Just before submitting/spawning the worker, add:

```python
def _assemble_user_research(ticker_: str) -> str:
    chunks = []
    # Per-ticker library entries the user kept ticked
    for m in list_research(USER_HOME, ticker_):
        if st.session_state.get(f"ur_{ticker_}_{m['hash']}_chk", True):
            chunks.append(f"## {m['filename']} (uploaded {m['uploaded_at'][:10]})\n{m['summary']}")
    # Per-run uploads
    for m in st.session_state.get("ur_per_run", []):
        chunks.append(f"## {m['filename']} (this run)\n{m['summary']}")
    return "\n\n---\n\n".join(chunks)

user_research_text = _assemble_user_research(ticker) if ticker else ""
```

Then add a `"user_research"` key to the request dict serialized to worker.py:

```python
req = {
    # ... existing keys ...
    "user_research": user_research_text,
}
```

After the worker process completes (where the existing code clears caches / finalizes), call:

```python
clear_run_dir(USER_HOME, st.session_state["ur_run_id"])
st.session_state["ur_per_run"] = []
st.session_state["ur_run_id"] = f"run-{int(time.time())}-{os.getpid()}"
```

(Place this in the existing `_release_slot(run_id)` near line 484 or in the result-rendering branch — wherever the run is acknowledged complete.)

- [ ] **Step 12.4: Smoke-test the import chain**

Run: `python -c "import ast; ast.parse(open('webui.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 12.5: Manual UI verification**

Run streamlit, sign in, upload a small `.md` note saying "TEST_MARKER_UPLOAD_42 — bullish on AAPL". Confirm:
- "Summarizing…" spinner shows
- Summary success toast
- Library entry appears under the expander
- Delete button removes the entry

(Per memory feedback: this is required, not optional, before claiming the task done.)

- [ ] **Step 12.6: Commit**

```bash
git add webui.py
git commit -m "feat(webui): research upload component + per-ticker library manager"
```

---

### Task 13: Telegram one-liner indicator for research-augmented runs

**Files:**
- Modify: `scheduler.py` (the `_push_full_report` function)

- [ ] **Step 13.1: Add a small render**

In the section of `_push_full_report` where the headline message is built (right where ticker/decision is rendered), append a one-line annotation when `full_state.get("user_research_report")` is non-empty. Read the function to find the headline-building line, then add:

```python
    n_notes = 0
    user_research_report = full_state.get("user_research_report", "") or ""
    if user_research_report:
        n_notes = user_research_report.count("\n## ") or 1
    if n_notes:
        headline += f"\n📎 Used {n_notes} user-uploaded research note{'s' if n_notes != 1 else ''}"
```

(If `headline` isn't the variable name in your code, adapt to whatever string is sent first.)

- [ ] **Step 13.2: Quick manual verification with a fake state**

Run a small script (no commit):

```bash
python -c "
import scheduler
from unittest.mock import patch
sent = []
def cap(c, m, **kw):
    sent.append(m); return True, 'ok'
with patch('scheduler.notify.send_telegram', side_effect=cap), \
     patch('scheduler.compute_range_stats', side_effect=Exception('skip')):
    scheduler._push_full_report(
        chat_id='123', ticker='AAPL', trade_date='2026-05-06',
        full_state={
            'final_trade_decision': 'BUY',
            'market_report': 'M', 'fundamentals_report': 'F',
            'sentiment_report': 'S', 'news_report': 'N',
            'trader_investment_plan': 'BUY', 'investment_plan': 'BUY',
            'user_research_report': '## a\\ncontent\\n## b\\ncontent',
        },
    )
print(sent[0])
"
```

Expected: stdout contains `📎 Used 2 user-uploaded research notes`.

- [ ] **Step 13.3: Commit**

```bash
git add scheduler.py
git commit -m "feat(scheduler): annotate Telegram report when user research was used"
```

---

### Task 14: End-to-end research-upload smoke

**Files:** none new; verification only.

- [ ] **Step 14.1: Run the full WebUI flow**

Start `streamlit run webui.py`. Sign in. Pick `AAPL`. Upload a tiny PDF (synthesize via reportlab or use any short report). Click "Start analysis".

Confirm:
- Run starts without exception.
- Worker logs show `user_research_report` non-empty (add a temporary `print` in `worker.py` if needed; remove before commit).
- Final state's `market_report` includes range-stats markdown.
- `bull` and `bear` outputs reference the uploaded note's content (verify with a marker phrase like `UNIQUE_MARKER_UPLOAD_42` you put in the PDF).

(Per memory `feedback_e2e_test_after_changes.md`: healthz + ast.parse are NOT sufficient. This step is mandatory.)

- [ ] **Step 14.2: Run the entire test suite**

Run: `pytest tests/ -v`
Expected: all NEW tests pass; no previously-passing tests break.

- [ ] **Step 14.3: Verify per-run cleanup**

After the run completes, confirm:
```bash
ls ~/.tradingagents/users/*/research/_shared_for_run/ 2>/dev/null
```
Expected: empty (per-run dir deleted on completion per Task 12.3).

- [ ] **Step 14.4: No commit needed (verification only).**

---

## Self-Review Notes

**Spec coverage:**
- Range stats compute → Task 1 ✓
- 3 formatters → Task 2 ✓
- LangChain tool + market_analyst → Task 3 ✓
- WebUI pre-analysis card → Task 4 ✓
- Telegram render → Task 5 ✓
- pypdf dependency → Task 7 ✓
- PDF/md/txt extract → Task 7 ✓
- SHA dedupe + per-user storage + per-run scratch + list/delete + run-dir cleanup → Task 8 ✓
- LLM summarize w/ retry+fallback → Task 9 ✓
- AgentState field + propagate kwarg + worker wiring → Task 10 ✓
- 4 downstream prompts → Task 11 ✓
- WebUI upload + library manager + per-run scratch cleanup → Task 12 ✓
- Telegram research indicator → Task 13 ✓
- E2E smoke for both features → Task 6 + Task 14 ✓

**Type consistency check:**
- `compute_range_stats(symbol, trade_date) -> dict` — used identically in Tasks 1, 3, 4, 5.
- `_save(file_bytes, summary_md, ticker, user_root, original_filename, run_id)` — defined Task 8, called by `ingest_research` in Task 9 with the same kwargs.
- `ingest_research(file_bytes, filename, ticker, user_root, summarize_fn, run_id=None)` — defined Task 9, called from `webui.py` in Task 12 with all kwargs supplied.
- `list_research(user_root, ticker) -> list[dict]` — defined Task 8, used in Task 12 (UI) and Task 14 verification.
- `delete_research(user_root, ticker, digest)` — defined Task 8, used in Task 12.
- `clear_run_dir(user_root, run_id)` — defined Task 8, used in Task 12.3.
- `format_range_stats_telegram(stats)` — defined Task 2, called in Task 5.
- `format_range_stats_for_webui(stats)` — defined Task 2, used in Task 4.
- AgentState key `user_research_report` — declared Task 10.3, populated Task 10.4, read Task 11 in 4 prompts.
- Worker payload key `user_research` — written Task 12.3 (webui), read Task 10.6 (worker).

**Placeholder scan:** none found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-06-range-stats-and-research-upload.md`.
