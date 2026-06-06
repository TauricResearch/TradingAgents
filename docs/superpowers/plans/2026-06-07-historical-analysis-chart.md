# Historical Analysis Chart — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a right-side `HistoricalAnalysisDrawer` to the dashboard that visualizes every past run for a focused ticker on a single recharts price chart, evaluates per-run verdicts (BUY/SELL/HOLD with optional target) against a user-controlled Δ window, and aggregates per-action stats that update live as the user sweeps Δ and the HOLD threshold.

**Architecture:** New backend module `web/server/history.py` wraps yfinance with an in-memory TTL cache and exposes `GET /api/tickers/{t}/history?range=<preset>`. New frontend drawer fetches that endpoint, holds bars + runs in memory, and runs a pure TypeScript verdict function (`src/verdicts.ts`) on every Δ/threshold change. Existing `RunHistoryDrawer` is replaced by the enhanced `HistoricalAnalysisDrawer`. A configurable TanStack Query refetch interval (default 30s) keeps the chart and active run's band live.

**Tech Stack:** FastAPI (existing) + yfinance (existing, new usage) + react-query 5 (existing) + zustand (existing) + recharts (new) + vitest + @testing-library/react (existing).

---

## File Structure

### Backend
- `web/server/history.py` — **new** — `resolve_range`, `fetch_history_bars` (with in-memory TTL cache), `get_history` orchestrator, module-level `_bar_cache` dict.
- `web/server/app.py` — **modify** — register `GET /api/tickers/{ticker}/history`.
- `web/server/tests/fixtures/fake_yfinance.py` — **extend** — add `make_fake_ticker_with_history()` and `make_history_df()` helpers.
- `web/server/tests/test_history.py` — **new** — unit tests for `history.py`.
- `web/server/tests/test_app.py` — **extend** — add `TestHistoryEndpoint` class with integration tests.

### Frontend
- `web/frontend/package.json` — **modify** — add `recharts` dependency.
- `web/frontend/src/verdicts.ts` — **new** — pure functions: `barsInWindow`, `computeVerdict`, `computeStats`, plus `actionColor` / `actionTint` / `Verdict` / `Stats` / `Bar` types. Zero React imports.
- `web/frontend/src/verdicts.test.ts` — **new** — vitest unit tests.
- `web/frontend/src/lib/api.ts` — **extend** — add `Bar`, `HistoryResponse` types and `getTickerHistory` helper.
- `web/frontend/src/lib/format.ts` — **extend** — add `fmtDelta`, `fmtPrice`, `fmtPct`, `fmtTime` helpers.
- `web/frontend/src/store/ui.ts` — **extend** — add `historyOpenByTicker` + `setHistoryOpen`, `holdThresholdPct` + setter, `historyPollIntervalMs` + setter; update `partialize` to persist the last two.
- `web/frontend/src/components/HistoryChart.tsx` — **new** — recharts wrapper (pure presentational; receives all data via props).
- `web/frontend/src/components/HistoryChart.test.tsx` — **new** — component test (vitest + @testing-library/react).
- `web/frontend/src/components/HistoryStats.tsx` — **new** — stats card (pure).
- `web/frontend/src/components/HistoryControls.tsx` — **new** — Δ slider, HOLD% slider, refresh interval dropdown.
- `web/frontend/src/components/RunListItem.tsx` — **new** — single run row with action badge, target, verdict, pct move.
- `web/frontend/src/components/HistoricalAnalysisDrawer.tsx` — **new** — top-level right-side drawer; owns the query and the local Δ + range state.
- `web/frontend/src/components/RunHistoryDrawer.tsx` — **delete** — replaced by `HistoricalAnalysisDrawer`.
- `web/frontend/src/App.tsx` — **modify** — swap import + JSX usage.

### Docs
- `docs/superpowers/specs/2026-06-07-historical-analysis-chart-design.md` — existing spec, no change.

---

## Task Index

**Phase 1 — Backend**
- Task 1: `resolve_range` (TDD)
- Task 2: `fetch_history_bars` with TTL cache (TDD)
- Task 3: `get_history` orchestrator with 404/422/502 handling (TDD)
- Task 4: Register `GET /api/tickers/{ticker}/history` route
- Task 5: Extend `fake_yfinance.py` with `make_fake_ticker_with_history()` and `make_history_df()` helpers
- Task 6: Add `TestHistoryEndpoint` integration tests

**Phase 2 — Frontend foundation**
- Task 7: Add `recharts` dependency
- Task 8: Extend `format.ts` with `fmtDelta`, `fmtPrice`, `fmtPct`, `fmtTime`
- Task 9: Extend `lib/api.ts` with `Bar`, `HistoryResponse`, `getTickerHistory`
- Task 10: Extend `store/ui.ts` with history state + persistence
- Task 11: `verdicts.ts` types + `barsInWindow` (TDD)
- Task 12: `computeVerdict` (TDD)
- Task 13: `computeStats` (TDD)

**Phase 3 — Frontend components**
- Task 14: `HistoryStats.tsx`
- Task 15: `HistoryControls.tsx`
- Task 16: `RunListItem.tsx`
- Task 17: `HistoryChart.tsx` (TDD: component test)
- Task 18: `HistoricalAnalysisDrawer.tsx`

**Phase 4 — Wire-up + cleanup**
- Task 19: Swap drawer in `App.tsx`
- Task 20: Delete `RunHistoryDrawer.tsx`
- Task 21: Final lint + build + manual integration checklist

## Task 1: `resolve_range` in `web/server/history.py` (TDD)

**Files:**
- Create: `web/server/history.py`
- Create: `web/server/tests/test_history.py`

- [ ] **Step 1: Write the failing tests for `resolve_range`**

Create `web/server/tests/test_history.py` with:

```python
"""Unit tests for web.server.history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from web.server import history


_NOW = datetime(2026, 6, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixed_now(monkeypatch):
    """Pin history.now_utc() to a fixed instant so the resolver is deterministic."""
    monkeypatch.setattr(history, "now_utc", lambda: _NOW)


def test_resolve_range_1d_returns_one_day_window_at_1m(fixed_now):
    start, end, interval = history.resolve_range("1d", earliest_started_at=None)
    assert interval == "1m"
    assert end == _NOW
    assert start == _NOW - timedelta(days=1)


def test_resolve_range_5d_returns_five_day_window_at_1m(fixed_now):
    _, _, interval = history.resolve_range("5d", earliest_started_at=None)
    assert interval == "1m"


def test_resolve_range_1mo_returns_thirty_day_window_at_1h(fixed_now):
    _, _, interval = history.resolve_range("1mo", earliest_started_at=None)
    assert interval == "1h"  # 30d > 7d → 1h


def test_resolve_range_3mo_returns_ninety_day_window_at_1d(fixed_now):
    _, _, interval = history.resolve_range("3mo", earliest_started_at=None)
    assert interval == "1d"  # 90d > 60d → 1d


def test_resolve_range_all_caps_at_one_year_at_1d(fixed_now):
    _, _, interval = history.resolve_range("all", earliest_started_at=None)
    assert interval == "1d"


def test_resolve_range_auto_uses_earliest_run_started_at(fixed_now):
    earliest = _NOW - timedelta(days=12)
    start, end, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert start == earliest
    assert end == _NOW
    assert interval == "1h"  # 12d → 1h


def test_resolve_range_auto_with_no_runs_raises(fixed_now):
    with pytest.raises(ValueError, match="no runs"):
        history.resolve_range("auto", earliest_started_at=None)


def test_resolve_range_invalid_preset_raises(fixed_now):
    with pytest.raises(ValueError, match="invalid preset"):
        history.resolve_range("bogus", earliest_started_at=None)


def test_resolve_range_seven_day_span_still_picks_1m(fixed_now):
    earliest = _NOW - timedelta(days=7)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1m"


def test_resolve_range_sixty_day_span_picks_1h(fixed_now):
    earliest = _NOW - timedelta(days=60)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1h"
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -v
```

Expected: `ModuleNotFoundError: No module named 'web.server.history'`.

- [ ] **Step 3: Write `web/server/history.py` with `resolve_range`**

Create `web/server/history.py`:

```python
"""Yfinance-backed historical price bars for the dashboard's chart feature.

Wraps ``yf.Ticker.history`` with an in-memory TTL cache and exposes
range resolution (preset → start/end/interval). The HTTP layer in
:mod:`web.server.app` is a thin adapter around :func:`get_history`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import yfinance as yf


log = logging.getLogger(__name__)


#: Window size for each preset. "all" is the 1y cap per the spec.
_PRESET_WINDOWS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "5d": timedelta(days=5),
    "1mo": timedelta(days=30),
    "3mo": timedelta(days=90),
    "6mo": timedelta(days=180),
    "1y": timedelta(days=365),
    "all": timedelta(days=365),
}


def now_utc() -> datetime:
    """Pluggable clock for tests."""
    return datetime.now(timezone.utc)


def resolve_range(
    preset: str,
    *,
    earliest_started_at: Optional[datetime],
) -> tuple[datetime, datetime, str]:
    """Translate a user preset into a concrete (start, end, interval).

    Args:
        preset: One of ``{1d, 5d, 1mo, 3mo, 6mo, 1y, all, auto}``.
        earliest_started_at: The earliest run's ``started_at`` for
            ``preset="auto"``. ``None`` for all other presets. Required
            for ``auto`` — the function raises :class:`ValueError` if
            missing.

    Returns:
        ``(start, end, interval)`` where ``interval`` is one of
        ``{"1m", "1h", "1d"}`` chosen by the span between start and end.

    Raises:
        ValueError: on an unknown preset, or on ``auto`` with no runs.
    """
    if preset == "auto":
        if earliest_started_at is None:
            raise ValueError("auto preset requires earliest_started_at (no runs)")
        start = earliest_started_at
        end = now_utc()
    else:
        if preset not in _PRESET_WINDOWS:
            raise ValueError(f"invalid preset: {preset!r}")
        end = now_utc()
        start = end - _PRESET_WINDOWS[preset]

    interval = _interval_for_span(end - start)
    return start, end, interval


def _interval_for_span(span: timedelta) -> str:
    """Pick the yfinance interval that fits the span without oversampling.

    ≤ 7d → 1m   (highest resolution; 1m is fresh for 7 days)
    ≤ 60d → 1h  (1m caps at 7d; 1h caps at 730d)
    > 60d → 1d  (1h is wasteful; 1d is fine for multi-month views)
    """
    if span <= timedelta(days=7):
        return "1m"
    if span <= timedelta(days=60):
        return "1h"
    return "1d"
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -v
```

Expected: all 10 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/history.py web/server/tests/test_history.py
git commit -m "feat(history): add resolve_range for chart preset→(start,end,interval)"
```

---

## Task 2: `fetch_history_bars` with TTL cache (TDD)

**Files:**
- Modify: `web/server/history.py`
- Modify: `web/server/tests/test_history.py`

- [ ] **Step 1: Add the failing tests for `fetch_history_bars` and the cache**

Append to `web/server/tests/test_history.py`:

```python
import pandas as pd
import yfinance as yf


# ---- fetch_history_bars ----


def _bar_df(start: datetime, n: int, *, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a tz-aware UTC DatetimeIndex."""
    idx = pd.date_range(start=start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open":  [base + i * step for i in range(n)],
            "High":  [base + i * step + 0.1 for i in range(n)],
            "Low":   [base + i * step - 0.1 for i in range(n)],
            "Close": [base + i * step for i in range(n)],
            "Volume": [1000.0 for _ in range(n)],
        },
        index=idx,
    )


class _CountingTicker:
    """Stand-in for ``yf.Ticker`` that records call count and returns a fixed DataFrame."""

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self.calls = 0

    def history(self, **kwargs):
        self.calls += 1
        return self._df


@pytest.fixture
def counting_ticker(monkeypatch):
    """Patch ``yf.Ticker`` to a class that records ``.history`` invocations."""
    df = _bar_df(_NOW - timedelta(hours=24), 24)
    ticker = _CountingTicker(df)
    monkeypatch.setattr(yf, "Ticker", lambda _t: ticker)
    return ticker


def test_fetch_history_bars_calls_yf_with_resolved_window(fixed_now, counting_ticker):
    bars = history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert isinstance(bars, list)
    assert len(bars) == 24
    assert all(set(b.keys()) == {"t", "o", "h", "l", "c", "v"} for b in bars)
    # Timestamps are ISO with Z suffix and sorted ascending.
    assert all(bars[i]["t"] < bars[i + 1]["t"] for i in range(len(bars) - 1))
    assert all(b["t"].endswith("Z") for b in bars)


def test_fetch_history_bars_cache_hit_avoids_second_yf_call(fixed_now, counting_ticker):
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 1


def test_fetch_history_bars_cache_key_includes_ticker(fixed_now, monkeypatch):
    """Two tickers with the same window must NOT share a cache entry."""
    history._bar_cache.clear()
    a = _CountingTicker(_bar_df(_NOW - timedelta(hours=2), 2))
    b = _CountingTicker(_bar_df(_NOW - timedelta(hours=2), 2))
    queue = iter([a, b])

    def _pick(_t):
        return next(queue)

    monkeypatch.setattr(yf, "Ticker", _pick)
    history.fetch_history_bars("AAA", start=None, end=None, interval="1h")
    history.fetch_history_bars("BBB", start=None, end=None, interval="1h")
    assert a.calls == 1 and b.calls == 1
    assert len(history._bar_cache) == 2


def test_fetch_history_bars_cache_respects_ttl(fixed_now, counting_ticker, monkeypatch):
    """An entry past its TTL must be re-fetched (1h resolution → 300s TTL)."""
    fake_now = [_NOW.timestamp()]
    monkeypatch.setattr(history.time, "monotonic", lambda: fake_now[0])
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 1
    fake_now[0] += 600  # past 5-min TTL
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 2


def test_fetch_history_bars_returns_empty_list_for_empty_dataframe(fixed_now, monkeypatch):
    empty = _CountingTicker(pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]))
    monkeypatch.setattr(yf, "Ticker", lambda _t: empty)
    bars = history.fetch_history_bars("DEAD", start=None, end=None, interval="1d")
    assert bars == []
```

- [ ] **Step 2: Run new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -k "fetch_history_bars" -v
```

Expected: `AttributeError: module 'web.server.history' has no attribute 'fetch_history_bars'`.

- [ ] **Step 3: Implement `fetch_history_bars` + cache**

Append to `web/server/history.py`:

```python
# ---- cache ----

#: Key ``(ticker_upper, interval, start.date(), end.date())``.
#: Value ``(fetched_at_monotonic, bars)``.
_bar_cache: dict[tuple[str, str, object, object], tuple[float, list[dict]]] = {}

#: TTL by interval. 1m polls are short; 1d polls are long.
_CACHE_TTL_S: dict[str, int] = {
    "1m": 60,
    "1h": 300,
    "1d": 3600,
}


def fetch_history_bars(
    ticker: str,
    *,
    start: Optional[datetime],
    end: Optional[datetime],
    interval: str,
) -> list[dict]:
    """Return OHLCV bars for ``ticker`` between ``start`` and ``end``.

    Caches the result in process memory keyed by
    ``(ticker, interval, start.date(), end.date())`` with a TTL that
    depends on the interval. ``start``/``end`` are resolved by the
    caller (typically :func:`resolve_range`); passing ``None`` is
    allowed but uses epoch / now as the implicit bounds, which usually
    is not what you want.

    Returns a list of ``Bar`` dicts (the JSON shape the API serialises).
    An empty DataFrame yields ``[]`` (not an error).
    """
    if end is None:
        end = now_utc()
    if start is None:
        start = end - timedelta(days=365)

    key = (ticker.upper(), interval, start.date(), end.date())
    now_mono = time.monotonic()
    ttl = _CACHE_TTL_S.get(interval, 60)
    cached = _bar_cache.get(key)
    if cached is not None:
        fetched_at, bars = cached
        if now_mono - fetched_at < ttl:
            return bars

    df = yf.Ticker(ticker.upper()).history(
        start=start, end=end, interval=interval, auto_adjust=False,
    )
    bars = _df_to_bars(df)
    _bar_cache[key] = (now_mono, bars)
    return bars


def _df_to_bars(df) -> list[dict]:
    """Convert a yfinance DataFrame to the API's Bar JSON shape.

    Empty DataFrame → []. Index is normalised to UTC; rows are returned
    in index order (ascending).
    """
    if df is None or len(df) == 0:
        return []
    idx = df.index
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert("UTC")
    elif hasattr(idx, "tz_localize"):
        idx = idx.tz_localize("UTC")
    ts_iso = [t.isoformat().replace("+00:00", "Z") for t in idx]
    if "Volume" in df.columns:
        volumes = df["Volume"].tolist()
    else:
        volumes = [0.0] * len(df)
    return [
        {"t": t, "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": float(v)}
        for t, o, h, l, c, v in zip(
            ts_iso, df["Open"].tolist(), df["High"].tolist(),
            df["Low"].tolist(), df["Close"].tolist(), volumes,
        )
    ]
```

- [ ] **Step 4: Run the new tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -k "fetch_history_bars" -v
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/history.py web/server/tests/test_history.py
git commit -m "feat(history): add fetch_history_bars with TTL cache"
```

---

## Task 3: `get_history` orchestrator (TDD)

**Files:**
- Modify: `web/server/history.py`
- Modify: `web/server/tests/test_history.py`

- [ ] **Step 1: Add the failing tests for `get_history`**

Append to `web/server/tests/test_history.py`:

```python
from web.server import storage


# ---- get_history ----


def test_get_history_404_when_ticker_has_no_runs(fixed_now, data_root):
    out = history.get_history("ZZZZ", preset="auto")
    assert out == (404, {"error": "no_runs", "detail": "ZZZZ has no completed runs"})


def test_get_history_422_for_invalid_preset(fixed_now, data_root):
    out = history.get_history("MU", preset="bogus")
    assert out[0] == 422
    assert out[1]["error"] == "invalid_range"
    assert "bogus" in out[1]["detail"]


def test_get_history_502_when_yfinance_raises(fixed_now, data_root, monkeypatch):
    rid = storage.create_run_dir("MU")["run_id"]
    storage.mark_run_status(
        rid, status="done", started_at="2026-05-01T00:00:00Z", finished_at="2026-05-01T00:01:00Z",
        decision_action="BUY", decision_target=200.0,
    )
    def _raise(**kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(history, "fetch_history_bars", _raise)
    out = history.get_history("MU", preset="1mo")
    assert out[0] == 502
    assert out[1]["error"] == "yfinance_failed"
    assert "network down" in out[1]["detail"]


def test_get_history_returns_200_with_bars_and_runs(fixed_now, data_root, monkeypatch):
    """Happy path: ticker has a run, yfinance returns bars, response is shaped."""
    rid = storage.create_run_dir("MU")["run_id"]
    storage.mark_run_status(
        rid, status="done", started_at="2026-06-06T00:00:00Z", finished_at="2026-06-06T00:01:00Z",
        decision_action="BUY", decision_target=160.0, start_price=148.20,
        start_price_at="2026-06-06T00:00:00Z",
    )
    monkeypatch.setattr(
        history, "fetch_history_bars",
        lambda **_kw: _bar_df(_NOW - timedelta(days=2), 48, base=148.0, step=0.25),
    )
    status, body = history.get_history("MU", preset="5d")
    assert status == 200
    assert body["ticker"] == "MU"
    assert body["range"] == "5d"
    assert body["resolution"] == "1m"
    assert len(body["bars"]) == 48
    assert all(set(b) == {"t", "o", "h", "l", "c", "v"} for b in body["bars"])
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["id"] == rid
    assert run["decision_action"] == "BUY"
    assert run["decision_target"] == 160.0
    assert run["start_price"] == 148.20


def test_get_history_returns_empty_bars_array_on_empty_yfinance(fixed_now, data_root, monkeypatch):
    rid = storage.create_run_dir("MU")["run_id"]
    storage.mark_run_status(
        rid, status="done", started_at="2026-06-06T00:00:00Z", finished_at="2026-06-06T00:01:00Z",
    )
    monkeypatch.setattr(history, "fetch_history_bars", lambda **_kw: [])
    status, body = history.get_history("MU", preset="5d")
    assert status == 200
    assert body["bars"] == []
    assert body["resolution"] == "1m"
```

- [ ] **Step 2: Run the new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -k "get_history" -v
```

Expected: `AttributeError: module 'web.server.history' has no attribute 'get_history'`.

- [ ] **Step 3: Implement `get_history`**

Append to `web/server/history.py`:

```python
from web.server import queries, storage as _storage


def get_history(ticker: str, preset: str) -> tuple[int, object]:
    """Orchestrator: resolve the range, fetch bars, and load runs.

    Returns ``(status_code, body)`` where ``body`` is either an error
    envelope ``{"error": str, "detail": str}`` (status 404/422/502) or
    the success body from the spec's API section.

    Does not raise — converts yfinance failures and bad input into
    structured responses so the FastAPI layer can forward them.
    """
    safe = ticker.upper()

    # 1. Load runs. A ticker with zero completed runs → 404.
    rows = _storage.list_ticker_runs(safe, limit=500)
    if not rows:
        return 404, {"error": "no_runs", "detail": f"{safe} has no completed runs"}

    # 2. Resolve the range. Unknown preset → 422.
    earliest = None
    for r in rows:
        s = r.get("started_at")
        if not s:
            continue
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            continue
        if earliest is None or dt < earliest:
            earliest = dt
    try:
        start, end, interval = resolve_range(preset, earliest_started_at=earliest)
    except ValueError as exc:
        return 422, {"error": "invalid_range", "detail": str(exc)}

    # 3. Fetch bars. yfinance failures → 502.
    try:
        bars = fetch_history_bars(safe, start=start, end=end, interval=interval)
    except Exception as exc:  # noqa: BLE001 — yfinance raises a zoo of types
        log.warning("yfinance failed for %s: %s", safe, exc)
        return 502, {"error": "yfinance_failed", "detail": str(exc)}

    # 4. Shape runs for the response. Use the existing helper so the
    #    shape matches GET /api/runs/{id} (events, llm_calls, stages).
    runs_out = [queries.run_to_dict(r) for r in rows]

    body = {
        "ticker": safe,
        "range": preset,
        "range_start": start.isoformat().replace("+00:00", "Z"),
        "range_end": end.isoformat().replace("+00:00", "Z"),
        "resolution": interval,
        "bars": bars,
        "runs": runs_out,
    }
    return 200, body
```

- [ ] **Step 4: Run the new tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_history.py -k "get_history" -v
```

Expected: all 5 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/history.py web/server/tests/test_history.py
git commit -m "feat(history): add get_history orchestrator with 404/422/502 envelopes"
```

---

## Task 4: Register the route in `web/server/app.py`

**Files:**
- Modify: `web/server/app.py`

- [ ] **Step 1: Add the route**

In `web/server/app.py`, immediately after the `list_ticker_runs` route (around line 188), add:

```python
    @app.get("/api/tickers/{ticker}/history")
    def get_ticker_history(ticker: str, range: str = "auto") -> dict:
        from . import history as _history
        from fastapi import HTTPException
        status, body = _history.get_history(ticker, range)
        if status != 200:
            # Body is a {"error","detail"} envelope; forward as 4xx/5xx
            # with the same shape used by the rest of the API.
            raise HTTPException(status_code=status, detail=body)
        return body
```

The `from . import history` is a deferred import so yfinance (which pulls in pandas) isn't loaded at module-import time.

- [ ] **Step 2: Smoke-check the route file compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -c "from web.server.app import create_app; print('ok')"
```

Expected: prints `ok`. (Pre-existing LSP errors in `runner.py` / `test_runner.py` are unrelated and out of scope.)

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/app.py
git commit -m "feat(app): register GET /api/tickers/{ticker}/history route"
```

---

## Task 5: Extend `fake_yfinance.py` with a history fixture

**Files:**
- Modify: `web/server/tests/fixtures/fake_yfinance.py`

- [ ] **Step 1: Add the `make_fake_ticker_with_history` factory and `make_history_df` helper**

Append to `web/server/tests/fixtures/fake_yfinance.py`:

```python
import pandas as pd


def make_fake_ticker_with_history(df: pd.DataFrame) -> type:
    """Return a stand-in for ``yf.Ticker`` whose ``.history()`` returns ``df``.

    The class records every ``.history`` call on ``.calls`` so cache-hit
    assertions can count yfinance invocations.
    """

    class _FakeTicker:
        calls = 0

        def history(self, **kwargs):
            type(self).calls += 1
            return df

    return _FakeTicker


def make_history_df(
    start,  # datetime (stringified to keep this file stdlib-friendly)
    n: int,
    *,
    base: float = 100.0,
    step: float = 0.5,
    freq: str = "1h",
) -> pd.DataFrame:
    """Build a deterministic OHLCV DataFrame starting at ``start`` with ``n`` rows.

    Columns: Open, High, Low, Close, Volume. Index: tz-aware UTC
    ``DatetimeIndex`` with the given ``freq``.
    """
    idx = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "Open":  [base + i * step for i in range(n)],
            "High":  [base + i * step + 0.1 for i in range(n)],
            "Low":   [base + i * step - 0.1 for i in range(n)],
            "Close": [base + i * step for i in range(n)],
            "Volume": [1000.0 for _ in range(n)],
        },
        index=idx,
    )
```

- [ ] **Step 2: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/fixtures/fake_yfinance.py
git commit -m "test(fixtures): add fake yfinance history factory and history-df builder"
```

---

## Task 6: Integration tests in `test_app.py`

**Files:**
- Modify: `web/server/tests/test_app.py`

- [ ] **Step 1: Add `TestHistoryEndpoint` to `test_app.py`**

Append to `web/server/tests/test_app.py`:

```python
class TestHistoryEndpoint:
    """GET /api/tickers/{ticker}/history. Powers the historical chart drawer."""

    def test_history_200_returns_bars_and_runs(self, client, data_root, monkeypatch):
        from datetime import datetime, timezone
        from web.server.tests.fixtures.fake_yfinance import (
            make_fake_ticker_with_history, make_history_df,
        )
        import yfinance as _yf

        rid = storage.create_run_dir("MU")["run_id"]
        storage.mark_run_status(
            rid, status="done",
            started_at="2026-06-06T00:00:00Z",
            finished_at="2026-06-06T00:01:00Z",
            decision_action="BUY",
            decision_target=160.0,
            start_price=148.20,
            start_price_at="2026-06-06T00:00:00Z",
        )
        df = make_history_df(
            start=datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc),
            n=48, base=148.0, step=0.25, freq="1h",
        )
        FakeTicker = make_fake_ticker_with_history(df)
        monkeypatch.setattr(_yf, "Ticker", lambda _t: FakeTicker())

        r = client.get("/api/tickers/MU/history?range=5d")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "MU"
        assert body["range"] == "5d"
        assert body["resolution"] in {"1m", "1h"}  # depends on now() wall clock
        assert len(body["bars"]) == 48
        assert all(set(b) == {"t", "o", "h", "l", "c", "v"} for b in body["bars"])
        assert len(body["runs"]) == 1
        run = body["runs"][0]
        assert run["id"] == rid
        assert run["decision_action"] == "BUY"
        assert run["decision_target"] == 160.0
        assert run["start_price"] == 148.20

    def test_history_404_when_ticker_has_no_runs(self, client):
        r = client.get("/api/tickers/ZZZZ/history?range=auto")
        assert r.status_code == 404
        body = r.json()["detail"]
        assert body["error"] == "no_runs"

    def test_history_422_for_invalid_range(self, client, data_root):
        storage.create_run_dir("MU")
        r = client.get("/api/tickers/MU/history?range=bogus")
        assert r.status_code == 422
        body = r.json()["detail"]
        assert body["error"] == "invalid_range"
        assert "bogus" in body["detail"]

    def test_history_502_when_yfinance_raises(self, client, data_root, monkeypatch):
        from web.server import history
        rid = storage.create_run_dir("MU")["run_id"]
        storage.mark_run_status(
            rid, status="done", started_at="2026-06-06T00:00:00Z", finished_at="2026-06-06T00:01:00Z",
        )
        def _raise(**_kw):
            raise RuntimeError("network unreachable")
        monkeypatch.setattr(history, "fetch_history_bars", _raise)
        r = client.get("/api/tickers/MU/history?range=5d")
        assert r.status_code == 502
        body = r.json()["detail"]
        assert body["error"] == "yfinance_failed"
        assert "network unreachable" in body["detail"]

    def test_history_default_range_is_auto(self, client, data_root, monkeypatch):
        from datetime import datetime, timezone
        from web.server.tests.fixtures.fake_yfinance import (
            make_fake_ticker_with_history, make_history_df,
        )
        import yfinance as _yf

        rid = storage.create_run_dir("MU")["run_id"]
        storage.mark_run_status(
            rid, status="done", started_at="2026-06-06T00:00:00Z", finished_at="2026-06-06T00:01:00Z",
        )
        df = make_history_df(
            start=datetime(2026, 6, 6, 0, 0, tzinfo=timezone.utc),
            n=4, base=148.0, freq="1h",
        )
        FakeTicker = make_fake_ticker_with_history(df)
        monkeypatch.setattr(_yf, "Ticker", lambda _t: FakeTicker())

        r = client.get("/api/tickers/MU/history")
        assert r.status_code == 200
        assert r.json()["range"] == "auto"
```

- [ ] **Step 2: Run the new tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/test_app.py::TestHistoryEndpoint -v
```

Expected: all 5 pass.

- [ ] **Step 3: Run the full backend suite, confirm nothing broke**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/ -v
```

Expected: all pre-existing tests still pass; the 5 new ones are added on top.

- [ ] **Step 4: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/test_app.py
git commit -m "test(app): add integration tests for /api/tickers/{t}/history"
```

---

## Task 7: Add `recharts` dependency

**Files:**
- Modify: `web/frontend/package.json`
- Modify: `web/frontend/package-lock.json` (auto-generated)

- [ ] **Step 1: Install recharts**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npm install recharts@^2.15.0 --save
```

Expected: `package.json` gets `"recharts": "^2.15.0"` in `dependencies`; `package-lock.json` is updated. If `npm` reports peer-dep issues with React 19, switch to the `--legacy-peer-deps` flag and document it in the commit message.

- [ ] **Step 2: Verify the install**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
node -e "import('recharts').then(m => console.log(Object.keys(m).slice(0, 5)))"
```

Expected: prints the first 5 recharts exports (e.g. `['LineChart', 'Line', 'XAxis', 'YAxis', 'ReferenceArea']`).

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/package.json web/frontend/package-lock.json
git commit -m "chore(deps): add recharts for historical analysis chart"
```

---

## Task 8: Extend `format.ts` with new helpers

**Files:**
- Modify: `web/frontend/src/lib/format.ts`

- [ ] **Step 1: Append the four formatters**

Append to `web/frontend/src/lib/format.ts` (after the existing `formatDuration` function):

```ts
/** Snap a Δ value to the nearest "named" horizon and format it. */
export function fmtDelta(deltaMs: number): string {
  const min = 5 * 60_000;
  const hour = 60 * 60_000;
  const day = 24 * hour;
  if (deltaMs < hour) return `${Math.max(1, Math.round(deltaMs / min))}m`;
  if (deltaMs < day) {
    const h = Math.round(deltaMs / hour);
    return `${h}h`;
  }
  const d = Math.round(deltaMs / day);
  return `${d}d`;
}

/** Format a price for axis tick labels: 2 decimals, no $ sign. */
export function fmtPrice(p: number): string {
  if (p == null || Number.isNaN(p)) return "—";
  return p.toFixed(2);
}

/** Format a signed percentage with a leading sign and 1 decimal. */
export function fmtPct(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return "—";
  const s = p.toFixed(1);
  return p > 0 ? `+${s}%` : `${s}%`;
}

/** Format an ms timestamp for a chart x-axis tick.
 *
 *  ``scale`` controls the granularity:
 *    "m"  (≤ 1d)  → "HH:MM"
 *    "h"  (≤ 60d) → "MMM d HH:MM"
 *    "d"  (> 60d) → "MMM d"
 */
export function fmtTime(ms: number, scale: "m" | "h" | "d"): string {
  const d = new Date(ms);
  if (scale === "d") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  if (scale === "h") {
    const date = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${date} ${time}`;
  }
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}
```

- [ ] **Step 2: Verify the TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/lib/format.ts
git commit -m "feat(format): add fmtDelta, fmtPrice, fmtPct, fmtTime helpers"
```

---

## Task 9: Extend `lib/api.ts` with `Bar`, `HistoryResponse`, `getTickerHistory`

**Files:**
- Modify: `web/frontend/src/lib/api.ts`

- [ ] **Step 1: Append the new types and helper**

Append to `web/frontend/src/lib/api.ts`:

```ts
// ---- Historical analysis chart ----

export type Bar = {
  t: string; // ISO timestamp with Z suffix
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export type HistoryRange = "1d" | "5d" | "1mo" | "3mo" | "6mo" | "1y" | "all" | "auto";

export interface HistoryResponse {
  ticker: string;
  range: HistoryRange;
  range_start: string;
  range_end: string;
  resolution: "1m" | "1h" | "1d";
  bars: Bar[];
  runs: RunDetail[];
}

export async function getTickerHistory(
  ticker: string,
  range: HistoryRange = "auto",
): Promise<HistoryResponse> {
  const r = await fetch(
    `${base}/api/tickers/${encodeURIComponent(ticker)}/history?range=${encodeURIComponent(range)}`,
  );
  if (!r.ok) {
    throw new ApiError(`history ${r.status}`, r.status, await readJsonOrNull(r));
  }
  return r.json();
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/lib/api.ts
git commit -m "feat(api): add Bar, HistoryResponse, getTickerHistory"
```

---

## Task 10: Extend `store/ui.ts` with history state

**Files:**
- Modify: `web/frontend/src/store/ui.ts`

- [ ] **Step 1: Add the new fields and setters**

Add the new types near the top of `web/frontend/src/store/ui.ts`:

```ts
export type HistoryPollInterval = 0 | 5_000 | 15_000 | 30_000 | 60_000 | 300_000;
```

Then in the `UiState` interface, after the existing `eventBuffer` field, add:

```ts
  // Per-ticker drawer open/closed flag. Lives in the store so the
  // HistoricalAnalysisDrawer can be triggered from anywhere in the app,
  // but is NOT persisted — the drawer should be closed on reload.
  historyOpenByTicker: Record<string, boolean>;
  // HOLD threshold in percent (0.1..5.0). Default 1.0. PERSISTED so
  // the user's "is this HOLD within tolerance" knob survives a refresh.
  holdThresholdPct: number;
  // Polling interval in ms for the history chart, or 0 to disable.
  // Default 30_000 (30s). PERSISTED.
  historyPollIntervalMs: HistoryPollInterval;
```

In the interface's setters section, add:

```ts
  setHistoryOpen: (ticker: string, open: boolean) => void;
  setHoldThresholdPct: (pct: number) => void;
  setHistoryPollIntervalMs: (ms: HistoryPollInterval) => void;
```

Inside the `create<UiState>()(persist((set) => ({...})))` body, after the existing default state fields, add:

```ts
      historyOpenByTicker: {},
      holdThresholdPct: 1.0,
      historyPollIntervalMs: 30_000,
```

And after the existing setter implementations, add:

```ts
      setHistoryOpen: (ticker, open) =>
        set((s) => ({ historyOpenByTicker: { ...s.historyOpenByTicker, [ticker]: open } })),
      setHoldThresholdPct: (pct) => set({ holdThresholdPct: pct }),
      setHistoryPollIntervalMs: (ms) => set({ historyPollIntervalMs: ms }),
```

Finally, update the `partialize` function to persist the new fields:

```ts
      partialize: (s) => ({
        focusedTicker: s.focusedTicker,
        lastRunIdByTicker: s.lastRunIdByTicker,
        historicalRunIdByTicker: s.historicalRunIdByTicker,
        holdThresholdPct: s.holdThresholdPct,
        historyPollIntervalMs: s.historyPollIntervalMs,
      }),
```

(`historyOpenByTicker` is intentionally omitted — the drawer should be closed on reload.)

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/store/ui.ts
git commit -m "feat(ui): add historyOpenByTicker, holdThresholdPct, historyPollIntervalMs"
```

---

## Task 11: `verdicts.ts` types and `barsInWindow` (TDD)

**Files:**
- Create: `web/frontend/src/verdicts.ts`
- Create: `web/frontend/src/verdicts.test.ts`

- [ ] **Step 1: Write the failing tests for `barsInWindow`**

Create `web/frontend/src/verdicts.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { barsInWindow, computeVerdict, computeStats, type Bar, type RunLike } from "./verdicts";

const t0 = "2026-06-01T12:00:00Z";
const delta1h = 60 * 60 * 1000;

function bar(t: string, c: number, o = c, h = c + 0.5, l = c - 0.5, v = 1000): Bar {
  return { t, o, h, l, c, v };
}

describe("barsInWindow", () => {
  it("returns bars whose t is in [start, start+delta]", () => {
    const bars = [
      bar("2026-06-01T11:00:00Z", 100), // before
      bar(t0, 100),                       // T
      bar("2026-06-01T12:30:00Z", 101),
      bar("2026-06-01T13:00:00Z", 102), // T+delta
      bar("2026-06-01T13:30:00Z", 103), // after
    ];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T15:00:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z", "2026-06-01T13:00:00Z"]);
  });

  it("clips the window at nowIso", () => {
    const bars = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101), bar("2026-06-01T13:00:00Z", 102)];
    const inWin = barsInWindow(bars, t0, delta1h, "2026-06-01T12:45:00Z");
    expect(inWin.map((b) => b.t)).toEqual([t0, "2026-06-01T12:30:00Z"]);
  });

  it("returns an empty array for empty input or no bars in window", () => {
    expect(barsInWindow([], t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
    const far = [bar("2026-06-01T10:00:00Z", 100)];
    expect(barsInWindow(far, t0, delta1h, "2026-06-01T15:00:00Z")).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the new test file, confirm it fails**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts -t "barsInWindow"
```

Expected: `Failed to resolve import "./verdicts"`.

- [ ] **Step 3: Write `verdicts.ts` with types and `barsInWindow`**

Create `web/frontend/src/verdicts.ts`:

```ts
/**
 * Pure verdict logic for the historical analysis chart.
 *
 * Zero React / UI imports. The drawer, chart, and run list all consume
 * the output of these functions; verdict rules live here and nowhere else.
 *
 * Coordinate convention: bar timestamps are ISO-8601 strings with a "Z"
 * suffix. The chart layer converts to ms numbers at its boundary; this
 * module never sees a Date or a number for time.
 */

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };

export type Action = "BUY" | "SELL" | "HOLD";

export type VerdictReason =
  | "target_hit"            // BUY/SELL with target that was hit (right)
  | "target_miss"           // BUY/SELL with target that was missed (wrong)
  | "direction"             // no-target BUY/SELL, status carried by .status (right or wrong)
  | "within_threshold"      // HOLD: |pctMove| <= holdThresholdPct (right)
  | "threshold_exceeded"    // HOLD: |pctMove| > holdThresholdPct (wrong)
  | "incomplete_window"     // T + Δ > now (unknown, counted as pending)
  | "no_data"               // zero bars in window (unknown)
  | "tie"                   // no-target BUY/SELL with close == start_price (unknown)
  | "no_start_price"        // run is missing start_price (unknown)
  | "unknown_action";       // defensive: action is not BUY/SELL/HOLD (unknown)

export type VerdictStatus = "right" | "wrong" | "unknown";

export interface Verdict {
  runId: string;
  status: VerdictStatus;
  reason: VerdictReason;
  pctMove: number | null;     // signed % from T to last bar in window
  targetHit: boolean | null;  // null for HOLD, no-target BUY/SELL
  maxHigh: number | null;     // for BUY target context
  minLow: number | null;      // for SELL target context
  endPrice: number | null;    // close of the last bar in window
}

export interface RunLike {
  id: string;
  startedAt: string;
  decisionAction: Action | string | null;
  decisionTarget: number | null;
  startPrice: number | null;
}

export interface Stats {
  total: number;
  right: number;
  wrong: number;
  unknown: number;
  pending: number;            // unknown AND reason == "incomplete_window"
  rightPct: number | null;    // right / (right + wrong), null if counted == 0
  byAction: Record<"BUY" | "SELL" | "HOLD", { right: number; wrong: number; unknown: number }>;
}

function isoToMs(iso: string): number {
  return new Date(iso).getTime();
}

/**
 * Filter ``bars`` to those whose ``t`` falls in ``[start, start+delta]``.
 * Clipped at ``nowIso`` for in-flight windows. End-boundary is inclusive.
 */
export function barsInWindow(
  bars: Bar[],
  startIso: string,
  deltaMs: number,
  nowIso: string,
): Bar[] {
  if (bars.length === 0) return [];
  const startMs = isoToMs(startIso);
  const endMs = Math.min(startMs + deltaMs, isoToMs(nowIso));
  const out: Bar[] = [];
  for (const b of bars) {
    const t = isoToMs(b.t);
    if (t >= startMs && t <= endMs) out.push(b);
  }
  return out;
}

// ---- Action colors / tints (used by HistoryChart and RunListItem) ----

export const ACTION_COLORS: Record<Action, string> = {
  BUY: "#16a34a",   // green-600
  SELL: "#dc2626",  // red-600
  HOLD: "#6b7280",  // gray-500
};

export const ACTION_TINTS: Record<Action, string> = {
  BUY: "rgba(22, 163, 74, 0.10)",
  SELL: "rgba(220, 38, 38, 0.10)",
  HOLD: "rgba(107, 114, 128, 0.10)",
};

export function actionColor(action: string | null | undefined): string {
  if (action === "BUY" || action === "SELL" || action === "HOLD") return ACTION_COLORS[action];
  return "#94a3b8"; // slate-400, neutral
}

export function actionTint(action: string | null | undefined): string {
  if (action === "BUY" || action === "SELL" || action === "HOLD") return ACTION_TINTS[action];
  return "rgba(148, 163, 184, 0.10)";
}

export { computeVerdict, computeStats };
```

- [ ] **Step 4: Run the new test file, confirm `barsInWindow` tests pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts -t "barsInWindow"
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/verdicts.ts web/frontend/src/verdicts.test.ts
git commit -m "feat(verdicts): add types and barsInWindow"
```

---

## Task 12: Add `computeVerdict` (TDD)

**Files:**
- Modify: `web/frontend/src/verdicts.ts`
- Modify: `web/frontend/src/verdicts.test.ts`

- [ ] **Step 1: Append the failing tests for `computeVerdict`**

Append to `web/frontend/src/verdicts.test.ts`:

```ts
describe("computeVerdict", () => {
  const baseRun: RunLike = {
    id: "run-1", startedAt: t0,
    decisionAction: "BUY", decisionTarget: 110, startPrice: 100,
  };

  it("BUY with target: target_hit when max(high) >= target", () => {
    const win = [
      bar(t0, 100),
      bar("2026-06-01T12:30:00Z", 112, 110, 112.5, 110, 1000), // high 112.5 hits 110
      bar("2026-06-01T12:45:00Z", 108),
    ];
    const v = computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("target_hit");
    expect(v.targetHit).toBe(true);
    expect(v.maxHigh).toBe(112.5);
  });

  it("BUY with target: target_miss when max(high) < target", () => {
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 103)];
    const v = computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("target_miss");
    expect(v.targetHit).toBe(false);
  });

  it("SELL with target: target_hit when min(low) <= target", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: 90 };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 92, 93, 91.5, 92, 1000)];
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("target_hit");
    expect(v.minLow).toBe(91.5);
  });

  it("SELL with target: target_miss when min(low) > target", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: 80 };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 95)];
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("target_miss");
  });

  it("HOLD within threshold is right (within_threshold)", () => {
    const run: RunLike = { ...baseRun, decisionAction: "HOLD", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5)]; // 0.5% ≤ 1.0
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("right");
    expect(v.reason).toBe("within_threshold");
    expect(v.pctMove).toBeCloseTo(0.5, 1);
  });

  it("HOLD over threshold is wrong (threshold_exceeded)", () => {
    const run: RunLike = { ...baseRun, decisionAction: "HOLD", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 102)]; // 2.0% > 1.0
    const v = computeVerdict(run, win, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("wrong");
    expect(v.reason).toBe("threshold_exceeded");
  });

  it("BUY no-target: close > start is right (direction); close < start is wrong", () => {
    const run: RunLike = { ...baseRun, decisionAction: "BUY", decisionTarget: null };
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101)], delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("right");
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 99)],  delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("wrong");
  });

  it("SELL no-target: close < start is right (direction); close > start is wrong", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: null };
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 99)],  delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("right");
    expect(computeVerdict(run, [bar(t0, 100), bar("2026-06-01T12:30:00Z", 101)], delta1h, 1.0, "2026-06-01T15:00:00Z").status).toBe("wrong");
  });

  it("BUY/SELL no-target tie → unknown: tie", () => {
    const buy: RunLike = { ...baseRun, decisionAction: "BUY", decisionTarget: null };
    const sell: RunLike = { ...baseRun, decisionAction: "SELL", decisionTarget: null };
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100)];
    expect(computeVerdict(buy,  win, delta1h, 1.0, "2026-06-01T15:00:00Z").reason).toBe("tie");
    expect(computeVerdict(sell, win, delta1h, 1.0, "2026-06-01T15:00:00Z").reason).toBe("tie");
  });

  it("missing start_price → unknown: no_start_price", () => {
    const run: RunLike = { ...baseRun, startPrice: null };
    const v = computeVerdict(run, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("no_start_price");
  });

  it("empty window → unknown: no_data", () => {
    const v = computeVerdict(baseRun, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("no_data");
  });

  it("incomplete window (T+Δ > nowIso) → unknown: incomplete_window", () => {
    const v = computeVerdict(baseRun, [], delta1h, 1.0, "2026-06-01T12:30:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("incomplete_window");
  });

  it("incomplete window flips to definite once nowIso passes T+Δ", () => {
    const win = [bar(t0, 100), bar("2026-06-01T13:00:00Z", 105)];
    expect(computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T12:30:00Z").reason).toBe("incomplete_window");
    expect(computeVerdict(baseRun, win, delta1h, 1.0, "2026-06-01T14:00:00Z").status).toBe("right");
  });

  it("defensive: unknown action → unknown: unknown_action", () => {
    const run: RunLike = { ...baseRun, decisionAction: "SOMETHING" };
    const v = computeVerdict(run, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(v.status).toBe("unknown");
    expect(v.reason).toBe("unknown_action");
  });
});
```

- [ ] **Step 2: Run new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts -t "computeVerdict"
```

Expected: import error (`computeVerdict` not exported from `./verdicts`).

- [ ] **Step 3: Implement `computeVerdict`**

Append to `web/frontend/src/verdicts.ts`:

```ts
export function computeVerdict(
  run: RunLike,
  windowBars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Verdict {
  const base: Pick<Verdict, "pctMove" | "targetHit" | "maxHigh" | "minLow" | "endPrice"> = {
    pctMove: null, targetHit: null, maxHigh: null, minLow: null, endPrice: null,
  };

  const action = run.decisionAction;
  if (action !== "BUY" && action !== "SELL" && action !== "HOLD") {
    return { runId: run.id, status: "unknown", reason: "unknown_action", ...base };
  }
  if (run.startPrice == null) {
    return { runId: run.id, status: "unknown", reason: "no_start_price", ...base };
  }
  const startMs = isoToMs(run.startedAt);
  if (startMs + deltaMs > isoToMs(nowIso)) {
    return { runId: run.id, status: "unknown", reason: "incomplete_window", ...base };
  }
  if (windowBars.length === 0) {
    return { runId: run.id, status: "unknown", reason: "no_data", ...base };
  }

  const maxHigh = windowBars.reduce((m, b) => Math.max(m, b.h), -Infinity);
  const minLow = windowBars.reduce((m, b) => Math.min(m, b.l), Infinity);
  const endPrice = windowBars[windowBars.length - 1].c;
  const pctMove = ((endPrice - run.startPrice) / run.startPrice) * 100;
  const filled = { pctMove, targetHit: null, maxHigh, minLow, endPrice };

  if (action === "HOLD") {
    if (Math.abs(pctMove) <= holdThresholdPct) {
      return { runId: run.id, status: "right", reason: "within_threshold", ...filled };
    }
    return { runId: run.id, status: "wrong", reason: "threshold_exceeded", ...filled };
  }

  if (run.decisionTarget != null) {
    if (action === "BUY") {
      const hit = maxHigh >= run.decisionTarget;
      return { runId: run.id, status: hit ? "right" : "wrong", reason: hit ? "target_hit" : "target_miss", ...filled, targetHit: hit };
    }
    const hit = minLow <= run.decisionTarget;
    return { runId: run.id, status: hit ? "right" : "wrong", reason: hit ? "target_hit" : "target_miss", ...filled, targetHit: hit };
  }

  // No-target BUY/SELL: direction rule with tie protection.
  if (endPrice === run.startPrice) {
    return { runId: run.id, status: "unknown", reason: "tie", ...filled };
  }
  const up = endPrice > run.startPrice;
  const right = action === "BUY" ? up : !up;
  return { runId: run.id, status: right ? "right" : "wrong", reason: "direction", ...filled };
}
```

- [ ] **Step 4: Run all verdict tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts
```

Expected: 3 (barsInWindow) + 13 (computeVerdict) = 16 tests pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/verdicts.ts web/frontend/src/verdicts.test.ts
git commit -m "feat(verdicts): add computeVerdict with full status table"
```

---

## Task 13: Add `computeStats` (TDD)

**Files:**
- Modify: `web/frontend/src/verdicts.ts`
- Modify: `web/frontend/src/verdicts.test.ts`

- [ ] **Step 1: Append the failing tests for `computeStats`**

Append to `web/frontend/src/verdicts.test.ts`:

```ts
describe("computeStats", () => {
  it("rightPct is null when no runs are scored", () => {
    const runs: RunLike[] = [
      { id: "n", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
    ];
    const s = computeStats(runs, [], delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(s.right).toBe(0);
    expect(s.wrong).toBe(0);
    expect(s.unknown).toBe(1);
    expect(s.rightPct).toBeNull();
  });

  it("counts pending incomplete_window runs separately", () => {
    const runs: RunLike[] = [
      { id: "x", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
      { id: "y", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 },
    ];
    const win = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5, 100, 112, 100, 1000)];
    const s = computeStats(runs, win, delta1h, 1.0, "2026-06-01T12:15:00Z");
    expect(s.pending).toBe(2);
    expect(s.unknown).toBe(2);
    expect(s.right).toBe(0);
    expect(s.wrong).toBe(0);
    expect(s.rightPct).toBeNull();
  });

  it("aggregates per-action counts and rightPct = right/(right+wrong)", () => {
    const buyRight: RunLike = { id: "1", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 };
    const buyWrong: RunLike = { id: "2", startedAt: t0, decisionAction: "BUY", decisionTarget: 110, startPrice: 100 };
    const winA = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 100.5, 100, 112, 100, 1000)];  // hits
    const winB = [bar(t0, 100), bar("2026-06-01T12:30:00Z", 105, 100, 106, 105, 1000)];     // misses
    const sRight = computeStats([buyRight], winA, delta1h, 1.0, "2026-06-01T15:00:00Z");
    const sWrong = computeStats([buyWrong], winB, delta1h, 1.0, "2026-06-01T15:00:00Z");
    expect(sRight.right).toBe(1); expect(sRight.wrong).toBe(0);
    expect(sWrong.right).toBe(0); expect(sWrong.wrong).toBe(1);
    expect(sRight.byAction.BUY).toEqual({ right: 1, wrong: 0, unknown: 0 });
    expect(sWrong.byAction.BUY).toEqual({ right: 0, wrong: 1, unknown: 0 });
    expect(sRight.rightPct).toBe(1.0);
    expect(sWrong.rightPct).toBe(0.0);
  });
});
```

- [ ] **Step 2: Run new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts -t "computeStats"
```

Expected: import error (`computeStats` not exported from `./verdicts`).

- [ ] **Step 3: Implement `computeStats`**

Append to `web/frontend/src/verdicts.ts`:

```ts
export function computeStats(
  runs: RunLike[],
  bars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Stats {
  const byAction: Stats["byAction"] = {
    BUY:  { right: 0, wrong: 0, unknown: 0 },
    SELL: { right: 0, wrong: 0, unknown: 0 },
    HOLD: { right: 0, wrong: 0, unknown: 0 },
  };
  let right = 0, wrong = 0, unknown = 0, pending = 0;

  for (const run of runs) {
    const windowBars = barsInWindow(bars, run.startedAt, deltaMs, nowIso);
    const v = computeVerdict(run, windowBars, deltaMs, holdThresholdPct, nowIso);

    if (v.status === "right") right++;
    else if (v.status === "wrong") wrong++;
    else unknown++;

    if (v.reason === "incomplete_window") pending++;

    const action = run.decisionAction;
    if (action === "BUY" || action === "SELL" || action === "HOLD") {
      const bucket = byAction[action];
      if (v.status === "right") bucket.right++;
      else if (v.status === "wrong") bucket.wrong++;
      else bucket.unknown++;
    }
  }

  const counted = right + wrong;
  const rightPct = counted === 0 ? null : right / counted;

  return { total: runs.length, right, wrong, unknown, pending, rightPct, byAction };
}
```

- [ ] **Step 4: Run all verdict tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/verdicts.test.ts
```

Expected: 3 + 13 + 3 = 19 tests pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/verdicts.ts web/frontend/src/verdicts.test.ts
git commit -m "feat(verdicts): add computeStats with per-action aggregation"
```

---

## Task 14: `HistoryStats.tsx`

**Files:**
- Create: `web/frontend/src/components/HistoryStats.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { Stats } from "../verdicts";

export function HistoryStats({ stats }: { stats: Stats }) {
  const headline = stats.rightPct == null ? "—" : `${Math.round(stats.rightPct * 100)}%`;
  const scored = stats.right + stats.wrong;
  return (
    <div className="border-b border-slate-200 px-3 py-2 text-xs text-slate-700">
      <div className="font-medium text-slate-900">
        {stats.total} runs · {stats.right} right · {stats.wrong} wrong · {stats.pending} pending · {headline} right
      </div>
      {scored === 0 && (
        <div className="text-slate-500 mt-0.5">No scored runs at this Δ.</div>
      )}
      <div className="mt-1 flex flex-wrap gap-x-3">
        <span><strong className="text-slate-900">BUY</strong> {stats.byAction.BUY.right}/{stats.byAction.BUY.right + stats.byAction.BUY.wrong} right</span>
        <span><strong className="text-slate-900">SELL</strong> {stats.byAction.SELL.right}/{stats.byAction.SELL.right + stats.byAction.SELL.wrong} right</span>
        <span><strong className="text-slate-900">HOLD</strong> {stats.byAction.HOLD.right}/{stats.byAction.HOLD.right + stats.byAction.HOLD.wrong} right</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/HistoryStats.tsx
git commit -m "feat(chart): add HistoryStats card"
```

---

## Task 15: `HistoryControls.tsx`

**Files:**
- Create: `web/frontend/src/components/HistoryControls.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useUi, type HistoryPollInterval } from "../store/ui";
import { fmtDelta, fmtPct } from "../lib/format";

const REFRESH_OPTIONS: Array<{ label: string; value: HistoryPollInterval }> = [
  { label: "Off", value: 0 },
  { label: "5s", value: 5_000 },
  { label: "15s", value: 15_000 },
  { label: "30s", value: 30_000 },
  { label: "1m", value: 60_000 },
  { label: "5m", value: 300_000 },
];

export function HistoryControls({
  deltaMs,
  onDeltaChange,
}: {
  deltaMs: number;
  onDeltaChange: (ms: number) => void;
}) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const setHoldThresholdPct = useUi((s) => s.setHoldThresholdPct);
  const historyPollIntervalMs = useUi((s) => s.historyPollIntervalMs);
  const setHistoryPollIntervalMs = useUi((s) => s.setHistoryPollIntervalMs);

  // Log-scale slider: position 0..1000 maps to 5m..30d exponentially.
  // pos 0   → 5m,   pos 500 → 1d,   pos 1000 → 30d.
  const posToDelta = (pos: number): number => {
    const min = 5 * 60_000;
    const max = 30 * 24 * 60 * 60_000;
    const logMin = Math.log(min);
    const logMax = Math.log(max);
    return Math.exp(logMin + (pos / 1000) * (logMax - logMin));
  };
  const deltaToPos = (ms: number): number => {
    const min = 5 * 60_000;
    const max = 30 * 24 * 60 * 60_000;
    const logMin = Math.log(min);
    const logMax = Math.log(max);
    return ((Math.log(ms) - logMin) / (logMax - logMin)) * 1000;
  };

  return (
    <div className="border-b border-slate-200 px-3 py-2 text-xs space-y-2">
      <div className="flex items-center gap-2">
        <label htmlFor="delta-slider" className="w-12 text-slate-600">Δ</label>
        <input
          id="delta-slider"
          data-testid="delta-slider"
          type="range"
          min={0}
          max={1000}
          value={deltaToPos(deltaMs)}
          onChange={(e) => onDeltaChange(posToDelta(Number(e.target.value)))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtDelta(deltaMs)}</span>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="hold-slider" className="w-12 text-slate-600">HOLD%</label>
        <input
          id="hold-slider"
          data-testid="hold-threshold-slider"
          type="range"
          min={0.1}
          max={5.0}
          step={0.1}
          value={holdThresholdPct}
          onChange={(e) => setHoldThresholdPct(Number(e.target.value))}
          className="flex-1"
        />
        <span className="w-12 text-right font-medium text-slate-900">{fmtPct(holdThresholdPct)}</span>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor="refresh-select" className="w-12 text-slate-600">Refresh</label>
        <select
          id="refresh-select"
          data-testid="refresh-select"
          value={historyPollIntervalMs}
          onChange={(e) => setHistoryPollIntervalMs(Number(e.target.value) as HistoryPollInterval)}
          className="flex-1 border border-slate-300 rounded px-1 py-0.5 bg-white"
        >
          {REFRESH_OPTIONS.map((o) => (
            <option key={o.label} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/HistoryControls.tsx
git commit -m "feat(chart): add HistoryControls (Δ + HOLD + refresh)"
```

---

## Task 16: `RunListItem.tsx`

**Files:**
- Create: `web/frontend/src/components/RunListItem.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { Verdict } from "../verdicts";
import { actionColor } from "../verdicts";
import { fmtPct, fmtPrice, fmtTime } from "../lib/format";

export interface RunListItemProps {
  run: {
    id: string;
    started_at: string | null;
    decision_action: string | null;
    decision_target: number | null;
    start_price: number | null;
  };
  verdict: Verdict;
  selected: boolean;
  scale: "m" | "h" | "d";
  onClick: () => void;
}

function verdictBadge(v: Verdict): { glyph: string; tone: string; subtext: string } {
  if (v.status === "right") {
    return { glyph: "✓", tone: "text-green-700", subtext: v.reason === "within_threshold" ? "within" : "hit" };
  }
  if (v.status === "wrong") {
    return { glyph: "✗", tone: "text-red-700", subtext: v.reason === "threshold_exceeded" ? "exceeded" : "miss" };
  }
  if (v.reason === "incomplete_window") return { glyph: "?", tone: "text-slate-500", subtext: "pending" };
  if (v.reason === "no_data") return { glyph: "?", tone: "text-slate-500", subtext: "no data" };
  if (v.reason === "tie") return { glyph: "?", tone: "text-slate-500", subtext: "tie" };
  if (v.reason === "no_start_price") return { glyph: "?", tone: "text-slate-500", subtext: "no start price" };
  if (v.reason === "unknown_action") return { glyph: "?", tone: "text-slate-500", subtext: "unknown action" };
  return { glyph: "?", tone: "text-slate-500", subtext: "unknown" };
}

export function RunListItem({ run, verdict, selected, scale, onClick }: RunListItemProps) {
  const t = run.started_at ? new Date(run.started_at).getTime() : null;
  const badge = verdictBadge(verdict);
  const pct = verdict.pctMove;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`run-row-${run.id}`}
      className={`w-full text-left px-3 py-2 border-b border-slate-100 hover:bg-slate-50 ${
        selected ? "bg-slate-100 border-l-2 border-l-slate-700" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs text-slate-500 w-24 shrink-0">
            {t != null ? fmtTime(t, scale) : "—"}
          </span>
          <span
            className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
            style={{ color: actionColor(run.decision_action), border: `1px solid ${actionColor(run.decision_action)}` }}
          >
            {run.decision_action ?? "—"}
          </span>
          {run.start_price != null && (
            <span className="text-xs text-slate-700">${fmtPrice(run.start_price)}</span>
          )}
          {run.decision_target != null && run.decision_action !== "HOLD" && (
            <>
              <span className="text-xs text-slate-400">→</span>
              <span className="text-xs text-slate-700">${fmtPrice(run.decision_target)}</span>
            </>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {pct != null && (
            <span className={`text-xs font-mono ${pct >= 0 ? "text-green-700" : "text-red-700"}`}>
              {fmtPct(pct)}
            </span>
          )}
          <span className={`text-sm ${badge.tone}`} title={badge.subtext}>
            {badge.glyph}
          </span>
        </div>
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/RunListItem.tsx
git commit -m "feat(chart): add RunListItem row with verdict badge"
```

---

## Task 17: `HistoryChart.tsx` + tests (TDD)

**Files:**
- Create: `web/frontend/src/components/HistoryChart.tsx`
- Create: `web/frontend/src/HistoryChart.test.tsx`

- [ ] **Step 1: Write the failing component test**

Create `web/frontend/src/HistoryChart.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { HistoryChart } from "./components/HistoryChart";
import type { Bar, RunLike, Verdict } from "./verdicts";

const t0 = "2026-06-01T12:00:00Z";
const t1 = "2026-06-01T13:00:00Z";
const bars: Bar[] = [
  { t: t0, o: 100, h: 101, l: 99, c: 100.5, v: 1000 },
  { t: t1, o: 100.5, h: 102, l: 100, c: 101, v: 1000 },
];
const runBuy: RunLike = { id: "buy-1", startedAt: t0, decisionAction: "BUY", decisionTarget: 105, startPrice: 100 };
const runHold: RunLike = { id: "hold-1", startedAt: t0, decisionAction: "HOLD", decisionTarget: null, startPrice: 100 };
const verdicts = new Map<string, Verdict>([
  ["buy-1",  { runId: "buy-1",  status: "right", reason: "target_hit",         pctMove: 1.0, targetHit: true,  maxHigh: 102, minLow: 100, endPrice: 101 }],
  ["hold-1", { runId: "hold-1", status: "right", reason: "within_threshold",  pctMove: 1.0, targetHit: null, maxHigh: 102, minLow: 100, endPrice: 101 }],
]);

const baseProps = {
  bars, runs: [runBuy, runHold], verdicts,
  deltaMs: 60 * 60 * 1000, holdThresholdPct: 1.0,
  nowIso: "2026-06-01T15:00:00Z", selectedRunId: "buy-1",
  resolution: "1h" as const, rangeStartIso: t0, rangeEndIso: t1,
};

describe("HistoryChart", () => {
  it("renders a recharts Surface", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelector(".recharts-surface")).toBeTruthy();
  });

  it("renders one ReferenceArea per run", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelectorAll(".recharts-reference-area")).toHaveLength(2);
  });

  it("renders a ReferenceLine for BUY target but not for HOLD, plus the now-cursor", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    // 1 target line for BUY, 1 now cursor. HOLD has no target line.
    expect(container.querySelectorAll(".recharts-reference-line")).toHaveLength(2);
  });

  it("renders a ReferenceDot per run", () => {
    const { container } = render(<HistoryChart {...baseProps} />);
    expect(container.querySelectorAll(".recharts-reference-dot")).toHaveLength(2);
  });

  it("always renders the now-cursor ReferenceLine even with no runs", () => {
    const { container } = render(
      <HistoryChart {...baseProps} runs={[]} verdicts={new Map()} selectedRunId={null} />,
    );
    // No runs → 0 target lines, 1 now cursor.
    expect(container.querySelectorAll(".recharts-reference-line")).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the new test file, confirm it fails**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/HistoryChart.test.tsx
```

Expected: import error (`HistoryChart` not exported from `./components/HistoryChart`).

- [ ] **Step 3: Implement `HistoryChart.tsx`**

```tsx
import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  ReferenceArea, ReferenceLine, ReferenceDot, ResponsiveContainer,
} from "recharts";
import type { Bar, RunLike, Verdict } from "../verdicts";
import { actionColor, actionTint } from "../verdicts";
import { fmtPrice, fmtTime } from "../lib/format";

export interface HistoryChartProps {
  bars: Bar[];
  runs: RunLike[];
  verdicts: Map<string, Verdict>;
  deltaMs: number;
  holdThresholdPct: number;
  nowIso: string;
  selectedRunId: string | null;
  resolution: "1m" | "1h" | "1d";
  rangeStartIso: string;
  rangeEndIso: string;
}

interface ChartRow { t: number; c: number; }

/** Downsample bars to ~3000 rows when the input is large. */
function downsample(bars: Bar[], target = 3000): Bar[] {
  if (bars.length <= target) return bars;
  const stride = Math.ceil(bars.length / target);
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i += stride) {
    const chunk = bars.slice(i, i + stride);
    const first = chunk[0];
    const last = chunk[chunk.length - 1];
    out.push({
      t: first.t,
      o: first.o,
      h: chunk.reduce((m, b) => Math.max(m, b.h), -Infinity),
      l: chunk.reduce((m, b) => Math.min(m, b.l), Infinity),
      c: last.c,
      v: chunk.reduce((s, b) => s + b.v, 0),
    });
  }
  return out;
}

function isoToMs(iso: string): number {
  return new Date(iso).getTime();
}

export function HistoryChart(props: HistoryChartProps) {
  const { bars, runs, deltaMs, nowIso, selectedRunId, resolution, rangeStartIso, rangeEndIso } = props;
  const scale: "m" | "h" | "d" = resolution === "1m" ? "m" : resolution === "1h" ? "h" : "d";

  const chartData: ChartRow[] = useMemo(
    () => downsample(bars).map((b) => ({ t: isoToMs(b.t), c: b.c })),
    [bars],
  );

  const rangeStartMs = isoToMs(rangeStartIso);
  const rangeEndMs = isoToMs(rangeEndIso);
  const nowMs = isoToMs(nowIso);

  return (
    <div className="w-full h-72" data-testid="history-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 2" />
          <XAxis
            dataKey="t"
            type="number"
            domain={[rangeStartMs, rangeEndMs]}
            scale="time"
            tickFormatter={(v) => fmtTime(v, scale)}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={fmtPrice}
            width={50}
            tick={{ fontSize: 10, fill: "#64748b" }}
            stroke="#cbd5e1"
          />
          <Line dataKey="c" dot={false} stroke="#475569" strokeWidth={1.5} isAnimationActive={false} />
          {runs.map((run) => {
            const startMs = isoToMs(run.startedAt);
            const endMs = Math.min(startMs + deltaMs, nowMs);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceArea
                key={`band-${run.id}`}
                x1={startMs} x2={endMs}
                fill={actionTint(run.decisionAction)}
                fillOpacity={isSelected ? 0.25 : 0.08}
                stroke="none"
                ifOverflow="visible"
              />
            );
          })}
          {runs.map((run) => {
            if (run.decisionTarget == null) return null;
            if (run.decisionAction === "HOLD") return null;
            const startMs = isoToMs(run.startedAt);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceLine
                key={`target-${run.id}`}
                y={run.decisionTarget}
                x1={startMs} x2={startMs + deltaMs}
                stroke={actionColor(run.decisionAction)}
                strokeWidth={isSelected ? 3 : 1.5}
                strokeDasharray={isSelected ? undefined : "4 2"}
                ifOverflow="visible"
              />
            );
          })}
          {runs.map((run) => {
            if (run.startPrice == null) return null;
            const startMs = isoToMs(run.startedAt);
            const isSelected = run.id === selectedRunId;
            return (
              <ReferenceDot
                key={`dot-${run.id}`}
                x={startMs} y={run.startPrice}
                r={isSelected ? 8 : 5}
                fill={actionColor(run.decisionAction)}
                stroke="#fff" strokeWidth={1}
              />
            );
          })}
          <ReferenceLine
            x={nowMs}
            stroke="#94a3b8"
            strokeDasharray="3 3"
            label={{ value: "now", position: "insideTopRight", fill: "#94a3b8", fontSize: 10 }}
            ifOverflow="extendDomain"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Run the test file, confirm all tests pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/HistoryChart.test.tsx
```

Expected: all 5 pass.

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/HistoryChart.tsx web/frontend/src/HistoryChart.test.tsx
git commit -m "feat(chart): add HistoryChart (recharts) with bands, targets, now cursor"
```

---

## Task 18: `HistoricalAnalysisDrawer.tsx`

**Files:**
- Create: `web/frontend/src/components/HistoricalAnalysisDrawer.tsx`

- [ ] **Step 1: Write the drawer component**

```tsx
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getTickerHistory, type HistoryRange, type RunDetail, type Bar,
} from "../lib/api";
import { useUi } from "../store/ui";
import {
  computeStats, computeVerdict, type Verdict,
} from "../verdicts";
import { HistoryStats } from "./HistoryStats";
import { HistoryChart } from "./HistoryChart";
import { HistoryControls } from "./HistoryControls";
import { RunListItem } from "./RunListItem";

// --- helpers ---

function scaleFor(resolution: "1m" | "1h" | "1d"): "m" | "h" | "d" {
  return resolution === "1m" ? "m" : resolution === "1h" ? "h" : "d";
}

function toRunLike(run: RunDetail) {
  return {
    id: run.id,
    startedAt: run.started_at ?? "",
    decisionAction: (run.decision_action ?? null) as "BUY" | "SELL" | "HOLD" | null,
    decisionTarget: run.decision_target,
    startPrice: run.start_price,
  };
}

function useTickingNow(intervalMs: number): { nowIso: string; nowMs: number } {
  const [tick, setTick] = useState(() => {
    const d = new Date();
    return { nowIso: d.toISOString(), nowMs: d.getTime() };
  });
  useEffect(() => {
    if (intervalMs <= 0) return;
    const id = window.setInterval(() => {
      const d = new Date();
      setTick({ nowIso: d.toISOString(), nowMs: d.getTime() });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return tick;
}

// --- main component ---

export function HistoricalAnalysisDrawer({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const holdThresholdPct = useUi((s) => s.holdThresholdPct);
  const historyPollIntervalMs = useUi((s) => s.historyPollIntervalMs);
  const focusedRunId = useUi((s) => {
    const hist = s.historicalRunIdByTicker[ticker];
    if (hist != null) return hist;
    return s.lastRunIdByTicker[ticker] ?? null;
  });
  const setHistoricalRunForTicker = useUi((s) => s.setHistoricalRunForTicker);

  const [range, setRange] = useState<HistoryRange>("auto");
  const [deltaMs, setDeltaMs] = useState<number>(24 * 60 * 60 * 1000); // 1d default
  const tick = useTickingNow(1000);

  const query = useQuery({
    queryKey: ["ticker-history", ticker, range],
    queryFn: () => getTickerHistory(ticker, range),
    refetchInterval: historyPollIntervalMs > 0 ? historyPollIntervalMs : false,
    staleTime: 0,
    enabled: !!ticker,
  });

  const data = query.data;
  const runs: RunDetail[] = data?.runs ?? [];
  const bars: Bar[] = data?.bars ?? [];
  const resolution = (data?.resolution ?? "1h") as "1m" | "1h" | "1d";
  const rangeStartIso = data?.range_start ?? tick.nowIso;
  const rangeEndIso = data?.range_end ?? tick.nowIso;
  const scale = scaleFor(resolution);

  const verdicts = useMemo(() => {
    const out = new Map<string, Verdict>();
    for (const run of runs) {
      const rl = toRunLike(run);
      const startMs = new Date(rl.startedAt).getTime();
      const endMs = Math.min(startMs + deltaMs, tick.nowMs);
      const win = bars.filter((b) => {
        const t = new Date(b.t).getTime();
        return t >= startMs && t <= endMs;
      });
      out.set(run.id, computeVerdict(rl, win, deltaMs, holdThresholdPct, tick.nowIso));
    }
    return out;
  }, [runs, bars, deltaMs, holdThresholdPct, tick.nowIso, tick.nowMs]);

  const stats = useMemo(
    () => computeStats(runs.map(toRunLike), bars, deltaMs, holdThresholdPct, tick.nowIso),
    [runs, bars, deltaMs, holdThresholdPct, tick.nowIso],
  );

  return (
    <div
      className="fixed inset-y-0 right-0 w-[28rem] max-w-full bg-white border-l border-slate-200 shadow-xl z-20 flex flex-col"
      data-testid="history-drawer"
    >
      <div className="flex items-center justify-between p-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold">{ticker}</h3>
          <select
            data-testid="range-select"
            value={range}
            onChange={(e) => setRange(e.target.value as HistoryRange)}
            className="text-xs border border-slate-300 rounded px-1 py-0.5 bg-white"
          >
            <option value="auto">Auto</option>
            <option value="1d">1d</option>
            <option value="5d">5d</option>
            <option value="1mo">1mo</option>
            <option value="3mo">3mo</option>
            <option value="6mo">6mo</option>
            <option value="1y">1y</option>
            <option value="all">All</option>
          </select>
        </div>
        <button onClick={onClose} className="text-sm text-slate-500">Close</button>
      </div>

      <HistoryStats stats={stats} />

      <div className="flex-1 min-h-0">
        {query.isLoading ? (
          <div className="p-4 text-xs text-slate-500">Loading…</div>
        ) : query.isError ? (
          <div className="p-4 text-xs text-slate-700 space-y-2">
            <p>Failed to load price history: <span className="font-mono">{(query.error as Error).message}</span></p>
            <button onClick={() => query.refetch()} className="text-blue-600">Retry</button>
          </div>
        ) : bars.length === 0 && runs.length > 0 ? (
          <div className="p-4 text-xs text-slate-700 space-y-2">
            <p>No price data for this range.</p>
            <p className="text-slate-500">Try a different range preset — yfinance 1m data is only available for the last 7 days.</p>
            <button onClick={() => setRange("1y")} className="text-blue-600">Use 1y</button>
          </div>
        ) : (
          <HistoryChart
            bars={bars}
            runs={runs.map(toRunLike)}
            verdicts={verdicts}
            deltaMs={deltaMs}
            holdThresholdPct={holdThresholdPct}
            nowIso={tick.nowIso}
            selectedRunId={focusedRunId}
            resolution={resolution}
            rangeStartIso={rangeStartIso}
            rangeEndIso={rangeEndIso}
          />
        )}
      </div>

      <HistoryControls deltaMs={deltaMs} onDeltaChange={setDeltaMs} />

      <div className="flex-1 min-h-0 overflow-y-auto border-t border-slate-200">
        {runs.length === 0 ? (
          <div className="p-4 text-xs text-slate-500">No runs for {ticker}.</div>
        ) : (
          runs.map((run) => (
            <RunListItem
              key={run.id}
              run={{
                id: run.id,
                started_at: run.started_at,
                decision_action: run.decision_action,
                decision_target: run.decision_target,
                start_price: run.start_price,
              }}
              verdict={verdicts.get(run.id) ?? {
                runId: run.id, status: "unknown", reason: "no_data",
                pctMove: null, targetHit: null, maxHigh: null, minLow: null, endPrice: null,
              }}
              selected={run.id === focusedRunId}
              scale={scale}
              onClick={() => setHistoricalRunForTicker(ticker, run.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/components/HistoricalAnalysisDrawer.tsx
git commit -m "feat(chart): add HistoricalAnalysisDrawer top-level container"
```

---

## Task 19: Swap drawer in `App.tsx`

**Files:**
- Modify: `web/frontend/src/App.tsx`

- [ ] **Step 1: Update the import and the JSX**

In `web/frontend/src/App.tsx`:

- Change `import { RunHistoryDrawer } from "./components/RunHistoryDrawer";` to:
  ```ts
  import { HistoricalAnalysisDrawer } from "./components/HistoricalAnalysisDrawer";
  ```
- Change the JSX `<RunHistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} />` to:
  ```tsx
  {focused && historyOpen && (
    <HistoricalAnalysisDrawer ticker={focused} onClose={() => setHistoryOpen(false)} />
  )}
  ```

The `historyOpen` boolean and the `setHistoryOpen` setter are still owned by `App.tsx`; the History button in the header (around line 113) still calls `setHistoryOpen(true)`. The new condition just guards the render so the drawer doesn't mount for a null ticker.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/App.tsx
git commit -m "feat(app): swap RunHistoryDrawer for HistoricalAnalysisDrawer"
```

---

## Task 20: Delete `RunHistoryDrawer.tsx`

**Files:**
- Delete: `web/frontend/src/components/RunHistoryDrawer.tsx`

- [ ] **Step 1: Remove the file**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
Remove-Item "web\frontend\src\components\RunHistoryDrawer.tsx"
```

- [ ] **Step 2: Verify the build / tsc are clean**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx tsc --noEmit
```

Expected: no errors. (`App.tsx` no longer imports `RunHistoryDrawer`.)

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add -u web/frontend/src/components/RunHistoryDrawer.tsx
git commit -m "refactor: remove RunHistoryDrawer (replaced by HistoricalAnalysisDrawer)"
```

---

## Task 21: Final lint + build + manual integration checklist

**Files:** none (verification only)

- [ ] **Step 1: Run frontend lint**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npm run lint
```

Expected: no errors. Warnings are OK; fix any blocking ones.

- [ ] **Step 2: Run frontend build**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npm run build
```

Expected: succeeds (tsc + vite build).

- [ ] **Step 3: Run the full frontend test suite**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run
```

Expected: all pass (3 barsInWindow + 13 computeVerdict + 3 computeStats + 5 HistoryChart = 24 frontend tests, plus any pre-existing tests).

- [ ] **Step 4: Run the full backend test suite**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m pytest web/server/tests/ -v
```

Expected: all pass (10 resolve_range + 5 fetch_history_bars + 5 get_history + 5 TestHistoryEndpoint = 25 new tests, plus all pre-existing tests).

- [ ] **Step 5: Manual integration checklist (run with `TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED=1`)**

Start the dashboard, then verify:

- [ ] History button in the header opens the drawer on the right for the focused ticker.
- [ ] Closing the drawer hides it; reopening restores the last range + Δ + HOLD%.
- [ ] Range preset "Auto" picks a sensible window for tickers with old runs.
- [ ] Switching to "5d" then "1y" refetches and re-renders the chart.
- [ ] Yfinance unavailable (toggle `TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED=0` and disconnect) → error state with Retry.
- [ ] Ticker with no runs → "No runs for TICKER" in the run list area.
- [ ] Selected run (the one bolded in the run list) has the more opaque band, larger dot, and thicker target line.
- [ ] Dragging the Δ slider updates `right%` headline in `HistoryStats` live.
- [ ] Dragging the HOLD% slider updates the HOLD row's right/wrong counts.
- [ ] Refresh dropdown setting "Off" halts the bar poller; "30s" resumes.
- [ ] Active run's band grows as time advances (the in-flight `now` cursor moves right on the chart).

If any of these fail, do not declare the feature complete — open a follow-up task to fix and re-verify.

---

## Self-Review (checklist run after writing the plan)

**1. Spec coverage**

- `resolve_range` for all 8 presets and `auto` — Task 1.
- `fetch_history_bars` with TTL cache — Task 2.
- `get_history` orchestrator returning the spec's body shape, with 404/422/502 envelopes — Task 3.
- `GET /api/tickers/{t}/history?range=...` route — Task 4.
- Yfinance fixture extension for tests — Task 5.
- Integration tests — Task 6.
- recharts dep — Task 7.
- Format helpers (`fmtDelta`, `fmtPrice`, `fmtPct`, `fmtTime`) — Task 8.
- Frontend API types + helper — Task 9.
- UI store: `historyOpenByTicker`, `holdThresholdPct`, `historyPollIntervalMs` — Task 10.
- Pure verdict module: types, `barsInWindow`, `computeVerdict`, `computeStats` — Tasks 11-13.
- `HistoryStats` — Task 14.
- `HistoryControls` (Δ log-slider 5m..30d, HOLD% linear 0.1..5.0, refresh dropdown) — Task 15.
- `RunListItem` — Task 16.
- `HistoryChart` (recharts: bands, target lines, action dots, now-cursor, downsampling) — Task 17.
- `HistoricalAnalysisDrawer` (top-level container, query, ticking `now`, range preset, run list) — Task 18.
- App.tsx swap + delete old drawer + final verification — Tasks 19-21.

No spec gaps found.

**2. Placeholder scan**

No "TBD", "TODO", "implement later", "add appropriate error handling", or "similar to Task N" placeholders remain. All code steps are complete.

**3. Type consistency**

- `Bar` type defined in `verdicts.ts` and re-used by `api.ts` (same shape).
- `HistoryResponse.bars: Bar[]`; `HistoryResponse.runs: RunDetail[]` — `RunDetail` is the pre-existing API type from `api.ts`.
- `RunLike` in `verdicts.ts` is the shape `toRunLike(run: RunDetail)` produces; both are referenced consistently.
- `Verdict`, `Stats`, `actionColor`, `actionTint` exported from `verdicts.ts`; consumed by `HistoryChart`, `HistoryStats`, `RunListItem`, `HistoricalAnalysisDrawer`.
- `HistoryPollInterval` exported from `store/ui.ts`; consumed by `HistoryControls` and `HistoricalAnalysisDrawer`.

No type mismatches.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-07-historical-analysis-chart.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?

