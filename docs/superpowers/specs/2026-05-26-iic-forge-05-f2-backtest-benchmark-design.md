# IIC-FORGE-05 — F2 Forward-Test Harness + Leaderboard — Design

| Field | Value |
|---|---|
| **Track** | IIC-FORGE |
| **Document** | 05 |
| **Scope** | Per-phase design for F2 (Validation: backtest + benchmark). One level deeper than [the program-level spec §7](2026-05-25-iic-forge-program-design.md). |
| **Base engine** | TauricResearch/TradingAgents v0.2.5 (F1 shipped to `main`) |
| **Owner** | Ziwei |
| **Date** | 2026-05-26 |
| **Status** | Ready for implementation planning |
| **Supersedes** | — |
| **Amends** | — (operates within the program design's existing schema and risk register) |
| **Relates to** | [IIC-FORGE-03 program design](2026-05-25-iic-forge-program-design.md) §7 F2, §8 R10, §10 ADR-NEW-3; [IIC-FORGE-04 F1 plan](../plans/2026-05-25-iic-forge-04-f1-decision-core.md) |
| **Companion plan (next)** | `docs/superpowers/plans/2026-05-26-iic-forge-05-f2-backtest-benchmark.md` (output of `superpowers:writing-plans`) |

## Quick links

- §1 Executive summary
- §2 Anchoring decisions
- §3 Architecture and module layout
- §4 Data model (no schema changes)
- §5 Two invocation modes
- §6 Exit-gate execution mechanics
- §7 Persona prompt wiring
- §8 Reflection / outcome_log integration
- §9 Testing strategy
- §10 Risks (F2 additions to the program register)
- §11 Always-on operation (24/7)
- §12 Out of scope
- §13 Open questions deferred to implementation

---

## 1 · Executive summary

F2 ships a **forward-testing harness** with a **real-time leaderboard** over the SQLite store F1 built. The harness has one code path that handles both live forward tests (held 30 calendar days from `today`) and back-dated runs (the exit-gate path, where `start_date = today − 30 days` so the window has already elapsed). The same shape later powers F5's brief-scoped backtests.

Four things change relative to F1:

1. **Persona prompts go from cosmetic to behaviorally meaningful.** `system_prompt_fragment` and `risk_debate.weights` get wired into the agent prompts and the risk-debate aggregation. Without this, F2's per-persona comparison is reporting numbers against three near-identical strategies.
2. **A new `tradingagents.backtest` package** owns the forward-test lifecycle, the leaderboard, and the deterministic Markdown report. No schema changes — the `backtests` and `backtest_runs` tables F1 designed upfront are exactly the shape we need.
3. **A multi-source, resolution-agnostic price layer** lands as a first-class abstraction. `PriceFallbackChain` mirrors the agents' existing fallback chain (yfinance → polygon → alpha_vantage → futu); F2 implements only the yfinance adapter, but the `PriceSource` protocol and `Resolution` enum make registering Polygon / Futu / a 1-min source later a single-file addition.
4. **The reflection / scoring story gains a persona-aware path.** The existing `_resolve_pending_entries` reflection loop continues writing to the legacy filesystem `memory_log`, untouched. F2 adds a second write path: when a forward test matures, one `outcome_log` row is written keyed by the original `run_id`, tagged with `persona_id` and `backtest_id`.

The exit gate is a single CLI invocation that takes ~15 minutes of compute, writes 15 `backtest_runs` rows (5 tickers × 3 personas) into one `backtests` row, and produces a Markdown report whose content is byte-equal on rerun modulo a single timestamp line. 24/7 operation is supported via a `forge backtest sweep` one-shot maturation pass (cronnable) and a `forge backtest watch` long-running daemon (the always-on path); both share the same maturation logic and survive restarts cleanly because all state is in SQLite.

## 2 · Anchoring decisions

Settled during brainstorming. Each one rules out alternatives that would have changed the design materially.

### D1 — Forward testing, not back-testing

A forward test is one persona × one ticker × one decision held over a 30-day window. **The graph is invoked exactly once per (ticker × persona)** — not at every historical decision date. The decision is captured at `start_date`, translated to a position (+1/0/−1), and held for 30 calendar days. At `end_date` the position is closed, daily mark-to-market is computed for the entire window in one batch, and final metrics are written.

This shape is forced by what the user actually wants: personas produce strategies; users accept them; the system tracks how those accepted strategies perform from acceptance onward. It also keeps LLM cost predictable — 15 graph runs per harness invocation rather than the ~90 a "point-in-time replay every 5 days" model would have required.

### D2 — Same code path for live and exit-gate; back-date via `start_date`

The exit gate doesn't wait 30 real days. It passes `start_date = today − 30 days`, the harness detects `end_date ≤ today`, and maturation runs inline. **No `--immediate-close` flag** — the calendar decides. This means the harness has one mode, exercised two ways:

| Path | `start_date` | When maturation runs |
|---|---|---|
| Live forward test | `today` | At `end_date` — by `forge backtest close`, a future F4 sweep, or as a side-effect of running the leaderboard |
| Exit-gate validation | `today − 30 days` | Inline, immediately after all 15 graph runs complete |

### D3 — Long/short SELL semantics

`BUY → position=+1, HOLD → position=0, SELL → position=−1`. Honest forward-test of the persona's directional conviction — a momentum persona that flags a top can demonstrate alpha by being short into a drawdown. No shorting cost, no borrow fee, no slippage modeling — keep the simulator pure. The leaderboard reports unleveraged signal-adjusted return.

### D4 — Persona prompt wiring lands as part of F2

`system_prompt_fragment` is injected into the analyst, research-manager, trader, and portfolio-manager system prompts when a persona is active. `risk_debate.weights` is applied as a multiplier at the risk-debate aggregation step. Without these, F2's per-persona comparison would be three near-identical lines. Boundary tests assert the fragment text actually reaches the LLM call.

### D5 — `--strict-historical` assertion at the data-flow boundary

A thin wrapper around yfinance / Polygon / Alpha Vantage calls asserts `returned_date ≤ trade_date`. **Enabled automatically when `start_date < today`** (i.e., for back-dated runs including the exit gate); a no-op for live forward tests (`trade_date = today` means data can't return future dates anyway). Disabled for the live `deepdive` CLI path. If any tool leaks future data, back-dated runs fail loudly rather than silently overstating alpha. Mitigates R10 (over-trusting framework alpha).

### D6 — No schema changes

The `backtests` and `backtest_runs` tables F1 designed are sufficient. All forward-test lifecycle state lives in the JSON `backtest_runs.metrics` column, with documented shape (§4).

### D7 — Multi-source price data via fallback chain; resolution-agnostic from day one

A `PriceSource` protocol with a `PriceFallbackChain` mirrors the agents' existing `DataVendorError` fallback (program §8 R8). Default chain: yfinance → polygon → alpha_vantage → futu. F2 implements only the yfinance adapter; the others are stub registrations the user (or F3) fills in later — but the abstraction is in place so adding a source is "register one more `PriceSource` implementation."

**Resolution is parameterized from the API down.** `PriceSource.get_bars(ticker, start, end, resolution)` accepts `Resolution.DAILY` or `Resolution.ONE_MIN`. The simulator operates on whatever return-series length the `Bars` object carries — 22 datapoints (daily) or ~8,580 (1-min over 30 days) — without code change. F2 ships `DAILY` only; `ONE_MIN` raises `NotImplementedError` from the yfinance adapter (yfinance is limited to ~7 days of 1-min data, insufficient for 30-day forward tests). When Polygon or another paid source is registered with `ONE_MIN` support, `harness.run_watchlist(..., resolution=Resolution.ONE_MIN)` works with no harness, simulator, or report changes.

**Contradictions across sources are NOT reconciled.** F2 trusts the highest-priority available source. Same philosophy as the agents.

## 3 · Architecture and module layout

### New `tradingagents.backtest` package

The harness is a peer to `tradingagents.secretary` — it owns its DB writes, its lifecycle state, and its report rendering. It calls into `TradingAgentsGraph` for fresh decisions (watchlist mode) and into `tradingagents.persistence.store` for reads/writes. It is NOT a graph node — backtests aggregate ACROSS many runs, which is the wrong shape for a per-run node.

```
tradingagents/backtest/
├── __init__.py
├── harness.py          # BacktestHarness — orchestrator for both invocation modes
├── simulator.py        # Pure functions: signal → position → return-series PnL (resolution-agnostic)
├── prices.py           # PriceSource protocol, PriceFallbackChain, Resolution enum, Bars dataclass
├── sources/
│   ├── __init__.py
│   ├── yfinance_source.py     # F2 ships this one; daily only
│   ├── polygon_source.py      # stub registration; user fills in later
│   ├── alpha_vantage_source.py# stub registration; user fills in later
│   └── futu_source.py         # stub registration; user fills in later
├── strict_historical.py # The trade_date <= cutoff assertion wrapper (applies across sources)
├── leaderboard.py      # Read-only aggregations over backtest_runs (lazy MTM via PriceFallbackChain)
├── report.py           # Deterministic Markdown report renderer
├── reflection.py       # On-close hook — writes one outcome_log row per matured forward test
└── sweep.py            # Stateless maturation pass — used by `forge backtest sweep` and `watch`
```

**`PriceSource` protocol sketch:**

```python
class Resolution(StrEnum):
    DAILY = "1d"
    ONE_MIN = "1m"

@dataclass(frozen=True)
class Bars:
    ticker: str
    resolution: Resolution
    bars: list[tuple[datetime, float]]   # (timestamp, close_price)
    source: str                          # e.g., "yfinance" — set by the producer

class PriceSource(Protocol):
    name: str
    supports: set[Resolution]
    def get_bars(self, ticker: str, start: date, end: date, resolution: Resolution) -> Bars: ...

class PriceFallbackChain:
    def __init__(self, sources: list[PriceSource]): ...  # ordered by priority
    def get_bars(self, ticker, start, end, resolution=Resolution.DAILY) -> Bars:
        # try each source that `supports` the resolution; return the first success
        # if all fail, raise PriceDataUnavailable (caught by harness → status=errored)
```

The simulator consumes `Bars` without caring whether it's 22 daily closes or 8,580 1-min bars — the return-series math is identical at both resolutions.

### `tradingagents.personas` extensions

```
tradingagents/personas/
├── prompt_overlay.py   # NEW — applies persona.system_prompt_fragment to existing prompts
└── risk_weights.py     # NEW — applies persona.risk_debate.weights at risk-debate aggregation
```

Both are pure helper modules — they take an existing prompt string (or risk-debate aggregation step) and a `Persona`, return a modified version. Called from `tradingagents.graph.setup.GraphSetup.setup_graph()` when a persona is active. The change to `setup.py` is one wiring line per overlay point; the wiring helpers are unit-tested in isolation.

### New CLI surface

```
cli/forge.py  (new Typer command group, registered in cli/main.py)
  forge backtest start --watchlist=AAPL,MSFT,GOOG,NVDA,TSLA --start-date=2026-04-26
                       [--resolution=daily|1min]    # default daily; 1min raises NotImplementedError until a 1min source is registered
                       [--sources=yfinance,polygon] # override fallback chain order
  forge backtest start --brief-id=<id>
  forge backtest leaderboard [--open|--closed|--all] [--persona=macro]
  forge backtest report <backtest_id>
  forge backtest sweep                              # one-shot: mature any open tests whose scheduled_close_date <= today
  forge backtest watch [--interval=300]             # long-running: loop sweep every N seconds (default 5 min)
  forge backtest close <btr_id>                     # manual single-test maturation (mostly for tests)
```

The CLI is the user-facing surface for F2 until F5 puts a Streamlit dashboard on top.

### Data flow — watchlist mode

```
forge backtest start --watchlist=... --start-date=T
        │
        ▼
BacktestHarness.run_watchlist(tickers, personas, start_date=T)
        │
        ├─► insert backtests row (status=open)
        │
        ├─► for each (ticker, persona) in tickers × personas:
        │       │  (with strict_historical enabled when T < today)
        │       ├─► TradingAgentsGraph(persona=p).propagate(ticker, trade_date=T)
        │       │     (RunRecorder writes runs row + costs row + filesystem artifacts)
        │       │
        │       ├─► entry_price = prices.at(ticker, T)
        │       ├─► position = {BUY:+1, HOLD:0, SELL:-1}[decision]
        │       └─► insert backtest_runs row, status=open, metrics={entry snapshot}
        │
        ├─► if end_date <= today:                       # auto-maturation path
        │       for each open backtest_runs row:
        │           daily_returns = simulator.compute_daily(prices, entry, end_date)
        │           write final metrics, status=closed
        │           reflection.write_outcome_log_row(...)
        │       update backtests row, status=closed
        │       Report.render(backtest_id) → data/backtests/<backtest_id>/report.md
        │
        └─► else (live mode):
                # forward tests left open; maturation deferred
```

### Data flow — brief-scoped mode (called by F5)

```
BacktestHarness.run_brief_scoped(brief_id)
        │
        ├─► read briefs.run_ids
        ├─► for each run_id:
        │       runs row → (ticker, persona_id, decision, started_ts)
        │       entry_date = started_ts::date
        │       entry_price = prices.at(ticker, entry_date)
        │       insert backtest_runs row (status=open, metrics seeded from run)
        │
        ├─► triggered_by_brief_id = brief_id on the backtests row
        │
        └─► (same maturation logic as watchlist mode — inline if end_date <= today)
```

The brief-scoped mode **never re-invokes the graph**. The persona decisions are already persisted in `runs`; the harness just opens forward tests on them.

## 4 · Data model (no schema changes)

### `backtests` row — one per harness invocation

| Column | Watchlist mode | Brief-scoped mode |
|---|---|---|
| `backtest_id` | autoinc | autoinc |
| `triggered_by_brief_id` | NULL | brief_id from the F5-accepted prompt |
| `universe` | JSON list of N tickers | JSON list of tickers from the brief |
| `start_date` | user-supplied (or `today − 30` for exit gate) | `briefs.generated_ts::date` |
| `end_date` | `start_date + 30` calendar days | `start_date + 30` calendar days |
| `status` | `open` until all `backtest_runs` close; then `closed` | same |
| `report_path` | `backtests/<backtest_id>/report.md` (relative to `iic_data_dir`) | same |
| `created_ts` | now() | now() |

### `backtest_runs.metrics` JSON shape

Fixed columns: `btr_id`, `backtest_id`, `persona_id`, `ticker`. All lifecycle state lives in `metrics`:

```json
{
  "status": "open" | "closed" | "errored",
  "run_id": "<runs.run_id that produced this decision>",
  "decision": "BUY" | "HOLD" | "SELL",
  "position": 1 | 0 | -1,
  "entry_date": "2026-04-26",
  "entry_price": 213.45,
  "benchmark": "SPY",
  "benchmark_entry_price": 521.12,
  "scheduled_close_date": "2026-05-26",
  "resolution": "1d",                       // "1d" | "1m"
  "price_source": "yfinance",               // string if uniform; list-of-pairs e.g. [["yfinance","2026-04-26..2026-05-10"],["polygon","2026-05-11..2026-05-26"]] if mixed

  // populated on close:
  "close_date": "2026-05-26",
  "exit_price": 219.30,
  "benchmark_exit_price": 528.05,
  "total_return": 0.0274,                   // signal-adjusted: position * (exit - entry) / entry
  "benchmark_return": 0.0133,
  "alpha": 0.0141,                          // total_return - benchmark_return
  "returns": [...],                         // signal-adjusted return series at the run's resolution
                                             //   daily: ~22 datapoints; 1min: ~8580 datapoints over 30 days
  "sharpe": 1.42,                           // annualized from `returns` (annualization factor depends on resolution)
  "max_drawdown": -0.018,
  "win_rate": 0.59,                         // fraction of `returns` > 0
  "holding_days_elapsed": 30,

  // populated only when status = errored:
  "error": "string",                        // includes which source(s) failed when relevant
  "errored_sources": ["yfinance", "polygon"]
}
```

**Why store the return series?** The leaderboard needs intraday MTM. Sharpe needs a return series. Storing the full mark-to-market datapoints on close means reports never re-fetch prices — they aggregate from frozen JSON, which is what makes the report byte-equal on rerun. At daily resolution the series is ~22 points; at 1-min over 30 days it's ~8,580 points, still well within SQLite TEXT-column limits.

**Annualization factor for Sharpe:** `√252` for daily, `√(252 × 390)` for 1-min (US market). Stored alongside `sharpe` implicitly via `resolution`; the simulator picks the right factor.

### Foreign-key threading

- `metrics.run_id` (string in JSON) → `runs.run_id` — soft FK, used by `outcome_log` writes and by report rendering. Not a SQL constraint.
- `backtest_runs.backtest_id` → `backtests.backtest_id` — hard FK, defined in F1 schema.
- `backtests.triggered_by_brief_id` → `briefs.brief_id` — nullable hard FK, defined in F1 schema.

### Cost-guard surface

One new config key: `backtest_max_concurrent_graph_runs: int = 5`. Measurement always on (counts concurrent graph runs, logged to `costs`). Enforcement gated by `cost_guard_enabled` (default False), per the program design Appendix A.

## 5 · Two invocation modes

### Watchlist mode

The F2 exit-gate path. Manually invoked from the CLI; potentially scheduled later by F4. Generates fresh persona decisions, opens forward tests.

**Inputs:** ticker list, persona list (defaults to all loaded personas), start_date (defaults to today), end_date (defaults to start_date + 30 days).

**Behavior:** for each (ticker × persona), invoke the graph at `trade_date=start_date`. Strict-historical assertion is ON automatically when `start_date < today`. Open forward tests using the resulting decisions. If `end_date ≤ today`, mature inline; otherwise leave open.

### Brief-scoped mode

The F5 path — called when a user accepts a "run a backtest?" post-delivery prompt (program design ADR-NEW-3). Both modes coded in F2 so F5 has the API to call; only watchlist is exercised by the F2 exit gate.

**Inputs:** brief_id.

**Behavior:** read `briefs.run_ids`, resolve to (ticker, persona, decision, started_ts) tuples. Open forward tests using the persisted decisions — **no fresh graph invocation**. `entry_date = briefs.generated_ts::date`. `triggered_by_brief_id` is set so the result can be traced back to the brief that originated it.

**Implication for the user experience:** if a brief is 7 days old when the user accepts the backtest prompt, the forward tests are already 7 days into their 30-day window, and the remaining 23 days play out forward. This is correct — it measures "how is the strategy doing relative to when the user got the recommendation."

## 6 · Exit-gate execution mechanics

This is the load-bearing question "how do we ship F2 without waiting 30 real days." The answer: back-date.

### The command

```bash
forge backtest start \
  --watchlist=AAPL,MSFT,GOOG,NVDA,TSLA \
  --start-date=2026-04-26
# end_date defaults to start_date + 30 calendar days = 2026-05-26
# end_date <= today (2026-05-26) → harness matures inline automatically
```

### Step-by-step

1. **Insert `backtests` row** — status=open, universe=5 tickers, start_date=2026-04-26, end_date=2026-05-26.
2. **Strict-historical mode enabled** because `start_date < today`.
3. **For each of 15 (ticker × persona) pairs (sequential, ~1 min each):**
   - `TradingAgentsGraph(persona=p).propagate(ticker, trade_date="2026-04-26")` — agents reason using data only up to 2026-04-26 (this is the existing F1 smoke-test pattern, see commit `4d5b0b5 fix(smoke): use a past trade_date so yfinance has historical OHLCV`). RunRecorder writes one `runs` row.
   - `Simulator.open_position(decision)` → insert `backtest_runs` row with entry snapshot, status=open.
4. **Inline maturation pass** (because `end_date ≤ today`):
   - For each open `backtest_runs` row: fetch the ~22 historical daily closes for `[2026-04-26..2026-05-26]`, compute the signal-adjusted daily return series, compute Sharpe / max_drawdown / win_rate / total_return / alpha vs SPY, write final metrics to JSON, transition status=closed.
   - Write one `outcome_log` row per matured run, tagged `{persona_id, backtest_id, source: "forward_test"}`.
5. **Render report** to `data/backtests/<backtest_id>/report.md`. Contains:
   - Header with `generated_ts` (the only non-deterministic line).
   - Per-persona aggregate table (3 rows × {Sharpe, total_return, alpha, win_rate}).
   - Per-(persona × ticker) detail (15 rows).
   - Buy-and-hold baseline row (per-ticker, plus SPY).
   - Any errored rows in a separate section.
6. **Update `backtests` row** to status=closed.

### Byte-equality verification

```bash
forge backtest report <backtest_id> > first.md
forge backtest report <backtest_id> > second.md
diff <(sed '/^generated_ts:/d' first.md) <(sed '/^generated_ts:/d' second.md)
# Expected: empty diff
```

The smoke test `tests/smoke/test_f2_exit_gate.py` asserts this byte-equality.

### Universe for the exit gate

AAPL, MSFT, GOOG, NVDA, TSLA. Large-cap US tech, liquid, well-covered by yfinance + Polygon + Alpha Vantage. Three personas should produce genuinely different reads on these (macro = rates / AI capex, value = earnings yield, momentum = options flow). Diverse enough to stress persona divergence; not so diverse that data-quality issues bury the signal.

## 7 · Persona prompt wiring

### Two wiring points

1. **`system_prompt_fragment`** — concatenated onto the system prompt of:
   - all enabled analyst nodes (market, news, fundamentals, social, derivatives)
   - the research-manager node
   - the trader node
   - the portfolio-manager / final-decision node

   The fragment is appended (not replaced) so analyst-specific instructions remain. Wiring lives in `tradingagents/personas/prompt_overlay.py` as `apply_fragment(base_prompt: str, persona: Persona) -> str`.

2. **`risk_debate.weights`** — applied at the risk-debate aggregation step where Aggressive / Conservative / Neutral arguments are combined for the PM. Each argument's weight is multiplied by `persona.risk_debate.weights[argument_role]`. The PM still sees all three arguments; the weights bias which one carries more force in the aggregated context the PM reads.

   Wiring lives in `tradingagents/personas/risk_weights.py` as a small helper called from the risk-debate aggregation node.

### How a persona becomes active

When `TradingAgentsGraph(persona=Persona)` is constructed (deep-dive launches three of these in parallel), the constructor stores the persona on `self.persona`. `GraphSetup.setup_graph()` consults `self.persona` when building nodes and applies both overlays. When `persona=None` (legacy / non-IIC call path), the overlays are no-ops — preserves backward compatibility.

### Boundary tests

- `tests/personas/test_prompt_overlay.py` — mocks the LLM, captures the prompt argv at invocation, asserts the persona's fragment text is in the captured prompt. Three personas → three distinct fragments observable in three separate runs.
- `tests/personas/test_risk_weights.py` — asserts the weights are applied at the right aggregation step using a synthetic risk-debate state.

### Validation that wiring is "real" (R-F2-2)

It is possible to wire the fragment and still produce three near-identical strategies — the LLM may simply ignore the fragment. The honest test is the exit-gate report itself: if Sharpe spread across personas is < 0.1 in absolute terms across all 5 tickers, the wiring is cosmetic and the design needs revisiting (e.g., heavier-handed prompt structure, different model, or rejecting the assumption that LLMs can be steered into trading personalities at all).

This is a soft warning in the exit-gate smoke test, not a hard fail — the harness is doing its job either way; the signal is about whether the persona model holds.

## 8 · Reflection / outcome_log integration

The program spec (§7-F2 deliverables) says: "Extends TradingAgents' reflection loop to write `outcome_log` rows (persona-aware)." Two scoring paths now exist:

| Path | Trigger | Writes to | Persona-aware? |
|---|---|---|---|
| **Existing** (`_resolve_pending_entries`) | Start of next `propagate()` for same ticker; uses raw / alpha return over 5-day holding window | Filesystem `memory_log` JSON (legacy) | No |
| **New** (`backtest.reflection`) | Forward test closes (matures at `end_date`) | `outcome_log` SQLite table | Yes — `tags.persona_id` |

The two paths intentionally don't overlap. The existing reflection is the live per-run loop that fires whenever a deep-dive runs on a ticker with same-ticker pending entries. The new forward-test close path fires exactly once per forward test, when the test matures.

**Schema interaction:** `outcome_log.run_id` is FK to `runs.run_id`. Both paths key by `run_id`. A single `run_id` can in principle have multiple `outcome_log` rows (the schema doesn't enforce uniqueness on `run_id`). The two paths produce DIFFERENT row content (different `outcome_md`, different `tags`); for query/recall, both are visible to the cross-persona OutcomeLog.

**Why not unify the paths?** The existing reflection is filesystem-based, fires at variable timing relative to outcomes, and is tightly coupled to the legacy `TradingMemoryLog` interface. F2 ships the new path; F3 or F4 can decide whether to retire the legacy path. **Both work, neither is the wrong shape.**

## 9 · Testing strategy

### Test layout

```
tests/backtest/
├── __init__.py
├── test_simulator.py            # unit: signal → position → daily PnL; alpha; Sharpe
├── test_prices.py               # unit: yfinance fetcher determinism + cache reuse
├── test_strict_historical.py    # unit: assertion fires on stubbed future-dated data
├── test_leaderboard.py          # unit: open-row MTM, closed-row aggregation, persona grouping
├── test_report.py               # unit: byte-equality on rerun (modulo generated_ts)
├── test_harness.py              # integration: full watchlist mode with mocked graph
└── test_reflection_outcome.py   # unit: on-close hook writes one outcome_log row, persona-tagged

tests/personas/
├── test_prompt_overlay.py       # unit: system_prompt_fragment injected into analyst/PM prompts
└── test_risk_weights.py         # unit: weights applied at risk-debate aggregation

tests/smoke/
└── test_f2_exit_gate.py         # smoke: end-to-end watchlist 5 × 3, back-dated 30d
                                  # asserts: report exists; persona table has 3 rows × 4 metrics;
                                  # outcome_log gains 15 rows; byte-equality on re-render
```

### Five boundary contracts (P7 antidote)

Each gets an explicit smoke assertion:

1. **Run Recorder fires for every persona run.** Already from F1; F2 must not break it. Re-asserted in F2 exit-gate smoke.
2. **`backtest_runs.metrics.run_id` matches an actual `runs.run_id`.** No orphan forward tests.
3. **`outcome_log` writes happen exactly once per closed forward test.** Not zero, not more. Persona-tagged via `tags`.
4. **Persona prompt fragment actually reaches the LLM.** Tests mock the LLM, capture prompt argv, assert fragment text is present. Three personas, three distinct fragments observable.
5. **`--strict-historical` raises on look-ahead.** Test stubs a data-flow function to return a future-dated bar; assert exception fires; assert disabled-by-default in live mode.

### Markers

Following F1 conventions: `unit` (default, fast, isolated), `integration` (real API calls or external state), `smoke` (quick end-to-end checks). The F2 exit-gate test is marked `smoke` and `integration` — it spends real LLM cost and takes ~15 minutes.

## 10 · Risks (F2 additions to the program register)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R-F2-1** | **Look-ahead data leakage** from data-flow tools that ignore `trade_date` | High | `--strict-historical` assertion at boundary; default ON when `start_date < today`. Failed assertion stops the run loudly. |
| **R-F2-2** | **Persona wiring is "loaded but cosmetic"** — fragment is injected but LLM ignores it | Med | Boundary test asserts fragment IS in prompts. Exit-gate report itself is the real validation: if Sharpe spread across personas is < 0.1 absolute across all tickers, wiring is cosmetic and the design needs revisiting. Soft warning in smoke test, not hard fail. |
| **R-F2-3** | **yfinance flakiness** — partial / missing historical bars cause some forward tests to error | Med | `PriceFallbackChain` (D7) tries the next source on per-bar failure. F2 ships yfinance-only so this risk is real until a second source is registered; `errored_sources` in metrics surfaces it. Errored tests tagged `status=errored`; report shows them in a separate section. |
| **R-F2-3b** | **Source contradictions** — two sources give different prices for the same (ticker, date) | Low | F2 does NOT reconcile. Uses the highest-priority available source. Per-window source recorded in `metrics.price_source` for audit. Reconciliation is a deliberate non-goal — the program is decision-support, not a reference data product. |
| **R-F2-4** | **stockstats vwma/macdh `Date` KeyError** (known, see [saved memory](../../../.claude/projects/-home-ziwei-huang-TradingAgents/memory/stockstats-vwma-macdh-date-error.md)) surfaces during 15 graph runs | Low | Non-blocking — those two indicators silently fail and the analyst proceeds. **Defer fix beyond F2**, document in exit-gate report header. |
| **R-F2-5** | **Sharpe-from-N=22 is noisy** | Med | Report shows Sharpe with explicit "30-day sample" caveat. Win-rate-daily (N=22) is the more stable comparator; flag as primary exit-gate metric. |
| **R-F2-6** | **Brief-scoped mode untested end-to-end** in F2 (F5 is the consumer) | Low | Unit test mocks an F5-style call; asserts the harness reads `briefs.run_ids`, opens forward tests, never re-invokes the graph. End-to-end validation deferred to F5. |
| **R-F2-7** | **15 sequential graph runs hits LLM rate limits or transient API errors** | Low | Sequential execution (no parallelism in F2). `backtest_max_concurrent_graph_runs: 5` shipped as future throttle, enforcement OFF. Per-run errors tagged `status=errored`, harness continues. |

### Risks the program register already covers

- R10 (over-trusting framework alpha) — F2 is the first-class mitigation. Exit-gate report is the artifact; R-F2-2 calibrates how seriously to take it.
- R3 (synthesis prompt averages disagreement away) — F2 makes this measurable for the first time. If the wiring is real but the persona spread is tiny, that's evidence the synthesis prompt or the personas themselves need work.

## 11 · Always-on operation (24/7)

The IIC-FORGE system is designed to run continuously without shutdown (program design P5 — local-first, low-ops). F2 must not introduce gaps in that posture. Forward tests opened by deep-dives or scheduled morning runs must mature automatically at day 30, even with no human in the loop and no leaderboard query running.

### Durability across restarts

All forward-test state lives in SQLite (`backtests` + `backtest_runs.metrics`). A crash, restart, OS update, or power loss never destroys a forward test — on restart, open tests are still queryable and the next sweep matures any whose `scheduled_close_date <= today`. There is **no in-memory state** the harness needs to preserve. This property comes for free from F1's persistence design; F2 just doesn't break it.

### Two entry points for maturation

Both use the same underlying logic in `sweep.py`:

| Command | Shape | When to use |
|---|---|---|
| `forge backtest sweep` | One-shot: query open tests, mature the matured ones, exit. | Cron timer, systemd `OnCalendar=*:0/15`, CI tests, manual user checks. The canonical primitive. |
| `forge backtest watch [--interval=300]` | Long-running: loop the sweep every N seconds (default 5 min). | Always-on systemd service. The "no external scheduler needed" path. |

`watch` is `sweep` in a `while True: sweep(); sleep(interval)` wrapper with signal handling for graceful shutdown. No extra primitives — both paths exercise the same `sweep.run_maturation_pass()` function, which is what the F2 tests target.

### Recording results

When `sweep` matures a test, it writes (atomically per row):
1. Final metrics into `backtest_runs.metrics` (status `open` → `closed`).
2. One `outcome_log` row tagged `{persona_id, backtest_id, source: "forward_test"}`.
3. Sweep summary line into `data/logs/sweep-YYYY-MM-DD.log` for operability.

Failures during maturation (transient API errors, missing exit price across all sources) write `status=errored` to that row and continue with other rows — one bad row does not stop the sweep. A subsequent sweep retries errored rows whose `scheduled_close_date <= today` ONLY if a new flag is set; by default errored rows stay errored to avoid retry-storms. (Retry behavior is one of the §13 implementation calls.)

### Handoff to F4

F4's queue + worker will wrap `forge backtest sweep` as one of its job types. At that point, `forge backtest watch` becomes redundant (the queue worker takes over the scheduling responsibility) but harmless. **F2 doesn't need to anticipate F4** — both `sweep` and `watch` keep working unchanged once F4 ships. Same primitive, different invoker.

### What 24/7 does NOT require in F2

- Streaming price feeds (polling per sweep is sufficient at daily resolution).
- A separate process supervisor (systemd / launchd is the right tool).
- Distributed locking (single secretary process owns DB writes per program design R5).
- Hot-reloading of persona configs (restart the watch process; takes seconds).

## 12 · Out of scope

- **Streamlit dashboard for the leaderboard** — F5 territory. F2 ships the CLI surface only.
- **Transaction costs, slippage, borrow fees, leverage** — keep the simulator pure. Add later if measured alpha demands it.
- **Signal-weighted positions via `confidence`** — `confidence` is still `None` in F1's RunRecorder. F2 sticks with discrete ±1/0 positions.
- **Multi-period rebalancing** — one decision held for the full window; no rebalance.
- **Walk-forward / cross-validation** — out of scope; the watchlist mode is single-window forward testing.
- **A `prices` table for snapshotted daily closes** — F2 fetches via `PriceFallbackChain` and caches in-process per backtest. F4 or later can add a `prices` snapshot table if reproducibility against live data drifts (yfinance occasionally revises historicals).
- **Retiring the legacy filesystem `memory_log`** — both reflection paths coexist; retirement decision deferred.
- **1-min resolution implementation** — designed for via the `Resolution` enum and `PriceSource` API (D7); F2 ships `DAILY` only. Implementation lands when a paid 1-min source (Polygon / Alpha Vantage premium) is registered.
- **Non-yfinance `PriceSource` adapters** — stubs only in F2; the user registers real adapters as needed. The fallback chain is in place from day one.
- **F4-scale scheduling** — `forge backtest watch` covers single-process 24/7 in F2; F4 wraps `sweep` into the queue when it ships.
- **Source contradiction reconciliation** — F2 trusts the highest-priority available source; cross-source price audit / quality scoring is a separate concern.

## 13 · Open questions deferred to implementation

1. **Calendar handling for `start_date + 30 calendar days`** — if the resulting `end_date` lands on a weekend or US market holiday, the simulator uses the last available trading day's close. Implementation owner picks the convention (probably: forward to next trading day at most 3 days, else error).
2. **`risk_debate.weights` normalization** — apply as raw multipliers, or normalize to sum to 1.0 across roles first? Implementation owner picks; document the choice in `risk_weights.py`.
3. **Buy-and-hold baseline aggregation** — report per-ticker AND a 5-ticker equal-weight basket, vs. just the basket. Probably both (cheap to add).
4. **Persona inclusion in the exit-gate CLI** — accept `--personas=macro,value,momentum` for explicit listing, or default to all YAMLs in `tradingagents/personas/`? Probably default-all with override-by-flag.
5. **Per-channel `exit_price`** — close-of-day price on `end_date`, or VWAP, or open-of-next-day? Close-of-day is simplest and matches the daily return series. Default to close-of-day; document the choice.
6. **Errored-row retry behavior in `sweep`** — by default errored rows stay errored to avoid retry storms. A `--retry-errored` flag on `sweep` could be added later; not required for F2.
7. **`watch` interval default** — 5 minutes (300s) is the proposed default. Implementation owner can tune; nothing depends on the exact value.
8. **PriceFallbackChain construction site** — built once at `BacktestHarness` init from `default_config.backtest_price_sources` (a config key listing source names in priority order), or constructed per-call? Probably once-at-init for cache reuse.

These are calls the implementer can make as they go without re-opening the design.

---

*End of IIC-FORGE-05. The implementation plan (output of `superpowers:writing-plans`) follows at `docs/superpowers/plans/2026-05-26-iic-forge-05-f2-backtest-benchmark.md`.*
