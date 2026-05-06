# Range Stats + User Research Upload — Design Spec

**Date**: 2026-05-06
**Status**: Approved by user, ready for implementation plan
**Branch**: `feat/webui-scheduler-telegram` (will branch off for implementation)

## Problem

Two feature requests from a teammate:

1. **Range stats** — On every analysis day, expose how today's open price, close price, and volume sit relative to recent ranges:
   - 4 lookback windows: **52 weeks, 6 months, 3 months, 1 month**
   - 3 daily metrics: **open, close, volume**
   - 3 numbers per (window, metric): **% above period low**, **% below period high**, **position-in-range %**
   - Total: 4 × 3 × 3 = **36 numbers per analysis run**

2. **User research upload** — Let the user upload broker / analyst research notes (PDFs, markdown, text). The AI agents should consume the content as an additional input alongside the existing market / fundamentals / sentiment / news reports.

Both should reuse one source of truth and surface in three places: the LLM agents, the Streamlit WebUI, and the daily Telegram report.

## Goals

- Range stats computed once, rendered three ways (LangChain tool, WebUI card, Telegram section)
- Research upload supports per-ticker library (long-lived) AND per-run one-off
- Per-user isolation (matches existing email-OTP multi-user WebUI)
- Pre-summarize uploaded research with the configured `quick_thinking_llm` so each run reuses a compact summary, not the full PDF
- LLM agents see a separate `user_research_report` field, framed explicitly as "user-supplied prior, not platform data"
- Backwards-compatible: empty research field → existing prompts behave identically

## Non-Goals (YAGNI)

- DOCX, image/OCR, or non-PDF/text formats
- Full-text research search
- Telegram upload of research files
- Cross-user research sharing
- "Stale research" expiry warnings
- Multi-ticker research (industry note shared across tickers)
- CLI integration (only WebUI + scheduler/Telegram path)

## Architecture Overview

```
┌──────────── Data layer (new modules) ────────────┐
│  tradingagents/dataflows/range_stats.py          │   pure compute: OHLCV → 36 numbers
│  tradingagents/dataflows/user_research.py        │   PDF/text extract + LLM summarize + storage
└───────────────────────────────────────────────────┘
            ↑                ↑                  ↑
    ┌───────┴────────┐  ┌────┴─────┐  ┌────────┴─────────┐
    │ market_analyst │  │ webui.py │  │ scheduler.py /    │
    │ + 4 downstream │  │  cards + │  │ notify.py         │
    │ agents (state) │  │  uploads │  │ Telegram render   │
    └────────────────┘  └──────────┘  └───────────────────┘
```

### New files

- `tradingagents/dataflows/range_stats.py` — pure compute + multiple render formats
- `tradingagents/agents/utils/range_stats_tool.py` — LangChain `@tool` wrapper
- `tradingagents/dataflows/user_research.py` — extract / summarize / persist / list / delete
- `tests/test_range_stats.py`
- `tests/test_user_research.py`

### Modified files (shallow edits)

- `tradingagents/agents/utils/agent_states.py` — add `user_research_report: str` field
- `tradingagents/agents/utils/agent_utils.py` — re-export new tool
- `tradingagents/agents/analysts/market_analyst.py` — add `get_range_stats` to tools list, prompt mentions calling it first
- `tradingagents/agents/researchers/bull_researcher.py` — append `user_research_report` block to prompt
- `tradingagents/agents/researchers/bear_researcher.py` — same
- `tradingagents/agents/managers/research_manager.py` — same
- `tradingagents/agents/trader/trader.py` — same
- `tradingagents/graph/propagation.py` — initialize `user_research_report = ""`
- `tradingagents/graph/trading_graph.py` — `propagate(...)` accepts `user_research: str = ""`, writes into initial state
- `webui.py` — pre-analysis range-stats card, research upload component, per-ticker library manager
- `scheduler.py` — invoke range-stats render in daily report
- `notify.py` — `format_range_stats_telegram(stats)` helper
- `requirements.txt` and `pyproject.toml` — add `pypdf>=4.0,<6`

---

## Feature 1 — Range Stats

### `range_stats.py` API

```python
def compute_range_stats(symbol: str, trade_date: str) -> dict:
    """Returns structured dict: 4 windows × 3 metrics × 4 numbers."""

def format_range_stats_markdown(stats: dict) -> str:
    """Renders the dict as markdown tables (LLM tool + Telegram + WebUI markdown fallback)."""

def format_range_stats_for_webui(stats: dict) -> dict:
    """Returns raw numbers + color hints for streamlit card rendering."""
```

### Compute logic

1. Pull ~380 calendar days of OHLCV via existing `get_stock_data(symbol, start, end)` (covers 52 weeks + buffer for non-trading days)
2. Find the row matching `trade_date`; if `trade_date` is a non-trading day, fall back to the most recent trading day with data
3. Today's row → extract `open`, `close`, `volume`
4. For each lookback window in **trading days**:
   - 52w = 252
   - 6m = 126
   - 3m = 63
   - 1m = 21
5. Slice the last N trading days **including today** → compute `low`, `high` (matches Bloomberg/Yahoo "trailing 52w high" convention; if today sets a new high, position = 100%)
6. For each (metric ∈ {open, close, volume}, window) compute:
   - `pct_above_low = (current - low) / low * 100`
   - `pct_below_high = (current - high) / high * 100` (typically ≤ 0)
   - `position_pct = (current - low) / (high - low) * 100` (0–100, higher = closer to high)

### LLM-facing markdown format

```
# Price & Volume Range Stats for AAPL on 2026-05-06
Today: open=189.23  close=192.15  volume=58,231,400

## Close (192.15) vs historical ranges
| Window | Low    | High   | vs Low   | vs High  | Position |
|--------|--------|--------|----------|----------|----------|
| 52w    | 164.20 | 215.40 | +17.0%   | -10.8%   | 54.5%    |
| 6m     | 170.10 | 215.40 | +12.9%   | -10.8%   | 48.6%    |
| 3m     | 178.50 | 210.00 | +7.6%    | -8.5%    | 43.3%    |
| 1m     | 184.00 | 198.20 | +4.4%    | -3.0%    | 57.4%    |

## Open (189.23) vs historical ranges
[ same 4-row table for open ]

## Volume (58,231,400) vs historical ranges
[ same 4-row table for volume ]
```

### Edge cases

| Case | Behavior |
|------|----------|
| Insufficient history for a window (e.g. 100 days available → 6m and 52w n/a, but 1m and 3m valid) | Mark only the affected windows `n/a`, do not raise |
| `trade_date` is weekend/holiday | Use most recent trading row |
| `high == low` in window | `position = 50.0` with note |
| `volume == 0` (halt) | `pct_above_low` = `n/a` |
| yfinance / vendor failure | Raise `RangeStatsUnavailable`; tool returns "Range stats unavailable for SYMBOL today"; WebUI shows fallback |

### Caching

No new cache layer. The underlying `get_stock_data` already routes through vendor caches (yfinance / AlphaVantage). All three call sites (LLM tool, WebUI card, Telegram render) hit the same cache.

### Three integration points

#### 1. `market_analyst` LangChain tool

```python
@tool
def get_range_stats(
    symbol: Annotated[str, "ticker symbol"],
    trade_date: Annotated[str, "current trading date in YYYY-MM-DD"],
) -> str:
    """Compute today's open/close/volume vs 52w/6m/3m/1m high-low ranges
    (% above low, % below high, position-in-range). Use this to assess
    whether the stock is at a 52-week high/low or where it sits in recent ranges."""
    stats = compute_range_stats(symbol, trade_date)
    return format_range_stats_markdown(stats)
```

`market_analyst.py` adds `get_range_stats` to the tools list and the system prompt instructs:
> Always call `get_range_stats` first to anchor the price/volume context, then select indicators.

#### 2. WebUI card (pre-analysis)

Triggered as soon as the user enters a valid ticker (before clicking "Start analysis").
- 3 columns: Close / Open / Volume
- Each column: 4-row table with `Low | High | vs Low | vs High | Position`
- Color hints:
  - `position > 80` or `vs High > -2%` → red (near recent high)
  - `position < 20` or `vs Low < 2%` → green (near recent low)
- `compute_range_stats` is called directly from the WebUI, **not parsed back out of `market_report`** (LLM-generated text is unreliable to parse). Cost is near-zero thanks to the underlying cache.

#### 3. Telegram daily report

`notify.py::format_range_stats_telegram(stats)` produces a compact single message section:

```
📊 Range Stats (AAPL, 2026-05-06)
Close 192.15  → 52w +17%/-11% (54%)  1m +4%/-3% (57%)
Open  189.23  → 52w +15%/-12% (50%)  1m +3%/-4% (50%)
Vol   58.2M   → 52w +120%/-45% (62%) 1m +30%/-20% (55%)
```

Only the 52w and 1m windows are shown in Telegram (full 4-window table is in WebUI). `scheduler.py` includes this section in the assembled multi-message report.

---

## Feature 2 — User Research Upload

### Storage layout (per-user)

```
<user_home>/research/
  ├── _shared_for_run/
  │   └── <YYYYMMDD-HHMMSS>/
  │       ├── original.<ext>
  │       └── summary.md
  └── <TICKER>/
      ├── <hash>.<ext>            # original (PDF/MD/TXT)
      ├── <hash>.summary.md       # LLM summary
      └── <hash>.meta.json        # {filename, uploaded_at, size, pages}
```

`<hash>` = first 12 hex chars of SHA256 over file bytes — same file uploaded twice de-duplicates.

`_shared_for_run/<run-id>/` is **deleted immediately when the analysis run finishes** (per-run = strict one-shot).

### Ingest pipeline

```python
def ingest_research(
    file_bytes: bytes,
    filename: str,
    ticker: str | None,           # None = per-run only
    user_email: str,
    summarize_fn: callable,       # quick_thinking_llm injection point
    run_id: str | None = None,    # required when ticker is None
) -> dict:
    # 1. Extract text (pypdf for .pdf, raw decode for .md/.txt)
    text = _extract_text(file_bytes, filename)
    # 2. Hard cap at 100k chars going into the summarizer
    text = text[:100_000]
    # 3. Summarize once
    summary_md = _summarize(text, ticker, summarize_fn)
    # 4. Persist (per-ticker library OR per-run scratch)
    path = _save(file_bytes, summary_md, ticker, user_email, run_id)
    return {"path": path, "summary": summary_md, "filename": filename}
```

### Summarization prompt

```
You are summarizing a research report for ticker {ticker}.
Produce a markdown summary with:
- **Bottom line** (1-2 sentences)
- **Key thesis** (3-5 bullets)
- **Price targets / numbers** (if any)
- **Key risks** (3-5 bullets)
- **Notable quotes** (1-3, with page if known)

Keep total output under 1500 words. Source:
{text}
```

If the ticker is unknown (per-run upload before ticker is finalized), pass a placeholder; this is rare in practice because the WebUI requires a ticker before the upload component is enabled.

### State schema change

`agent_states.py`:

```python
user_research_report: str   # default ""
```

`graph/propagation.py` initializes to `""`. `graph/trading_graph.py::propagate(...)` accepts a new `user_research: str = ""` kwarg and writes to initial state.

### Assembling the field at run-time

In `webui.py`, when the user clicks "Start analysis":

```python
combined = []
# (a) per-ticker library entries the user kept checked
for meta in list_research(user_email, ticker, only_checked=True):
    combined.append(f"## {meta['filename']} (uploaded {meta['uploaded_at']})\n{meta['summary']}")
# (b) per-run uploads from this session
for f in just_uploaded_per_run:
    combined.append(f"## {f['filename']} (this run)\n{f['summary']}")
user_research_report = "\n\n---\n\n".join(combined) if combined else ""
```

Pass into `propagate(..., user_research=user_research_report)`.

### Downstream prompt changes (4 files)

`bull_researcher.py`, `bear_researcher.py`, `research_manager.py`, `trader.py` each gain a conditional block appended after the existing four reports:

```python
user_research_block = ""
if user_research_report.strip():
    user_research_block = (
        "\nUser-uploaded research (provided by the user; treat as one expert "
        "opinion among many, NOT ground truth):\n"
        f"{user_research_report}\n"
    )
```

The block is empty-string when no research is provided, so existing flows are byte-identical.

### WebUI UX

#### Main page upload area (between ticker input and date)

```
┌─ 📎 Research notes (optional) ─────────────────────┐
│  Drop PDF / .md / .txt here ⬆                       │
│  ☐ Save to <TICKER> library (else: use this run only)│
│                                                      │
│  Library for <TICKER>: 3 notes  [▾ manage]          │
└──────────────────────────────────────────────────────┘
```

- "Library for X" count refreshes when ticker changes
- After upload: filename + spinner "Generating summary…" → ✓ + [preview] (shows summary markdown)
- **Summarization is synchronous-blocking** — user waits 5-15s; "Start analysis" button disabled until done. (Async would require streamlit threading + session-state choreography; out of scope.)

#### Library manager (`▾ manage` expander)

```
┌─ AAPL research library ───────────────────────────────┐
│ ☑ Q4_2025_Earnings_Deep_Dive.pdf  (12 pages, 2 days   │
│   ago)                              [preview] [delete] │
│ ☑ Goldman_Tech_Outlook_2026.pdf   (28 pages, 1 week   │
│   ago)                              [preview] [delete] │
│ ☐ stale_old_report.pdf            (6 pages, 4 mo. ago)│
│                                     [preview] [delete] │
└────────────────────────────────────────────────────────┘
☑ = include in next analysis    ☐ = skip this time
```

- Checkboxes control which library entries feed into this run (per-run filtering on top of the long-lived library)
- preview opens summary markdown
- delete requires a second confirmation click

#### Telegram exposure

No upload via Telegram (low frequency, high implementation cost).
Daily report shows a one-liner: `📎 Used 2 user-uploaded research notes` so the user knows the AI was research-augmented.

### Limits

- Single file ≤ 20 MB
- Up to 5 files per upload action
- Source text into summarizer truncated at 100,000 chars
- All limits raise clear UI errors, never silent truncation

### Security / input validation

- Filenames sanitized (regex strip of path separators, control chars)
- Tickers validated via existing `validate_ticker` (commit 2c97bad)
- PDF parsing via `pypdf` (no code execution paths in malformed PDFs)
- Summary markdown rendered through streamlit `st.markdown` (HTML disabled by default)

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| F1: yfinance / vendor timeout | Raise `RangeStatsUnavailable`; LLM tool returns "Range stats unavailable for SYMBOL today"; WebUI card shows "Data unavailable, retry later"; Telegram section omitted |
| F1: insufficient history for one or more windows | Mark only those windows `n/a`; the rest compute normally; never block analysis |
| F2: PDF extraction fails | Raise `ResearchExtractionError`; WebUI shows "Could not extract text from <filename>"; do not save, do not call summarizer (cost saver) |
| F2: Summary LLM fails | Retry once; if still fails save original + `summary = "(summary failed, raw text excerpt) <first 2000 chars>"` so the upload is not wasted |
| F2: File > 20MB or > 5 files at once | Streamlit-level rejection with clear error |
| F2: `user_research_report == ""` | All 4 prompts skip the block (existing flows unchanged) |

---

## Testing

### `tests/test_range_stats.py`

- 60-day hard-coded OHLCV DataFrame (no network) → assert exact percentages
- Edge cases: `high == low`, `volume == 0`, < 21 days
- `trade_date` on weekend → falls back to last trading row
- Markdown format snapshot

### `tests/test_user_research.py`

- `_extract_text` for fixture .pdf / .md / .txt → expected text
- `ingest_research` with mock summarizer → file persisted at expected path; `<hash>` de-duplication on second upload
- Summary failure path → falls back to raw excerpt
- `list_research` / `delete_research` are scoped to the user's directory only

### End-to-end (per memory `feedback_e2e_test_after_changes.md`)

A full `worker.py` analysis run for AAPL with one small PDF uploaded, asserting:

- `market_report` contains the range-stats markdown table
- bull / bear / manager / trader prompts all received non-empty `user_research_report` (verify via debug log)
- WebUI card renders without exception
- Telegram render produces well-formed message text

`healthz` + `ast.parse` are NOT sufficient.

---

## Dependencies

```
pypdf>=4.0,<6
```

No DOCX, OCR, or extraction libraries beyond pypdf. No new ML/embedding deps. No DB migration.

---

## Rollback

- Feature 1 broken: remove `get_range_stats` from `market_analyst.tools`; comment out the WebUI card. The compute module can stay; nothing else depends on it.
- Feature 2 broken: `user_research_report` defaults to `""` in state; the if-guard in 4 prompts means analysis runs unaffected. Bad data lives in user directories only — deleting `<user_home>/research/` returns to clean state.

---

## Open questions

None at spec time. All decisions confirmed in brainstorming session.
