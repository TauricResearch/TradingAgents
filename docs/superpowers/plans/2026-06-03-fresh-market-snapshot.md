# Fresh Market Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a freshness-aware numerical market data layer so IIC-FORGE studies always know which prices, bars, volumes, and vendors the investment team is relying on.

**Architecture:** Add a canonical `MarketSnapshot` contract and route it through a provider chain ordered `yfinance, akshare, futu, polygon`. The graph pre-fetches one snapshot before the analyst workflow, injects a Markdown summary into the market analyst prompt, keeps existing tools available for follow-up calls, and persists the snapshot with every run and analysis pack. The existing yfinance OHLCV path is fixed first so live studies stop silently omitting the current trading date or reusing stale same-day cache files.

**Tech Stack:** Python 3.10+, yfinance, AKShare, Futu OpenD SDK, Polygon REST API, pandas, LangChain tools, pytest, SQLite-backed IIC artifacts.

---

## Source Notes

- yfinance `history(..., end=...)` treats `end` as exclusive. The live `get_YFin_data_online` path must pass `end_date + 1 day` when the requested date range is date-granular.
- AKShare currently exposes `stock_us_daily`, `stock_zh_a_hist`, and `stock_hk_hist`. Its upstream project warns that data interfaces can change, so the adapter must normalize columns defensively and be covered by unit tests.
- Futu remains optional because it requires a running, logged-in OpenD gateway.
- Polygon remains final fallback because the existing repo already treats Polygon as optional and because its current module is a request-shape stub.

## File Structure

Create:

- `tradingagents/dataflows/market_snapshot.py` - dataclasses, freshness classification, provider-chain helpers, and Markdown formatting.
- `tradingagents/dataflows/akshare.py` - AKShare vendor adapter for US, China A-share, and HK daily bars.
- `tradingagents/agents/utils/market_snapshot_tools.py` - LangChain tool wrapper for `get_market_snapshot`.
- `tests/dataflows/test_market_snapshot.py` - snapshot model, formatting, and freshness tests.
- `tests/dataflows/test_yfinance_freshness.py` - inclusive end-date, empty-data fallback, and yfinance snapshot tests.
- `tests/dataflows/test_akshare_vendor.py` - AKShare symbol mapping and normalization tests.
- `tests/dataflows/test_futu_vendor.py` - Futu symbol mapping and OHLCV formatting tests.
- `tests/dataflows/test_polygon_vendor.py` - Polygon aggregate formatting tests.
- `tests/graph/test_market_snapshot_injection.py` - graph pre-fetch and run artifact tests.

Modify:

- `pyproject.toml` - add AKShare as a core dependency so the first fallback is usable after normal installation.
- `tradingagents/default_config.py` - add market-data freshness config and provider order.
- `tradingagents/dataflows/interface.py` - register `get_market_snapshot`, add `akshare`, and make fallback ordering deterministic.
- `tradingagents/dataflows/y_finance.py` - fix date inclusivity, raise typed fallback errors, and expose yfinance snapshot provider.
- `tradingagents/dataflows/stockstats_utils.py` - refresh same-day cache files by age instead of blindly reusing them.
- `tradingagents/dataflows/futu.py` - implement daily OHLCV instead of raising a stub error.
- `tradingagents/dataflows/polygon.py` - implement daily aggregate OHLCV instead of raising a stub error.
- `tradingagents/agents/utils/agent_utils.py` - re-export `get_market_snapshot`.
- `tradingagents/agents/analysts/market_analyst.py` - include snapshot prompt context and snapshot tool.
- `tradingagents/graph/trading_graph.py` - pre-fetch snapshot before graph invocation and store it in state.
- `tradingagents/graph/propagation.py` - initialize snapshot fields.
- `tradingagents/graph/run_recorder.py` - persist `market_snapshot.md` and `market_snapshot.json`.
- `tradingagents/analysis_pack/builder.py` - include the snapshot in reusable packs.
- `README.md` - document provider order, freshness semantics, and required credentials.

## Implementation Tasks

### Task 1: Add The Canonical Market Snapshot Contract

**Files:**
- Create: `tradingagents/dataflows/market_snapshot.py`
- Test: `tests/dataflows/test_market_snapshot.py`

- [ ] **Step 1: Write the failing model and formatter tests**

```python
# tests/dataflows/test_market_snapshot.py
from datetime import datetime, timezone

import pytest

from tradingagents.dataflows.market_snapshot import (
    FreshnessStatus,
    MarketBar,
    MarketSnapshot,
    classify_freshness,
    format_market_snapshot,
)


def test_classify_freshness_for_same_day_bar():
    now = datetime(2026, 6, 3, 16, 30, tzinfo=timezone.utc)
    bar_ts = datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc)

    assert classify_freshness(
        last_bar_ts=bar_ts,
        requested_date="2026-06-03",
        now_utc=now,
        stale_after_seconds=3600,
    ) is FreshnessStatus.FRESH


def test_classify_freshness_for_old_intraday_bar():
    now = datetime(2026, 6, 3, 20, 30, tzinfo=timezone.utc)
    bar_ts = datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc)

    assert classify_freshness(
        last_bar_ts=bar_ts,
        requested_date="2026-06-03",
        now_utc=now,
        stale_after_seconds=3600,
    ) is FreshnessStatus.STALE


def test_format_market_snapshot_includes_vendor_and_warning():
    snap = MarketSnapshot(
        ticker="AAPL",
        requested_date="2026-06-03",
        source="akshare",
        as_of_utc="2026-06-03T20:30:00+00:00",
        freshness=FreshnessStatus.STALE,
        last_bar=MarketBar(
            timestamp="2026-06-02T20:00:00+00:00",
            open=195.0,
            high=198.0,
            low=194.0,
            close=197.0,
            volume=1234567,
        ),
        bars=[
            MarketBar(
                timestamp="2026-06-02T20:00:00+00:00",
                open=195.0,
                high=198.0,
                low=194.0,
                close=197.0,
                volume=1234567,
            )
        ],
        warnings=["latest bar is older than requested date"],
    )

    text = format_market_snapshot(snap)

    assert "# Market snapshot for AAPL" in text
    assert "Source: akshare" in text
    assert "Freshness: stale" in text
    assert "latest bar is older than requested date" in text
    assert "| timestamp | open | high | low | close | volume |" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_market_snapshot.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.market_snapshot'`.

- [ ] **Step 3: Implement the snapshot contract**

```python
# tradingagents/dataflows/market_snapshot.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

import pandas as pd

from tradingagents.dataflows.errors import DataVendorError


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    DELAYED = "delayed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class MarketDataUnavailable(DataVendorError):
    """Raised when one provider cannot return usable market data."""


@dataclass(frozen=True)
class MarketBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    requested_date: str
    source: str
    as_of_utc: str
    freshness: FreshnessStatus
    last_bar: MarketBar | None
    bars: list[MarketBar]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["freshness"] = self.freshness.value
        return data


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_freshness(
    *,
    last_bar_ts: datetime | None,
    requested_date: str,
    now_utc: datetime | None = None,
    stale_after_seconds: int = 900,
) -> FreshnessStatus:
    if last_bar_ts is None:
        return FreshnessStatus.UNAVAILABLE

    now = now_utc or datetime.now(timezone.utc)
    last_bar_utc = _parse_dt(last_bar_ts)
    requested = pd.Timestamp(requested_date).date()

    if last_bar_utc.date() < requested:
        return FreshnessStatus.STALE

    age_seconds = (now - last_bar_utc).total_seconds()
    if age_seconds <= stale_after_seconds:
        return FreshnessStatus.FRESH
    return FreshnessStatus.DELAYED


def normalize_ohlcv_frame(df: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise MarketDataUnavailable(f"{source}: empty OHLCV frame")

    renamed = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in {"date", "datetime", "timestamp", "time"}:
            renamed[col] = "timestamp"
        elif key in {"open", "开盘"}:
            renamed[col] = "open"
        elif key in {"high", "最高"}:
            renamed[col] = "high"
        elif key in {"low", "最低"}:
            renamed[col] = "low"
        elif key in {"close", "收盘", "adj close", "adjusted close"}:
            renamed[col] = "close"
        elif key in {"volume", "vol", "成交量"}:
            renamed[col] = "volume"

    out = df.rename(columns=renamed).copy()
    if "timestamp" not in out.columns:
        out = out.reset_index().rename(columns={out.index.name or "index": "timestamp"})

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise MarketDataUnavailable(f"{source}: missing OHLCV columns {missing}")

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    if out.empty:
        raise MarketDataUnavailable(f"{source}: no valid OHLCV rows")
    return out[required]


def bars_from_frame(df: pd.DataFrame, *, source: str) -> list[MarketBar]:
    clean = normalize_ohlcv_frame(df, source=source)
    bars: list[MarketBar] = []
    for row in clean.itertuples(index=False):
        bars.append(
            MarketBar(
                timestamp=row.timestamp.isoformat(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
        )
    return bars


def snapshot_from_bars(
    *,
    ticker: str,
    requested_date: str,
    source: str,
    bars: Iterable[MarketBar],
    stale_after_seconds: int = 900,
    warnings: list[str] | None = None,
) -> MarketSnapshot:
    materialized = list(bars)
    last_bar = materialized[-1] if materialized else None
    freshness = classify_freshness(
        last_bar_ts=_parse_dt(last_bar.timestamp) if last_bar else None,
        requested_date=requested_date,
        stale_after_seconds=stale_after_seconds,
    )
    return MarketSnapshot(
        ticker=ticker.upper(),
        requested_date=requested_date,
        source=source,
        as_of_utc=utc_now_iso(),
        freshness=freshness,
        last_bar=last_bar,
        bars=materialized,
        warnings=list(warnings or []),
    )


def format_market_snapshot(snapshot: MarketSnapshot) -> str:
    lines = [
        f"# Market snapshot for {snapshot.ticker}",
        "",
        f"- Requested date: {snapshot.requested_date}",
        f"- Source: {snapshot.source}",
        f"- As of UTC: {snapshot.as_of_utc}",
        f"- Freshness: {snapshot.freshness.value}",
    ]
    if snapshot.last_bar:
        lines.extend(
            [
                f"- Last close: {snapshot.last_bar.close}",
                f"- Last bar timestamp: {snapshot.last_bar.timestamp}",
                f"- Last bar volume: {snapshot.last_bar.volume}",
            ]
        )
    if snapshot.warnings:
        lines.append("")
        lines.append("## Warnings")
        for warning in snapshot.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append("## Recent OHLCV")
    lines.append("| timestamp | open | high | low | close | volume |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for bar in snapshot.bars[-10:]:
        lines.append(
            f"| {bar.timestamp} | {bar.open:.4f} | {bar.high:.4f} | "
            f"{bar.low:.4f} | {bar.close:.4f} | {bar.volume:.0f} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/dataflows/test_market_snapshot.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/market_snapshot.py tests/dataflows/test_market_snapshot.py
git commit -m "feat(data): add market snapshot contract"
```

### Task 2: Fix yfinance Date Inclusivity And Add yfinance Snapshot Provider

**Files:**
- Modify: `tradingagents/dataflows/y_finance.py`
- Test: `tests/dataflows/test_yfinance_freshness.py`

- [ ] **Step 1: Write failing yfinance tests**

```python
# tests/dataflows/test_yfinance_freshness.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows.market_snapshot import FreshnessStatus, MarketDataUnavailable


def test_yfinance_stock_data_uses_inclusive_date_end():
    from tradingagents.dataflows.y_finance import get_YFin_data_online

    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-06-03")]),
    )
    history = MagicMock(return_value=df)
    ticker = MagicMock(history=history)

    with patch("yfinance.Ticker", return_value=ticker):
        payload = get_YFin_data_online("AAPL", "2026-06-01", "2026-06-03")

    history.assert_called_once_with(start="2026-06-01", end="2026-06-04")
    assert "2026-06-03" in payload


def test_yfinance_stock_data_empty_raises_vendor_error():
    from tradingagents.dataflows.y_finance import get_YFin_data_online

    ticker = MagicMock(history=MagicMock(return_value=pd.DataFrame()))

    with patch("yfinance.Ticker", return_value=ticker):
        with pytest.raises(MarketDataUnavailable, match="empty"):
            get_YFin_data_online("ZZZZ", "2026-06-01", "2026-06-03")


def test_yfinance_market_snapshot_formats_recent_bars():
    from tradingagents.dataflows.y_finance import get_market_snapshot

    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.5],
            "Volume": [1000, 1200],
        },
        index=pd.DatetimeIndex(
            [pd.Timestamp("2026-06-02"), pd.Timestamp("2026-06-03")]
        ),
    )
    ticker = MagicMock(history=MagicMock(return_value=df))

    with patch("yfinance.Ticker", return_value=ticker):
        text = get_market_snapshot("AAPL", "2026-06-03", lookback_days=3)

    assert "# Market snapshot for AAPL" in text
    assert "Source: yfinance" in text
    assert "Freshness:" in text
    assert "102.5000" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_yfinance_freshness.py -v`

Expected: FAIL because `end` is still exclusive, empty data returns prose, and `get_market_snapshot` does not exist in `y_finance.py`.

- [ ] **Step 3: Implement yfinance fixes**

```python
# Add near imports in tradingagents/dataflows/y_finance.py
from datetime import timedelta
from .market_snapshot import (
    MarketDataUnavailable,
    bars_from_frame,
    format_market_snapshot,
    snapshot_from_bars,
)


def _inclusive_history_end(end_date: str) -> str:
    return (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
```

Replace the `history` call and empty-data return in `get_YFin_data_online`:

```python
    data = yf_retry(
        lambda: ticker.history(start=start_date, end=_inclusive_history_end(end_date))
    )

    if data.empty:
        raise MarketDataUnavailable(
            f"yfinance returned empty OHLCV for {symbol} between "
            f"{start_date} and {end_date}"
        )
```

Add the provider function at the bottom of `y_finance.py`:

```python
def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    tk = yf.Ticker(ticker.upper())
    data = yf_retry(
        lambda: tk.history(start=start_date, end=_inclusive_history_end(curr_date))
    )
    bars = bars_from_frame(data, source="yfinance")
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="yfinance",
        bars=bars,
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)
```

- [ ] **Step 4: Run the yfinance tests**

Run: `pytest tests/dataflows/test_yfinance_freshness.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing prompt determinism test**

Run: `pytest tests/dataflows/test_prompt_determinism.py -v`

Expected: PASS. The snapshot formatter includes `as_of_utc`, but existing yfinance payloads used by old tools must still not include prompt-visible runtime retrieval phrases.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/y_finance.py tests/dataflows/test_yfinance_freshness.py
git commit -m "fix(data): make yfinance market data freshness explicit"
```

### Task 3: Register Snapshot Routing And Provider Order

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `pyproject.toml`
- Test: `tests/test_dataflows_config.py`

- [ ] **Step 1: Write failing routing tests**

Append to `tests/test_dataflows_config.py`:

```python
def test_market_snapshot_default_vendor_order():
    from tradingagents.dataflows.config import get_config

    cfg = get_config()

    assert cfg["data_vendors"]["market_snapshot"] == "yfinance, akshare, futu, polygon"
    assert cfg["data_vendors"]["core_stock_apis"] == "yfinance, akshare, futu, polygon"
    assert cfg["market_data_stale_after_seconds"] == 900
    assert cfg["market_data_cache_ttl_seconds"] == 900


def test_market_snapshot_route_falls_back_to_akshare(monkeypatch):
    import tradingagents.dataflows.interface as iface

    calls = []

    def yfinance_fail(*args, **kwargs):
        calls.append("yfinance")
        raise iface.DataVendorError("no yfinance data")

    def akshare_ok(*args, **kwargs):
        calls.append("akshare")
        return "akshare snapshot"

    monkeypatch.setitem(
        iface.VENDOR_METHODS,
        "get_market_snapshot",
        {"yfinance": yfinance_fail, "akshare": akshare_ok},
    )
    monkeypatch.setattr(
        iface,
        "get_vendor",
        lambda category, method=None: "yfinance, akshare, futu, polygon",
    )

    assert iface.route_to_vendor("get_market_snapshot", "AAPL", "2026-06-03") == (
        "akshare snapshot"
    )
    assert calls == ["yfinance", "akshare"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_dataflows_config.py::test_market_snapshot_default_vendor_order tests/test_dataflows_config.py::test_market_snapshot_route_falls_back_to_akshare -v`

Expected: FAIL because the new category and provider registration are absent.

- [ ] **Step 3: Add config defaults**

In `tradingagents/default_config.py`, add inside the main config dict near the data fetching parameters:

```python
    "market_data_stale_after_seconds": 900,
    "market_data_cache_ttl_seconds": 900,
```

Then replace the relevant `data_vendors` entries:

```python
        "core_stock_apis": "yfinance, akshare, futu, polygon",
        "market_snapshot": "yfinance, akshare, futu, polygon",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        "options_data": "yfinance",
        "osint_social": "telegram",
```

- [ ] **Step 4: Add AKShare dependency**

In `pyproject.toml`, add the core dependency so the first fallback is usable after normal installation:

```toml
    "akshare>=1.18.64",
```

Add a marker comment directly above it:

```toml
    # AKShare is the first market-data fallback after yfinance.
```

- [ ] **Step 5: Register `get_market_snapshot` and `akshare`**

Before editing `interface.py`, add temporary fallback-compatible snapshot stubs so the new imports resolve until Tasks 5 and 6 replace the bodies.

In `tradingagents/dataflows/futu.py`, add:

```python
def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    raise DataVendorError("futu.get_market_snapshot unavailable before Task 5")
```

In `tradingagents/dataflows/polygon.py`, add:

```python
def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    raise DataVendorError("polygon.get_market_snapshot unavailable before Task 6")
```

In `tradingagents/dataflows/interface.py`, add imports:

```python
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_market_snapshot as get_yfinance_market_snapshot,
)
from .akshare import (
    get_stock_data as get_akshare_stock,
    get_market_snapshot as get_akshare_market_snapshot,
)
```

Add category:

```python
    "market_snapshot": {
        "description": "Freshness-aware numerical market snapshot",
        "tools": ["get_market_snapshot"],
    },
```

Add vendor:

```python
VENDOR_LIST = [
    "yfinance",
    "akshare",
    "alpha_vantage",
    "polygon",
    "futu",
]
```

Add methods:

```python
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "akshare": get_akshare_stock,
        "polygon": get_polygon_stock,
        "futu": get_futu_stock,
    },
    "get_market_snapshot": {
        "yfinance": get_yfinance_market_snapshot,
        "akshare": get_akshare_market_snapshot,
        "futu": get_futu_market_snapshot,
        "polygon": get_polygon_market_snapshot,
    },
```

Also import the Futu and Polygon snapshot functions in the existing import blocks:

```python
from .polygon import (
    get_stock_data as get_polygon_stock,
    get_options_chain as get_polygon_options_chain,
    get_options_overview as get_polygon_options_overview,
    get_news as get_polygon_news,
    get_market_snapshot as get_polygon_market_snapshot,
)
from .futu import (
    get_stock_data as get_futu_stock,
    get_options_chain as get_futu_options_chain,
    get_market_snapshot as get_futu_market_snapshot,
)
```

- [ ] **Step 6: Run routing tests**

Run: `pytest tests/test_dataflows_config.py::test_market_snapshot_default_vendor_order tests/test_dataflows_config.py::test_market_snapshot_route_falls_back_to_akshare -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tradingagents/default_config.py tradingagents/dataflows/interface.py tests/test_dataflows_config.py
git commit -m "feat(data): route market snapshots through provider chain"
```

### Task 4: Implement AKShare Fallback Provider

**Files:**
- Create: `tradingagents/dataflows/akshare.py`
- Test: `tests/dataflows/test_akshare_vendor.py`

- [ ] **Step 1: Write failing AKShare adapter tests**

```python
# tests/dataflows/test_akshare_vendor.py
from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows.market_snapshot import MarketDataUnavailable


def test_akshare_us_daily_formats_stock_data(monkeypatch):
    import tradingagents.dataflows.akshare as akmod

    fake_ak = SimpleNamespace(
        stock_us_daily=lambda symbol, adjust="": pd.DataFrame(
            {
                "date": ["2026-06-02", "2026-06-03"],
                "open": [100.0, 101.0],
                "high": [102.0, 103.0],
                "low": [99.0, 100.0],
                "close": [101.0, 102.5],
                "volume": [1000, 1200],
            }
        )
    )
    monkeypatch.setattr(akmod, "_ak", lambda: fake_ak)

    text = akmod.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "2026-06-03" in text
    assert "102.5" in text


def test_akshare_china_a_share_symbol_mapping(monkeypatch):
    import tradingagents.dataflows.akshare as akmod

    captured = {}

    def stock_zh_a_hist(symbol, period, start_date, end_date, adjust=""):
        captured.update(
            {
                "symbol": symbol,
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return pd.DataFrame(
            {
                "日期": ["2026-06-03"],
                "开盘": [10.0],
                "最高": [11.0],
                "最低": [9.0],
                "收盘": [10.5],
                "成交量": [10000],
            }
        )

    fake_ak = SimpleNamespace(stock_zh_a_hist=stock_zh_a_hist)
    monkeypatch.setattr(akmod, "_ak", lambda: fake_ak)

    text = akmod.get_market_snapshot("600519.SS", "2026-06-03")

    assert captured == {
        "symbol": "600519",
        "period": "daily",
        "start_date": "20260524",
        "end_date": "20260603",
    }
    assert "Source: akshare" in text
    assert "10.5000" in text


def test_akshare_unsupported_symbol_raises():
    import tradingagents.dataflows.akshare as akmod

    with pytest.raises(MarketDataUnavailable, match="unsupported"):
        akmod.get_stock_data("BTC-USD", "2026-06-01", "2026-06-03")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_akshare_vendor.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the AKShare adapter**

```python
# tradingagents/dataflows/akshare.py
from __future__ import annotations

from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.market_snapshot import (
    MarketDataUnavailable,
    bars_from_frame,
    format_market_snapshot,
    snapshot_from_bars,
)


def _ak():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise MarketDataUnavailable("akshare package is not installed") from exc
    return ak


def _compact_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d")


def _market(symbol: str) -> tuple[str, str]:
    s = symbol.strip().upper()
    if s.endswith(".SS") or s.endswith(".SH"):
        return "cn", s.split(".")[0]
    if s.endswith(".SZ"):
        return "cn", s.split(".")[0]
    if s.endswith(".HK"):
        return "hk", s.split(".")[0].zfill(5)
    if "-" in s:
        raise MarketDataUnavailable(f"akshare unsupported symbol {symbol}")
    return "us", s


def _fetch_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ak = _ak()
    market, code = _market(symbol)
    if market == "us":
        df = ak.stock_us_daily(symbol=code, adjust="")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return df[(df["date"] >= start) & (df["date"] <= end)]
    if market == "cn":
        return ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=_compact_date(start_date),
            end_date=_compact_date(end_date),
            adjust="",
        )
    if market == "hk":
        return ak.stock_hk_hist(
            symbol=code,
            period="daily",
            start_date=_compact_date(start_date),
            end_date=_compact_date(end_date),
            adjust="",
        )
    raise MarketDataUnavailable(f"akshare unsupported symbol {symbol}")


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _fetch_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="akshare")])
    if clean.empty:
        raise MarketDataUnavailable(
            f"akshare returned empty OHLCV for {symbol} between {start_date} and {end_date}"
        )
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(clean)}\n\n"
    return header + clean.to_csv(index=False)


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    df = _fetch_frame(ticker, start_date, curr_date)
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="akshare",
        bars=bars_from_frame(df, source="akshare"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)
```

- [ ] **Step 4: Run AKShare tests**

Run: `pytest tests/dataflows/test_akshare_vendor.py -v`

Expected: PASS.

- [ ] **Step 5: Run import and routing tests together**

Run: `pytest tests/dataflows/test_akshare_vendor.py tests/test_dataflows_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/akshare.py tests/dataflows/test_akshare_vendor.py pyproject.toml
git commit -m "feat(data): add akshare market-data fallback"
```

### Task 5: Implement Futu Daily OHLCV Fallback

**Files:**
- Modify: `tradingagents/dataflows/futu.py`
- Test: `tests/dataflows/test_futu_vendor.py`

- [ ] **Step 1: Write failing Futu tests**

```python
# tests/dataflows/test_futu_vendor.py
from types import SimpleNamespace

import pandas as pd


class FakeContext:
    def __init__(self):
        self.calls = []
        self.closed = False

    def request_history_kline(self, code, start, end, ktype):
        self.calls.append((code, start, end, ktype))
        return 0, pd.DataFrame(
            {
                "time_key": ["2026-06-03 16:00:00"],
                "open": [100.0],
                "high": [102.0],
                "low": [99.0],
                "close": [101.5],
                "volume": [1500],
            }
        )

    def close(self):
        self.closed = True


def test_futu_symbol_translation():
    from tradingagents.dataflows.futu import translate_symbol

    assert translate_symbol("AAPL") == "US.AAPL"
    assert translate_symbol("0700.HK") == "HK.00700"
    assert translate_symbol("600519.SS") == "SH.600519"
    assert translate_symbol("000001.SZ") == "SZ.000001"


def test_futu_stock_data_formats_ohlcv(monkeypatch):
    import tradingagents.dataflows.futu as futu_mod

    fake_ctx = FakeContext()
    monkeypatch.setattr(futu_mod, "_ctx", lambda: fake_ctx)
    monkeypatch.setattr(futu_mod, "_futu_constants", lambda: SimpleNamespace(K_DAY="K_DAY"))

    text = futu_mod.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert fake_ctx.calls == [("US.AAPL", "2026-06-01", "2026-06-03", "K_DAY")]
    assert fake_ctx.closed is True
    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "101.5" in text


def test_futu_market_snapshot_uses_futu_source(monkeypatch):
    import tradingagents.dataflows.futu as futu_mod

    monkeypatch.setattr(futu_mod, "_ctx", lambda: FakeContext())
    monkeypatch.setattr(futu_mod, "_futu_constants", lambda: SimpleNamespace(K_DAY="K_DAY"))

    text = futu_mod.get_market_snapshot("AAPL", "2026-06-03", lookback_days=2)

    assert "Source: futu" in text
    assert "101.5000" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_futu_vendor.py -v`

Expected: FAIL because `translate_symbol`, `_futu_constants`, and working Futu bodies are absent.

- [ ] **Step 3: Implement Futu daily bars and snapshot**

Replace `tradingagents/dataflows/futu.py` with:

```python
"""Futu OpenD vendor implementation."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .config import get_config
from .errors import DataVendorError
from .market_snapshot import (
    bars_from_frame,
    format_market_snapshot,
    snapshot_from_bars,
)


def _futu_constants():
    try:
        from futu import KLType  # type: ignore
    except ImportError as e:
        raise DataVendorError("futu-api not installed") from e
    return KLType


def _ctx():
    try:
        from futu import OpenQuoteContext  # type: ignore
    except ImportError as e:
        raise DataVendorError("futu-api not installed") from e
    cfg = get_config()
    try:
        return OpenQuoteContext(
            host=cfg.get("futu_opend_host", "127.0.0.1"),
            port=int(cfg.get("futu_opend_port", 11111)),
        )
    except Exception as e:
        raise DataVendorError(f"Cannot reach OpenD: {e}") from e


def translate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        return f"HK.{s.split('.')[0].zfill(5)}"
    if s.endswith(".SS") or s.endswith(".SH"):
        return f"SH.{s.split('.')[0]}"
    if s.endswith(".SZ"):
        return f"SZ.{s.split('.')[0]}"
    if "." in s or "-" in s:
        raise DataVendorError(f"futu unsupported symbol {symbol}")
    return f"US.{s}"


def _fetch_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ctx = _ctx()
    try:
        constants = _futu_constants()
        ret, data = ctx.request_history_kline(
            translate_symbol(symbol),
            start=start_date,
            end=end_date,
            ktype=constants.K_DAY,
        )
        if ret != 0:
            raise DataVendorError(f"futu returned error code {ret}")
        return data.rename(columns={"time_key": "timestamp"})
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _fetch_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="futu")])
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(clean)}\n\n"
    return header + clean.to_csv(index=False)


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    df = _fetch_frame(ticker, start_date, curr_date)
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="futu",
        bars=bars_from_frame(df, source="futu"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)


def get_options_chain(symbol: str, expiration: str = "") -> str:
    raise DataVendorError("futu.get_options_chain is not implemented")
```

- [ ] **Step 4: Run Futu tests**

Run: `pytest tests/dataflows/test_futu_vendor.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/futu.py tests/dataflows/test_futu_vendor.py
git commit -m "feat(data): implement futu daily market fallback"
```

### Task 6: Implement Polygon Daily Aggregate Fallback

**Files:**
- Modify: `tradingagents/dataflows/polygon.py`
- Test: `tests/dataflows/test_polygon_vendor.py`

- [ ] **Step 1: Write failing Polygon tests**

```python
# tests/dataflows/test_polygon_vendor.py
import pandas as pd


def test_polygon_stock_data_formats_aggregates(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    captured = {}

    def fake_get(path, **params):
        captured["path"] = path
        captured["params"] = params
        return {
            "results": [
                {
                    "t": 1780516800000,
                    "o": 100.0,
                    "h": 103.0,
                    "l": 99.0,
                    "c": 102.0,
                    "v": 10000,
                }
            ]
        }

    monkeypatch.setattr(polygon, "_get", fake_get)

    text = polygon.get_stock_data("AAPL", "2026-06-01", "2026-06-03")

    assert captured["path"] == "/v2/aggs/ticker/AAPL/range/1/day/2026-06-01/2026-06-03"
    assert captured["params"]["adjusted"] == "true"
    assert "# Stock data for AAPL from 2026-06-01 to 2026-06-03" in text
    assert "102.0" in text


def test_polygon_market_snapshot_uses_polygon_source(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    monkeypatch.setattr(
        polygon,
        "_get",
        lambda path, **params: {
            "results": [
                {
                    "t": 1780516800000,
                    "o": 100.0,
                    "h": 103.0,
                    "l": 99.0,
                    "c": 102.0,
                    "v": 10000,
                }
            ]
        },
    )

    text = polygon.get_market_snapshot("AAPL", "2026-06-03", lookback_days=2)

    assert "Source: polygon" in text
    assert "102.0000" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_polygon_vendor.py -v`

Expected: FAIL because Polygon still raises stub `DataVendorError` after requesting.

- [ ] **Step 3: Implement Polygon aggregate formatting**

Add imports:

```python
from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta

from .market_snapshot import bars_from_frame, format_market_snapshot, snapshot_from_bars
```

Add helper and replace `get_stock_data`:

```python
def _aggs_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = _get(
        f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start_date}/{end_date}",
        adjusted="true",
        sort="asc",
        limit=5000,
    )
    rows = []
    for item in data.get("results", []):
        rows.append(
            {
                "timestamp": pd.to_datetime(item["t"], unit="ms", utc=True),
                "open": item.get("o"),
                "high": item.get("h"),
                "low": item.get("l"),
                "close": item.get("c"),
                "volume": item.get("v"),
            }
        )
    return pd.DataFrame(rows)


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    df = _aggs_frame(symbol, start_date, end_date)
    clean = pd.DataFrame([bar.__dict__ for bar in bars_from_frame(df, source="polygon")])
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(clean)}\n\n"
    return header + clean.to_csv(index=False)


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    snapshot = snapshot_from_bars(
        ticker=ticker,
        requested_date=curr_date,
        source="polygon",
        bars=bars_from_frame(_aggs_frame(ticker, start_date, curr_date), source="polygon"),
        stale_after_seconds=stale_after_seconds,
    )
    return format_market_snapshot(snapshot)
```

- [ ] **Step 4: Run Polygon tests**

Run: `pytest tests/dataflows/test_polygon_vendor.py -v`

Expected: PASS.

- [ ] **Step 5: Run all provider tests**

Run: `pytest tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/polygon.py tests/dataflows/test_polygon_vendor.py
git commit -m "feat(data): implement polygon daily market fallback"
```

### Task 7: Make Technical Indicator Cache Freshness-Aware

**Files:**
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Test: `tests/dataflows/test_yfinance_freshness.py`

- [ ] **Step 1: Add failing cache-refresh tests**

Append to `tests/dataflows/test_yfinance_freshness.py`:

```python
import os
import time


def test_same_day_ohlcv_cache_refreshes_when_stale(tmp_path, monkeypatch):
    import tradingagents.dataflows.stockstats_utils as utils

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-06-02,1,1,1,1,1\n",
        encoding="utf-8",
    )
    old_mtime = time.time() - 3600
    os.utime(cache_file, (old_mtime, old_mtime))

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-06-03"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is True


def test_same_day_ohlcv_cache_reuses_fresh_file(tmp_path, monkeypatch):
    import tradingagents.dataflows.stockstats_utils as utils

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-06-03,2,2,2,2,2\n",
        encoding="utf-8",
    )

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-06-03"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is False


def test_past_ohlcv_cache_reuses_file_even_when_old(tmp_path):
    import tradingagents.dataflows.stockstats_utils as utils

    cache_file = tmp_path / "AAPL-YFin-data-test.csv"
    cache_file.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-05-01,2,2,2,2,2\n",
        encoding="utf-8",
    )
    old_mtime = time.time() - 86400
    os.utime(cache_file, (old_mtime, old_mtime))

    assert utils._should_refresh_cache(
        str(cache_file),
        curr_date_dt=pd.Timestamp("2026-05-01"),
        today_date=pd.Timestamp("2026-06-03"),
        ttl_seconds=900,
    ) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/dataflows/test_yfinance_freshness.py::test_same_day_ohlcv_cache_refreshes_when_stale tests/dataflows/test_yfinance_freshness.py::test_same_day_ohlcv_cache_reuses_fresh_file tests/dataflows/test_yfinance_freshness.py::test_past_ohlcv_cache_reuses_file_even_when_old -v`

Expected: FAIL because `load_ohlcv` always reuses an existing file.

- [ ] **Step 3: Implement cache TTL**

In `tradingagents/dataflows/stockstats_utils.py`, add:

```python
def _should_refresh_cache(data_file: str, *, curr_date_dt: pd.Timestamp, today_date: pd.Timestamp, ttl_seconds: int) -> bool:
    if not os.path.exists(data_file):
        return True
    if curr_date_dt.date() < today_date.date():
        return False
    age_seconds = time.time() - os.path.getmtime(data_file)
    return age_seconds > ttl_seconds
```

Replace:

```python
    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
```

with:

```python
    ttl_seconds = int(config.get("market_data_cache_ttl_seconds", 900))
    if not _should_refresh_cache(
        data_file,
        curr_date_dt=curr_date_dt,
        today_date=today_date,
        ttl_seconds=ttl_seconds,
    ):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
```

- [ ] **Step 4: Run cache tests**

Run: `pytest tests/dataflows/test_yfinance_freshness.py::test_same_day_ohlcv_cache_refreshes_when_stale tests/dataflows/test_yfinance_freshness.py::test_same_day_ohlcv_cache_reuses_fresh_file tests/dataflows/test_yfinance_freshness.py::test_past_ohlcv_cache_reuses_file_even_when_old -v`

Expected: PASS.

- [ ] **Step 5: Run indicator tests that exercise stockstats**

Run: `pytest tests/test_signal_processing.py tests/dataflows/test_yfinance_freshness.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/dataflows/stockstats_utils.py tests/dataflows/test_yfinance_freshness.py
git commit -m "fix(data): refresh same-day ohlcv cache by ttl"
```

### Task 8: Add Snapshot Tool And Pre-Fetch It For Every Graph Run

**Files:**
- Create: `tradingagents/agents/utils/market_snapshot_tools.py`
- Modify: `tradingagents/agents/utils/agent_utils.py`
- Modify: `tradingagents/graph/propagation.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Test: `tests/graph/test_market_snapshot_injection.py`

- [ ] **Step 1: Write failing graph injection tests**

```python
# tests/graph/test_market_snapshot_injection.py
from unittest.mock import MagicMock


def test_initial_state_contains_market_snapshot_slots():
    from tradingagents.graph.propagation import Propagator

    state = Propagator().create_initial_state("AAPL", "2026-06-03")

    assert state["market_snapshot_text"] == ""
    assert state["market_snapshot_error"] == ""


def test_graph_prefetches_market_snapshot(monkeypatch, tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    class FakePropagator:
        def create_initial_state(self, company_name, trade_date, asset_type="stock", past_context=""):
            return {
                "messages": [("human", company_name)],
                "company_of_interest": company_name,
                "asset_type": asset_type,
                "trade_date": trade_date,
                "past_context": past_context,
                "market_snapshot_text": "",
                "market_snapshot_error": "",
                "investment_debate_state": {},
                "risk_debate_state": {},
                "market_report": "",
                "fundamentals_report": "",
                "sentiment_report": "",
                "news_report": "",
                "derivatives_report": "",
            }

        def get_graph_args(self):
            return {}

    graph = object.__new__(TradingAgentsGraph)
    graph.memory_log = MagicMock(get_past_context=lambda ticker: "")
    graph.propagator = FakePropagator()
    graph.config = {"market_data_stale_after_seconds": 900}
    graph.run_recorder = MagicMock(start=lambda **kwargs: None)
    graph.debug = False
    graph.graph = MagicMock(
        invoke=lambda state, **kwargs: {
            **state,
            "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "trader_investment_plan": "",
            "investment_debate_state": {"bull_history": "", "bear_history": "", "history": "", "current_response": "", "judge_decision": ""},
            "risk_debate_state": {"aggressive_history": "", "conservative_history": "", "neutral_history": "", "history": "", "judge_decision": ""},
            "investment_plan": "",
        }
    )
    graph._log_state = MagicMock()
    graph.process_signal = lambda signal: "HOLD"
    graph.memory_log.store_decision = MagicMock()

    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.route_to_vendor",
        lambda method, ticker, trade_date, **kwargs: "# Market snapshot for AAPL\n",
    )

    final_state, decision = graph._run_graph("AAPL", "2026-06-03")

    assert decision == "HOLD"
    assert final_state["market_snapshot_text"] == "# Market snapshot for AAPL\n"
    assert final_state["market_snapshot_error"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/graph/test_market_snapshot_injection.py -v`

Expected: FAIL because snapshot fields and prefetch do not exist.

- [ ] **Step 3: Add the LangChain tool**

```python
# tradingagents/agents/utils/market_snapshot_tools.py
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_market_snapshot(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD format"],
) -> str:
    """Retrieve a freshness-aware numerical market snapshot with source provenance."""
    return route_to_vendor("get_market_snapshot", ticker, curr_date)
```

In `tradingagents/agents/utils/agent_utils.py`, add:

```python
from .market_snapshot_tools import get_market_snapshot
```

- [ ] **Step 4: Add state slots**

In `tradingagents/graph/propagation.py`, add to the returned dict:

```python
            "market_snapshot_text": "",
            "market_snapshot_error": "",
```

- [ ] **Step 5: Pre-fetch the snapshot**

In `tradingagents/graph/trading_graph.py`, add import:

```python
from tradingagents.dataflows.interface import route_to_vendor
```

In `_run_graph`, immediately after `init_agent_state` is created and before event context injection, add:

```python
        try:
            init_agent_state["market_snapshot_text"] = route_to_vendor(
                "get_market_snapshot",
                company_name,
                str(trade_date),
                stale_after_seconds=self.config.get("market_data_stale_after_seconds", 900),
            )
            init_agent_state["market_snapshot_error"] = ""
        except Exception as e:
            init_agent_state["market_snapshot_text"] = ""
            init_agent_state["market_snapshot_error"] = (
                f"Market snapshot unavailable for {company_name} on {trade_date}: {e}"
            )
            logger.warning(init_agent_state["market_snapshot_error"])
```

- [ ] **Step 6: Inject snapshot into market analyst prompt and tools**

In `tradingagents/agents/analysts/market_analyst.py`, import:

```python
    get_market_snapshot,
```

Update tools:

```python
        tools = [
            get_market_snapshot,
            get_stock_data,
            get_indicators,
        ]
```

Update prompt human message:

```python
                (
                    "human",
                    "For your reference, the current date is {current_date}. "
                    "{instrument_context}\n\n"
                    "Numerical market snapshot provided before analysis:\n"
                    "{market_snapshot_text}\n"
                    "{market_snapshot_error}",
                ),
```

Add partials:

```python
        prompt = prompt.partial(market_snapshot_text=state.get("market_snapshot_text", ""))
        prompt = prompt.partial(market_snapshot_error=state.get("market_snapshot_error", ""))
```

- [ ] **Step 7: Run graph injection tests**

Run: `pytest tests/graph/test_market_snapshot_injection.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add tradingagents/agents/utils/market_snapshot_tools.py tradingagents/agents/utils/agent_utils.py tradingagents/graph/propagation.py tradingagents/graph/trading_graph.py tradingagents/agents/analysts/market_analyst.py tests/graph/test_market_snapshot_injection.py
git commit -m "feat(graph): inject market snapshots into analyst runs"
```

### Task 9: Persist Snapshots In Run Artifacts And Analysis Packs

**Files:**
- Modify: `tradingagents/graph/run_recorder.py`
- Modify: `tradingagents/analysis_pack/builder.py`
- Test: `tests/graph/test_market_snapshot_injection.py`
- Test: `tests/analysis_pack/test_analysis_pack_builder.py`

- [ ] **Step 1: Add failing run artifact test**

Append to `tests/graph/test_market_snapshot_injection.py`:

```python
def test_run_recorder_writes_market_snapshot(tmp_path):
    import json

    from tradingagents.persistence.db import connect
    from tradingagents.graph.run_recorder import RunRecorder

    class EmptyCosts:
        def totals_by_model(self):
            return {}

    conn = connect(str(tmp_path / "iic.db"))
    rec = RunRecorder(
        conn=conn,
        data_dir=str(tmp_path),
        run_id="run-snapshot",
        persona_id="balanced",
        cost_callback=EmptyCosts(),
    )
    rec.start("AAPL", started_ts="2026-06-03T20:30:00+00:00")
    rec.record(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2026-06-03",
            "market_snapshot_text": "# Market snapshot for AAPL\n",
            "market_snapshot_error": "",
            "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **HOLD**",
            "trader_investment_plan": "",
            "risk_debate_state": {},
        }
    )

    run_dir = tmp_path / "runs" / "run-snapshot"
    assert (run_dir / "market_snapshot.md").read_text(encoding="utf-8") == (
        "# Market snapshot for AAPL\n"
    )
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["market_snapshot_artifact"] == "market_snapshot.md"
```

- [ ] **Step 2: Add failing analysis pack test**

Append to `tests/analysis_pack/test_analysis_pack_builder.py`:

```python
def test_analysis_pack_collects_market_snapshot(tmp_path):
    from tradingagents.analysis_pack.builder import build_pack_content_from_runs
    from tradingagents.persistence.db import connect
    from tradingagents.persistence import store

    conn = connect(str(tmp_path / "iic.db"))
    run_dir = tmp_path / "runs" / "run-snapshot"
    run_dir.mkdir(parents=True)
    (run_dir / "market_snapshot.md").write_text("# Market snapshot for AAPL\n", encoding="utf-8")
    (run_dir / "pm_synthesis.md").write_text("FINAL TRANSACTION PROPOSAL: **HOLD**", encoding="utf-8")

    store.insert_run(
        conn,
        run_id="run-snapshot",
        ticker="AAPL",
        persona_id="balanced",
        started_ts="2026-06-03T20:30:00+00:00",
        artifact_dir="runs/run-snapshot",
    )

    content = build_pack_content_from_runs(
        conn=conn,
        data_dir=tmp_path,
        event_id="event-1",
        ticker="AAPL",
        trade_date="2026-06-03",
        event_context="",
        run_ids=["run-snapshot"],
    )

    assert content["market_snapshot"] == "# Market snapshot for AAPL\n"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/graph/test_market_snapshot_injection.py::test_run_recorder_writes_market_snapshot tests/analysis_pack/test_analysis_pack_builder.py::test_analysis_pack_collects_market_snapshot -v`

Expected: FAIL because artifacts and packs do not collect snapshots.

- [ ] **Step 4: Persist snapshot artifacts**

In `tradingagents/graph/run_recorder.py`, after event context handling, add:

```python
        snapshot_text = state.get("market_snapshot_text", "") or ""
        snapshot_error = state.get("market_snapshot_error", "") or ""
        if snapshot_text:
            (run_path / "market_snapshot.md").write_text(snapshot_text, encoding="utf-8")
            (run_path / "market_snapshot.json").write_text(
                json.dumps(
                    {
                        "ticker": ticker,
                        "trade_date": state.get("trade_date"),
                        "content": snapshot_text,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if snapshot_error:
            (run_path / "market_snapshot_error.md").write_text(
                snapshot_error,
                encoding="utf-8",
            )
```

Add to `meta.json` payload:

```python
            "market_snapshot_artifact": "market_snapshot.md" if snapshot_text else "",
            "market_snapshot_error": snapshot_error,
```

- [ ] **Step 5: Include snapshot in analysis packs**

In `tradingagents/analysis_pack/builder.py`, add helper:

```python
def _collect_market_snapshot_from_artifacts(artifact_dir: Path) -> str:
    return _read_text(artifact_dir / "market_snapshot.md")
```

In `build_pack_content_from_runs`, initialize:

```python
    market_snapshot = ""
```

Inside the run loop after `artifact_dir`:

```python
        if not market_snapshot:
            market_snapshot = _collect_market_snapshot_from_artifacts(artifact_dir)
```

Add to returned dict:

```python
        "market_snapshot": market_snapshot,
```

- [ ] **Step 6: Run artifact and pack tests**

Run: `pytest tests/graph/test_market_snapshot_injection.py tests/analysis_pack/test_analysis_pack_builder.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tradingagents/graph/run_recorder.py tradingagents/analysis_pack/builder.py tests/graph/test_market_snapshot_injection.py tests/analysis_pack/test_analysis_pack_builder.py
git commit -m "feat(state): persist market snapshots with runs"
```

### Task 10: Surface Snapshot Limitations In Reports And Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md`
- Test: `tests/test_default_config_f1.py`

- [ ] **Step 1: Add config assertion**

Append to `tests/test_default_config_f1.py`:

```python
def test_market_data_provider_order_documented_in_config():
    from tradingagents.default_config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["data_vendors"]["market_snapshot"] == (
        "yfinance, akshare, futu, polygon"
    )
    assert DEFAULT_CONFIG["market_data_stale_after_seconds"] == 900
```

- [ ] **Step 2: Run the config test**

Run: `pytest tests/test_default_config_f1.py::test_market_data_provider_order_documented_in_config -v`

Expected: PASS after Task 3, otherwise FAIL.

- [ ] **Step 3: Update README market-data section**

Add under `## Configuration` in `README.md`:

```markdown
### Market Data Freshness

Full studies pre-fetch a numerical market snapshot before the TradingAgents graph starts. The default provider order is:

```text
yfinance -> AKShare -> Futu OpenD -> Polygon
```

The snapshot is injected into the market analyst prompt and persisted under each run directory as `market_snapshot.md`. It records provider, as-of timestamp, last bar timestamp, freshness status, recent OHLCV, and warnings. `market_data_stale_after_seconds` and `market_data_cache_ttl_seconds` default to `900` seconds so same-day runs do not reuse stale cache files for the whole session.

Provider requirements:

- yfinance: installed by default.
- AKShare: installed by default as the first fallback; strongest for US, China A-share, and HK daily bars.
- Futu: requires `futu-api`, a running OpenD gateway, and a logged-in account.
- Polygon: requires `POLYGON_API_KEY`; used last in the default chain.
```

- [ ] **Step 4: Amend the redesign spec note**

Add to `docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md` after `## Cost And Cache Controls`:

```markdown
## Market Data Freshness

The default approved study now starts by fetching a canonical market snapshot through `yfinance, akshare, futu, polygon`. The snapshot is prompt-visible to the market analyst and persisted in run artifacts, so every full brief can be audited for provider and freshness. yfinance daily ranges use an inclusive requested end date by passing `end_date + 1 day`, and same-day technical-indicator cache files refresh by TTL.
```

- [ ] **Step 5: Run docs-related config test**

Run: `pytest tests/test_default_config_f1.py::test_market_data_provider_order_documented_in_config -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md tests/test_default_config_f1.py
git commit -m "docs(data): document market snapshot freshness"
```

### Task 11: End-To-End Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused dataflow suite**

Run:

```bash
pytest tests/dataflows/test_market_snapshot.py tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py tests/test_dataflows_config.py -v
```

Expected: PASS.

- [ ] **Step 2: Run graph and artifact suite**

Run:

```bash
pytest tests/graph/test_market_snapshot_injection.py tests/analysis_pack/test_analysis_pack_builder.py tests/test_default_config_f1.py -v
```

Expected: PASS.

- [ ] **Step 3: Run existing safety tests around symbol handling and prompt determinism**

Run:

```bash
pytest tests/test_ticker_symbol_handling.py tests/dataflows/test_prompt_determinism.py tests/test_safe_ticker_component.py -v
```

Expected: PASS.

- [ ] **Step 4: Run the full unit suite**

Run:

```bash
pytest -m unit -v
```

Expected: PASS. If this command runs longer than the local budget, stop after 10 minutes and record the slowest test file names in the final implementation note.

- [ ] **Step 5: Manual smoke with one known US ticker**

Run:

```bash
python -m cli.main deepdive AAPL --date 2026-06-03
```

Expected:

- The generated run directory contains `market_snapshot.md`.
- The snapshot says one of `Source: yfinance`, `Source: akshare`, `Source: futu`, or `Source: polygon`.
- The market analyst report references the provided numerical snapshot.
- If all providers are unavailable, the market analyst prompt includes `Market snapshot unavailable...` and the final brief does not pretend live prices were available.

## Self-Review

Spec coverage:

- Stage 1 quick fixes are covered by Tasks 2 and 7.
- Stage 2 canonical market snapshots are covered by Tasks 1, 3, 8, and 9.
- Stage 3 provider fallback expansion is covered by Tasks 4, 5, and 6.
- Requested fallback order is implemented in Task 3 as `yfinance, akshare, futu, polygon`.
- Investment-team auditability is covered by persisted artifacts in Task 9 and docs in Task 10.

Plan hygiene:

- A scan for forbidden placeholder strings returns no actionable hits.
- Every implementation task includes concrete test code, implementation code, commands, expected outcomes, and commit commands.

Type consistency:

- `MarketSnapshot`, `MarketBar`, `FreshnessStatus`, `MarketDataUnavailable`, `bars_from_frame`, `snapshot_from_bars`, and `format_market_snapshot` are defined in Task 1 before later tasks import them.
- Provider functions are consistently named `get_stock_data` and `get_market_snapshot`.
- State keys are consistently named `market_snapshot_text` and `market_snapshot_error`.
