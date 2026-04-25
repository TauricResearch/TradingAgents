# ADR 026: Reflexion Outcome Back-Fill Job

**Date**: 2026-04-25
**Status**: Proposed
**Tags**: [memory, reflexion, feedback-loop, observability]
**Related files**:
- `tradingagents/memory/reflexion.py`
- `tradingagents/memory/macro_memory.py`
- `agent_os/backend/services/langgraph_engine.py`
- `cli/main.py`

## Context

`ReflexionMemory.record_decision()` is called per ticker, per run,
and persists to MongoDB (or local JSON). The schema includes an
`outcome` field that is `None` at write time and is meant to be
filled later via `record_outcome()`:

```python
{
    "ticker": "AMD",
    "decision_date": "2026-04-24",
    "decision": "BUY",
    "rationale": "...",
    "outcome": None,        # to be back-filled
    ...
}
```

`MacroMemory` has the same shape with `record_outcome()` for regime
calls.

In the audited run (`01KQ05XQ07FCBTNSEFJN6EZCNY`, 2026-04-24) the
per-ticker memory rendered into the micro brief as
`"No prior decisions recorded for AMD."` and
`"No prior decisions recorded for INTC."` — confirming that no prior
outcomes have ever been written. Inspection of the codebase shows
that **nothing in the auto-pipeline calls `record_outcome()`**. The
feedback loop is wired but never closed.

The cost is concrete:

- `build_context(ticker, limit=3)` returns "no prior decisions" even
  after dozens of runs, so `micro_summary_agent` and the bull/bear
  researchers receive no learned context.
- `MacroMemory.build_macro_context(limit=3)` rendered the *current
  run's* regime call in the same run's prompt — a same-day
  self-reference rather than a true memory lookup.

Per the project's stated goal of "reflexion memory — learn from past
trading decisions" (`reflexion.py` docstring), this is a silent
feature-disable.

## Decision

Add a deterministic **outcome back-fill job** that runs out-of-band
from the trading graphs and closes the loop.

### Scope

The job processes any decision/regime record whose `outcome is None`
and whose `decision_date + evaluation_horizon_days <= today`. It is
**not** a graph node — it is a scheduled job invoked from the CLI
and from a daily cron in production.

### Configuration

```python
# default_config.py additions
"reflexion_evaluation_horizon_days": 5,    # T+5 by default
"macro_evaluation_horizon_days": 21,       # T+21 for regime calls
"reflexion_backfill_batch_size": 100,
```

Per-tier overrides via env vars per ADR 006.

### Per-decision evaluation

For each pending `ReflexionMemory` record:

1. Load price history `[decision_date, evaluation_date]` via the
   same `get_stock_data` route used by analysts.
2. Compute:
   ```python
   outcome = {
       "evaluation_date": today.isoformat(),
       "price_at_decision": close_at_decision,
       "price_at_evaluation": close_at_evaluation,
       "price_change_pct": pct_change,
       "correct": _evaluate_correctness(decision, pct_change),
   }
   ```
3. `_evaluate_correctness`:
   - `BUY`: correct iff `pct_change >= +1.0%`
   - `SELL`: correct iff `pct_change <= -1.0%`
   - `HOLD`: correct iff `abs(pct_change) <= 5.0%`
   - `SKIP`: not evaluated.
4. `mem.record_outcome(ticker, decision_date, outcome)`.

The thresholds are configurable but explicit — we do not silently
fall back to "neutral" when price data is missing. **Per ADR 023,
if `get_stock_data` fails for a record, the back-fill skips that
record and logs; it does not invent an outcome.**

### Per-regime evaluation

For each pending `MacroMemory` record:

1. Load VIX + sector returns over `[regime_date, evaluation_date]`.
2. Compute:
   ```python
   outcome = {
       "evaluation_date": today.isoformat(),
       "vix_at_evaluation": current_vix,
       "vix_delta_pct": (current_vix - old_vix) / old_vix,
       "regime_confirmed": _evaluate_regime(macro_call, vix_delta, sector_returns),
       "notes": "...",
   }
   ```
3. `_evaluate_regime`:
   - `risk-on` confirmed iff VIX did not spike >25 % and cyclicals
     outperformed defensives over the window.
   - `risk-off` confirmed iff VIX rose or defensives outperformed.
   - `transition` / `neutral` confirmed iff neither extreme held.

### Same-day duplicate prevention and outcome addressing

`MacroMemory.record_macro_state()` should refuse to insert when a
record with the same `regime_date` already exists for the same
`run_id`. Currently same-date rerun produces a duplicate that
`build_macro_context()` then renders as a self-reference. Add a
unique index on `(regime_date, run_id)` and convert insert
collisions into updates.

The same key must be used when writing outcomes. Change
`MacroMemory.record_outcome(...)` from a date-only update to a
deterministic addressable update:

```python
def record_outcome(
    self,
    date: str,
    outcome: dict[str, Any],
    *,
    run_id: str | None = None,
) -> bool: ...
```

When `run_id` is available, MongoDB and local JSON updates must match
`{"regime_date": date, "run_id": run_id, "outcome": None}`. Date-only
updates are permitted only for legacy records with missing `run_id`,
and must update at most one newest pending record while logging that
legacy addressing was used. The back-fill job should pass `run_id`
from each pending record so same-day runs are updated deterministically.

### Operator interface

```bash
# Back-fill all eligible records
python -m cli.main reflexion backfill

# Dry run
python -m cli.main reflexion backfill --dry-run

# Show pending counts
python -m cli.main reflexion status
```

The cron entry runs `reflexion backfill` once daily, after the
trading-day close. Failures of the back-fill job are alerts, not
graph errors — they do not affect any in-flight pipeline.

## Consequences

- After T+5 the per-ticker memory contains real outcomes. Bull/bear
  researchers and `micro_summary_agent` receive non-empty
  `build_context()` strings, so the prompt-injected past-decision
  block becomes a real signal.
- `MacroMemory.build_macro_context()` returns *historical* regimes,
  not self-references.
- Operators get a visible "decisions correct vs total" metric per
  ticker — the basis for any future model-evaluation work.
- The job is decoupled from the graph, so back-fill failures cannot
  pollute trading decisions (consistent with ADR 023's rule that
  memory persistence is non-decision-effecting).

## Out of scope

- Closed-loop confidence calibration — using outcome history to
  modify per-agent confidence in future decisions. That is a
  follow-up that depends on having outcome data first.
- Multi-horizon evaluation (T+1, T+5, T+21) per record. Start with
  the configured single horizon; extend later if needed.
- Long/short outcome attribution for trades sized differently from
  the decision (e.g., scaled-in positions). Treat the recorded
  decision as the unit of evaluation.
