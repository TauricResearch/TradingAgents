# Brief: Article-Derived Platform Gaps (Audit After IG Confirmation)

**Date:** 2026-07-25
**Status:** Proposed
**Priority:** P3
**Source:** "Build Your Trading Bot Like A System" (Sips & Scale, Readers Club, Feb 2026)
**Preceded by:** orientation + repo audit on `feat/markov-phase2`

---

## Preflight audit — what the article claims vs. what we already have

The article preaches a platform mindset for retail algo devs escaping a notebook.
The repo audit (post-IG confirmation) revises the earlier "three gaps" claim.
Most of the article is *already the architecture*; the surviving gaps are narrower
than first stated.

| Article thesis | Status | Evidence |
|---|---|---|
| System, not script (modular: data/strategy/risk/execution/ledger) | ✅ Already | `tradingagents/` (strategy) · `governance.ts` (risk) · hLedger + SQLite `trades` (ledger) · `analyze_stream.py` (data bridge) |
| Strategies emit signals; central risk layer says yes/no | ✅ Already, by construction | LLM agents produce a *decision*, never an order. `governance.ts` enforces max-position (15%), max-sector (30%), cash-floor (10%), max-drawdown (15%), max-holdings (24). Risk *debate* (Aggressive/Conservative/Neutral) is a second, deliberative spine. |
| Risk is the product — per-trade risk sizing | ◐ Partially — formulae exist, governance wiring is the gap | `src/lib/trade-calculator.ts` implements `(account × risk%) / (entry - stop)` with 2× ATR stop, Fib targets, 5% concentration flag. Default `riskPerTrade = 0.02`. The article's 0.5% is stricter; ours is configurable via `--risk`. **Gap:** the calculator's output is advisory, not an enforced governance ceiling. |
| Unify backtest and live (same strategy/risk code, swap executor) | ◐ Partially, structurally awkward | LLM strategy layer can't be backtested like a crossover. The Markov engine backtests *regime features* — different substrate. `governance.ts` *could* be shared between Markov backtest and live but isn't wired that way. |
| Execution as first-class subsystem (order state machine, retry, ledger) | ◐ Partially — path exists, machine is thin | `IGClient` + `trading execute` place real orders on `demo-api.ig.com/gateway/deal`, write to `trades` table. But: no `created → submitted → acked → partial → filled/canceled` state machine; no retry on transient errors; no partial-fill handling; confirmation is a single sync call. |
| Measure systems tax = gross PnL − actual PnL | ❌ Genuine gap | `feedback.ts` tracks signal accuracy + post-mortems. No `expected_price vs fill_price` capture — because the execute path doesn't persist the *planned* entry alongside the *actual* fill. The diagnostic frame is sound; the data feed doesn't exist. |

**Net:** the article is mostly redundant. Three items survive, refined below.

---

## Item 1 — Order state machine + retry (execution hardening)

**What:** Promote the IG execute path from "place-and-pray" to a first-class
subsystem with an explicit state machine and transient-error retry.

**Why it survived:** `src/cli/commands/execute.ts` places a market order, calls
`confirmTrade(dealReference)`, and writes to `trades` on `ACCEPTED`. There is no
state persistence between `createPosition` and `confirmTrade`, no retry on
network timeout, no handling of `REJECTED`-but-retryable, no partial-fill
awareness. A network hiccup between submit and confirm leaves the order in an
unknown state — the exact failure mode the article names.

**Proposed shape (minimal):**
- `order_states` table: `dealReference, status, epic, direction, size, planned_entry, planned_stop, planned_target, created_at, submitted_at, confirmed_at, fill_price, fill_size, error`
- States: `CREATED → SUBMITTED → ACKNOWLEDGED → (PARTIAL → )FILLED | REJECTED | CANCELED`
- Retry: transient HTTP errors (5xx, timeout) retried with backoff on `createPosition` only; **never** retry `createPosition` without first checking `confirmTrade` (avoids double-position).
- On `confirmTrade` timeout: query `getPositions` to reconcile by `dealReference` before declaring failure.

**Scope guard:** this is hardening of an existing path, not new broker integration. IG-only.

**Derrida check:** yes, in consideration set — execution is already built; this makes it survivable.

---

## Item 2 — Per-trade risk sizing: enforce as governance, not just advise

**What the article says:** per-trade risk ≤ 0.5% of equity, single position ≤ 5%, total ≤ 40%.

**What we have:** `trade-calculator.ts` already implements the sizing formula:

```
stopLoss     = entry - (2.0 × ATR14)
riskPerShare = entry - stopLoss
positionSize = floor((accountBalance × riskPerTrade) / riskPerShare)
riskAmount   = positionSize × riskPerShare
concentrationFlag = (positionSize × entry) > accountBalance × 0.05
```

Default `riskPerTrade = 0.02` (2%). The 5% concentration flag exists but is a
*warning*, not a *ceiling*.

**The formulae are already there.** The gap is governance enforcement, not
math. Two decisions to make:

1. **Risk-per-trade default.** Article says 0.5%; ours is 2%. For a $25k demo
   account at 2%, a 2%-away stop sizes to $2,500 notional (10% concentration —
   trips the flag). At 0.5%, $625 notional (2.5% — clean). The article's number
   is more survivable for retail. Recommend: lower default to `0.005` for the
   IG demo path, keep `0.02` as an explicit opt-in for larger accounts.
2. **Enforcement vs advisory.** Currently `concentrationFlag` warns; the
   article's discipline is "if the risk layer says no, the trade does not
   exist." Recommend: add a `risk-budget` rule to `governance.yaml` that
   `execute.ts` checks *before* `createPosition`. If `positionSize × entry >
   max-position` or `riskAmount > max-risk-per-trade`, block — not warn.

**Volatility-aware sizing** (article mentions it): already implicit via ATR —
wider stop → smaller size for same risk budget. No new formula needed.

**Open question for the poker club:** should the risk debate (Aggressive/
Conservative/Neutral agents) *see* the trade calculator's output before voting?
Currently they debate in the abstract. Injecting the concrete plan (entry, stop,
size, concentration flag) would make the debate grounded rather than
rhetorical. That's a wiring change, not a formula change.

---

## Item 3 — Systems-tax diagnostic (data first, frame later)

**What:** Capture `expected_price vs fill_price` per trade so
`systems_tax = gross_pnl − actual_pnl` becomes computable.

**Why it's still a gap:** `feedback.ts` does signal-accuracy and post-mortems
but has no fill-vs-expected data because the execute path doesn't persist both.
The `trades` table stores `price` (the *planned* entry from `plan.entry`) but
not the *actual* fill level from `confirmation.level` — even though
`execute.ts` receives it.

**Minimal fix (one column, one write):**
- Add `fill_price REAL` and `fill_size REAL` to `trades` (or reuse `price` for
  planned and add `fill_price` for actual).
- In `execute.ts` step 12, write `confirmation.level` as `fill_price` and
  `confirmation.size` as `fill_size`.
- `slippage = fill_price - plan.entry` (signed; positive = worse for buys).
- `feedback.ts` gains a `systemsTax(ticker | date range)` query: sum of
  `slippage × fill_size` + fees, compared to gross signal PnL.

**Sequencing:** this is cheap *after* Item 1 lands (state machine persists the
data naturally). Doing it before Item 1 means bolting columns onto a path that
doesn't survive its own failures. **Order: Item 1 → Item 3 → Item 2 enforcement.**

**Derrida check:** yes — the data is a one-column addition to a path we've
confirmed exists. Not speculative.

---

## What this brief does NOT propose

- No new broker integration. IG-only.
- No rewrite of `trade-calculator.ts` — the formulae are sound.
- No ingestion of the article as documentation. It's a generalist field guide;
  the repo is already past its starting point.
- No LLM-backtest unification — structurally infeasible for the strategy layer;
  only the risk layer (`governance.ts`) is shareable, and that's a separate
  wiring task on the Markov branch.

---

## Recommended sequence

1. **Item 1** — order state machine + retry (execution hardening). P2.
2. **Item 3** — systems-tax data capture (rides on Item 1's state table). P3.
3. **Item 2** — governance enforcement of risk-per-trade + lower default. P3,
   and only after the risk-debate-injection question is decided.
4. **Item 4** — autonomous demo loop (the post-fix objective). See below.

---

## Item 4 — Autonomous demo loop (post-fix objective)

**What:** Let the system run its own IG demo account on its own signals, its
own risk profile, and its own sizing — autonomously, on a fixed cadence — so we
 can observe whether it is workable.

**Why this is the objective, not just a feature:** everything upstream of it
(the three fixes, the debate mechanism, the Markov regime engine) is *hypothesis*
until the system runs its own book. A backtest is a hypothesis; a demo account
running on its own signals is the only result that answers "is this workable?"
We are not in a position to determine workability by inspection — only by
observation. The demo loop *is* the observation.

**What already exists (the loop's components):**

| Component | Location | Role in loop |
|---|---|---|
| Signal source | `tradingagents/` LLM debate via `analyze_stream.py` | Produces buy/sell/hold + confidence per ticker |
| Signal store | `signals` table (auto-saved post-analysis) | Loop reads recent signals to find tradeable candidates |
| Prospect pool | `watchlist` table | Tickers to scan — curated, not the whole market |
| Sizing | `src/lib/trade-calculator.ts` | Converts signal + price history → plan (entry, stop, size) |
| Risk gate | `src/server/lib/governance.ts` | Enforces ceilings — *must block, not warn* (Item 2) |
| Execution | `src/cli/commands/execute.ts` + `IGClient` | Places demo orders, writes `trades` row |
| Ledger | hLedger + SQLite `trades` | Source of truth for what's actually held |
| Feedback | `src/server/lib/feedback.ts` | Signal accuracy, post-mortems, (after Item 3) systems tax |

**What does NOT exist (the spine):** no script/daemon that chains:
`pick watchlist → analyze each → filter to actionable signals → size each →
governance check → execute (or skip) → log outcome → repeat tomorrow.` That
chain is Item 4. Each link is built; the string between them is not.

**Proposed shape (minimal, conservative):**

- **Cadence:** daily, once. Borrow the `nightshift.yaml` cron shape (2am).
  Not continuous. Not intraday. The LLM debate is non-deterministic and costs
  real tokens per run — a daily loop on a curated watchlist is the right
  throttle.
- **Watchlist scope:** start with ≤ 5 tickers from `watchlist`. Expand only
  after a week survives without governance breaches or unexplained fills.
- **Budget guard:** hard cap on analyses-per-run (e.g. 5) and a daily token
  budget. If the budget is exhausted mid-loop, stop — don't half-finish.
- **Governance gate:** every candidate passes through `governance.ts` *after*
  sizing and *before* execution. If the gate says no, the trade does not exist.
  This is why Item 2 (enforce, not warn) is a prerequisite.
- **Human-in-the-loop seam:** keep `--yes` gate for the first week of runs.
  Log every decision (signal, plan, governance result, fill) to the DB so the
  human can review before approving the next run. Removing the gate is a
  moat question, not an engineering one — defer it.
- **Exit handling:** the loop must also *close* positions — check open IG
  positions against their exit plans (`src/server/lib/positions.ts`) and act on
  stops/targets/time-stops. A loop that only opens is a chip pan fire waiting
  for a lid.

**Why the fixes are prerequisites, not bureaucracy:**

- Without **Item 1** (state machine), a network hiccup mid-loop leaves an order
  in limbo and the next iteration doesn't know it. The loop eats itself.
- Without **Item 2** (enforce), the "risk profile" is advisory and the system
  improvises under its own enthusiasm. A loop that warns but doesn't block is a
  muppet with a newsletter.
- Without **Item 3** (`fill_price` capture), a week of demo trading produces no
  measurable outcome — an experiment with no instruments.

**Success criteria (the muppet-exclusion gate, system-level):**

The loop passes if, over a one-week demo run, it:
- Respects every governance ceiling (no breaches, only warnings-or-clean).
- Places no order that the risk gate rejected.
- Recovers from at least one transient IG API error without duplicating a
  position (proves Item 1).
- Produces a systems-tax number per ticker (proves Item 3).
- Closes positions on their exit plans, not just opens new ones.

The loop *fails* if it breaches governance, duplicates on retry, or runs a week
with no measurable outcome. A fail is not a disaster — it's the observation we
need. The point is to find out, not to pretend to know.

**Derrida check:** yes. The loop is the eval. Without it, workability is a
speculation; with it, workability is a measurement.

---

## Open questions for the user

- Risk-per-trade default: 0.5% (article, survivable) or 2% (current, aggressive)?
- Should the risk debate agents see the concrete trade plan before voting?
- Auto-execution (no `--yes` gate): deferred per the moat question — but when?
  After one clean week of human-approved demo runs?
- Watchlist scope for the first loop run: which 5 tickers?
