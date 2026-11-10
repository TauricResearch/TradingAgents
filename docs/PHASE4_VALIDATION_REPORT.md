# Phase 4 — End-to-end validation, observability and release verification

Report of the fourth phase. Every number below was produced by executing the
code on this branch; nothing is estimated, and where a check could not be run it
is marked **NOT RUN** with the reason rather than reported as passing.

The reliability claim of this phase rests on reproducible results, not on what
any agent wrote. Where a figure is quoted from a report, it is quoted as the
*claim under test*, and the assertion is always on the computation.

---

## 1. Architecture actually verified

```
                       ┌──────────────────────────────┐
 SEC EDGAR ──filings──▶│  fundamentals freshness gate │──stale/unavailable──┐
 (point-in-time)       └──────────────────────────────┘                     │
                                                                           ▼
 Yahoo snapshot ──▶ verified_market_snapshot ──▶ bar assessment ──▶ Execution Gate
 (price, indicators)   (price_as_of, close,           (OPEN/AFTER_HOURS/    │
                        sma50/200, high_52w)           CLOSED, is_final)    │
                                                                           │
 analyst reports ──▶ extraction ──▶ RunInputs ──▶ MetricRegistry ──────────┤
 (labelled figures)   (F2/F3)        (provenance:  (VERIFIED/              │
                                      VERIFIED vs    NOT_COMPUTABLE/        │
                                      LLM_CLAIMED)   UNSUPPORTED/REFUSED)   │
                                                                           │
 simulated book ──▶ sizing (risk budget ∧ exposure cap) ───────────────────┤
 (equity, cash)                                                             │
                                                                           ▼
                                                         ┌─────────────────────────────┐
                                                         │  AuditRecord (JSON)         │
                                                         │  RunRecord (unique id)      │
                                                         └─────────────────────────────┘
```

Verified in this phase: every arrow above has at least one test that exercises
it through the real code path, and each was mutation-checked (see §5).

**The boundary.** There is no broker adapter in this repository.
`PaperOrder` is a frozen dataclass; `ExecutionGate.submit` appends to an
in-memory dict and reaches nothing. The verified end of the line is therefore
the gate, and `tests/test_p4_execution_boundary.py::test_no_broker_adapter_exists_to_call`
fails if an adapter is ever added, so the claim cannot silently become false.

## 2. Commit and build executed

| Item | Value |
|---|---|
| Base | `cc2d11b` — head of Phase 3, which contains Phase 1 (`2288249`) and Phase 2 (`04aacdc`) |
| Branch | `test/p4-tradingagents-e2e-reliability` |
| Interpreter | CPython 3.14.4 (local); CI also runs 3.11 / 3.12 / 3.13 |
| Build id | `<commit>@<code-load timestamp>` — the pair that distinguishes "restarted after merge" from "still running pre-merge code" |

Phase 1–3 are still open as PRs #24, #25, #26. Phase 4 is stacked on their
combined head, so the merge order is #24 → #25 → #26 → this PR.

## 3. Metric results — frozen BRK-B run

State: Q3 2026 consolidated revenue, equity, both share classes, price from an
intraday snapshot at 12:37 New York, and a 100,000 USD simulated book.

| Metric | Status | Value | Independent expectation |
|---|---|---|---|
| `revenue_growth` | VERIFIED | 11.2402 % | (105,647 − 94,972) / 94,972 = 11.2402 % ✓ |
| `book_value_per_share_B` | VERIFIED | 359.5506 | 800e9 / 2.225e9 = 359.5506 ✓ |
| `price_to_book` | VERIFIED | 1.6041 | 576.74 / 359.5506 = 1.6041 ✓ |
| `distance_from_sma200` | VERIFIED | 14.6942 % | (576.74 − 502.85) / 502.85 ✓ |
| `distance_from_sma50` | VERIFIED | 5.8044 % | (576.74 − 545.10) / 545.10 ✓ |
| `distance_from_high` | VERIFIED | −29.0035 % | (576.74 − 812.35) / 812.35 ✓ |
| `session_return` | VERIFIED | 0.5650 % | (576.74 − 573.50) / 573.50 ✓ |
| `eps_gaap` | NOT_COMPUTABLE | — | no EPS in the run; correct to refuse |
| `pe_trailing` | NOT_COMPUTABLE | — | refused because the EPS is not certified |

Two figures the report asserted do **not** reproduce, and both are recorded as
the claims they were:

| Claim in the report | Computed | Why it differs |
|---|---|---|
| P/B 1.73x | 1.6041 | no single input pair produces 1.73 |
| P/B ≈ 0.00116x | 0.0010694 | the A/B ratio applied backwards; even that quotient is not exact |

### Bar, sizing, authorization

| Item | Value |
|---|---|
| Session status at snapshot | `OPEN` (12:37 America/New_York) |
| `bar_is_final` | `false` |
| Quantity proposed | 8 shares |
| Exposure-capped quantity | 8 shares |
| Binding constraint | `EXPOSURE_CAP` (5 % of 100,000 = 5,000 → floor(5,000/576) = 8) |
| Risk-budget-only quantity | 47 (refused: 70 % of the book in one ticker) |
| Planned risk | 168.00 USD (8 × 21.00) |
| Gate action | `PROPOSE_PAPER_ORDER`, reasons `["OK"]` |
| Authorized orders | `[{ticker: BRK-B, quantity: 8, entry: 576.0, stop: 555.0}]` |

## 4. Comparison of the five runs

Five executions over identical frozen inputs, with **five different narratives**
(the premise being that an LLM's words may vary):

| Dimension compared | Result |
|---|---|
| Certified metrics (status, value, formula, operands) | **identical** across all five |
| Raw and normalized `RunInputs` | **identical** |
| Formula ids and operands | **identical** |
| Bar session status and `is_final` | **identical** (`OPEN` / `false`) |
| Authorized quantity for the same candidate | **identical** (8) |
| Risk limits (binding constraint, planned risk, notional, cap applied) | **identical** |
| Gate verdict and reason codes | **identical** |

The narratives were asserted to actually differ, so the comparison is not
vacuous. Narrative variation is visible in the stored reports and changes no
certified number — which is exactly the distinction §5 requires.

## 5. Tests PASS / FAIL

```
ruff check .                         All checks passed
pytest tests/ -q                     2303 passed, 4 skipped, 1 deselected
  of which Phase 4                   55 passed
```

The 4 skips are pre-existing and unrelated: `langchain_aws` is not installed,
and three BRK-B/AAPL/NVDA concept cases are covered by blocking tests instead.

| Suite | Tests | What it proves |
|---|---|---|
| `test_p4_e2e_brkb.py` | 20 | The whole pipeline on the frozen fixture: revenue, growth, BVPS, P/B, EPS unverified, indicators, intraday bar, registry, quantity, authorization, run persistence |
| `test_p4_determinism.py` | 11 | Five repeats agree on every certified number |
| `test_p4_negative.py` | 11 | Ten injected defects each caught, none authorized |
| `test_p4_execution_boundary.py` | 13 | Spies prove no order is created for an invalid plan; no broker adapter exists |
| `test_p3_math_wiring.py` | 27 | The engine is wired into the run path (Phase 3) |

### Mutation verification

A test that cannot fail is not a test. Each policy fix was disabled in turn and
the corresponding tests re-run:

| Mutation | Tests that failed |
|---|---|
| `equity` field removed from `PortfolioContext` | 2 (sizing, cap) |
| `PortfolioContext` ignores unknown keys | 1 (typo rejection) |
| `pe_trailing` registered before EPS reconciliation | 1 (unverified P/E) |
| `claimed_inputs` provenance ignored | 1 (LLM figure certified) |
| Extraction not wired into the graph | 1 (registry populated) |
| Dual-class inputs not read from state | 3 (BVPS, P/B, negative case 1) |
| `write_run` allows overwrite | 1 (never-overwritten) |
| Redaction disabled | 1 (credentials) |
| Run id without a random suffix | 2 (same-day runs, retention) |
| Broker marker injected into the tree | 1 (boundary statement) |

## 6. Proof that invalid orders are blocked

Ten defects injected one at a time into the otherwise-sound BRK-B run. Each case
asserts both that the right reason code appears **and** that
`authorized_orders == ()`.

| # | Injected defect | Reason code | Order authorized |
|---|---|---|---|
| 1 | P/B 1.73x incompatible | numeric claim / valuation | no |
| 2 | Component revenue labelled consolidated | reconciliation finding | no |
| 3 | EPS with no basis | `NO_CERTIFIED_METRIC` | no |
| 4 | ATR inconsistent with stop distance | `INVALID_STOP_ATR_DISTANCE` | no |
| 5 | Wrong stated percentage (+24.2 %) | `ARITHMETIC_MISMATCH` | no |
| 6 | Stop on the wrong side | `RISK_PLAN_BLOCKED` | no |
| 7 | Quantity above the exposure limit | reduced to 8, never 47 | no |
| 8 | Portfolio state absent | `PORTFOLIO_RISK_BUDGET_MISSING` | no |
| 9 | Intraday bar declared EOD | `usable_as_close == false` | n/a (no order path) |
| 10 | SELL read as opening a short | `RATING_NOT_TRADEABLE` | no |

A baseline test asserts the *unmodified* run raises none of these reasons and
does propose, so a system that blocks everything cannot pass this suite.

## 7. Controls still missing

Stated plainly, because each one is a real gap rather than a detail:

1. **`trigger_met` is never computed.** It defaults to `False` and no node
   derives it, so a real run reaches the gate as `WAIT` unless the caller passes
   `True`. The gate is fail-closed either way, but the absence of a real trigger
   evaluation is a functional gap, not a safety one. Out of scope for Phase 4
   and recorded here rather than silently left.
2. **No broker end-to-end verification — and none claimed.** There is no adapter
   to test. §7 of the task anticipated this and asks for the boundary to be
   documented; `docs/DEPLOYMENT_VERIFICATION.md` and
   `test_p4_execution_boundary.py` do so.
3. **Sizing depends on a labelled plan.** Entry/stop/ATR come from
   `extract_plan_numbers` over the trader's text. An unlabelled plan yields no
   risk figures and the gate does not block on that specific absence.
4. **Structured analyst metrics do not exist yet.** Extraction reads labelled
   prose. The intended fix (agents emitting structured metrics) is the §7 gap in
   `docs/specs/ANALYST_CONTEXT_OPTIMIZATION.md`, unchanged by this phase.
5. **The live service was not restarted.** No authorization was given, and the
   procedure explicitly forbids it without one. Whether the *running* production
   process serves this commit is therefore **NOT VERIFIED** — the means to check
   it now exist (§3 of this report) but the check itself was not run against
   production.
6. **Retention is opt-in.** `run_record_keep` defaults to `None`, so disks grow
   until an operator sets a limit. Deliberate (an audit that ages out unasked is
   not an audit) but it is an operational task, not a solved problem.

## 8. Execution evidence

Commands run on this branch, with the results quoted above:

```
ruff check .                          → All checks passed
pytest tests/ -q                      → 2303 passed, 4 skipped, 1 deselected
pytest tests/test_p4_*.py -q          → 55 passed
```

CI on `8ffd7363`, all eight checks green:

```
tests (py3.11)                                      pass  1m4s
tests (py3.12, America/New_York)                    pass  1m10s
tests (py3.13)                                      pass  59s
tests (py3.14)                                      pass  53s
clean-install smoke                                 pass  45s
ruff (strict, full repo)                            pass  7s
P0 reliability regression (offline)                 pass  35s
End-to-end reliability (offline, frozen fixtures)   pass  42s
```

Measured values (from `evaluate_decision` on the frozen fixture):

```
revenue_growth            11.2402 %    VERIFIED
book_value_per_share_B    359.5506     VERIFIED
price_to_book             1.6041       VERIFIED
session status            OPEN         is_final=false
qty_proposed              8            binding=EXPOSURE_CAP
planned_risk              168.0
gate action               PROPOSE_PAPER_ORDER   reasons=["OK"]
authorized_orders         [{ticker: BRK-B, quantity: 8, entry: 576.0, stop: 555.0}]
```

Reproduce with:

```bash
source .venv/bin/activate
python -m pytest tests/test_p4_e2e_brkb.py tests/test_p4_determinism.py \
                 tests/test_p4_negative.py tests/test_p4_execution_boundary.py -q
```

## 9. Deployment procedure

`docs/DEPLOYMENT_VERIFICATION.md`. Summary of the gates:

1. Target SHA is the `custom` merge commit **and** CI is green.
2. `/api/health` reports that commit, a `service_started_at` *later* than the
   merge, and every `validators` entry `true`.
3. The suites pass in an isolated environment (separate `results_dir`, spare
   port).
4. No listener on the production port predates the merge.
5. Restart — **requires explicit authorization**; no script performs it.
6. Post-deploy: one run record inspected for id, fingerprint, registry and gate
   verdict; no run records overwritten.

**NOT RUN:** steps 2–6 against production. Only the isolated-environment suites
(step 3) were executed, as part of the test run.

## 10. Commit SHA and PR

| Item | Value |
|---|---|
| Branch | `test/p4-tradingagents-e2e-reliability` |
| Base | `custom` (PR target), stacked on `cc2d11b` |
| Commit | `8ffd7363` (`8ffd736373eaa3cef411cf28ce993156aa583917`) |
| PR | [#27](https://github.com/muzzye/TradingAgents/pull/27) |
| CI | 8/8 green — including the new `End-to-end reliability (offline, frozen fixtures)` job, now also a **required** check on `custom` |

Merge order: **#24 → #25 → #26 → this PR**. No merges were performed.

Because the end-to-end job was added to the ruleset's required checks, a P0
failure in the Phase 4 suites now blocks a merge into `custom` rather than merely
appearing in the run log.

---

## Definition of Done — status

| Requirement | Status | Evidence |
|---|---|---|
| No unresolved P0 mathematical error | **met** for the cases in the suite | §6 — ten defects all caught |
| The service runs the expected code | **means provided, not verified in production** | §3, §7 item 5 |
| Every critical metric has verifiable provenance | **met** | `source_status` VERIFIED vs LLM_CLAIMED; §3 |
| Formulas are executed by code | **met** | every certified metric carries `formula_id` + `operands` |
| Agents cannot overwrite certified numbers | **met** | `LLM_CLAIMED` is not a trusted source; mutation-verified |
| Intraday data distinguished from EOD | **met** | bar `OPEN`, `is_final=false`, blocks confirmed-close strategies |
| Sizing uses real simulated-portfolio data | **met** | equity 100,000 → 8 shares, cap binding |
| The Execution Gate is fail-closed | **met** | 6 parametrized invalid plans, all refused, none authorized |
| All mandatory tests pass | **met** | 2301 passed, 0 failed |
| Every execution keeps an independent audit | **met** | one record per run, never overwritten |

**Not claimed:** real-broker safety. No adapter exists, none was tested, and
`test_no_broker_adapter_exists_to_call` fails if that changes.
