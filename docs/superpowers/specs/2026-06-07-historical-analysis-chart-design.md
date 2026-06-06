# Historical Analysis Chart — Design

**Date:** 2026-06-07
**Status:** Approved
**Scope:** Backend history endpoint + frontend right-side drawer + recharts integration + verdict computation + real-time updates

## Goal

Add a historical analysis view to the TradingAgents dashboard that lets the
user visualize all past runs for a focused ticker on a single price chart and
evaluate, per run, whether the model's decision (BUY / SELL / HOLD with an
optional target price) was "right" within a user-controlled evaluation
window (Δ). Aggregate per-action stats update live as Δ and the HOLD
threshold are adjusted, so the user can hunt for the model's sweet spot.

Specifically:

1. **One enhanced right-side drawer** (`HistoricalAnalysisDrawer`) replaces
   the current `RunHistoryDrawer`. It owns the chart, the stats card, the
   sliders, and the run list.
2. **A price chart** renders the ticker's price across the visible time
   range, overlaid with one *tinted evaluation band* per run (from `T` to
   `T + Δ`), an *action dot* at each run's `T`, and a *target line* for
   BUY/SELL runs that have a target. The currently focused run (the one
   the main pane is showing) is rendered with stronger visuals — bolder
   band, bigger dot, thicker target line.
3. **Verdict computation is client-side and pure**, driven by
   `verdicts.ts`. The user drags a Δ slider and verdicts + stats update
   synchronously, with no backend round-trip.
4. **The backend serves raw yfinance bars** (with a TTL cache) and the
   list of runs for the ticker. The endpoint is `GET /api/tickers/{t}/
   history?range=<preset>`.
5. **Real-time updates** — while the drawer is open, bars are
   re-fetched on a configurable interval (default 30s), the active run's
   band grows live toward `T + Δ`, and its verdict flips from
   `incomplete_window` to a definite result the moment the window closes.
   A vertical "now" cursor on the chart makes the live edge obvious.

## Motivation

Today, the dashboard records decisions (action, target, start price) and
shows them in isolation, run-by-run, in the main pane. There is no way to
ask "how often has the model been right over the last 10 runs for MU?" or
"at what Δ does this model perform best?" without manually opening each
run, checking the target, and looking up the price. The data needed to
answer these questions is already on disk in `run.json` (decision,
target, start price, start time) and one yfinance call away (the actual
price path). This spec wires the two together with a chart-first UI.

The feature also doubles as a calibration tool: by sweeping Δ and the
HOLD threshold, the user gets a direct read on the model's reliability
across horizons and decision types.

## Non-Goals

- **Backfilling** runs whose `started_at` predates available yfinance
  data. Those runs render as `unknown: no_data` and are excluded from
  stats. (Matches the spec principle: graceful degradation > retroactive
  fetch.)
- **Cumulative P&L** based on the verdicts (modeling a hypothetical
  trade). A separate feature.
- **Multi-ticker overlay** (comparing two tickers' runs on one chart). A
  separate feature.
- **Per-ticker HOLD threshold** — the threshold is a global setting
  shared across all tickers. (Easy follow-up if needed.)
- **Exporting** verdict history to CSV. A separate feature.
- **Persisting** `deltaMs` and `rangePreset` across sessions. Defaults
  are good enough for v1.
- **Disk cache** for price bars across process restarts. The in-memory
  cache matches the existing live price feed's behavior.
- **Drift-correcting** yfinance splits/dividends in the chart. We use
  raw close prices; if a split occurs inside a run's window, the verdict
  may be misleading. Documented as a known limitation, not solved here.
- **Real-time bar updates for ranges that don't include "now"** (e.g.,
  user navigates to a historical 3-month view from a year ago — bars
  stay static; only the focused-ticker view auto-refreshes).

## Approach

A new backend module (`web/server/history.py`) wraps yfinance with a
TTL in-memory cache and exposes one new endpoint. A new frontend
drawer fetches that endpoint, holds the bars + runs in memory, and
runs a pure TypeScript verdict function on every Δ / threshold change.
The recharts chart renders the price line plus per-run reference
shapes. The existing `RunHistoryDrawer` is deleted; its trigger button
now opens `HistoricalAnalysisDrawer` with the same right-side slide
behavior. A real-time poll refreshes the bars on a user-configurable
interval (default 30s), so the price line and active run's band stay
live while the drawer is open.

## Storage Schema

**No new persistent storage.** The feature is read-only on disk.

- **Runs** are read from existing `~/.tradingagents/data/{TICKER}/{run_slug}/run.json` files via the existing `run_to_dict()` helper (which already exposes `decision_action`, `decision_target`, `start_price`, `start_price_at`, `started_at`, `finished_at`, `status`, `id`, and the metadata-enrichment fields).
- **Price bars** are fetched on demand from yfinance. The new module caches them in process memory (see Caching below).

### In-memory cache shape (`web/server/history.py`)

```python
_bar_cache: dict[tuple[str, str, date, date], tuple[float, list[Bar]]] = {}
# key: (ticker, interval, start.date(), end.date())
# value: (fetched_at_monotonic, bars)
# TTL by interval: 60s for 1m, 5min for 1h, 1h for 1d
```

The cache is best-effort: a process restart drops it; a stale entry
causes one extra yfinance call, not a correctness issue.

## API

### `GET /api/tickers/{ticker}/history?range=<preset>`

**Query parameters**
- `range` ∈ `{1d, 5d, 1mo, 3mo, 6mo, 1y, all, auto}` (default `auto`).
  - `auto` = span from the earliest run's `started_at` to "now" (capped
    to `1y` if the oldest run is more than a year old).
  - `all` = `1y` cap (yfinance's `period="max"` for `1d` interval).

**Response 200**
```json
{
  "ticker": "MU",
  "range": "auto",
  "range_start": "2026-01-15T14:30:00Z",
  "range_end":   "2026-06-07T19:00:00Z",
  "resolution":  "1h",
  "bars": [
    {"t": "2026-01-15T14:30:00Z", "o": 142.10, "h": 142.80, "l": 141.95, "c": 142.55, "v": 1284000},
    ...
  ],
  "runs": [
    {
      "id": "...",
      "ticker": "MU",
      "decision_action": "BUY",
      "decision_target": 160.00,
      "start_price": 148.20,
      "start_price_at": "2026-01-15T14:32:00Z",
      "started_at": "2026-01-15T14:32:00Z",
      "finished_at": "2026-01-15T14:48:00Z",
      "status": "done",
      "llm_provider": "...",
      "deep_think_model": "...",
      "quick_think_model": "...",
      "total_duration_s": 942.3,
      "stages": [...],
      "events": [...],
      "llm_calls": [...]
    },
    ...
  ]
}
```

`runs` is the full `RunDetail` shape (same as the existing `GET /api/runs/{id}`), so the drawer's run list rows can render the same fields as the existing drawer did.

**Error responses**
- `404 {"error": "no_runs", "detail": "Ticker has no completed runs"}` — when the ticker has zero runs on disk. (A ticker in the watchlist with no completed runs counts as zero.)
- `422 {"error": "invalid_range", "detail": "<preset>"}` — defensive guard for bad query strings.
- `502 {"error": "yfinance_failed", "detail": "<reason>"}` — when yfinance raises (network, delisted, etc.). Logged with ticker + exception.

**Edge case: empty bars**
If yfinance returns an empty DataFrame (e.g., ticker delisted, range outside available data), the endpoint returns `200` with `"bars": []` and the chosen `resolution`. The frontend distinguishes this from a hard failure and shows a "no data for this range" message with a preset hint.

### Resolution selection (`history.py:resolve_range`)

| Span (start..end) | yfinance `interval` | Reason |
|---|---|---|
| ≤ 7 days | `1m` | High resolution for short-horizon analysis. 1m data is fresh. |
| ≤ 60 days | `1h` | 1m data caps at 7d; 1h goes to 730d. |
| > 60 days | `1d` | 1h is wasteful; 1d is fine for multi-month views. |

The endpoint passes `period` computed from `range_start` / `range_end` and `interval` to `yf.Ticker(...).history(period=..., interval=...)`. (yfinance's `period` accepts strings like `"7d"`, `"60d"`, `"1y"`, `"max"` — the resolver uses these when possible, falling back to `start`/`end` ISO strings.)

## Capture Flow

N/A — read-only feature. No new writes to disk.

## UI Display

### Drawer trigger

The same button that today opens `RunHistoryDrawer` opens
`HistoricalAnalysisDrawer` after this change. Button location and label
are unchanged. The drawer slides in from the right with the same
animation as the existing drawer (matches the existing `ui.ts` open/
close state pattern).

### Drawer layout (top to bottom)

```
┌─────────────────────────────────────────────────────┐
│ MU  Range: [Auto ▾]                          [×]    │  ← Header
├─────────────────────────────────────────────────────┤
│  12 runs · 7 right · 3 wrong · 2 pending · 70% right│  ← HistoryStats
│  BUY: 5/8 right  SELL: 1/2 right  HOLD: 1/2 right  │
├─────────────────────────────────────────────────────┤
│                                                     │
│           HistoryChart (recharts)                   │
│   price line + per-run bands/dots/target lines      │
│   + vertical "now" cursor (dashed)                  │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Δ  [─────●─────────────] 1d                         │  ← HistoryControls
│ HOLD% [──────●──────] 1.0%                          │     (Δ slider)
│ Refresh: [30s ▾]                                    │     (HOLD threshold slider)
│                                                     │     (refresh interval dropdown)
├─────────────────────────────────────────────────────┤
│ 2026-06-07 14:32  BUY @ $148.20 → $160  ✓ +3.4%   │  ← Run list
│ 2026-06-06 11:15  SELL @ $152.00 → $148  ✗ −1.1%   │     (scrollable,
│ 2026-06-05 09:50  HOLD              ✓  +0.4%       │      fills remaining
│ ...                                                 │      height)
└─────────────────────────────────────────────────────┘
```

### `HistoryStats.tsx` — stats card

A compact card with the headline numbers in one row, then a per-action
breakdown:

```
12 runs · 7 right · 3 wrong · 2 pending · 70% right (excl. pending)
BUY  5/8 right   SELL  1/2 right   HOLD  1/2 right
```

- `rightPct = right / (right + wrong)`. Displayed as `N%`. When
  `right + wrong == 0`, the percentage is `—` and a small "no scored
  runs at this Δ" hint replaces it.
- `pending` counts the runs whose window is still in progress (verdict
  reason `incomplete_window`).
- The breakdown is a single inline line, no per-action mini-bars in v1.

### `HistoryChart.tsx` — recharts wrapper

Pure component. Props: `bars`, `runs`, `deltaMs`, `holdThresholdPct`,
`nowIso`, `selectedRunId`, `resolution`.

Renders a single `<LineChart>` with:

- **Price line** — `<Line dataKey="c" dot={false} stroke="#475569" strokeWidth={1.5} isAnimationActive={false} />`. Single series, no legend.
**Coordinate convention.** The chart uses recharts' `type="number"` + `scale="time"` X-axis, so all x values are **milliseconds since epoch** (`number`). The bars from the API arrive as `{ t: ISO_string, ... }`; the chart layer converts to `{ t: ms, ... }` once via `useMemo` before passing to recharts. `verdicts.ts` works on the ISO form (since `barsInWindow` does ISO comparisons) and returns ISO timestamps; the chart does the ms conversion at its boundary. This separation keeps verdict logic pure-string and the chart pure-number.

- **Per-run overlays** (one `<Fragment>` per run, keyed by `run.id`):
  - `<ReferenceArea x1={ms(run.startedAt)} x2={Math.min(ms(run.startedAt) + deltaMs, ms(nowIso))} fill={actionTint(run.action)} fillOpacity={run.id === selectedRunId ? 0.25 : 0.08} />` — the evaluation window. Clipped at `ms(nowIso)` so an in-flight run's band is visibly growing.
  - `<ReferenceDot x={ms(run.startedAt)} y={run.startPrice} r={run.id === selectedRunId ? 8 : 5} fill={actionColor(run.action)} stroke="#fff" strokeWidth={1} />` — the decision moment. Hover label shows action + start price.
  - `<ReferenceLine>` rendered only when `run.decisionTarget != null` AND `run.action !== 'HOLD'` (HOLD ignores target per the verdict rules). `y={run.decisionTarget}`, `x1={ms(run.startedAt)}`, `x2={ms(run.startedAt) + deltaMs}`, `stroke={actionColor(run.action)}`, `strokeWidth={run.id === selectedRunId ? 3 : 1.5}`, `strokeDasharray="4 2"` for unselected runs and solid for selected.
- **"Now" cursor** — `<ReferenceLine x={ms(nowIso)} stroke="#94a3b8" strokeDasharray="3 3" label={{ value: "now", position: "insideTopRight", fill: "#94a3b8", fontSize: 10 }} />`. Always visible.
- **Axes** — `<XAxis type="number" domain={[rangeStartMs, rangeEndMs]} tickFormatter={fmtTime(scale)} scale="time" />`. `<YAxis domain={['auto', 'auto']} tickFormatter={fmtPrice} width={60} />`.
- **Tooltip** — custom `<HistoryTooltip runs={runs} verdicts={verdicts} nowIso={nowIso} />` that resolves the hovered x to a timestamp and shows the verdicts for runs whose `T` falls within ±5 minutes of the cursor (or, if cursor is on a band, the run owning that band).

**Performance guard (downsample).** If `bars.length > 5000`, downsample
to ~3000 points by merging adjacent bars: take first `o`, last `c`,
max `h`, min `l`, sum `v`, `t` = first bar's `t`. Done in `useMemo`.
The verdict computation is **not** affected — it slices the original
full-resolution `bars` array by the run's window, not the chart data.

**Selected run logic.**
```
selectedRunId = historicalRunIdByTicker[ticker] ?? lastRunIdByTicker[ticker] ?? null
```
This is the same run the main pane is currently displaying. Existing
fields in `ui.ts` — no new state.

**Action colors and tints** (constants in `src/verdicts.ts` or a
sibling `colors.ts`):

| Action | Stroke | Tint (fill) |
|---|---|---|
| BUY | `#16a34a` (green-600) | `rgba(22, 163, 74, 0.1)` |
| SELL | `#dc2626` (red-600) | `rgba(220, 38, 38, 0.1)` |
| HOLD | `#6b7280` (gray-500) | `rgba(107, 114, 128, 0.1)` |

### `HistoryControls.tsx` — sliders + dropdown

Three controls in a compact column:

1. **Δ slider** — log-scale slider from 5m to 30d. Default `1d`. The label shows the current value formatted (`5m`, `1h`, `4h`, `1d`, `5d`, `14d`, `30d`). Snap points at the named values; in-between drag uses continuous log mapping.
2. **HOLD threshold slider** — linear 0.1% to 5.0%, step 0.1%. Default 1.0%. Label shows `X.X%`. Only affects HOLD verdicts.
3. **Refresh interval dropdown** — options: `Off`, `5s`, `15s`, `30s` (default), `1m`, `5m`. Maps to `historyPollIntervalMs` in the store (`Off` → `0`).

All three values are local component state except `holdThresholdPct`
and `historyPollIntervalMs`, which are persisted to `localStorage` via
the existing `ui.ts` `persist` middleware (keys
`ta-dashboard:holdThresholdPct` and
`ta-dashboard:historyPollIntervalMs`).

### Run list row (`RunListItem.tsx`)

Each row is a button that sets `historicalRunIdByTicker[ticker] = run.id`
on click (same pattern as the existing drawer). Renders:

```
[time]  [BUY @ $148.20 → $160.00]  [✓ +3.4%]
```

- The time is the run's `started_at`, formatted to the drawer's
  resolution scale (e.g. `Jun 7 14:32` for `1h`, `Jun 7` for `1d`).
- The middle segment shows action badge (color-coded), start price, "→"
  arrow, and target (if present and action ≠ HOLD). For HOLD or
  no-target BUY/SELL, only the action badge + start price.
- The verdict badge is right-aligned: `✓` (green) for right, `✗` (red)
  for wrong, `?` (gray) for unknown, with the reason subtext
  (`incomplete`, `no data`, `tie`, `no start price`). The `pctMove`
  is signed and color-coded (green up, red down).
- The currently selected row gets a stronger background and a left
  border accent (existing pattern, kept).

### Empty / loading / error states

- **Loading (initial fetch):** skeleton block where the chart goes, with the controls and stats hidden.
- **No runs (404):** centered message: *"No history yet for {TICKER}. Run an analysis to start tracking verdicts."* The range selector and chart are hidden.
- **No bars (200 with empty bars):** centered message: *"No price data for this range."* with a hint: *"Try a different range preset — yfinance 1m data is only available for the last 7 days."* The run list is still shown (with all rows `unknown: no_data`).
- **yfinance failed (502):** error card with the detail string, a "Retry" button (refetches), and a "Use 1d resolution" fallback button that retries with `range=1y`.

## Verdict Algorithm

### Inputs per run

From `run.json`: `id`, `started_at` (T), `decision_action`, `decision_target` (or `null`), `start_price` (or `null`).

### Window

A bar `b` is "in the window" for a run with start time `T` and delta `Δ` if `b.t >= T` AND `b.t <= T + Δ`. A bar that partially overlaps the window is fully included (a bar touching the window is in the window). The "last bar in window" is the bar with the greatest `t` in that set.

### Status rules (priority order)

| Action | Has target? | Right when… | Wrong when… | Unknown when… |
|---|---|---|---|---|
| BUY | yes | `max(high) >= target` | `max(high) < target` | no bars / incomplete / `start_price` missing |
| BUY | no | `close(last) > start_price` | `close(last) < start_price` | no bars / incomplete / `start_price` missing / tie |
| SELL | yes | `min(low) <= target` | `min(low) > target` | no bars / incomplete / `start_price` missing |
| SELL | no | `close(last) < start_price` | `close(last) > start_price` | no bars / incomplete / `start_price` missing / tie |
| HOLD | (target ignored) | `|pctMove| <= holdThresholdPct` | `|pctMove| > holdThresholdPct` | no bars / incomplete / `start_price` missing |

### `pctMove`

`pctMove = (close(last bar in window) - start_price) / start_price * 100`. Signed; positive = up.

### Incomplete rule

If `T + Δ > nowIso`, the window is still in progress. Status = `unknown`, reason = `incomplete_window`. The run is not counted in stats. The band on the chart is visually clipped at `nowIso` so the user can see the in-flight portion.

### No-data rule

If zero bars fall in the window (run predates available data, or the resolution+range combo excludes it), status = `unknown`, reason = `no_data`. Not counted.

### Tie rule (no-target BUY/SELL)

If `close(last bar) == start_price` exactly, status = `unknown`, reason = `tie`. The direction is genuinely ambiguous; counting it either way would bias the stats.

### Stats formula

```
counted   = right + wrong              # excludes all unknown variants
rightPct  = right / counted            # 0..1, null if counted == 0
pending   = count of incomplete_window
byAction  = { BUY: {r, w, u}, SELL: ..., HOLD: ... }
```

### `verdicts.ts` exports (pure, zero React/UI imports)

```ts
type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };

type Verdict = {
  runId: string;
  status: 'right' | 'wrong' | 'unknown';
  reason:
    | 'target_hit'            // BUY/SELL with target that was hit (right)
    | 'target_miss'           // BUY/SELL with target that was missed (wrong)
    | 'direction'             // no-target BUY/SELL, status carried by .status (right or wrong)
    | 'within_threshold'      // HOLD: |pctMove| <= holdThresholdPct (right)
    | 'threshold_exceeded'    // HOLD: |pctMove| > holdThresholdPct (wrong)
    | 'incomplete_window'     // T + Δ > now (unknown, counted as pending)
    | 'no_data'               // zero bars in window (unknown)
    | 'tie'                   // no-target BUY/SELL with close == start_price (unknown)
    | 'no_start_price'        // run is missing start_price (unknown)
    | 'unknown_action';       // defensive: action is not BUY/SELL/HOLD (unknown)
  pctMove: number | null;     // signed % from T to T+Δ
  targetHit: boolean | null;  // null for HOLD, no-target BUY/SELL
  maxHigh: number | null;     // for BUY target context
  minLow: number | null;      // for SELL target context
  endPrice: number | null;    // close(last bar in window)
};

type Stats = {
  total: number;
  right: number;
  wrong: number;
  unknown: number;
  pending: number;            // unknown AND reason == 'incomplete_window'
  rightPct: number | null;    // right / (right + wrong), null if counted == 0
  byAction: Record<'BUY' | 'SELL' | 'HOLD', { right: number; wrong: number; unknown: number }>;
};

export function barsInWindow(bars: Bar[], startIso: string, deltaMs: number, nowIso: string): Bar[];
export function computeVerdict(
  run: { id: string; startedAt: string; decisionAction: 'BUY' | 'SELL' | 'HOLD'; decisionTarget: number | null; startPrice: number | null },
  windowBars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Verdict;
export function computeStats(
  runs: Array<{ id: string; startedAt: string; decisionAction: 'BUY' | 'SELL' | 'HOLD'; decisionTarget: number | null; startPrice: number | null }>,
  bars: Bar[],
  deltaMs: number,
  holdThresholdPct: number,
  nowIso: string,
): Stats;
```

These three functions are the only place verdict logic lives. The
chart, the run list, and the stats card all consume their output.

## Real-time Updates

### Polling

The TanStack Query for the history endpoint is configured with
`refetchInterval: useUiStore(s => s.historyPollIntervalMs) || false`.
`false` disables polling (the "Off" option in the dropdown maps to
`0` → `false`). `staleTime: 0` so the timer is what drives refetches,
not cache age. Polling pauses automatically when the tab is hidden
(TanStack Query default).

### Cadence vs. resolution

| Resolution | Polling at 30s | Effect |
|---|---|---|
| `1m` | New bar every minute; chart updates within 30s of each new bar | Live |
| `1h` | New bar every hour; chart updates within 30s of each new bar | Live at the hour boundary |
| `1d` | One bar covering the whole day; chart updates at most daily | Effectively static during a day |

The "now" cursor is the only always-live element on the chart — it
moves every render and gives visual feedback even at `1d` resolution.

### Active run's band

For each tick of the polling interval, the band's `x2` re-evaluates
to `Math.min(startedAt + deltaMs, nowIso)`. The right edge creeps
rightward in 30s steps (or whatever interval is set). The moment
`nowIso >= startedAt + deltaMs`, the run's verdict flips from
`incomplete_window` to a definite result on the next recompute.

### Δ-drag is still instant

The Δ slider updates local component state. The next refetch (if
any) just replaces the underlying `bars` underneath. Verdict
recomputation is `useMemo`'d on `(runs, bars, deltaMs,
holdThresholdPct, nowIso)`, so a Δ drag with no concurrent refetch
triggers one synchronous recompute and one re-render.

### Recharts animation

`isAnimationActive={false}` on the `<Line>`. Without this, every
30s refresh would tween the line for ~300ms, which is jarring.
Reference shapes don't animate by default.

## Error Handling & Edge Cases

| Failure | Where caught | UX |
|---|---|---|
| Ticker has 0 runs | backend → 404 `no_runs` | Drawer shows "No history yet" hint with the ticker name |
| yfinance raises (network, delisted, etc.) | backend → 502 `yfinance_failed` | Drawer shows error card with the detail string and a "Retry" button |
| yfinance returns empty bars | backend → 200 `{bars: []}` | Drawer shows "No price data for this range" + preset hint |
| Run predates available bars | `verdicts.ts` → `unknown: no_data` | Run row shows gray `no data` badge; not counted in stats |
| Window still in progress (`T + Δ > now`) | `verdicts.ts` → `unknown: incomplete_window` | Run row shows `pending` badge; band clipped at `nowIso`; not counted |
| Tied direction (no-target BUY/SELL, `close == start_price`) | `verdicts.ts` → `unknown: tie` | Run row shows `tie` badge; not counted |
| `start_price` missing on run | `verdicts.ts` → `unknown: no_start_price` | Run row shows `no start price` badge; not counted |
| Invalid `range` preset sent | backend → 422 `invalid_range` | Defensive log + ignore; UI should not send these (preset is a fixed enum) |
| Backend timeout / slow | TanStack Query loading state | Loading skeleton; ticker pane is not blocked |
| 1m cap exceeded silently | `resolve_range` picks `1h` for spans 8–60d and `1d` for >60d | No surprise: user picked `1d`/`5d` they get 1m; picked `1mo` they get 1h |
| Run with `decision_action` outside {BUY, SELL, HOLD} | `verdicts.ts` → `unknown` with reason `unknown_action` | Defensive guard; logged once per unique value |
| Many runs with overlapping bands | chart renders all bands; visual density is a function of run count | Out of scope: filtering, collapsing. Documented as v2. |
| Stock split inside a run's window | Verdict uses raw high/low; may be misleading | Documented limitation. Out of scope. |
| User drags Δ slider while a refetch is in flight | TanStack Query returns the new data after fetch; the `useMemo` re-runs | No conflict; last-arriving data wins, consistent with React semantics |
| User opens drawer for a different ticker mid-fetch | The first fetch's `enabled` flips to `false`; query is abandoned | No leak: TanStack Query cancels in-flight requests on disable |

## Testing

### Backend (`web/server/tests/test_history.py` — new)

- `resolve_range('auto', runs)` picks `1m` for a 5-day span, `1h` for a 30-day span, `1d` for a 6-month span.
- `resolve_range('1d')` returns the right `(start, end, '1m')` regardless of runs.
- `resolve_range('1y')` returns the right `(start, end, '1d')`.
- `resolve_range('all')` returns `('1y', '1d')` cap.
- `fetch_history_bars` calls `yf.Ticker(...).history(...)` with the right args; cache hit on a second call within TTL avoids the second yfinance call (monkey-patch `yf.Ticker` to count).
- Cache TTL expiration: monkey-patch `time.monotonic`, set the entry's age past the interval's TTL, confirm re-fetch on next call.
- `get_history` returns 404 when the ticker has 0 runs.
- `get_history` returns 502 when yfinance raises (mock to raise `yf.exceptions.YFException`).
- `get_history` returns `bars: []` when yfinance returns an empty DataFrame.
- `get_history` returns 422 for an invalid range preset.

### Backend API integration (`web/server/tests/test_api.py` — extend)

- `GET /api/tickers/{t}/history?range=auto` returns 200 with the expected shape.
- 404 for a ticker with no runs.
- 422 for an invalid range.

### Backend test seam (`web/server/tests/fixtures/fake_yfinance.py` — extend)

Add a `fake_history(ticker, period, interval, start, end)` method that
returns a deterministic OHLCV DataFrame from a small fixture file. The
existing `TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED=1` env var extends
to also stub `history.fetch_history_bars` (single env var covers both
external-data stubs since they're conceptually identical).

### Frontend (`web/frontend/src/verdicts.test.ts` — new, Vitest)

- BUY with target: `max(high) >= target` → right; otherwise wrong.
- BUY target hit only at the very last bar in window.
- SELL with target: `min(low) <= target` → right.
- HOLD within threshold (`|pctMove| <= holdThresholdPct`) → right; over threshold → wrong.
- BUY no-target: `close > start` → right; `close < start` → wrong; `close == start` → tie.
- SELL no-target: `close < start` → right; `close > start` → wrong; tie.
- `start_price` missing → `unknown: no_start_price`.
- Empty window → `unknown: no_data`.
- Window where `T + Δ > nowIso` → `unknown: incomplete_window`; flip the test's `nowIso` past `T + Δ` and re-run → verdict becomes a definite result.
- `computeStats` with mixed runs (BUY right, SELL wrong, HOLD pending, HOLD no_data) — assert the per-action counts and `rightPct` math.
- `barsInWindow` edge cases: window crossing many bar boundaries, single-bar window, empty bars input.

### Frontend (`web/frontend/src/HistoryChart.test.tsx` — new, Vitest + Testing Library)

- Renders `<LineChart>` with the input bars.
- Renders exactly one `<ReferenceArea>`, one `<ReferenceDot>` per run (query by class or by ARIA — recharts assigns stable data attributes).
- Renders `<ReferenceLine>` for each BUY/SELL run with a target; **does not** render for HOLD runs.
- Selected run's reference shapes have the stronger props (snapshot assertion on rendered SVG, or attribute checks on `fill-opacity` / `r` / `stroke-width`).
- "Now" cursor `<ReferenceLine>` is always present.

### Frontend manual / integration checklist (executed pre-merge)

- Ticker with 0 runs → drawer opens with the empty state.
- Ticker with 1 run → 1 dot, 1 band, 1 target line (if BUY/SELL with target).
- Ticker with 5+ runs at varying times → chart readable, bands distinguishable, target lines visible.
- Drag Δ from `5m` to `30d` → verdicts flip in real time, stats update, run list badges update.
- Drag HOLD threshold from `0.5%` to `5.0%` → HOLD verdicts flip; BUY/SELL untouched.
- Switch range preset `1d` → `1mo` → `1y` → bars update, all in-range runs still shown, out-of-range runs disappear from the list (or show as `no_data` if they predate the new range).
- Click a run in the list → main pane loads that run, that run's chart shapes become bold.
- yfinance stubbed off (`TRADINGAGENTS_DASHBOARD_DISABLE_PRICE_FEED=1`) → drawer still works with fixture bars.
- Refresh dropdown set to `Off` → chart stops auto-refreshing.
- Refresh dropdown set to `5s` → chart updates noticeably faster (5s gaps between refetches).
- Open drawer, watch a HOLD run with a tight `Δ` for ~1 minute → band's right edge creeps right; verdict badge stays `pending` until the window closes, then flips.
- "Now" cursor visible on the chart at all resolutions, moves on every refetch.
- 1m × 7d (~10k bars) + 5 runs → chart renders in <500ms after a Δ drag (manual stopwatch).
- 1y × 1d (~365 bars) + 20 runs → trivially fast.

## Files Touched

### Backend
- `web/server/history.py` — **new** — `resolve_range`, `fetch_history_bars` (with in-memory TTL cache), `get_history` orchestrator, `_bar_cache`.
- `web/server/routes.py` (or equivalent route file) — register `GET /api/tickers/{ticker}/history`.
- `web/server/tests/fixtures/fake_yfinance.py` — add `fake_history`; extend the disable env var to also stub `history.fetch_history_bars`.
- `web/server/tests/test_history.py` — **new**.
- `web/server/tests/test_api.py` — extend with the new endpoint's integration cases.
- `pyproject.toml` — no new deps (yfinance already a dep).

### Frontend
- `web/frontend/src/components/HistoricalAnalysisDrawer.tsx` — **new** — top-level right-side drawer. Owns the query, the local Δ and range state, the layout.
- `web/frontend/src/components/HistoryChart.tsx` — **new** — recharts wrapper (pure).
- `web/frontend/src/components/HistoryStats.tsx` — **new** — stats card (pure).
- `web/frontend/src/components/HistoryControls.tsx` — **new** — Δ slider, HOLD threshold slider, refresh interval dropdown.
- `web/frontend/src/components/RunListItem.tsx` — **new** — row with action, target, verdict badge, pct move.
- `web/frontend/src/components/RunHistoryDrawer.tsx` — **deleted** (replaced by `HistoricalAnalysisDrawer`).
- `web/frontend/src/verdicts.ts` — **new** — `barsInWindow`, `computeVerdict`, `computeStats`, action colors and tints.
- `web/frontend/src/verdicts.test.ts` — **new**.
- `web/frontend/src/HistoryChart.test.tsx` — **new**.
- `web/frontend/src/lib/api.ts` — add `getTickerHistory`, `Bar`, `HistoryResponse`, `Verdict`, `Stats` types.
- `web/frontend/src/store/ui.ts` — add `historyOpenByTicker` + `setHistoryOpen`, `holdThresholdPct` + setter, `historyPollIntervalMs` + setter. All three persisted via existing `persist` middleware.
- `web/frontend/src/App.tsx` — swap `RunHistoryDrawer` import → `HistoricalAnalysisDrawer`.
- `web/frontend/package.json` — add `recharts` (and `@types/recharts` if not bundled).

### Docs
- `docs/superpowers/specs/2026-06-07-historical-analysis-chart-design.md` — **this file**.

## Out-of-Scope Follow-Ups (for a future spec)

- **Multi-ticker overlay** — comparing two tickers' runs on one chart (e.g. "is MU's model better than DELL's at 1d?"). Needs shared time axis + per-ticker color series.
- **Cumulative P&L** based on the verdicts — model a hypothetical trade using each run's action + target + actual price path. Would extend `verdicts.ts` with a `simulateTrade` function and add a new card to the drawer.
- **Per-ticker HOLD threshold overrides** — currently global; the store schema and the slider are both global. Per-ticker is a one-key change in `ui.ts` and a per-ticker persistence key.
- **Exporting verdict history to CSV** — backend endpoint that returns CSV; frontend button in the drawer header.
- **Persisting `deltaMs` and `rangePreset` across sessions** — Zustand `persist` keys; trivial to add when desired.
- **Disk cache for price bars** — survives process restarts. Would require a small SQLite or LMDB store and a TTL eviction policy.
- **Per-run focus / drill-down** — clicking a run's dot zooms the chart to `T..T+Δ`. Different mental model from the time-axis default; could be a toggle.
- **Split / dividend adjustment** — feeds yfinance's `actions=True` and applies split factors to historical bars. Somewhat invasive; affects the verdict math.
- **Filtering the run list** by action, date, or verdict status. Useful once a ticker has 50+ runs.
- **Collapsing overlapping bands** when many runs cluster in a tight window. Visual de-clutter only; doesn't affect the math.
