# Verification Report (Member C)

Status: **current as of this verification step.** Records actual outcomes only.
Nothing here is a claim beyond what the offline suite demonstrates; the semantic
gate and CI governance gates are **not** verified (see §5).

Date context: working selection `docs/req/selected-requirements.md`; implementation
at commit `d94c9f8`; application code was **not** modified by this work.

## 1. Environment and commands

```
Python: .venv (3.12)
# New independent C suite
.venv/bin/python -m pytest test/offline -p no:cacheprovider
# Upstream regression baseline
.venv/bin/python -m pytest -q -p no:cacheprovider
```

## 2. Upstream regression baseline (observed)

| Metric | Count |
|---|---|
| Passed | 1412 |
| Failed | 1 |
| Skipped | 0 |
| Deselected | 1 (the single `integration`-marked test) |
| Exit | 1 |

**The one failure** — `tests/test_bedrock_provider.py::test_construction_when_extra_installed`
— is **environmental, not a regression**:
- Reproduced individually (exit 1). Traceback: `NormalizedChatBedrockConverse`
  tries AWS credential resolution and fails with
  `Failed to connect to proxy URL: "http://127.0.0.1:7890"`.
- Re-run with proxy vars unset (`env -u http_proxy -u https_proxy -u HTTP_PROXY -u
  HTTPS_PROXY …`) → **exit 0, 1 passed**.
- Cause: `langchain_aws` installed + a stale global HTTP proxy. Unrelated to the
  `SEL-TA-*` work. Needs an A/E decision to record as a known environment-dependent
  exception for the "zero unapproved regressions" gate (GOV-003).

## 3. C offline acceptance suite (observed)

| Metric | Count |
|---|---|
| Collected | 74 |
| Passed | 74 |
| Failed | 0 |
| Skipped | 0 |
| Exit | 0 |
| Duration | ~1 s |

Coverage: `SEL-TA-FR-001..007` and `SEL-TA-NFR-001..006` (all Must or Should in the
selection). Test IDs, scenarios and expected results are in
`docs/verification/test-plan.md` §4; the E-facing roll-up is
`docs/verification/requirement-test-mapping.md`.

### 3.1 Strengthened end-to-end cases (latest run)

Two cases were rewritten to exercise the full shared `run_analysis_api` path
(publish + read back) rather than the isolated seam. Both pass in the latest run:

| Test ID | What it now proves | Result |
|---|---|---|
| TC-FR006-e | Two runs, identical portfolio contents + analysis date, fresh run ID each, different scripted model text. Both distinct texts appear in the published reports; manifest input-provenance fields (excluding run ID/timestamps) and report provenance lines (excluding Run ID) are identical. | PASSED |
| TC-FR007-d | `OutputChecker.evaluate` is patched to raise *during* `run_analysis_api`; the checker is confirmed called, and the returned result is `COMPLETED`, rating `Hold`, `output_check=NEEDS_REVIEW`, with **exactly one** `CHECK_ERROR` finding (fail-closed, graph-returned retained). | PASSED |

Suite after these changes: **69 collected, 69 passed, 0 failed, 0 skipped, exit 0**.

### 3.2 FR-005 / NFR-003 coverage additions (latest run)

Existing FR-005 (a–c) and NFR-003 (a–c) cases were kept and left unchanged;
assertions were added only where coverage was missing. Three end-to-end cases
were added and pass. Suite after additions: **72 collected, 72 passed, exit 0**.

| Test ID | What it now proves | Result |
|---|---|---|
| TC-FR005-d | A report with **different** Research Manager / Trader / Portfolio Manager judgments labels all three stages (`## II/III/V` + `### Research Manager/Trader/Portfolio Manager`). Each stage carries its own text; exactly one `- Final Portfolio Manager rating:` line is present and equals the PM rating (`Sell`), matching `result.final_rating`. | PASSED |
| TC-NFR003-d | Model error (`TimeoutError` carrying 4 planted secret types) raised through `run_analysis_api` with a synthetic portfolio containing an unrelated-holding marker. Result, report, manifest and `events.jsonl` contain none of the secrets or the unrelated holding; the redacted diagnostic (`TimeoutError` + `[REDACTED]`) is present (non-vacuous); run is `INCOMPLETE`/`MODEL_FAILURE`; source portfolio bytes unchanged. | PASSED |
| TC-NFR003-e | CLI pre-run portfolio input error (`cli.main` with a synthetic file embedding a fake key + unrelated holding) exits 1 and its console output contains neither the secret nor the unrelated holding; source bytes unchanged. | PASSED |

### 3.3 NFR-003 data-error (vendor) path (latest run)

TC-NFR003-f was added to close the remaining mid-run **data-error** gap. Suite
after this addition: **73 collected, 73 passed, exit 0**.

| Test ID | What it now proves | Result |
|---|---|---|
| TC-NFR003-f | Through `run_analysis_api` with a confirmed synthetic holdings snapshot, a scripted vendor stub is confirmed **reached** and raises an unrecovered `NoMarketDataError` (a real `tradingagents.dataflows` vendor error) whose message embeds a unique fake credential. Result is `INCOMPLETE` / `DATA_FAILURE` / `NOT_RUN` with `final_rating=None`. All outputs produced on the path were located and checked leak-free: `reports/complete_report.md`, `reports/complete_report.html`, `manifest.json`, `events.jsonl`, and the returned `RunResult`. The redacted vendor diagnostic (`NoMarketDataError`, `[REDACTED]`) is present in the report (non-vacuous); the manifest records `stop_reason=DATA_FAILURE` and the envelope shows `- Stop reason: DATA_FAILURE`. The fake credential and an unrelated holding marker are absent everywhere; source portfolio bytes unchanged. | PASSED |

**Outputs produced by the data-error path (recorded):** `reports/complete_report.md`,
`reports/complete_report.html`, `manifest.json`, `events.jsonl` under
`results/<ticker>/<run_id>/`, plus the returned `RunResult`. No final rating is
produced; `output_check=NOT_RUN`; the terminal event's `event_outcome` is
`INCOMPLETE` (progress vocabulary), while the typed `stop_reason=DATA_FAILURE`
lives in the result, manifest and report envelope.

### 3.4 NFR-003 credential redaction in a published narrative (latest run)

TC-NFR003-g was added to cover redaction inside a **successfully published**
model narrative (not only error paths). Suite after this addition: **74 collected,
74 passed, exit 0**.

| Test ID | What it now proves | Result |
|---|---|---|
| TC-NFR003-g | A unique fake credential (`sk-NARRATIVELEAK…`) placed next to a benign sentence in the scripted `final_trade_decision`, run via `run_analysis_api` with HTML enabled. Run is `COMPLETED`; **both** `reports/complete_report.md` and `reports/complete_report.html` retain the benign sentence, omit the original credential, and contain the `[REDACTED]` marker (non-vacuous). Synthetic inputs only; existing fixtures reused; no external calls. | PASSED |

## 4. Findings surfaced by the suite

1. **No application defect found in FR-001..007 / NFR-001..006** under offline
   contract testing. Code matched the design contracts.
2. **Design-vs-plan discrepancy (documentation, not code):** the as-of enforcement
   for `--portfolio` lives in `cli/input_ui.resolve_run_context`, not in
   `cli/main.py`. Tests were pointed at the enforcing guard.
3. **Classification nuance:** a bare `ConnectionError` is `INTERNAL_ERROR` by
   design (`classify_exception` matches names/modules). Real provider failures are
   module-tagged. Pinned by TC-NFR001-d2.
4. **Stop reason lives in result/manifest/report envelope, not events:** the
   terminal JSONL event carries the progress outcome (`INCOMPLETE`), while the
   typed `stop_reason` (`DATA_FAILURE`) is in the `RunResult`, manifest and report
   envelope. Recorded while writing TC-NFR003-f; matches NFR-002's stated
   separation of progress vocabulary from terminal `run_outcome`.

## 5. Limitations (explicit)

- Offline suite only for §3: no live provider, no network; a **scripted engine**
  stands in for the graph there. Real model-output variability is exercised
  separately by the live GOV-004 evaluation (§6), which is opt-in.
- **Semantic evaluation (GOV-004): PASS** under the confirmed scoring plan — see §6.
- The limited output checker (Q1–Q4) is verified, but `PASSED` certifies only
  those deterministic rules, not factual accuracy or suitability.
- Persistence-failure fault injection (R13a/b, R14) beyond happy-path isolation is
  **pending**.
- CI/permission governance gates (GOV-001/003/005/006) are **not** verified —
  E has not installed enforcement.

## 6. Live semantic-evaluation status (GOV-004)

- **Status: PASS** under the confirmed scoring plan. Full record, command set,
  run IDs, scores and citations: `docs/verification/semantic-evaluation.md`.
- **Method:** five fixed cases replayed against the live model
  (`deepseek` / `CS5351/DeepSeek-V4-Flash`, `git:e975528`), **two valid attempts
  per case** (10 required, trials 1 and 2). All 10 completed in this pass with
  no transient failures.
  (An earlier evidence set was deleted and regenerated by re-running the live
  suite; run IDs and report text differ from that deleted set, but the fixed
  population, configuration, scores and verdict are unchanged. Any incomplete or
  unverified-exposure attempt is retained rather than dropped.)
- **PASS criteria (observed):** 10/10 completed (≥9/10); 5/5 cases have valid
  reports; semantic score **28/28 = 100%** (≥90%); **0** critical violations;
  challenge exposure verified 4/4.
- **Deterministic vs semantic:** the system verdict for C4/C5 remains
  **NEEDS_REVIEW (Q4)** — the deterministic checker matches the challenge phrase
  the model quoted/refused — and is preserved separately from the human semantic
  score (R5 = pass on context). The two records are not merged.
- **Approval reference:** the human reviewer's instruction for this verification
  step ("Complete the formal GOV-004 evaluation using the confirmed scoring
  plan"), recorded in the session transcript, consistent with the test-plan §2
  approval convention; no separate signed artifact exists.
- **Evidence:** `test/live/evidence/gov004_*.json` (trial 1 and trial 2),
  `test/live/evidence/gov004_scores.json`, artefact trees under
  `test/live/evidence/runs/`.
- **Exit-code contract (for CI):** `score_gov004.py` returns `0`=PASS,
  `1`=FAIL, `2`=PENDING to match its printed verdict; verified offline by
  `test/live/test_score_gov004_exitcodes.py` (4 passed), including the saved
  evidence yielding exit `0`. See `semantic-evaluation.md` §6.1 and
  `verification-constraints.md` E9.

## 7. Remaining verification work

1. ~~Freeze semantic rubric/threshold (C+A) and run GOV-004 population.~~ Done —
   GOV-004 PASS (§6, `semantic-evaluation.md`).
2. Persistence-failure walkthrough tests (report/manifest/rename/terminal-append).
3. INTERRUPTED (R12) and checkpoint-resume behaviour tests if in scope.
4. GOV-001/003/005/006 CI + denied-write tests once E installs enforcement.
5. Resolve the bedrock baseline failure as a recorded environment exception.
6. Course `test/offline` + `test/live` split — **both now exist**; E to wire the
   opt-in live gate per `docs/code-governance/verification-constraints.md`.
7. NFR-003 residual nuance: the deterministic tests prove planted secrets and an
   unrelated holding are absent on the exercised sinks/paths, including a
   successfully published narrative (TC-NFR003-g). Universal absence of
   *arbitrary/paraphrased* secrets inside model narrative is still not proven
   here — it depends on the `Redactor` patterns plus the GOV-004 semantic
   evaluation (now run and PASS for the fixed population; not a proof of
   universal absence).
