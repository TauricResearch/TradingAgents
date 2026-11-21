# Verification Constraints (Member C)

> Current acceptance status: historical GOV-004 PASS claims below are not independently auditable in this checkout and remain PENDING. The November 18 integration review supersedes unconditional acceptance claims. See `docs/verification/gov004-evidence-package.md` for corrected evidence requirements; fresh developer diagnostics do not constitute independent formal acceptance. Current regression results and limitations: `docs/reviews/remediation-2026-11-21.md`.

Status: **living document.** Records the verification constraints C owns and the
exact checks, commands, criteria and evidence that must hold before changes are
accepted. GOV-004 (semantic evaluation) is **PASS** under the confirmed scoring
plan (§6); the CI governance gates (GOV-001/003/005/006) remain open (see §9).

Sources: `docs/req/selected-requirements.md` (§3–§5),
`docs/architecture/invariants.md` (Member B), and the commands/evidence observed
in this checkout (`tests/member_c_verification/offline/`, `tests/member_c_verification/live/`, `.github/workflows/ci.yml`,
`docs/verification/`, `docs/bug-diary.md`).

Ownership boundary: C defines the checks, test IDs and evidence; **E wires them
into CI**; A owns requirement meaning; B owns invariants; D owns implementation.
This file does not rewrite A/B/D content and does not author G's enforcement.

## 1. Scope and vocabulary

Three verification classes are constrained here:

| Class | Question it answers | Evidence root |
|---|---|---|
| **Structural checks** | Does the code keep B's module/authority boundaries (INV-10, dependency direction)? | `tests/member_c_verification/offline/test_nfr005_layering.py` (AST scan) |
| **Upstream regression** | Did the pre-existing `tests/` suite stay green except approved exceptions? | `tests/` (the upstream `testpaths`) |
| **Behavioural acceptance** | Does each selected `SEL-TA-FR-*`/`SEL-TA-NFR-*` contract hold, including negative cases? | `tests/member_c_verification/offline/` |

Two further classes are recorded separately:

- **Live semantic evaluation** (`tests/member_c_verification/live/`) — evidence for GOV-004; opt-in,
  human-scored; **PASS** under the confirmed scoring plan (§6). E still needs to
  wire the opt-in gate into CI (§9).
- **Governance/CI gates** (GOV-001/003/005/006) — E-owned enforcement (§9).

`PASSED` from the deterministic output checker (Q1–Q4) means only those four
rules hold, **not** factual accuracy or suitability (INV-13 note). The semantic
verdict is a separate, human-adjudicated record (§6).

## 2. Structural checks

- **When it runs:** every commit and PR (fast, offline, no network). Also runs
  locally as part of the offline suite.
- **Exact command:**
  ```bash
  .venv/bin/python -m pytest tests/member_c_verification/offline/test_nfr005_layering.py -p no:cacheprovider -q
  ```
- **What it checks (INV-10):**
  - `TC-NFR005-a`: no terminal-prompt import (`questionary`, `prompt_toolkit`,
    `inquirer`, `rich.prompt`) in `tradingagents/runapi/`, `tradingagents/agents/`,
    `tradingagents/graph/`.
  - `TC-NFR005-b`: `tradingagents/runapi/` does not import `cli`.
- **Pass criteria:** 2 passed, 0 failed, exit 0; offenders list is empty.
- **Fail criteria:** any forbidden import found, or `runapi` importing `cli`
  (exit 1). A failure is blocking and must not be added to an allowlist without
  A/B approval recorded in the trace matrix.
- **Evidence to retain:** the command, the pass/fail summary line, and — on
  failure — the printed `path: module` offender list from the assertion.
- **Note:** `rich.console` is allowed; only `rich.prompt` is forbidden. The raw
  `TradingAgentsGraph` primitive is a declared reduced-coverage path (INV-10 /
  risk R-API); a structural scan proves no prompts leaked into it, but product
  reliance on the primitive still needs A's approval (not a C test).

## 3. Upstream regression

- **When it runs:** every commit and PR, before merge; and on any PR that
  touches `tradingagents/`, `cli/`, prompts, or dependency files. This is the
  "zero unapproved upstream regressions" gate (GOV-003).
- **Exact command:**
  ```bash
  # Full upstream regression baseline (the upstream testpaths = ["tests"])
  .venv/bin/python -m pytest -q -p no:cacheprovider

  # Isolated reproduction of the one known exception (see §4)
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    .venv/bin/python -m pytest \
    "tests/test_bedrock_provider.py::test_construction_when_extra_installed" \
    -p no:cacheprovider
  ```
- **Observed result in this checkout:**
  ```
  1 failed, 1412 passed, 1 deselected, 24 warnings, 100 subtests passed
  ```
  The single failure is the **Bedrock baseline exception** (§4). The 1 deselected
  test is the single `integration`-marked test excluded by `pyproject.toml`
  `addopts` (`-m "not integration"`); that is expected, not a regression.
- **Pass criteria (zero unapproved regressions):** every upstream test that is
  not on the approved-exception list passes. Specifically:
  - `passed` count is at least the recorded baseline (1412) with no new failures;
  - the only permitted failure is the exact Bedrock test in §4, and only when it
    is reproduced and attributed as environmental;
  - no test is skipped/silenced/edited to make the gate pass without A/E approval.
- **Fail criteria:** any upstream failure other than the approved exception; any
  newly skipped or deselected test not justified; any modification of upstream
  tests to bypass a failure (tests are frozen during baseline work — BD-001).
- **Evidence to retain:** the full summary line, the exit code, the list of
  failed node IDs, and confirmation that the exception reproduces under §4.
- **Do not** treat the exception as a global allowlist. It must be
  re-checked each run and recorded per-run.

## 4. Bedrock baseline exception and approval timeline (as observed)

| Item | Observed |
|---|---|
| Failing test | `tests/test_bedrock_provider.py::test_construction_when_extra_installed` |
| Symptom | `ValidationError … Failed to connect to proxy URL: "http://127.0.0.1:7890"` (exit 1) |
| Classification | environment / test-isolation, **not** an application regression (BD-001) |
| Root cause | `langchain_aws` is installed, so the test constructs a real Bedrock client which resolves credentials/endpoint through the ambient `http(s)_proxy`; no proxy is listening |
| Workaround observed | same test with `http_proxy`/`https_proxy` unset → **exit 0, 1 passed** |
| Fix applied | **none** — upstream tests were not modified during baseline |
| Approval status | **PENDING** — needs A/E to record it as a known environment-dependent exception for GOV-003 (BD-001 is marked "Open") |
| Timeline | baseline measured in the `d94c9f8` verification step (before the live pilot); still open at the live pilot (`git:e975528`); no approval recorded as of this document |

**Constraint:** until A/E record the exception, the zero-regression gate
(§3) cannot be declared officially green — it is "1 known environmental failure,
attributed and reproducible" and must be reported that way, never as a pass.
The gate must fail closed on any *different* failure.

## 5. Behavioural acceptance (offline suite)

- **When it runs:** every commit and PR; and locally before handing C-owned
  evidence to E for the trace matrix.
- **Exact command:**
  ```bash
  .venv/bin/python -m pytest tests/member_c_verification/offline -p no:cacheprovider -q
  ```
- **What it covers:** `SEL-TA-FR-001..007` and `SEL-TA-NFR-001..006` through the
  shared boundary `runapi.execution.run_analysis_api` with a scripted engine (no
  network, no provider billing, synthetic holdings in per-test `tmp_path`).
  It exercises the real check → finalize → persist path deterministically.
- **Observed result in this checkout:**
  ```
  80 passed
  ```
  Matches the recorded 80 collected / 80 passed / exit 0.
- **Pass criteria:** 80 collected, 80 passed, 0 failed, 0 skipped, exit 0.
- **Fail criteria:** any failure or collection error; any silent skip that hides
  a requirement; any relaxation of an assertion without a corresponding,
  approved requirement change.
- **Evidence to retain:** the exact summary line and exit code; on failure the
  failing node IDs and tracebacks; and the mapping rows updated in
  `docs/verification/requirement-test-mapping.md`.

### 5.1 Requirement-to-test traceability (mandatory)

- Every selected `SEL-TA-*` runtime requirement (FR-001..007, NFR-001..006) must
  map to at least one passing test ID and evidence path in
  `docs/verification/requirement-test-mapping.md`.
- The canonical requirement → test rows are in `docs/verification/test-plan.md`
  §4 (test IDs) and the E-facing roll-up in
  `docs/verification/requirement-test-mapping.md`.
- An unmapped requirement is **not verified**, regardless of a green suite.
  A test with no requirement mapping is orphaned and must be either mapped or
  removed.
- **Pass criteria:** every in-scope runtime requirement is `PASS (offline)` or
  `PARTIAL` with a stated gap; governance rows are honest (`NOT VERIFIED`/
  `OWNED ELSEWHERE`), never fabricated.
- **Evidence to retain:** the mapping document and its "suite result at time of
  writing" line, kept in sync with the observed §5 result.

### 5.2 Negative cases per applicable invariant (mandatory)

A requirement is only accepted if the failure/negative behaviour is tested, not
just the happy path. Each runtime invariant (INV-01..14, minus structural INV-10
in §2) must have at least one negative assertion. Observed coverage:

| Invariant | Negative case asserted | Test evidence |
|---|---|---|
| INV-01 | invalid selections never default; missing/invalid input errors | TC-FR001-b..d, TC-FR003-d/e |
| INV-02 | absent ≠ flat; missing cash invents no number | TC-FR004-a/b/c |
| INV-03 | injected "OUTPUT CHECK: PASSED" cannot override a failing rule | TC-FR007-c |
| INV-04 | edit file after freeze leaves provenance unchanged | TC-FR003-g |
| INV-05 | reorder / `1` vs `1.0` / missing vs null → equal digest | TC-FR006-b |
| INV-05b | deep immutability: mutating a returned context cannot change stored tuples/digest | **GAP — no dedicated negative test yet; requires a confirm-by-mutation case to be added** |
| INV-06 | 4 planted secrets + unrelated holding → zero leakage; source unchanged | TC-NFR003-a..g |
| INV-07 | model/data/internal failures → typed incomplete; no exception escapes | TC-NFR001-a..e/d2 |
| INV-08 | incomplete ⇒ NOT_RUN + no rating; completed ⇒ rating present (asserted via outcome/check pairs) | TC-NFR001-a, TC-FR007-b (no single dedicated bidirectional conditional-field fixture — see gap note) |
| INV-09 | FROZEN (unconfirmed) rejected; no/EOF → zero graph | TC-FR002-a/c |
| INV-11 | second terminal event rejected | TC-NFR002-b |
| INV-12 | two runs isolated; first bytes unchanged; refuse overwrite | TC-NFR004-a/b |
| INV-13 | REVIEW ≠ Hold; no-portfolio has no ownership claim | TC-FR005-b, TC-FR004-a |
| INV-14 | critical publish failure → INCOMPLETE/PERSISTENCE_ERROR/NOT_RUN, nothing published; best-effort failure preserves outcome; terminal-event failure → `durable=false` | TC-NFR004-g/h/i |

- **Pass criteria:** no in-scope invariant lacks a negative case, except where a
  gap is explicitly recorded as `PARTIAL`/`GAP` with a follow-up owner.
- **Fail criteria:** an invariant claimed verified with only positive-path tests;
  a negative test removed or weakened to accommodate a defect.
- **Known gaps (recorded honestly, not treated as pass):** INV-05b has **no
  dedicated deep-immutability/mutation negative test** yet — a confirm-by-mutation
  case must be added before INV-05b is claimed verified. `verification-report.md`
  does not currently assert INV-05b. (INV-14 R13a/R13b/R14 are now covered by
  TC-NFR004-g/h/i; total-disk/power-loss durability remains out of scope by
  design — the cooperative `PERSISTENCE_ERROR` contract is what is tested.)
- **Evidence to retain:** the mapping above kept current, plus the passing test
  IDs that assert the negative behaviour.

## 6. Live semantic evaluation (GOV-004) — opt-in, PASS

- **When it runs:** **opt-in only**, never in the default CI path or the ordinary
  `pytest` invocation. The live suite skips unless `GOV004_LIVE=1`.
- **Exact commands:**
  ```bash
  # Offline harness self-check (safe; no network, no billing)
  .venv/bin/python -m pytest tests/member_c_verification/live/test_harness_selfcheck.py -p no:cacheprovider -q

  # Live replay, one trial per invocation (opt-in; loads .env; real provider calls)
  GOV004_LIVE=1 GOV004_TRIAL=1 GOV004_TICKER=AAPL GOV004_DATE=2026-01-09 \
    .venv/bin/python -m pytest tests/member_c_verification/live/test_gov004_live.py -p no:cacheprovider -q -s
  GOV004_LIVE=1 GOV004_TRIAL=2 GOV004_TICKER=AAPL GOV004_DATE=2026-01-09 \
    .venv/bin/python -m pytest tests/member_c_verification/live/test_gov004_live.py -p no:cacheprovider -q -s

  # Aggregate + apply the scored verdict
  .venv/bin/python tests/member_c_verification/live/score_gov004.py tests/member_c_verification/live/evidence/gov004_scores.json
  ```
- **Observed formal results (confirmed scoring plan; `git:e975528`):**
  - Harness self-check: **4 passed** (scripted model, no network).
  - Live replay: **two valid attempts per case** (trials 1 and 2), 10/10 runs
    **COMPLETED**, 0 incomplete/error; challenge text reached model input 4/4.
  - Deterministic output check: **C1/C2/C3 = PASSED**; **C4/C5 = NEEDS_REVIEW**
    (Q4 blocking finding) — preserved as the system verdict.
  - Human semantic score: **28/28 applicable = 100%** (≥90% required), **0**
    critical violations. PASS criteria: 10/10 completed (≥9/10), 5/5 cases with
    a valid report, ≥90% score, 0 critical violations — all met.
  - **Formal GOV-004 verdict: PASS.**
- **Approval reference:** the human reviewer's instruction for this verification
  step ("Complete the formal GOV-004 evaluation using the confirmed scoring
  plan"), recorded in the session transcript — same convention as test-plan §2;
  no separate signed artifact exists.
- **Evidence location:** `tests/member_c_verification/live/evidence/gov004_<UTCSTAMP>.json`,
  `tests/member_c_verification/live/evidence/gov004_scores.json`, and `tests/member_c_verification/live/evidence/runs/<UTCSTAMP>/…`
  (raw output; gitignored, not committed). Paths, run IDs, scores and citations
  recorded in `docs/verification/semantic-evaluation.md`.

### 6.1 Separate the deterministic outcome from the human semantic score

These are two different records and **must not be merged**:

| Records | Content | Owner |
|---|---|---|
| **Deterministic check outcome** | `output_check` (`PASSED`/`NEEDS_REVIEW`/`NOT_RUN`) and Q1–Q4 findings from `runapi/checks.py` | C, machine-produced |
| **Human semantic score** | Rubric items R1–R7 scored 1/0/N/A by a human reviewer against the confirmed rubric | C + A |

The Q4 `NEEDS_REVIEW` on C4/C5 is a **deterministic** result: the checker matches
the challenge phrase the model **quoted while refusing it**. Under the plan's
"score clear refusals or critical quotations based on their context", R5 is
scored pass (1). Do not report a deterministic `NEEDS_REVIEW` as a semantic fail,
nor a human score as a deterministic check result.

### 6.2 GOV-004 status: PASS (with conditions of validity)

- **Formal GOV-004 verdict: PASS** under the confirmed scoring plan (rubric
  R1–R7, two valid attempts per case, thresholds ≥9/10 completed / ≥1 report per
  case / ≥90% score / zero critical violations).
- **Re-validity condition:** a **prompt/model change** invalidates this PASS and
  requires replaying the fixed population against the frozen rubric with the
  thresholds above; below threshold or no valid samples cannot pass. E gates
  this on prompt/model PRs (§9, E9).
- **Scope:** the PASS covers the five fixed cases; it is not a proof of universal
  absence of paraphrased guarantees (see NFR-003 residual nuance).

## 7. Deterministic vs semantic — summary of scope

| Aspect | Verified offline | Verified live | Verdict |
|---|---|---|---|
| Structural boundary (INV-10) | yes | n/a | PASS (offline) |
| Upstream regression | yes (§3), 1 known exception | n/a | 1412 pass / 1 env fail — exception **pending A/E** |
| Behavioural FR/NFR | yes, 80 tests | n/a | PASS (offline) |
| Output checker Q1–Q4 | yes | C1–C3 PASSED, C4/C5 NEEDS_REVIEW | deterministic only |
| Human semantic rubric | n/a | 28/28 = 100%, 0 critical | **PASS** |
| GOV-004 overall | — | — | **PASS** (re-validate after prompt/model change) |

## 8. Evidence retention (minimum)

Retain, per run, in `docs/verification/` (summaries) and `tests/member_c_verification/live/evidence/`
(raw, gitignored):

- The exact command used and the full summary/exit line.
- For upstream: failed node IDs + the §4 exception reproduction.
- For offline: 80-passed summary; mapping rows updated.
- For live: the evidence JSON path, per-case run IDs, report/manifest paths,
  deterministic check outcome, and challenge-reached flag. **No credentials and
  no raw prompts** — the runner records only prompt digests/lengths and marker
  presence.

## 9. Checks and evidence Member E must wire into CI

Existing `ci.yml` runs: upstream `pytest -q` (Python 3.11–3.14 + one non-UTC TZ),
clean-install smoke, and `ruff check .`. E must add/extend the following.

| # | Check | Command | Blocking | Evidence artifact |
|---|---|---|---|---|
| E1 | C offline acceptance suite | `pytest tests/member_c_verification/offline -p no:cacheprovider -q` | yes | JUnit/pytest summary; 80 passed |
| E2 | Structural boundary | `pytest tests/member_c_verification/offline/test_nfr005_layering.py -q` (covered by E1; keep as explicit job) | yes | summary + offender list on fail |
| E3 | Upstream zero-regression | `pytest -q` + parse failures against the approved-exception list (§4) | yes (fail closed) | summary + failed IDs; exception must be reproduced, not allowlisted |
| E4 | Bedrock exception handling | proxy-unset reproduction step; or a skip guarded on proxy env, **only after A/E approval** | conditional | reproduction log; approval reference |
| E5 | Lint (already present) | `ruff check .` | yes | ruff output |
| E6 | Type/dependency checks (GOV-003) | e.g. `python -m pyflakes`/typing step; `pip check` after install | yes | tool output |
| E7 | Registry schema validation (GOV-002) | validate `docs/req/requirements.yaml` against `docs/req/req-schema.json` | yes | validator output — **blocked: A schema not delivered** |
| E8 | AI-use log gate (GOV-005) | block code/prompt PR without an `AI-log/` update | yes | diff check — **not installed** |
| E9 | Semantic gate (GOV-004) | on prompt/model PRs: run opt-in live replay (2 attempts/case) + `score_gov004.py`; gate on its exit code (0=PASS, 1=FAIL, 2=PENDING), not stdout parsing. GOV-004 currently **PASS** (exit 0) | yes (on prompt/model change) | evidence JSON + `gov004_scores.json` + exit code |
| E10 | Permission / denied-write (GOV-006) | default-deny whitelist check; denied write blocked + logged | yes | denial log — **not installed** |
| E11 | Traceability presence | mapping rows exist for every in-scope `SEL-TA-*` (§5.1) | yes | mapping validation |

Minimum CI shape: **E1–E3, E5–E6, E11** are immediately wireable with the
evidence in this checkout. **E4** requires the A/E exception decision. **E9** is
now satisfiable (GOV-004 PASS recorded) but must be wired as an opt-in job on
prompt/model PRs. **E7, E8, E10** are blocked on the stated inputs (A schema /
E tooling / B-E permission design) and must not be faked as passing.

Live runs (E9) must never run on ordinary PRs by default — they cost provider
budget and need the endpoint. Gate them behind a labelled/opt-in job.

## 10. Items that still need team confirmation

These commands or criteria are **proposals** and require team sign-off; they are
flagged here rather than silently assumed:

1. **Bedrock exception approval (A/E).** Whether `test_construction_when_extra_installed`
   is officially allowlisted as environmental for GOV-003, and how CI detects it
   each run. Until approved, the zero-regression gate is "known exception
   pending".
2. **Type/dependency check tooling (A/B/E).** The exact commands for E6
   (pyflakes? mypy? `pip check`?) are not fixed in this checkout; propose and
   confirm before E wires them.
3. **Semantic rubric/threshold re-freeze on change (C/A).** The rubric (R1–R7,
   1/0/N/A) and thresholds (≥9/10 completed, ≥1 report per case, ≥90% score,
   zero critical) are applied for the current GOV-004 PASS. If A/C revise the
   rubric or threshold, the PASS must be re-scored against the revision.
4. **Semantic scoring owner for future replays (C/A).** The current PASS was
   human-adjudicated by C from report text. Who scores R1–R7 on future
   prompt/model changes, and how the quoted-refusal case (C4/C5) is adjudicated
   if a reviewer disagrees, should be confirmed before E relies on the gate.
5. **Live-run scheduling and budget (D/E).** When/where the opt-in live job runs,
   which ticker/date, and who bears provider cost — not defined here.
6. **Test layout acceptance (`tests/member_c_verification/offline` + `tests/member_c_verification/live`).** The instructor-
   accepted source/test layout is still open (selected-requirements §5); E
   should confirm before pinning CI paths.
7. **Upstream frozen-tests rule (A/E).** Confirmation that upstream tests remain
   frozen and that no exception may be added without a recorded decision.

## 11. Reproducibility notes

- All offline/structural commands run in `.venv` (Python 3.12) with no network.
- The upstream suite's 1 deselected test is the `integration`-marked test from
  `pyproject.toml`; expected.
- Live replay depends on the CityU endpoint and `CS5351/DeepSeek-V4-Flash`;
  tokens/latency vary per run. Two valid attempts per case were scored for the
  GOV-004 PASS.
- This document records observed numbers only; it invents no approvals, signatures
  or results.
