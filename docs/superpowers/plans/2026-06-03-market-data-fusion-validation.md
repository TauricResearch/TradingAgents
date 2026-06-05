# Market Data Fusion Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate and implement a market-data fusion layer that detects missing OHLCV sessions, skips weekends and known fixed-date holidays, fills missing sessions from fallback vendors, and presents the investment team with one complete provenance-aware chart.

**Architecture:** Keep the current graph/tool contract (`get_market_snapshot`) unchanged, but replace provider-level-only fallback with a fused snapshot engine behind the interface. The fusion engine computes expected trading sessions, treats weekends and fixed-date holiday whitelist entries as allowed missing dates, fetches only uncovered ranges from yfinance -> AKShare -> Futu -> Polygon, and formats one full Markdown chart with per-row source provenance.

**Tech Stack:** Python 3.12, pandas, pytest, existing `tradingagents.dataflows` vendor adapters, existing LangChain market snapshot tool, existing RunRecorder artifact persistence.

---

## File Structure

- Create `tradingagents/dataflows/market_calendar.py`
  - Owns simple expected-session logic.
  - Skips weekends.
  - Skips fixed-date closure whitelist entries such as `01-01`, `05-01`, `06-19`, `07-04`, `10-01`, and `12-25`.
  - Does not try to model observed holidays or exchange-specific half days.

- Create `tradingagents/dataflows/market_fusion.py`
  - Owns fused OHLCV dataclasses, missing-session detection, fallback fetch sequencing, source provenance, and Markdown chart formatting.
  - Imports `normalize_ohlcv_frame`, `MarketDataUnavailable`, `classify_freshness`, and `utc_now_iso` from `market_snapshot.py`.
  - Uses raw vendor fetch functions instead of each vendor's Markdown `get_market_snapshot()`.

- Modify `tradingagents/dataflows/y_finance.py`
  - Add `fetch_ohlcv_frame(symbol, start_date, end_date) -> pd.DataFrame`.
  - Keep existing `get_YFin_data_online()` and `get_market_snapshot()` compatibility.

- Modify `tradingagents/dataflows/akshare.py`
  - Add public `fetch_ohlcv_frame(symbol, start_date, end_date) -> pd.DataFrame` wrapper around `_fetch_frame()`.

- Modify `tradingagents/dataflows/futu.py`
  - Add public `fetch_ohlcv_frame(symbol, start_date, end_date) -> pd.DataFrame` wrapper around `_fetch_frame()`.

- Modify `tradingagents/dataflows/polygon.py`
  - Add public `fetch_ohlcv_frame(symbol, start_date, end_date) -> pd.DataFrame` wrapper around `_aggs_frame()`.

- Modify `tradingagents/dataflows/interface.py`
  - Special-case `route_to_vendor("get_market_snapshot", ...)` to call the fusion layer with the configured provider order.
  - Leave the existing vendor registry intact for other methods.

- Modify `README.md`
  - Clarify that snapshot fallback is bar/session-level after this work, not just whole-provider fallback.
  - Document the holiday/weekend skip policy as approximate by design.

- Test `tests/dataflows/test_market_calendar.py`
- Test `tests/dataflows/test_market_fusion.py`
- Test `tests/test_dataflows_config.py`
- Test `tests/graph/test_market_snapshot_injection.py`

---

### Task 1: Calendar Whitelist And Expected Sessions

**Files:**
- Create: `tradingagents/dataflows/market_calendar.py`
- Test: `tests/dataflows/test_market_calendar.py`

- [ ] **Step 1: Write failing calendar tests**

Create `tests/dataflows/test_market_calendar.py`:

```python
import pandas as pd

from tradingagents.dataflows.market_calendar import (
    DEFAULT_FIXED_CLOSURE_DATES,
    expected_trading_sessions,
    is_allowed_market_closure,
)


def test_expected_sessions_skip_weekends():
    assert expected_trading_sessions("2026-06-05", "2026-06-08") == [
        "2026-06-05",
        "2026-06-08",
    ]


def test_expected_sessions_skip_fixed_holiday_whitelist():
    assert expected_trading_sessions("2026-12-24", "2026-12-26") == [
        "2026-12-24",
    ]


def test_fixed_holiday_whitelist_is_deliberately_simple():
    assert DEFAULT_FIXED_CLOSURE_DATES["01-01"] == "New Year's Day"
    assert DEFAULT_FIXED_CLOSURE_DATES["07-04"] == "Independence Day"
    assert DEFAULT_FIXED_CLOSURE_DATES["12-25"] == "Christmas Day"
    assert is_allowed_market_closure(pd.Timestamp("2026-07-04")) is True
    assert is_allowed_market_closure(pd.Timestamp("2026-07-03")) is False
```

- [ ] **Step 2: Run calendar tests and verify they fail**

Run:

```bash
pytest tests/dataflows/test_market_calendar.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.market_calendar'`.

- [ ] **Step 3: Implement simple expected-session helper**

Create `tradingagents/dataflows/market_calendar.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


DEFAULT_FIXED_CLOSURE_DATES: dict[str, str] = {
    "01-01": "New Year's Day",
    "05-01": "Labor Day / May Day",
    "06-19": "Juneteenth",
    "07-04": "Independence Day",
    "10-01": "China National Day",
    "12-25": "Christmas Day",
}


def _date_key(value: pd.Timestamp) -> str:
    return f"{value.month:02d}-{value.day:02d}"


def is_allowed_market_closure(
    value: str | pd.Timestamp,
    *,
    fixed_closures: Mapping[str, str] | None = None,
) -> bool:
    day = pd.Timestamp(value)
    if day.weekday() >= 5:
        return True
    closures = fixed_closures or DEFAULT_FIXED_CLOSURE_DATES
    return _date_key(day) in closures


def expected_trading_sessions(
    start_date: str,
    end_date: str,
    *,
    fixed_closures: Mapping[str, str] | None = None,
) -> list[str]:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if end < start:
        raise ValueError(f"end_date {end_date} must be on or after start_date {start_date}")

    sessions: list[str] = []
    for day in pd.date_range(start, end, freq="D"):
        if is_allowed_market_closure(day, fixed_closures=fixed_closures):
            continue
        sessions.append(day.strftime("%Y-%m-%d"))
    return sessions
```

- [ ] **Step 4: Run calendar tests and verify they pass**

Run:

```bash
pytest tests/dataflows/test_market_calendar.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/market_calendar.py tests/dataflows/test_market_calendar.py
git commit -m "feat(data): add simple market session calendar"
```

---

### Task 2: Fusion Primitives And Complete Chart Formatting

**Files:**
- Create: `tradingagents/dataflows/market_fusion.py`
- Test: `tests/dataflows/test_market_fusion.py`

- [ ] **Step 1: Write failing tests for fusion and formatting**

Create `tests/dataflows/test_market_fusion.py`:

```python
import pandas as pd

from tradingagents.dataflows.market_fusion import (
    FusedMarketBar,
    FusedMarketSnapshot,
    fuse_source_frames,
    format_fused_market_snapshot,
)


def _frame(rows):
    return pd.DataFrame(rows)


def test_fuse_source_frames_fills_missing_sessions_by_provider_order():
    expected = [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
    ]
    yfinance = _frame(
        [
            {"timestamp": "2026-06-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
            {"timestamp": "2026-06-02", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 110},
            {"timestamp": "2026-06-05", "open": 14, "high": 15, "low": 13, "close": 14.5, "volume": 140},
        ]
    )
    akshare = _frame(
        [
            {"timestamp": "2026-06-03", "open": 12, "high": 13, "low": 11, "close": 12.5, "volume": 120},
        ]
    )
    polygon = _frame(
        [
            {"timestamp": "2026-06-04", "open": 13, "high": 14, "low": 12, "close": 13.5, "volume": 130},
        ]
    )

    snapshot = fuse_source_frames(
        ticker="AAPL",
        requested_date="2026-06-05",
        expected_sessions=expected,
        source_frames=[
            ("yfinance", yfinance),
            ("akshare", akshare),
            ("polygon", polygon),
        ],
    )

    assert [bar.date for bar in snapshot.bars] == expected
    assert [bar.source for bar in snapshot.bars] == [
        "yfinance",
        "yfinance",
        "akshare",
        "polygon",
        "yfinance",
    ]
    assert snapshot.missing_sessions == []
    assert snapshot.coverage_ratio == 1.0


def test_format_fused_snapshot_exposes_full_chart_and_sources():
    snapshot = FusedMarketSnapshot(
        ticker="AAPL",
        requested_date="2026-06-05",
        as_of_utc="2026-06-05T21:00:00+00:00",
        freshness="fresh",
        expected_sessions=["2026-06-05"],
        missing_sessions=[],
        allowed_missing_sessions=["2026-07-04"],
        provider_errors={"futu": "futu-api not installed"},
        bars=[
            FusedMarketBar(
                date="2026-06-05",
                timestamp="2026-06-05T00:00:00+00:00",
                open=14.0,
                high=15.0,
                low=13.0,
                close=14.5,
                volume=140.0,
                source="yfinance",
            )
        ],
    )

    text = format_fused_market_snapshot(snapshot)

    assert "# Market snapshot for AAPL" in text
    assert "Coverage: 1/1 expected sessions (100.00%)" in text
    assert "Allowed missing sessions: 2026-07-04" in text
    assert "futu-api not installed" in text
    assert "## Fused OHLCV Chart" in text
    assert "| date | open | high | low | close | volume | source |" in text
    assert "| 2026-06-05 | 14.0000 | 15.0000 | 13.0000 | 14.5000 | 140 | yfinance |" in text
```

- [ ] **Step 2: Run fusion tests and verify they fail**

Run:

```bash
pytest tests/dataflows/test_market_fusion.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingagents.dataflows.market_fusion'`.

- [ ] **Step 3: Implement fusion dataclasses, merge logic, and formatter**

Create `tradingagents/dataflows/market_fusion.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

import pandas as pd

from tradingagents.dataflows.market_snapshot import (
    MarketDataUnavailable,
    classify_freshness,
    normalize_ohlcv_frame,
    utc_now_iso,
)


@dataclass(frozen=True)
class FusedMarketBar:
    date: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


@dataclass(frozen=True)
class FusedMarketSnapshot:
    ticker: str
    requested_date: str
    as_of_utc: str
    freshness: str
    expected_sessions: list[str]
    missing_sessions: list[str]
    allowed_missing_sessions: list[str]
    provider_errors: dict[str, str] = field(default_factory=dict)
    bars: list[FusedMarketBar] = field(default_factory=list)

    @property
    def coverage_ratio(self) -> float:
        if not self.expected_sessions:
            return 1.0
        covered = len(self.expected_sessions) - len(self.missing_sessions)
        return covered / len(self.expected_sessions)

    def to_dict(self) -> dict:
        return asdict(self)


def _bars_from_source_frame(source: str, frame: pd.DataFrame) -> list[FusedMarketBar]:
    clean = normalize_ohlcv_frame(frame, source=source)
    bars: list[FusedMarketBar] = []
    for row in clean.itertuples(index=False):
        date = row.timestamp.date().isoformat()
        bars.append(
            FusedMarketBar(
                date=date,
                timestamp=row.timestamp.isoformat(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                source=source,
            )
        )
    return bars


def fuse_source_frames(
    *,
    ticker: str,
    requested_date: str,
    expected_sessions: list[str],
    source_frames: Iterable[tuple[str, pd.DataFrame]],
    allowed_missing_sessions: list[str] | None = None,
    provider_errors: dict[str, str] | None = None,
    stale_after_seconds: int = 900,
) -> FusedMarketSnapshot:
    bars_by_date: dict[str, FusedMarketBar] = {}
    expected = set(expected_sessions)
    errors = dict(provider_errors or {})

    for source, frame in source_frames:
        try:
            for bar in _bars_from_source_frame(source, frame):
                if bar.date in expected and bar.date not in bars_by_date:
                    bars_by_date[bar.date] = bar
        except MarketDataUnavailable as exc:
            errors[source] = str(exc)

    bars = [bars_by_date[session] for session in expected_sessions if session in bars_by_date]
    missing = [session for session in expected_sessions if session not in bars_by_date]
    last_bar = bars[-1] if bars else None
    freshness = classify_freshness(
        last_bar_ts=pd.Timestamp(last_bar.timestamp).to_pydatetime() if last_bar else None,
        requested_date=requested_date,
        stale_after_seconds=stale_after_seconds,
    ).value

    return FusedMarketSnapshot(
        ticker=ticker.upper(),
        requested_date=requested_date,
        as_of_utc=utc_now_iso(),
        freshness=freshness,
        expected_sessions=expected_sessions,
        missing_sessions=missing,
        allowed_missing_sessions=list(allowed_missing_sessions or []),
        provider_errors=errors,
        bars=bars,
    )


def format_fused_market_snapshot(snapshot: FusedMarketSnapshot) -> str:
    covered = len(snapshot.expected_sessions) - len(snapshot.missing_sessions)
    coverage = f"{snapshot.coverage_ratio:.2%}"
    lines = [
        f"# Market snapshot for {snapshot.ticker}",
        "",
        f"- Requested date: {snapshot.requested_date}",
        "- Source: fused",
        f"- As of UTC: {snapshot.as_of_utc}",
        f"- Freshness: {snapshot.freshness}",
        f"- Coverage: {covered}/{len(snapshot.expected_sessions)} expected sessions ({coverage})",
    ]
    if snapshot.missing_sessions:
        lines.append(f"- Missing sessions: {', '.join(snapshot.missing_sessions)}")
    if snapshot.allowed_missing_sessions:
        lines.append(
            f"- Allowed missing sessions: {', '.join(snapshot.allowed_missing_sessions)}"
        )
    if snapshot.provider_errors:
        lines.append("")
        lines.append("## Provider Errors")
        for provider, error in snapshot.provider_errors.items():
            lines.append(f"- {provider}: {error}")

    lines.append("")
    lines.append("## Fused OHLCV Chart")
    lines.append("| date | open | high | low | close | volume | source |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for bar in snapshot.bars:
        lines.append(
            f"| {bar.date} | {bar.open:.4f} | {bar.high:.4f} | "
            f"{bar.low:.4f} | {bar.close:.4f} | {bar.volume:.0f} | {bar.source} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run fusion tests and verify they pass**

Run:

```bash
pytest tests/dataflows/test_market_fusion.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/market_fusion.py tests/dataflows/test_market_fusion.py
git commit -m "feat(data): add fused market snapshot primitives"
```

---

### Task 3: Public Raw OHLCV Fetchers For Vendors

**Files:**
- Modify: `tradingagents/dataflows/y_finance.py`
- Modify: `tradingagents/dataflows/akshare.py`
- Modify: `tradingagents/dataflows/futu.py`
- Modify: `tradingagents/dataflows/polygon.py`
- Test: `tests/dataflows/test_yfinance_freshness.py`
- Test: `tests/dataflows/test_akshare_vendor.py`
- Test: `tests/dataflows/test_futu_vendor.py`
- Test: `tests/dataflows/test_polygon_vendor.py`

- [ ] **Step 1: Add failing raw fetch tests**

Append to `tests/dataflows/test_yfinance_freshness.py`:

```python
def test_yfinance_fetch_ohlcv_frame_returns_normalized_frame(monkeypatch):
    yfmod = _load_yfinance_module(monkeypatch, ticker="AAPL")
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [103.0],
            "Low": [99.0],
            "Close": [102.5],
            "Volume": [12345],
        },
        index=pd.to_datetime(["2026-06-03"]),
    )
    yfmod.yf.Ticker.return_value.history.return_value = df

    out = yfmod.fetch_ohlcv_frame("AAPL", "2026-06-03", "2026-06-03")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 102.5
```

Append to `tests/dataflows/test_akshare_vendor.py`:

```python
def test_akshare_fetch_ohlcv_frame_exposes_normalized_data(monkeypatch):
    akmod = _load_akshare_module(monkeypatch)
    monkeypatch.setattr(
        akmod,
        "_fetch_frame",
        lambda symbol, start_date, end_date: pd.DataFrame(
            {
                "date": ["2026-06-03"],
                "open": [100],
                "high": [103],
                "low": [99],
                "close": [102],
                "volume": [12345],
            }
        ),
    )

    out = akmod.fetch_ohlcv_frame("AAPL", "2026-06-03", "2026-06-03")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 102
```

Append to `tests/dataflows/test_futu_vendor.py`:

```python
def test_futu_fetch_ohlcv_frame_exposes_normalized_data(monkeypatch):
    futu_mod = _load_futu_module(monkeypatch)
    monkeypatch.setattr(
        futu_mod,
        "_fetch_frame",
        lambda symbol, start_date, end_date: pd.DataFrame(
            {
                "time_key": ["2026-06-03"],
                "open": [100],
                "high": [103],
                "low": [99],
                "close": [102],
                "volume": [12345],
            }
        ),
    )

    out = futu_mod.fetch_ohlcv_frame("AAPL", "2026-06-03", "2026-06-03")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 102
```

Append to `tests/dataflows/test_polygon_vendor.py`:

```python
def test_polygon_fetch_ohlcv_frame_exposes_normalized_data(monkeypatch):
    import tradingagents.dataflows.polygon as polygon

    monkeypatch.setattr(
        polygon,
        "_aggs_frame",
        lambda symbol, start_date, end_date: pd.DataFrame(
            {
                "timestamp": ["2026-06-03"],
                "open": [100],
                "high": [103],
                "low": [99],
                "close": [102],
                "volume": [12345],
            }
        ),
    )

    out = polygon.fetch_ohlcv_frame("AAPL", "2026-06-03", "2026-06-03")

    assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == 102
```

- [ ] **Step 2: Run raw fetch tests and verify they fail**

Run:

```bash
pytest tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'fetch_ohlcv_frame'`.

- [ ] **Step 3: Add public raw fetchers**

Modify `tradingagents/dataflows/y_finance.py` after `get_YFin_data_online()`:

```python
def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    ticker = yf.Ticker(symbol.upper())
    data = yf_retry(
        lambda: ticker.history(start=start_date, end=_inclusive_history_end(end_date))
    )
    return normalize_ohlcv_frame(data, source="yfinance")
```

Also add `normalize_ohlcv_frame` to the existing import from `.market_snapshot`.

Modify `tradingagents/dataflows/akshare.py` after `_fetch_frame()`:

```python
def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return normalize_ohlcv_frame(_fetch_frame(symbol, start_date, end_date), source="akshare")
```

Also add `normalize_ohlcv_frame` to the existing import from `tradingagents.dataflows.market_snapshot`.

Modify `tradingagents/dataflows/futu.py` after `_fetch_frame()`:

```python
def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return normalize_ohlcv_frame(_fetch_frame(symbol, start_date, end_date), source="futu")
```

Also add `normalize_ohlcv_frame` to the existing import from `.market_snapshot`.

Modify `tradingagents/dataflows/polygon.py` after `_aggs_frame()`:

```python
def fetch_ohlcv_frame(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    return normalize_ohlcv_frame(_aggs_frame(symbol, start_date, end_date), source="polygon")
```

Also add `normalize_ohlcv_frame` to the existing import from `.market_snapshot`.

- [ ] **Step 4: Run raw fetch tests and verify they pass**

Run:

```bash
pytest tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/y_finance.py tradingagents/dataflows/akshare.py tradingagents/dataflows/futu.py tradingagents/dataflows/polygon.py tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py
git commit -m "feat(data): expose raw ohlcv fetchers for fusion"
```

---

### Task 4: Incremental Fallback Fetching For Missing Sessions

**Files:**
- Modify: `tradingagents/dataflows/market_fusion.py`
- Test: `tests/dataflows/test_market_fusion.py`

- [ ] **Step 1: Add failing tests for incremental vendor fallback**

Append to `tests/dataflows/test_market_fusion.py`:

```python
from tradingagents.dataflows.errors import DataVendorError
from tradingagents.dataflows.market_fusion import fetch_fused_market_snapshot


def test_fetch_fused_market_snapshot_fetches_missing_sessions_only():
    calls = []

    def yfinance_fetch(symbol, start_date, end_date):
        calls.append(("yfinance", start_date, end_date))
        return _frame(
            [
                {"timestamp": "2026-06-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
                {"timestamp": "2026-06-02", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 110},
                {"timestamp": "2026-06-05", "open": 14, "high": 15, "low": 13, "close": 14.5, "volume": 140},
            ]
        )

    def akshare_fetch(symbol, start_date, end_date):
        calls.append(("akshare", start_date, end_date))
        assert start_date == "2026-06-03"
        assert end_date == "2026-06-04"
        return _frame(
            [
                {"timestamp": "2026-06-03", "open": 12, "high": 13, "low": 11, "close": 12.5, "volume": 120},
                {"timestamp": "2026-06-04", "open": 13, "high": 14, "low": 12, "close": 13.5, "volume": 130},
            ]
        )

    snapshot = fetch_fused_market_snapshot(
        "AAPL",
        "2026-06-05",
        lookback_days=4,
        providers=["yfinance", "akshare"],
        fetchers={"yfinance": yfinance_fetch, "akshare": akshare_fetch},
    )

    assert snapshot.missing_sessions == []
    assert [bar.source for bar in snapshot.bars] == [
        "yfinance",
        "yfinance",
        "akshare",
        "akshare",
        "yfinance",
    ]
    assert calls == [
        ("yfinance", "2026-06-01", "2026-06-05"),
        ("akshare", "2026-06-03", "2026-06-04"),
    ]


def test_fetch_fused_market_snapshot_skips_weekends_and_fixed_holidays():
    calls = []

    def yfinance_fetch(symbol, start_date, end_date):
        calls.append((start_date, end_date))
        return _frame(
            [
                {"timestamp": "2026-12-24", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
            ]
        )

    snapshot = fetch_fused_market_snapshot(
        "AAPL",
        "2026-12-26",
        lookback_days=2,
        providers=["yfinance"],
        fetchers={"yfinance": yfinance_fetch},
    )

    assert snapshot.expected_sessions == ["2026-12-24"]
    assert snapshot.allowed_missing_sessions == ["2026-12-25", "2026-12-26"]
    assert snapshot.missing_sessions == []
    assert calls == [("2026-12-24", "2026-12-26")]


def test_fetch_fused_market_snapshot_continues_after_provider_error():
    def yfinance_fetch(symbol, start_date, end_date):
        raise DataVendorError("yfinance timeout")

    def akshare_fetch(symbol, start_date, end_date):
        return _frame(
            [
                {"timestamp": "2026-06-05", "open": 14, "high": 15, "low": 13, "close": 14.5, "volume": 140},
            ]
        )

    snapshot = fetch_fused_market_snapshot(
        "AAPL",
        "2026-06-05",
        lookback_days=0,
        providers=["yfinance", "akshare"],
        fetchers={"yfinance": yfinance_fetch, "akshare": akshare_fetch},
    )

    assert snapshot.missing_sessions == []
    assert snapshot.provider_errors["yfinance"] == "yfinance timeout"
    assert snapshot.bars[0].source == "akshare"
```

- [ ] **Step 2: Run incremental fallback tests and verify they fail**

Run:

```bash
pytest tests/dataflows/test_market_fusion.py -v
```

Expected: FAIL with `ImportError: cannot import name 'fetch_fused_market_snapshot'`.

- [ ] **Step 3: Implement incremental fetch orchestration**

Append to `tradingagents/dataflows/market_fusion.py`:

```python
from datetime import datetime
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows import akshare, futu, polygon, y_finance
from tradingagents.dataflows.errors import DataVendorError
from tradingagents.dataflows.market_calendar import (
    DEFAULT_FIXED_CLOSURE_DATES,
    expected_trading_sessions,
    is_allowed_market_closure,
)


DEFAULT_FETCHERS = {
    "yfinance": y_finance.fetch_ohlcv_frame,
    "akshare": akshare.fetch_ohlcv_frame,
    "futu": futu.fetch_ohlcv_frame,
    "polygon": polygon.fetch_ohlcv_frame,
}


def _missing_sessions(snapshot: FusedMarketSnapshot) -> list[str]:
    return list(snapshot.missing_sessions)


def _date_bounds(sessions: list[str]) -> tuple[str, str]:
    return min(sessions), max(sessions)


def _allowed_missing_sessions(start_date: str, end_date: str) -> list[str]:
    allowed = []
    for day in pd.date_range(pd.Timestamp(start_date), pd.Timestamp(end_date), freq="D"):
        if is_allowed_market_closure(day):
            allowed.append(day.strftime("%Y-%m-%d"))
    return allowed


def fetch_fused_market_snapshot(
    ticker: str,
    curr_date: str,
    *,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
    providers: list[str] | None = None,
    fetchers: dict[str, callable] | None = None,
) -> FusedMarketSnapshot:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - relativedelta(days=lookback_days)).strftime("%Y-%m-%d")
    expected = expected_trading_sessions(start_date, curr_date)
    allowed_missing = _allowed_missing_sessions(start_date, curr_date)
    provider_order = providers or ["yfinance", "akshare", "futu", "polygon"]
    fetcher_map = fetchers or DEFAULT_FETCHERS

    source_frames: list[tuple[str, pd.DataFrame]] = []
    provider_errors: dict[str, str] = {}
    remaining = list(expected)

    for provider in provider_order:
        if not remaining:
            break
        fetcher = fetcher_map.get(provider)
        if fetcher is None:
            provider_errors[provider] = "provider has no OHLCV fetcher"
            continue
        fetch_start, fetch_end = _date_bounds(remaining)
        try:
            frame = fetcher(ticker, fetch_start, fetch_end)
            source_frames.append((provider, frame))
        except DataVendorError as exc:
            provider_errors[provider] = str(exc)
            continue

        partial = fuse_source_frames(
            ticker=ticker,
            requested_date=curr_date,
            expected_sessions=expected,
            source_frames=source_frames,
            allowed_missing_sessions=allowed_missing,
            provider_errors=provider_errors,
            stale_after_seconds=stale_after_seconds,
        )
        remaining = _missing_sessions(partial)

    return fuse_source_frames(
        ticker=ticker,
        requested_date=curr_date,
        expected_sessions=expected,
        source_frames=source_frames,
        allowed_missing_sessions=allowed_missing,
        provider_errors=provider_errors,
        stale_after_seconds=stale_after_seconds,
    )


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    *,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
    providers: list[str] | None = None,
) -> str:
    snapshot = fetch_fused_market_snapshot(
        ticker,
        curr_date,
        lookback_days=lookback_days,
        stale_after_seconds=stale_after_seconds,
        providers=providers,
    )
    return format_fused_market_snapshot(snapshot)
```

- [ ] **Step 4: Run fusion tests and verify they pass**

Run:

```bash
pytest tests/dataflows/test_market_fusion.py tests/dataflows/test_market_calendar.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/market_fusion.py tests/dataflows/test_market_fusion.py
git commit -m "feat(data): fill missing market sessions from fallback vendors"
```

---

### Task 5: Route Existing Snapshot Tool Through Fusion Layer

**Files:**
- Modify: `tradingagents/dataflows/interface.py`
- Test: `tests/test_dataflows_config.py`
- Test: `tests/graph/test_market_snapshot_injection.py`

- [ ] **Step 1: Add failing interface routing test**

Append to `tests/test_dataflows_config.py`:

```python
def test_market_snapshot_route_uses_fusion_provider_order(monkeypatch):
    import tradingagents.dataflows.interface as iface

    calls = []

    def fake_fused_snapshot(ticker, curr_date, **kwargs):
        calls.append((ticker, curr_date, kwargs))
        return "# Market snapshot for AAPL\n\n## Fused OHLCV Chart\n"

    monkeypatch.setattr(iface, "get_fused_market_snapshot", fake_fused_snapshot)
    cfg = iface.get_config()
    cfg["data_vendors"]["market_snapshot"] = "yfinance, akshare, futu, polygon"
    iface.set_config(cfg)

    out = iface.route_to_vendor("get_market_snapshot", "AAPL", "2026-06-05")

    assert "## Fused OHLCV Chart" in out
    assert calls == [
        (
            "AAPL",
            "2026-06-05",
            {"providers": ["yfinance", "akshare", "futu", "polygon"]},
        )
    ]
```

- [ ] **Step 2: Run interface test and verify it fails**

Run:

```bash
pytest tests/test_dataflows_config.py::test_market_snapshot_route_uses_fusion_provider_order -v
```

Expected: FAIL with `AttributeError` for missing `get_fused_market_snapshot` on `interface`.

- [ ] **Step 3: Wire `get_market_snapshot` route to fusion**

Modify `tradingagents/dataflows/interface.py`.

Add this import near the existing imports:

```python
from .market_fusion import get_market_snapshot as get_fused_market_snapshot
```

Add this special case near the top of `route_to_vendor()` after `vendor_config` is resolved:

```python
    if method == "get_market_snapshot":
        providers = [v.strip() for v in vendor_config.split(",") if v.strip()]
        return get_fused_market_snapshot(*args, providers=providers, **kwargs)
```

Keep `VENDOR_METHODS["get_market_snapshot"]` intact during this task so existing tests that inspect the fallback map still have a stable registry, but the runtime route uses the fusion engine.

- [ ] **Step 4: Run interface and graph tests**

Run:

```bash
pytest tests/test_dataflows_config.py tests/graph/test_market_snapshot_injection.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/dataflows/interface.py tests/test_dataflows_config.py
git commit -m "feat(data): route market snapshots through fusion layer"
```

---

### Task 6: Preserve Investment-Team Visibility And Run Artifacts

**Files:**
- Modify: `tests/graph/test_market_snapshot_injection.py`
- Modify: `tests/graph/test_run_recorder.py`
- No production code change expected unless tests fail.

- [ ] **Step 1: Add graph visibility assertion**

Modify `tests/graph/test_market_snapshot_injection.py`, changing the fake route return in `test_graph_prefetches_market_snapshot()` to:

```python
        lambda method, ticker, trade_date, **kwargs: (
            "# Market snapshot for AAPL\n\n"
            "- Source: fused\n"
            "- Coverage: 5/5 expected sessions (100.00%)\n\n"
            "## Fused OHLCV Chart\n"
            "| date | open | high | low | close | volume | source |\n"
            "|---|---:|---:|---:|---:|---:|---|\n"
            "| 2026-06-05 | 14.0000 | 15.0000 | 13.0000 | 14.5000 | 140 | yfinance |\n"
        ),
```

Add this assertion at the end of the same test:

```python
    assert "## Fused OHLCV Chart" in final_state["market_snapshot_text"]
    assert "Coverage: 5/5 expected sessions" in final_state["market_snapshot_text"]
```

- [ ] **Step 2: Add recorder artifact assertion**

Modify `tests/graph/test_run_recorder.py` in `test_run_recorder_writes_market_snapshot_artifacts()` so `market_snapshot_text` is:

```python
            "market_snapshot_text": (
                "# Market snapshot for AAPL\n\n"
                "- Source: fused\n"
                "- Coverage: 5/5 expected sessions (100.00%)\n\n"
                "## Fused OHLCV Chart\n"
                "| date | open | high | low | close | volume | source |\n"
            ),
```

Replace the exact file-content assertion with:

```python
    snapshot_text = (run_path / "market_snapshot.md").read_text(encoding="utf-8")
    assert "## Fused OHLCV Chart" in snapshot_text
    assert "Coverage: 5/5 expected sessions" in snapshot_text
```

- [ ] **Step 3: Run graph/artifact tests**

Run:

```bash
pytest tests/graph/test_market_snapshot_injection.py tests/graph/test_run_recorder.py tests/analysis_pack/test_analysis_pack_builder.py -v
```

Expected: PASS. If this fails, fix only the production code needed to keep the fused Markdown text in `market_snapshot_text` and persisted as `market_snapshot.md`.

- [ ] **Step 4: Commit**

```bash
git add tests/graph/test_market_snapshot_injection.py tests/graph/test_run_recorder.py
git commit -m "test(graph): assert fused chart reaches analyst artifacts"
```

---

### Task 7: Documentation And Final Verification

**Files:**
- Modify: `README.md`
- Optional modify: `docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md`

- [ ] **Step 1: Update README market freshness section**

In `README.md`, replace the current "Market Data Freshness" section with:

```markdown
### Market Data Freshness

Full studies pre-fetch a numerical market snapshot before the TradingAgents
graph runs, then pass it into the market analyst and persist it with the run
artifacts. The default provider order is:

```text
yfinance -> AKShare -> Futu OpenD -> Polygon
```

`yfinance` remains the primary numerical data source. The market snapshot layer
now validates expected trading sessions, skips weekends and a simple whitelist
of fixed-date closures (`01-01`, `05-01`, `06-19`, `07-04`, `10-01`, `12-25`),
and fetches missing sessions from fallback providers. The resulting chart is
one fused OHLCV table with a `source` column for row-level provenance.

This holiday filter is intentionally approximate: it avoids common fixed-date
closures and weekends, but it does not model every exchange-specific or
observed holiday. Same-day OHLCV cache files refresh after
`market_data_cache_ttl_seconds`; past-date cache files are reused to keep
historical runs reproducible.
```

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/dataflows/test_market_calendar.py tests/dataflows/test_market_fusion.py tests/dataflows/test_market_snapshot.py tests/dataflows/test_yfinance_freshness.py tests/dataflows/test_akshare_vendor.py tests/dataflows/test_futu_vendor.py tests/dataflows/test_polygon_vendor.py tests/test_dataflows_config.py -v
```

Expected: PASS.

- [ ] **Step 3: Run graph/artifact verification**

Run:

```bash
pytest tests/graph/test_market_snapshot_injection.py tests/graph/test_run_recorder.py tests/analysis_pack/test_analysis_pack_builder.py tests/test_default_config_f1.py -v
```

Expected: PASS.

- [ ] **Step 4: Run prompt/symbol safety verification**

Run:

```bash
pytest tests/test_ticker_symbol_handling.py tests/dataflows/test_prompt_determinism.py tests/test_safe_ticker_component.py -v
```

Expected: PASS.

- [ ] **Step 5: Run broader unit verification with known local dependency note**

Run:

```bash
pytest -m unit -v
```

Expected: PASS if `tweepy` is installed. If it fails only in `tests/sensing/test_adapter_x.py` with `ModuleNotFoundError: No module named 'tweepy'`, record it as an unrelated local optional-dependency gap and run:

```bash
pytest -m unit --ignore=tests/sensing/test_adapter_x.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit docs**

```bash
git add README.md docs/superpowers/specs/2026-06-03-iic-forge-f4-f5-persona-cost-redesign.md
git commit -m "docs(data): describe fused market data chart"
```

---

## Self-Review

- Spec coverage:
  - Detects missingness: Task 2 and Task 4 tests validate missing expected sessions.
  - Automatically falls back: Task 4 tests prove missing sessions are fetched from the next provider.
  - Combines multiple sources into one chart: Task 2 formatter and Task 6 graph/artifact assertions prove one fused chart reaches the investment team and persisted artifacts.
  - Avoids holidays/weekends: Task 1 and Task 4 tests prove weekends and fixed-date whitelist closures do not count as missing.
  - Keeps existing graph/tool contract: Task 5 routes existing `get_market_snapshot` through fusion without changing market analyst or graph callers.

- Placeholder scan:
  - No implementation step uses TBD/TODO/fill-in language.
  - Each new test contains concrete code.
  - Each code-changing task includes exact target files and commands.

- Type consistency:
  - `FusedMarketBar`, `FusedMarketSnapshot`, `fuse_source_frames`, `fetch_fused_market_snapshot`, and `format_fused_market_snapshot` use the same names across tasks.
  - Vendor raw fetcher name is consistently `fetch_ohlcv_frame(symbol, start_date, end_date)`.
  - Interface import is consistently aliased as `get_fused_market_snapshot`.

