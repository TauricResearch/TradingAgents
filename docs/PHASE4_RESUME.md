# Resume point — Phase 4 complete, nothing merged

Snapshot of the working state, written so work can resume on any machine
without reading the chat history.

## Where the work stands

| Item | Value |
|---|---|
| Integration branch | `custom` at `f2e7da0` |
| Phase 4 branch | `test/p4-tradingagents-e2e-reliability` at `207dc7e` |
| Phase 4 PR | [#27](https://github.com/muzzye/TradingAgents/pull/27) → base `custom`, `MERGEABLE`, **8/8 checks pass** |
| Worktrees | `/tmp/ta-p1`, `/tmp/ta-p2`, `/tmp/ta-p3`, `/tmp/ta-p4`, `/tmp/ta-audit` |
| Working tree | clean; local and remote identical (0 ahead, 0 behind) |

**Nothing has been merged.** `custom` still does not contain Phases 1–4.

## Open pull requests, in merge order

| Order | PR | Branch | State |
|---|---|---|---|
| 1 | #24 | `fix/p1-runtime-gate-integration` | MERGEABLE |
| 2 | #25 | `fix/p2-financial-data-integrity` | MERGEABLE |
| 3 | #26 | `fix/p3-deterministic-math-wiring` | MERGEABLE |
| 4 | #27 | `test/p4-tradingagents-e2e-reliability` | MERGEABLE, 8/8 |
| — | #23 | `audit/tradingagents-data-lineage-brkb` | MERGEABLE (read-only audit docs) |
| — | #17, #19 | older P0 work | MERGEABLE, superseded |
| — | #11, #12, #13, #18 | older P0 work | **CONFLICTING**, superseded — close rather than merge |

The order is not arbitrary: #24 supplies the metric registry to the gate, #25
classifies vendor concepts, #26 wires the math engine end to end, #27 validates
all of it. Each is stacked on the previous head, so merging out of order
produces conflicts rather than a broken build.

## How to resume

```bash
# 1. Recreate the environment (the venv is not in git).
cd /var/www/TradingAgents
source .venv/bin/activate          # plain `python` does not exist on this host

# 2. Reattach the worktree if /tmp was cleared.
git worktree list
git worktree add /tmp/ta-p4 test/p4-tradingagents-e2e-reliability   # if missing

# 3. Confirm the saved state.
cd /tmp/ta-p4
git status --short                 # expect empty
git log --oneline -1               # expect 207dc7e
gh pr checks 27 --repo muzzye/TradingAgents
```

## Verification commands

```bash
cd /tmp/ta-p4 && source /var/www/TradingAgents/.venv/bin/activate

ruff check .                       # All checks passed
pytest tests/ -q                   # 2303 passed, 4 skipped, 1 deselected
pytest tests/test_p4_*.py -q       # 55 passed
```

The 4 skips are pre-existing: `langchain_aws` is not installed, and three
BRK-B/AAPL/NVDA concept cases are covered by blocking tests instead.

## Two decisions to make when work resumes

### 1. Merge the stack, or keep reviewing

Merging #24 → #25 → #26 → #27 brings `custom` to the fully validated state and
makes the `e2e-reliability` required check meaningful on the integration branch.
`AGENTS.md` §4.8 forbids autonomous merges; the user has authorised merges
explicitly in earlier phases but not for this stack.

Close #11, #12, #13, #18 first: they conflict and their content already lives in
the newer phases.

### 2. The known functional gap: `trigger_met`

`evaluate_decision(trigger_met=...)` defaults to `False` and **no node computes
it**. Measured consequence: five real runs over the frozen fixture all reach the
gate as `WAIT` with reason `ENTRY_TRIGGER_NOT_MET`.

This is fail-closed (no invalid order) but functionally incomplete: a real run
will never propose an order on its own trigger. Fixing it needs a decision the
contract does not make for us — what counts as a met trigger for this system
(entry reached? confirmation bar? rating change?). Options:

- derive it from the trader's plan text (`entry` vs current price, direction-aware);
- require the plan to state an explicit trigger and fail closed when absent;
- leave it caller-supplied and document it as an input, not an inference.

Do not invent one silently: the audit trail would then claim a trigger was
evaluated when it was assumed.

## Other residual gaps, in priority order

1. **Production not verified.** The service was never restarted (no authorisation
   requested). Whether the running process serves this commit is **NOT VERIFIED**.
   `docs/DEPLOYMENT_VERIFICATION.md` now makes the check possible; it has not been
   run against production.
2. **Sizing depends on a labelled plan.** If the trader does not write
   `entry`/`stop`/`ATR` in a recognisable form, `extract_plan_numbers` yields
   nothing and the gate does not block on that specific absence.
3. **Structured analyst metrics do not exist.** Extraction reads labelled prose —
   the §7 gap in `docs/specs/ANALYST_CONTEXT_OPTIMIZATION.md`, unchanged.
4. **Retention is opt-in.** `run_record_keep` defaults to `None`, so run records
   accumulate until an operator sets a limit.
5. **CHANGELOG has repeated `### Fixed` sections** under `[Unreleased]`,
   pre-existing since before Phase 3 and left alone as out of scope.

## What was proven in Phase 4

Measured on the frozen BRK-B fixture, all reproducible with the commands above:

| Metric | Status | Value | Independent check |
|---|---|---|---|
| `revenue_growth` | VERIFIED | 11.2402 % | (105,647 − 94,972) / 94,972 |
| `book_value_per_share_B` | VERIFIED | 359.5506 | 800e9 / 2.225e9 |
| `price_to_book` | VERIFIED | 1.6041 | 576.74 / 359.5506 |
| `eps_gaap` | NOT_COMPUTABLE | — | no EPS in the run: refusing is correct |

The report under test asserted P/B **1.73x** and **≈0.00116x**. Neither
reproduces; 0.00116 is also not the exact inverse ratio (0.0010694).

Five persisted runs over identical inputs, five different narratives: five
distinct run ids, **one** metric/risk/gate digest, **one** authorised quantity.

> The digest excludes `checked_at` / `generated_at` / `created_at`. An earlier
> version included them, passed locally (five runs inside one second) and failed
> in CI where the runs straddled a second boundary. §5 asks the *values* to
> agree; it does not ask five runs to share a clock. The test now also asserts
> that timestamps were present — so the strip removed something real — and that
> the remaining structure is identical, so no difference hid behind a missing
> key. Mutation-checked: a drifting registry id still fails it.

Ten injected defects, all caught, none authorised: incompatible P/B,
non-consolidated revenue labelled consolidated, EPS without a basis,
inconsistent ATR, wrong percentage, wrong-side stop, quantity over the cap,
absent portfolio, intraday bar declared EOD, `SELL` read as opening a short.

## Files added by Phase 4

```
tradingagents/dataflows/run_record.py          per-run immutable records, redaction, retention
tests/fixtures/brkb_2026_11_09.py              frozen fixture + independently written expectations
tests/test_p4_e2e_brkb.py                      20 tests: whole pipeline
tests/test_p4_determinism.py                   11 tests: five repeats agree, through the records too
tests/test_p4_negative.py                      11 tests: ten defects caught, none authorised
tests/test_p4_execution_boundary.py            13 tests: spies, and a guard against a silent broker adapter
docs/DEPLOYMENT_VERIFICATION.md                controlled release procedure
docs/PHASE4_VALIDATION_REPORT.md               the §10 technical report
```

Modified: `gate_integration.py` (run-scoped audit filename), `math/run_registry.py`
(dual-class inputs now read from state — a Phase 3 omission), `graph/trading_graph.py`
(run record written per analysis), `build_info.py` (runtime fingerprint),
`default_config.py` (retention and truncation limits), `.github/workflows/ci.yml`
(new `e2e-reliability` job, now a required check on `custom`).
