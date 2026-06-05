# TradingAgents Improvement Plan

> Generated 2026-06-04 from a multi-agent audit (Haiku readers + Opus analysts).
> Every finding is first-hand verified against source with `file:line` references.
> Impact/Effort scale: **H/M/L** impact, **S/M/L** effort.

## Executive Summary

The repo is a mature, well-structured multi-agent pipeline — the LangGraph
orchestration, docs workflow validators, and test suite are broad, and the
data-vendor fallback path is thoughtfully built. The dominant problems are
**operational and economic, not architectural**. First, the `.claude/`
automation layer ships three real correctness bugs in a script that would
silently lose data and run multi-hour Opus jobs at the wrong time of day.
Second, per-ticker cost is inflated by two multiplicative levers — every debate
agent re-injects all four full analyst reports each turn, and every agent is
pinned to the most expensive reasoning tier — so the bill scales as
`tickers × turns × duplicated-tokens × max-effort` rather than by new content.
Third, the system produces directional ratings but **never scores its own
accuracy**, so no prompt or threshold change can be evaluated. Highest-leverage
moves: fix the `.claude` automation (cheap, high blast-radius), split the
reasoning-effort knob and dedupe report injection (compounding token savings),
and add a deterministic correctness label plus a hit-rate report (turns the
existing reflection loop into a measurable backtest). As a second priority,
this plan also adds **multi-timeframe TD-9 (TD Sequential)** as a first-class
technical indicator — a net-new exhaustion/reversal signal absent from the
current RSI/MACD set. It reports the *current running setup count* (not just
completed 9s) across three tiered timeframes — **weekly (tier 1), monthly
(tier 2), daily (tier 3)** — and, unlike the existing indicators, needs a small
custom computation because `stockstats` ships no DeMark handler.

---

## Priority 0 — `.claude` folder

All small edits, high blast-radius.

### P0.2 — `autorun_gate.sh:19-20` runs the heavy job WITHOUT its log redirect (broken line continuation) — **H / S**

- **Current:** line 19 ends `&& nohup bash .claude/run_missing_today.sh ` (trailing space, **no backslash**); line 20 `> "/tmp/ta_runlogs/autorun_$(date +%F).log" 2>&1` is parsed as a separate, command-less redirect that just truncates the log to 0 bytes.
- **Change:** add a trailing backslash to line 19 and indent line 20 as a continuation:
  ```bash
        && nohup bash .claude/run_missing_today.sh \
             > "/tmp/ta_runlogs/autorun_$(date +%F).log" 2>&1
  ```
  Belt-and-suspenders: add `nohup.out` to `.gitignore`.
- **Why:** As written, the multi-hour run's stdout/stderr is never captured; because the script `cd "$REPO"` first, `nohup` falls back to writing `nohup.out` into the working tree (not gitignored). The `&&` chain also terminates at line 19, so the redirect is unconditional rather than gated.

### P0.3 — `autorun_gate.sh:14` time window is the inverse of its stated intent — **M / S**

- **Current:** `if [ "$dow" -le 5 ] && [ "$hour" -le 10 ]; then` — true only 00:00–10:59 Pacific.
- **Change:** decide the real intent and make code match comment. For the stated "7PM or later": `[ "$hour" -ge 19 ]`. If the true intent is "early morning before market open," fix the *header* instead. Comment and condition must agree.
- **Why:** Header (lines 4–5) says "7:00 PM or later," guard fires midnight-to-late-morning — the gate, if ever wired, kicks off a multi-hour Opus run **during the trading day**.

### P0.4 — `autorun_gate.sh:2-3` is an orphaned hook with a false header claim — **M / S**

- **Problem:** Header asserts it is "Invoked from the GLOBAL Claude hook," but the active `~/.claude/settings.json` SessionStart block only runs the telemetry hook; `autorun_gate.sh` appears nowhere. It is git-tracked dead code whose latent bugs P0.2/P0.3 go live the moment anyone wires it up.
- **Change:** choose one — (a) fix P0.2/P0.3 first, then add the command-type hook to `~/.claude/settings.json` SessionStart (the wiring lives in a personal machine file and can never be committed to the repo); or (b) if auto-run is abandoned, delete the script. **Minimum:** change the header to "Intended to be invoked from a SessionStart hook (not currently wired up)."

### P0.5 — `settings.local.json` allowlist hygiene (~105 entries) — **M / M**

- **Problem:** Blanket wildcards (`Bash(python *)`, `Bash(bash *)`, `Bash(git *)`, `Bash(uv run *)`, `Bash(grep *)`) approach arbitrary code execution and subsume dozens of dead-weight specific entries: literal-SHA `git log/show` lines (40–47), `Bash(kill 73474)` (96, a PID that never recurs), dated HEIC conversions (64–66), and two full `gh pr create` calls with hardcoded titles (29, 33).
- **Change:** prune to a small curated set. Replace `Bash(git *)`/`Bash(bash *)`/`Bash(python *)` with scoped forms like `Bash(git add:*)`, `Bash(uv run python -m cli.main run:*)`, and delete every one-off SHA/PID/screenshot/explicit-title entry the wildcards already cover. Safe to regenerate lean once P0.6 lands.

### P0.6 — `settings.local.json` ignore rule lives only in global git config, not the repo — **L / S**

- **Change:** add `.claude/settings.local.json` to the repo's own `.gitignore`. Leave `settings.json`/skill/command files committed (correctly shared).
- **Why:** A contributor without the global `~/.config/git/ignore` rule would not ignore this personal allowlist, risking an accidental commit. The protection should travel with the repo. (Do P0.6 *before* P0.5.)

> *Deferred: the per-day lock dir at `autorun_gate.sh:18` is never cleaned up via `trap`/`rmdir`; low priority while the script is orphaned — fix alongside P0.4 if the gate is kept.*

---

## Priority 1 — Introduce multi-timeframe TD-9 (TD Sequential) as a core technical indicator

> Second-highest priority after P0. New analytical capability, not a bug fix.
> **The blocking constraint:** every existing indicator is computed by handing
> its name to `stockstats` (`df[indicator]` at `stockstats_utils.py:158, 213`).
> A probe of the installed `stockstats` build shows **82 indicator handlers and
> none for DeMark / TD Sequential** (`demark`, `td_seq`, `countdown`, `setup`
> all absent; a lone `sequential` substring is an unrelated match). So TD-9
> **cannot** be added the way `rsi`/`macd`/`mfi` were — appending a catalog
> string is necessary but *not sufficient*; the count itself must be computed in
> our own code. This is what makes it M-effort rather than S.

### What this delivers (scope)

TD Sequential's **Setup** phase: a *bullish* (buy) setup counts bars whose Close
is **less** than the Close 4 bars earlier; a *bearish* (sell) setup counts bars
whose Close is **greater** than the Close 4 bars earlier. The run resets on any
break or directional flip. A completed count of 9 flags likely trend exhaustion
/ reversal — a signal class the current set (trend, momentum, volatility,
volume) lacks.

Two product requirements shape v1:

1. **Report the *current running count `n`*, not just completed 9s.** The signal
   is the live progress through the setup (e.g. "weekly buy-setup at 7/9"), not
   a fired-or-not boolean. The report must state the present `n` (signed by
   direction, 0–9) for **each** timeframe even when `n < 9`. A bare "no TD-9"
   throws away the "approaching exhaustion" information that is the whole point.
2. **Three timeframes, explicitly tiered by priority.** Compute the same Setup
   count on **weekly, monthly, and daily** bars and label the tier so the agent
   weights them correctly:
   - **Tier 1 — Weekly TD-9** (primary signal; swing/position horizon).
   - **Tier 2 — Monthly TD-9** (regime/secular context).
   - **Tier 3 — Daily TD-9** (entry-timing/noise filter).

   Higher tier dominates on conflict (a weekly 9 outranks a daily 9). The report
   surfaces all three current counts side by side; the prompt tells the agent the
   ranking so a daily blip can't override a weekly exhaustion.

**Data sufficiency (verified):** the existing cache fetches 5 years of daily
OHLCV (`stockstats_utils.py:83`). Resampling that window yields **~262 weekly and
~61 monthly bars** — comfortably past the ≥13 a Setup needs — so **no wider fetch
is required**; weekly/monthly are derived from the same cached daily frame via
`resample().last()` (Close-only is enough for the Setup count). The Countdown
phase and TDST price levels remain explicitly **deferred** (note in the docstring
as a deliberate cut, per Simplicity-First).

### P1.1 — Compute the running TD Setup count, with timeframe resampling, in our own dataflow helper — **H / M**

- **Where:** `tradingagents/dataflows/stockstats_utils.py` (alongside
  `get_stock_stats` / `load_ohlcv`, reusing the same cached, look-ahead-filtered
  `load_ohlcv(symbol, curr_date)` frame — `load_ohlcv` already filters rows after
  `curr_date` at `:123`, so resampling inherits the no-look-ahead guarantee).
- **Change:** two small pure functions over a DataFrame (no network):
  - `compute_td_setup(close: pd.Series) -> pd.Series` — walks Close vs
    Close-4-bars-prior, resets on break/flip, clamps magnitude at 9, signs it
    (`+` buy-setup, `−` sell-setup, `0` neutral). The **last** value is the
    current running `n` for that series.
  - `td_setup_by_timeframe(df, curr_date) -> dict` — resamples the daily frame to
    `W` and `ME` (`Close.resample(...).last()`), runs `compute_td_setup` on each
    of weekly/monthly/daily, and returns the **current** signed `n` per timeframe,
    e.g. `{"weekly": +7, "monthly": -3, "daily": +9}`. Off-session daily still
    returns the last completed bar's count rather than `"N/A"`, because the
    running count is meaningful between sessions (it only advances on a new bar).
- **Why custom:** confirmed above — `stockstats` has no handler, so `df["td_9"]`
  would raise. Keep each function ~15–25 lines; do not vendor a new lib.

### P1.2 — Expose tiered TD-9 through the existing indicator window + catalog — **H / M** (depends on P1.1)

- **Where (single source of truth problem):** the indicator catalog is currently
  **triplicated** and already drifting — `y_finance.py:65-136` (`best_ind_params`,
  has `mfi`), `alpha_vantage_indicator.py:30-58` (`supported_indicators`, **no**
  `mfi`), and the market-analyst prompt `market_analyst.py:25-49` (**no** `mfi`).
  Adding TD-9 to only one repeats that drift.
- **Change:** (a) in `y_finance.py`'s `get_stock_stats_indicators_window`
  (the yfinance impl behind `get_indicators`, `interface.py:79`), branch
  `indicator == "td_9"` to the P1.1 helper instead of the `_get_stock_stats_bulk`
  path. A single `td_9` call returns **all three tiers at once** — a compact block
  like:
  ```
  ## TD-9 (TD Sequential Setup) — current running count by timeframe (higher tier wins):
  - Tier 1 Weekly:  +7  (buy-setup, 7 of 9 — approaching exhaustion)
  - Tier 2 Monthly: -3  (sell-setup, 3 of 9)
  - Tier 3 Daily:   +9  (buy-setup COMPLETE — reversal watch)
  ```
  Returning all three from one indicator name (rather than `td_9_weekly`,
  `td_9_monthly`, `td_9_daily`) keeps the agent's "up to 8 indicators" budget
  intact and guarantees the tier ranking is always shown together. (b) add a
  **new "Sequential / Exhaustion" category** to the analyst prompt
  (`market_analyst.py:48-49`) documenting `td_9`, the running-count semantics,
  **and the weekly > monthly > daily tier order** so the LLM weights conflicts
  correctly; add the matching entry to `best_ind_params`. (c) handle `td_9` in
  `alpha_vantage_indicator.py` the same explicit way `vwma` is handled
  (`:145-148`) — Alpha Vantage has no TD endpoint, so return an informative
  "computed from OHLCV, not available from this vendor" string rather than a
  silent `ValueError`. The `route_to_vendor` fallback (`interface.py:153-174`)
  then lands on yfinance automatically.
- **Why:** `get_indicators` already splits comma lists and calls per-indicator
  (`technical_indicators_tools.py:25-31`), so no tool-signature change is needed
  — the agent gains one legal name that emits the full tiered block. Keeping all
  three catalogs in sync (or, better, deduping them — see the new TR8 below)
  prevents a `td_9` that works on yfinance but `ValueError`s the instant the
  vendor flips to Alpha Vantage.

### P1.3 — Unit-test the running count, resampling, and tiering — **H / S** (depends on P1.1/P1.2)

- **Where:** new `tests/test_td_sequential.py`, mirroring the no-network,
  hand-built-frame style of `tests/test_stockstats_date_column.py`.
- **Change:** assert on `compute_td_setup` / `td_setup_by_timeframe`:
  - **running count** — a series 7 bars into a down-setup reports exactly `+7`
    (not 0, not 9); 9 down-bars reports `+9`; 9 up-bars reports `−9`.
  - **reset** — a break at bar 5 restarts the run (no carry-over).
  - **resampling** — a daily frame spanning enough weeks yields the expected
    weekly/monthly current counts (build ~14 weekly closes, assert the weekly `n`).
  - **tiering payload** — `td_setup_by_timeframe` returns all three keys
    (`weekly`/`monthly`/`daily`) with signed ints.
  - **wiring** — `get_stock_stats_indicators_window(..., "td_9", ...)` returns a
    block containing all three tier labels and does **not** raise `ValueError`
    ("not supported").
- **Why:** the count is off-by-one-prone (the "4 bars earlier" lookback, the
  9-bar reset, and now the resample boundary) and is a tradeable signal — exactly
  the kind of pure logic the plan already protects with TR1/TR3.

> **Deliberately deferred (note in docstring, don't build):** TD Countdown (the
> 13-bar phase after a 9), TDST support/resistance levels, intraday timeframes,
> and any Alpha Vantage-native TD path (there is none). v1 is the Setup running
> count on weekly/monthly/daily only.

> **Pairs with TR8 (new, below):** if the three catalogs are deduped into one
> registry first, P1.2 collapses to a single insertion. Doing TR8 before P1.2 is
> the cleaner order but not required.

---

## Token Efficiency

| # | Title | File / area | Impact | Effort |
|---|-------|-------------|:------:|:------:|
| **T1** | Split reasoning-effort knob — don't pin quick-think to max | `default_config.py:74-75` → `trading_graph.py:148-156` | **H** | **S** |
| **T2** | Dedupe the 4 full analyst reports across all 5 debate agents (built once, not re-pasted 7–10×) | `bull_researcher.py:38-43`, `bear_researcher.py:40-43`, `risk_mgmt/{aggressive,conservative,neutral}_debator.py:31-34` | **H** | M |
| T3 | Lower default debate depth for routine scheduled runs; reserve `depth=5` for high-conviction names | `default_config.py:96-97`, `conditional_logic.py:55-67` | H | S |
| T4 | Skip "Not a trading day" filler rows in indicator window (~30% per block × up to 8 indicators) | `y_finance.py:155-170` (loop 167-170) | M | S |
| T5 | Cap/aggregate raw OHLCV CSV (last-N days, weekly downsample older); document the cap in the docstring | `y_finance.py:45`, `core_stock_tools.py get_stock_data` | M | S |
| T6 | Stop replaying full risk-debate history every turn (quadratic) — use existing `current_*_response` fields + running summary | `risk_mgmt/*_debator.py:35` | M | M |
| T7 | Truncate memory `past_context` bodies; lower `n_same` 5→2-3 | `memory.py:71, 284-292` | M | S |
| T8 | Extract shared analyst preamble; drop dead BUY/HOLD/SELL hand-off line | `market/news/fundamentals/sentiment_analyst.py` | L | S |

**T1 + T2 are the top picks** — savings multiply by every ticker and every turn.

---

## Forecasting Accuracy

| # | Title | File / area | Impact | Effort |
|---|-------|-------------|:------:|:------:|
| **F1** | Store a deterministic correct/wrong label per outcome (today a correct Sell call is never recognized as correct) | `reflection.py:31-57`, `trading_graph.py:296-312` (`_resolve_pending_entries`) | **H** | **S** |
| **F2** | Add hit-rate / calibration report (per-tier mean alpha, directional hit rate, reliability bins) — read-only over persisted data; depends on F1 | new `scripts/accuracy_report.py` over `memory.py:54-96 load_entries` | **H** | M |
| **F3** | Thread `past_context` lessons beyond the Portfolio Manager → Research Mgr + Trader (state already exists; only read-sites missing) | `portfolio_manager.py:35-38`, `propagation.py:23-40` | **H** | **S** |
| F4 | Match holding window to the rating's time horizon (`holding_days=5` hardcoded, ignores `time_horizon`) | `trading_graph.py:234-236, 291-293`, `schemas.py:203` | M | S |
| F5 | Tighten rating extraction — the single point where text becomes the tradeable signal | `rating.py:27-50` | M | S |
| F6 | Default `max_debate_rounds` 1→2 (today each side speaks once, no rebuttal; the "3 rounds" comment is wrong); allow concession | `conditional_logic.py:52-61`, `bull_researcher.py:27-45`, `aggressive_debator.py:24-37` | M | S |
| F7 | Enforce the verified market snapshot instead of merely suggesting it | `market_analyst.py:51`, `market_data_validator.py:114-122` | M | M |

F1 → F2 → F3 is the key chain: label outcomes, measure them, then feed lessons back to the agents that build the thesis.

---

## Docs Generation Quality

| # | Title | File / area | Impact | Effort |
|---|-------|-------------|:------:|:------:|
| **D1** | Force-close code fences at wrapper boundaries — one unclosed agent fence renders the whole report tail as literal code and silently yields `n/a`; add a unit test | `cli/report_headings.py:65-74` (`in_fence` in `transform`) | **H** | **S** |
| **D2** | De-date the current-price regexes — ~20 patterns hardcode "May 29"/"5/29"/"05-29" so they can never match later runs → `n/a` → `validate_homepage` hard-fails → weekly hand-patching; add two-date tests | `build_reports_site.py:185-208`, `report_workflow.py:256-257` | **H** | M |
| D3 | Surface tickers missing from a daily summary (silent `continue` hides partial runs on the non-workflow entrypoint) | `build_reports_site.py:331-348, 356-367` | M | S |
| D4 | Validate in-page anchors under `--strict` (mkdocs 1.6.1 leaves anchors at `info`; broken date-rail fragments 404 silently) | `mkdocs.yml` (add `validation.links.anchors: warn`) | M | S |
| D5 | Normalize the Trader "Action" field (`Buy 100 shares` misses `action_rank`, dumps row to rank 9 / wrong sort) | `build_reports_site.py:114-123, 320, 370-375, 431-432` | M | S |
| D6 | Exclude raw stage `*.md` pages (~12 extra public pages/run with competing un-pruned H1s) via `exclude_docs` glob `[1-5]_*/**.md` | `mkdocs.yml:81-82, 87-89` | M | S |
| D7 | Soften reassembler "byte-compatible" claim (partial runs diverge from the fixed analyst order) | `reassemble_complete_reports.py:43-77` vs `cli/main.py:710-728` | L | S |

---

## Testing & Reliability

| # | Title | File / area | Impact | Effort |
|---|-------|-------------|:------:|:------:|
| **TR1** | Test `ConditionalLogic` debate/risk round caps + the tool-routing branch (pure functions, ~15 lines of fixtures) | new `tests/test_conditional_logic.py` over `conditional_logic.py:52-73` | **H** | **S** |
| **TR2** | Test LLM `timeout`/`max_retries` forwarding (guards the 429/transient-failure budget) | `trading_graph.py:165-173` (`_get_provider_kwargs`) | **H** | **S** |
| TR3 | Anchor `parse_rating` label regex on `\b` word boundary (`integrating:`/`frustrating:` currently match); add regression test — pairs with F5 | `rating.py:27` (`_RATING_LABEL_RE`) | M | S |
| TR4 | Test Alpha Vantage rate-limit fallback + `first_error` re-raise | `interface.py:162-163, 193-194` | M | S |
| TR5 | Fix dead/misleading stream-mode merge loop (`stream_mode='values'` already gives cumulative state) | `trading_graph.py:387-399`, `cli/main.py:1266-1270` | L | S |
| TR6 | Fix invalid-escape-sequence SyntaxWarning (future SyntaxError) | `cli/utils.py:483` | L | S |
| TR7 | Harden `clear_checkpoint` against langgraph-sqlite schema drift (`checkpoint_blobs` not deleted) | `checkpointer.py:84-88` | L | M |
| TR8 | Dedupe the triplicated indicator catalog into one registry — `mfi` already drifted (in `y_finance.py`, missing from the AV catalog + analyst prompt); a test asserting the three sets match would have caught it. Unblocks P1.2 | `y_finance.py:65-136`, `alpha_vantage_indicator.py:30-58`, `market_analyst.py:25-49` | M | M |

---

## Suggested Sequencing

1. **P0.2** — one-line fixes that stop silent data loss and lost logs (do these first).
2. **P0.3, P0.4** — align the time gate and orphaned-hook header; decide keep-vs-delete.
3. **P0.6 → P0.5** — add the `.gitignore` entry, then prune the allowlist (safe once ignored).
4. **TR8 → P1.1 → P1.2 → P1.3** — dedupe the indicator catalog first (one insertion point), then compute the running TD Setup count across weekly/monthly/daily (tiered), wire the tiered `td_9` block into the window/catalog/prompt, and lock it with unit + wiring tests. Second priority overall; ships independently of the token/accuracy work.
5. **T1 + T2 + T3** — compounding token levers; ship together so savings multiply across the universe.
6. **TR1 + TR2 + TR3** — cheap pure-function/regex tests protecting the debate caps, retry budget, and rating signal.
7. **D1 + D2** — the two docs bugs that actively break published pages / the workflow gate.
8. **F1 → F2 → F3** — correctness label → hit-rate report → feed lessons to thesis-builders.
9. **D3, D4, D5, D6** — docs robustness and site-quality cleanups.
10. **T4–T8, F4–F7** — secondary token and accuracy refinements.
11. **D7, TR4–TR7** — documentation-claim and low-urgency reliability hardening last.

## What I'd Measure

- **`.claude` (P0):** after P0.2, the dated `autorun_*.log` is non-empty and **no `nohup.out` appears in `git status`**.
- **TD-9 indicator (P1):** the P1.3 unit tests pass (running count, reset, resampling, tiering, wiring); a live `get_indicators(..., "td_9", ...)` call returns a block showing **all three tier labels (weekly/monthly/daily) with a signed current count `n`**, including the `n < 9` case; and a generated `market.md` references the weekly tier as primary. Confirm `td_9` survives a forced Alpha-Vantage-primary config (falls back to yfinance, no `ValueError`).
- **Token efficiency (T1–T8):** track **mean input + reasoning tokens per ticker run** before/after via the existing per-call logs; T1+T2+T3 together should cut the debate-phase token cost by a large multiple. Confirm report quality is unchanged by spot-checking a few `complete_report.md` ratings against the prior run.
- **Forecasting accuracy (F1–F3):** the F2 report is the proxy — **directional hit rate and per-tier mean alpha** over resolved entries; success is that the numbers exist, are queryable, and move right (Buy mean-alpha > Sell mean-alpha) after F3 threads lessons into the thesis agents.
- **Docs (D1–D6):** **build-pass rate** of `mkdocs build --strict` and `validate_homepage` across consecutive dates with no hand-patching, and **zero `n/a` rows** in `docs/index.md` (`rg -n "n/a" docs/index.md` returns nothing); the D2 two-date regression test stays green.
- **Testing (TR1–TR8):** new tests pass and `pytest` collection emits **no SyntaxWarning**; coverage now includes the debate-cap, retry-forwarding, rate-limit-fallback, rating-misfire, and indicator-catalog-drift paths that previously had none.
