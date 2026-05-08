# Backtesting Engine — Design Spec

**Date:** 2026-05-08
**Status:** Approved

---

## Overview

Add a `tradingagents/backtesting/` module that runs the full 9-agent pipeline against
historical dates and measures how well the resulting signals performed. Results are
written incrementally to JSONL so crashed runs resume automatically. A separate report
layer computes all metrics without re-running the pipeline.

---

## Module Layout

```
tradingagents/backtesting/
    __init__.py      # exports BacktestEngine, BacktestReport, BacktestResult, BacktestSummary
    engine.py        # BacktestEngine — orchestrates pipeline runs, JSONL writes, resume
    report.py        # BacktestReport, BacktestSummary, is_win, get_holding_days
    models.py        # BacktestResult dataclass, DIRECTION_MAP, derive_direction
    returns.py       # fetch_returns() — extracted from TradingAgentsGraph._fetch_returns
    cli.py           # argparse + tqdm entrypoint
```

---

## Data Model (`models.py`)

```python
DIRECTION_MAP: dict[str, int] = {
    "Buy": +1, "Overweight": +1,
    "Hold": 0,
    "Underweight": -1, "Sell": -1,
}

def derive_direction(rating: Optional[str]) -> Optional[int]:
    """Return None for missing or unrecognised ratings — not 0 (Hold)."""
    if rating is None:
        return None
    return DIRECTION_MAP.get(rating, None)

@dataclass
class BacktestResult:
    ticker: str
    trade_date: str           # ISO-8601: "YYYY-MM-DD" — always this format
    rating: Optional[str] = None    # 5-tier PM output: Buy/Overweight/Hold/Underweight/Sell
    direction: Optional[int] = None # derived via derive_direction(); +1/0/-1 or None
    raw_output: str = ""            # full Portfolio Manager markdown
    run_duration_seconds: float = 0.0
    error: Optional[str] = None     # exception message for failed runs; rating/direction are None
```

**trade_date** must always be ISO-8601 `YYYY-MM-DD`. All datetime operations use
`datetime.strptime(result.trade_date, "%Y-%m-%d")` — a stray format causes silent bugs.

Failed runs write a `BacktestResult` with `rating=None`, `direction=None`, and
`error=<exception message>`. They are included in the JSONL output and excluded from
metric calculations (not silently dropped).

---

## Return Fetching (`returns.py`)

Extracted from `TradingAgentsGraph._fetch_returns`. Standalone module function — no
graph dependency.

```python
def fetch_returns(
    ticker: str,
    trade_date: str,          # "YYYY-MM-DD"
    holding_days: int,
) -> tuple[Optional[float], Optional[float], Optional[int]]:
    """Fetch (raw_return, alpha_vs_spy, actual_holding_days) via yfinance.

    Requires network access. Returns (None, None, None) for tickers that are
    too recent, delisted, or unreachable — callers must handle the None case.
    When mocking in tests, patch at `tradingagents.backtesting.returns.fetch_returns`.
    """
```

Uses a `holding_days + 7` calendar-day buffer when fetching to absorb weekends and
market holidays. `actual_holding_days` reflects how many trading days were actually
used (may be less than `holding_days` near the end of available data).

---

## Engine (`engine.py`)

```python
BacktestEngine(
    tickers: list[str],
    start_date: str,              # "YYYY-MM-DD"
    end_date: str,                # "YYYY-MM-DD"
    freq: str,                    # "monthly" | "weekly" | "biweekly"
    config: dict,                 # standard TradingAgents config
    analysts: list[str] = None,   # default: all four analysts
    max_workers: int = 2,         # parallel tickers; dates within a ticker are sequential
    output_file: str = None,      # JSONL path; defaults to ~/.tradingagents/backtests/<id>.jsonl
)

engine.run() -> list[BacktestResult]
```

### Date Generation

`pandas.date_range(start, end, freq=...)` with business-day alignment. Weekends and
standard market holidays are skipped. Supported freq values: `"monthly"` (MS),
`"weekly"` (W-MON), `"biweekly"` (2W-MON).

### Resume Support

At start, loads all completed `(ticker, trade_date)` pairs from the existing output
file and skips them from the run queue. A run is "completed" only if its
`BacktestResult` has `error=None`.

```python
completed = load_completed_pairs(output_file)   # set of (ticker, date) tuples
pairs = [(t, d) for t, d in all_pairs if (t, d) not in completed]
```

### Execution

- Tickers are parallelised via `ThreadPoolExecutor(max_workers=max_workers)`.
- Dates within a ticker run sequentially — the pipeline carries memory context forward
  between same-ticker runs, so order is load-bearing.
- Each `(ticker, date)` call wraps `TradingAgentsGraph.propagate()` in a try/except.
  Exceptions produce a `BacktestResult` with `error=<message>` rather than aborting
  the run.
- Results are written to the JSONL output file immediately after each run (one JSON
  object per line) so a crash loses at most one in-flight result.

### Rate Limit Backoff

429 responses from the LLM provider trigger exponential backoff on the same
`(ticker, date)` pair: 1s → 2s → 4s → … capped at 60s, up to 5 retries. The retry
loop runs inline so date ordering within a ticker is preserved.

---

## Report (`report.py`)

```python
BacktestReport(
    results: list[BacktestResult],
    risk_free_rate: float = 0.0,   # annualised; e.g. 0.045 for 4.5% T-bill
)

report.compute(hold_days_override: Optional[int] = None) -> BacktestSummary
```

`compute()` calls `fetch_returns(ticker, trade_date, holding_days)` for each result
where `error is None`. Holding days are resolved per-result:

```python
def get_holding_days(
    current_date: str,
    next_signal_date: Optional[str],
    hold_days_override: Optional[int],
    max_fallback_days: int = 21,
) -> int:
    if hold_days_override is not None:
        return hold_days_override
    if next_signal_date is not None:
        return business_days_between(current_date, next_signal_date)
    return max_fallback_days   # last date in range — ~1 trading month fallback
```

### Win Rate

```python
def is_win(direction: int, raw_return: float) -> Optional[bool]:
    if direction == 0:       # HOLD — excluded from directional win rate
        return None
    if raw_return == 0.0:    # exact tie — excluded
        return None
    return (direction > 0) == (raw_return > 0)
```

HOLD signals are counted separately in `BacktestSummary` and excluded from win rate.

### BacktestSummary

```python
@dataclass
class BacktestSummary:
    # Sanity check — always inspect before trusting any other metric
    signal_counts: dict[str, int]          # {"Buy": 3, "Hold": 8, "Sell": 1, ...}
    error_count: int                        # runs that failed

    # Raw returns
    total_return: Optional[float]           # sum of per-signal raw returns
    mean_return: Optional[float]            # mean per-signal raw return
    cumulative_equity: list[float]          # equity curve (starts at 1.0)

    # Alpha
    mean_alpha: Optional[float]             # mean alpha vs SPY per signal
    pct_beat_spy: Optional[float]           # fraction of signals that beat SPY

    # Signal quality
    win_rate: Optional[float]               # directional accuracy (excludes HOLD, ties)
    precision_recall_per_tier: dict         # per 5-tier rating: precision, recall, count
    hold_count: int                         # HOLD signals (excluded from win rate)

    # Risk (annualised)
    sharpe_ratio: Optional[float]
    max_drawdown: Optional[float]
    volatility: Optional[float]
```

All `Optional` fields are `None` when there is insufficient data (e.g. zero
non-HOLD signals → `win_rate=None`).

---

## CLI (`cli.py`)

```
python -m tradingagents backtest [options]

Required:
  --ticker TICKER [TICKER ...]   one or more ticker symbols
  --start YYYY-MM-DD
  --end   YYYY-MM-DD

Optional:
  --freq         monthly|weekly|biweekly   (default: monthly)
  --output       PATH                      (default: ~/.tradingagents/backtests/<hash>.jsonl)
  --resume                                 skip completed pairs from existing output file
  --hold-days    N                         override holding period (trading days)
  --workers      N                         parallel tickers (default: 2)
  --risk-free-rate FLOAT                   annualised, for Sharpe (default: 0.0)
  --analysts     ANALYST [...]             subset of: market social news fundamentals
```

Progress is displayed via `tqdm` — one bar per ticker showing completed dates.
On completion, a summary table is printed to stdout and the full `BacktestSummary`
is written alongside the JSONL file as `<output_stem>_summary.json`.

---

## Key Constraints

- **Point-in-time correctness**: The pipeline already passes `trade_date` through
  `create_initial_state()` and all data tools accept explicit date parameters.
  No changes to the data layer are needed.
- **Memory context carries forward**: `TradingAgentsGraph` is re-used across dates
  for the same ticker so the persistent decision log accumulates context as it would
  in a real sequential deployment. A fresh graph instance is created per ticker.
- **No confidence field**: The pipeline does not produce a confidence value. The
  `backend.py` confidence was hardcoded at 70 for real runs. It is not included here.
- **_fetch_returns extraction**: `TradingAgentsGraph._fetch_returns` remains on the
  graph class for the memory log resolution flow. `returns.fetch_returns` is a
  clean copy in the new module — both can exist without duplication becoming a
  maintenance problem, but a follow-up could unify them.
