# Design Spec: Batch Ticker Data Download

**Date:** 2026-06-22
**Status:** Approved
**Approach:** B (Moderate — Batch + Per-Ticker ZIPs)

---

## 1. Overview

Add download functionality to the TradingAgents dashboard that allows users to export ticker analysis data in multiple modes:

1. **Single-ticker download** — Download all data for a specific ticker (all runs, events, stages).
2. **Batch download** — Download data for multiple selected tickers in one bundle.
3. **Select all** — Quickly select all available tickers for batch download.

Each download is a ZIP file containing the raw run data plus a generated `summary.csv` for easy tabular analysis.

---

## 2. Goals

- **G1:** Users can download all data for any single ticker with one click.
- **G2:** Users can select multiple tickers (via checkbox + "Select all") and download as a single bundle.
- **G3:** Each per-ticker ZIP includes both raw data (events, stages, decisions) and a human-readable `summary.csv`.
- **G4:** Large downloads stream efficiently without memory pressure.
- **G5:** The feature integrates naturally into the existing RunHistoryMenu and watchlist UI.

---

## 3. Non-Goals

- No cloud export (S3, etc.) — local download only.
- No real-time streaming ZIP — generate on demand.
- No server-side caching of generated ZIPs (future optimization).

---

## 4. Architecture

### 4.1 Backend

**New endpoint:**
- `POST /api/tickers/download` — accepts `{ tickers: string[] }`, returns `StreamingResponse` with ZIP.
- `GET /api/tickers/{ticker}/download` — returns a single ticker's ZIP directly.

**Helper functions (new file `web/server/download.py`):**
- `generate_ticker_zip(ticker: str) -> BytesIO` — creates a ZIP of `data/{TICKER}/` including:
  - All run directories (events, stages, run.json)
  - Generated `summary.csv`
- `generate_summary_csv(ticker: str) -> str` — reads all `run.json` files for a ticker and produces a CSV.

**Existing modules used:**
- `web/server/storage.py` — to walk tickers and read run data.
- `web/server/queries.py` — to format run data consistently.

### 4.2 Frontend

**Modified components:**
- `RunHistoryMenu.tsx` — add a "Download data" button in the dropdown header.
- `App.tsx` or `WatchlistRail.tsx` — add a button to open the batch download dialog.

**New component `BatchDownloadDialog.tsx`:**
- Modal dialog listing all tickers in the watchlist.
- Checkbox per ticker + "Select all" checkbox.
- "Download ({n})" button that calls the backend and triggers browser download.

**New API function in `lib/api.ts`:**
- `downloadTickers(tickers: string[])` — calls `POST /api/tickers/download` and triggers `URL.createObjectURL` download.

### 4.3 ZIP Structure

```
AAPL-data.zip
├── summary.csv
├── 2024-01-15_10-30-00_IDT/
│   ├── run.json
│   ├── events.jsonl
│   ├── stages/
│   │   ├── market.json
│   │   ├── debate.json
│   │   └── ...
│   └── llm_calls.jsonl
├── 2024-01-16_14-45-00_IDT/
│   └── ...
└── ...
```

### 4.4 Summary CSV Format

| Column | Type | Description |
|---|---|---|
| run_id | string | Unique run identifier (e.g., AAPL:2024-01-15T08:30:00Z) |
| ticker | string | Ticker symbol (e.g., AAPL) |
| started_at | ISO timestamp | Run start time |
| finished_at | ISO timestamp | Run end time (nullable) |
| status | string | queued / running / done / failed / cancelled |
| decision_action | string | BUY / SELL / HOLD / null |
| decision_target | number | Target price (nullable) |
| decision_confidence | number | 0.0–1.0 (nullable) |
| llm_provider | string | Provider used (nullable) |
| deep_think_model | string | Model for deep reasoning (nullable) |
| start_price | number | Price at run start (nullable) |
| total_duration_s | number | Total run duration in seconds (nullable) |

---

## 5. Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  USER ACTION: Click "Download data" in RunHistoryMenu           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: fetch GET /api/tickers/AAPL/download                 │
│  → Response: application/zip (stream)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend: zip_ticker_data("AAPL")                               │
│  ├── Walk data/AAPL/ → list run directories                   │
│  ├── For each run dir, collect (run.json, events, stages)       │
│  ├── Generate summary.csv from all run.json files                 │
│  └── Package into in-memory ZIP (BytesIO / tempfile)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: const blob = await response.blob()                    │
│  → trigger download via URL.createObjectURL(blob)             │
└─────────────────────────────────────────────────────────────────┘

──────────────────────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────────────┐
│  USER ACTION: Open Batch Download dialog → check "Select all"   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: POST /api/tickers/download                           │
│  Body: { tickers: ["AAPL", "NVDA", "TSLA"] }                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend: For each ticker:                                       │
│  ├── Call zip_ticker_data(ticker) → per-ticker ZIP               │
│  └── Add to bundle ZIP as {ticker}-data.zip                       │
│  Return: tickers-bundle.zip                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: Blob download → tickers-bundle.zip                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Error Handling

| Scenario | Backend Behavior | Frontend Behavior |
|---|---|---|
| Ticker has no data | Return empty ZIP with only summary.csv (empty) | Show "No data for {ticker}" or download empty ZIP |
| Invalid ticker name | Return 400 Bad Request | Show error toast |
| ZIP generation fails | Log error, return 500 | Show generic error toast |
| Large bundle | Stream ZIP chunks (StreamingResponse) | Show progress/loading state |
| Network failure during download | N/A (handled by browser) | Allow retry |

---

## 7. UI/UX Design

### 7.1 Single-Ticker Download
- **Location:** In `RunHistoryMenu` dropdown header, right side.
- **Icon:** Download arrow (↓).
- **Label:** "Download data" (tooltip).
- **Action:** Immediate download of `{TICKER}-data.zip`.

### 7.2 Batch Download Dialog
- **Trigger:** Button in top header bar or next to watchlist title.
- **Layout:**
  - Title: "Download Ticker Data"
  - Checkbox list of tickers (scrollable, max height ~400px)
  - "Select all" checkbox at the top
  - Footer: "Cancel" and "Download ({n})" buttons
- **Select all behavior:**
  - Checked → all tickers selected
  - Unchecked → all tickers deselected
  - If some tickers are manually unchecked after "select all", the header checkbox goes to indeterminate state.

### 7.3 Download States
- Default state: button shows "Download ({n})"
- Loading state: button shows "Preparing…" with disabled state
- Completed: auto-close dialog, show toast "Download started"

---

## 8. Security Considerations

- **Ticker sanitization:** Use existing `safe_ticker_component()` to prevent path traversal (already used in `storage.py`).
- **No arbitrary path access:** Only allow tickers from the watchlist / data directory.
- **ZIP Bomb protection:** Limit max download size per response (e.g., 100MB); return 413 if exceeded.

---

## 9. Testing Plan

### Backend Tests (`web/server/tests/test_download.py`)
- `test_generate_summary_csv_empty` — ticker with no runs → empty CSV with headers.
- `test_generate_summary_csv_with_data` — multiple runs → correct CSV rows.
- `test_generate_ticker_zip` — ZIP contains expected files (run.json, summary.csv).
- `test_download_single_ticker` — endpoint returns valid ZIP with correct content-type.
- `test_download_multiple_tickers` — endpoint returns bundle ZIP with per-ticker sub-ZIPs.
- `test_download_invalid_ticker` — endpoint returns 400.

### Frontend Tests
- `BatchDownloadDialog` renders with correct tickers.
- "Select all" toggles all checkboxes.
- "Download" button triggers API call with correct payload.
- Dialog closes after successful download.

---

## 10. Implementation Phases

| Phase | Scope | Files |
|---|---|---|
| 1 | Backend ZIP generation & CSV summary | `web/server/download.py`, `web/server/app.py` |
| 2 | Single-ticker download endpoint (`GET /api/tickers/{ticker}/download`) | `web/server/app.py` |
| 3 | Batch download endpoint (`POST /api/tickers/download`) | `web/server/app.py` |
| 4 | Frontend: Add download button to `RunHistoryMenu` | `RunHistoryMenu.tsx`, `api.ts` |
| 5 | Frontend: Build `BatchDownloadDialog` and integrate | `BatchDownloadDialog.tsx`, `App.tsx` |
| 6 | Add tests (backend + frontend) | `test_download.py`, component tests |

---

## 11. Spec Self-Review

- ✅ No placeholders or TBDs.
- ✅ Internal consistency: ZIP structure matches data directory layout; summary.csv fields match `RunRow` interface.
- ✅ Scope is focused (single feature: download). No scope creep.
- ✅ Ambiguity resolved: "Select all" toggles all tickers; invalid tickers return 400; empty tickers return empty ZIP.
- ✅ Follows existing style: uses `safe_ticker_component`, `storage.py` conventions, React functional components.
