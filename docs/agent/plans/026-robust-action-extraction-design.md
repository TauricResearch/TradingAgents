    # 026 — Robust Action Extraction with LLM Fallback (Design Spec)

**Date:** 2026-05-03
**Status:** Design — awaiting user review before implementation plan
**Origin:** Audit of run `01KQQGTQN98BZHTFECB8QXPTKA` (2026-05-01) — see `ECONOMIST_VERIFICATION_REPORT_v2.md`
**Related rules:** ADR 011 (opt-in vendor fallback / no silent fallback), `feedback_no_decision_fallback` (decision-effecting nodes must hard-fail on parse errors)

---

## 1. Problem

The shared helper `_infer_recommendation` ([tradingagents/agents/utils/output_validation.py:556](../../../tradingagents/agents/utils/output_validation.py#L556)) extracts `BUY | SELL | HOLD` from PM/trader/RM/risk-synthesis prose using six single-line regex patterns. On no match, it **silently defaults to `HOLD`**.

In the audited run, the PM emitted its rating as a multi-line markdown header:

```
**1. Rating**
**Buy**
```

None of the six regexes match this format. The default kicks in, and `final_trade_decision_structured.action` becomes `"HOLD"` despite the prose unambiguously saying Buy. Downstream `_completed_scan_candidates` ([portfolio_setup.py:70](../../../tradingagents/graph/portfolio_setup.py#L70)) filters on `action == "BUY"`, so both BUY-rated tickers (OWL, TEAM) were dropped from `prioritized_candidates`. The portfolio PM correctly diagnosed the empty input and abstained, leaving the portfolio at 91% cash with capital that should have been deployed.

The same brittle helper feeds five callers, so the bug is shared:
- `build_investment_plan_structured` (RM recommendation)
- `build_trader_plan_structured` (trader's final action)
- `build_risk_synthesis_structured` (risk consensus direction)
- `build_final_decision_structured` (PM action) ← the one that bit us in this run
- legacy callsite from earlier prose-extraction code

This violates `feedback_no_decision_fallback`: a decision-effecting node is silently demoting BUY decisions to HOLD on a parse miss instead of hard-failing.

## 2. Goals

1. Stop the silent HOLD-on-parse-miss across all five callers.
2. Make extraction robust to reasonable prompt drift without rewriting regexes every release.
3. Surface parse failures as visible per-ticker failures so the portfolio graph can continue cleanly on the remaining tickers.
4. Preserve back-compat for the four non-final-decision callers via a thin shim that *raises* (instead of returning HOLD) on hard fail; update those callers to handle it.

## 3. Non-Goals (deferred)

- Per-builder explicit `RECOMMENDATION_LINE: BUY|SELL|HOLD` field in upstream agent prompts (the (c) follow-up — biggest blast radius, right end-state).
- Cross-stage disagreement guard (e.g., flag when trader=BUY, risk=HOLD, final=HOLD).
- Cash-sweep constraint awareness (separate small plan).
- Phantom zero-share sells filter (separate small plan).

## 4. Architecture

Two-stage extractor with explicit failure semantics:

```
text ──► _extract_action_regex(text) ──► ExtractionResult(action, confidence="high", source="regex")
              │ no match
              ▼
        _extract_action_llm(text)  ──► ExtractionResult(action, confidence∈{high,med,low},
              │                                          source="llm", evidence_quote)
              │ confidence == "low" or LLM error
              ▼
        raise ActionExtractionError
```

`_infer_recommendation` becomes a thin back-compat wrapper that calls the new `extract_action(text)` and returns the action string. Builders that need richer info (the new failure path) call `extract_action` directly.

## 5. Components

### 5.1 `ExtractionResult` (new dataclass)

```python
@dataclass(frozen=True)
class ExtractionResult:
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: Literal["high", "med", "low"]
    source: Literal["regex", "llm"]
    evidence_quote: str | None  # populated by LLM path; None for regex
```

### 5.2 `ActionExtractionError` (new exception)

```python
class ActionExtractionError(Exception):
    def __init__(self, text_excerpt: str, last_attempt: ExtractionResult | None):
        ...
```

Carries diagnostic context: first 300 chars of input text and the last attempted extraction (for log readability).

### 5.3 `_extract_action_regex(text) -> ExtractionResult | None` (new)

Keeps the current six patterns (line, colon, single-line) **plus** new patterns for markdown-header formats:
- `**Rating**\n**Buy**`
- `**1. Rating**\n**Buy**` (numbered headers)
- `### Rating\nBuy` / `## Rating\nBuy` (atx headers)
- Leading-number variants (`1. Rating: Buy`, `1) Rating — Buy`)
- Tolerance for trailing whitespace, mixed bold/italic, hyphen/dash separators

Returns `None` on miss (no more `"HOLD"` default).

### 5.4 `_extract_action_llm(text) -> ExtractionResult` (new)

- **Model:** quick-thinking model from `default_config` (same tier as `rm_consistency_guard`)
- **Input:** full `text` (no truncation — rating may be restated)
- **Output schema:** strict JSON `{"action": "BUY"|"SELL"|"HOLD", "confidence": "high"|"med"|"low", "evidence_quote": "string ≤200 chars"}`
- **Timeout:** 15s (single attempt, no retry)
- **Error handling:** any failure (timeout, JSON parse, schema mismatch, network, action not in enum) returns a sentinel `ExtractionResult(action="HOLD", confidence="low", source="llm", evidence_quote=None)` so the caller's "low ⇒ fail" path triggers uniformly. **Does not raise** — caller decides via the confidence field.

Prompt sketch (final wording in implementation):

```
You extract the final trading action from a portfolio manager's report.
Return strict JSON: {"action": "BUY"|"SELL"|"HOLD", "confidence": "high"|"med"|"low",
"evidence_quote": "<≤200 chars verbatim from the text>"}.
If the text is ambiguous or the action is missing, set confidence to "low".
TEXT:
<<<{text}>>>
```

### 5.5 `extract_action(text) -> ExtractionResult` (new public function)

```python
def extract_action(text: str) -> ExtractionResult:
    regex_result = _extract_action_regex(text)
    if regex_result is not None:
        return regex_result
    llm_result = _extract_action_llm(text)
    if llm_result.confidence == "low":
        raise ActionExtractionError(text_excerpt=text[:300], last_attempt=llm_result)
    return llm_result
```

### 5.6 `_infer_recommendation(text) -> str` (back-compat shim)

```python
def _infer_recommendation(text: str) -> str:
    return extract_action(text).action  # raises ActionExtractionError on hard fail
```

The shim no longer silently returns `"HOLD"` on miss. The four other callers must handle `ActionExtractionError` (see §6).

## 6. Caller Updates

All five `build_*_structured` functions get a unified failure branch added to their existing `status` switch (`completed` | `empty` | `timeout_fallback`):

```python
try:
    result = extract_action(text)
    action = result.action
    status = "completed"
    abort_reason = ""
except ActionExtractionError as exc:
    action = None  # explicit, not "HOLD"
    status = "extraction_failed"
    abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
```

The structured field for `action` (or its alias: `recommendation`, `final_action`, `consensus_direction`) is set to `None` on extraction-failure to avoid lying with a default value.

## 7. Per-Ticker Failure Propagation & Portfolio Guard

### 7.1 Ticker-Level Exclusion

`_completed_scan_candidates` ([portfolio_setup.py:70](../../../tradingagents/graph/portfolio_setup.py#L70)) already filters on:

```python
status == "completed" and action == "BUY"
```

A ticker with `status == "extraction_failed"` is naturally excluded. The portfolio graph proceeds on the remaining successfully-extracted tickers, exactly as if the failed ticker had never been analyzed.

This is the Q3-(i) behavior the user selected: *continue without the failed ticker*.

### 7.2 Portfolio PM Assertion Guard — Intent (Economist Report §9.1)

The portfolio PM is a decision-effecting node. Per ADR 011 and `feedback_no_decision_fallback`, it must hard-fail rather than silently abstain on phantom inputs. The intent: when the scanner produced equity candidates but the candidate-handoff pipeline dropped all of them — whether because of extraction failure, an unexplained filter regression, or any future variant — the portfolio graph must abort with full diagnostic context, not proceed to a phantom-input PM decision (the failure mode that produced the 91% cash drift in the audited run).

The implementation lives in §7.4. It catches both *unaccountable drops* (the audit's original silent-pipe class) and *total extraction failure* (the new failure class introduced by §6's no-default-HOLD behavior), while preserving two legitimate empty-candidate paths: scanner produced no candidates at all, and every trading-graph PM legitimately decided HOLD/SELL.

### 7.3 Total Failure Framing

The Q3-(i) "continue without failed tickers" rule must **not** silently degrade to "continue with zero candidates". A run where the scanner emitted N>0 equity candidates and *all* of them dropped to `extraction_failed` is exactly the silent-broken-pipe failure mode that ADR 011 / `feedback_no_decision_fallback` exists to prevent — and is precisely the failure mode that bit us in the audited run (only the proximate cause was different).

The trading-graph→portfolio-graph boundary therefore needs an explicit guard. See §7.4 for the implementation.

### 7.4 Portfolio PM Entry Guard (new node)

A new guard runs at the entry of the portfolio PM decision node, *after* `prioritize_candidates_node` ([portfolio_setup.py:586](../../../tradingagents/graph/portfolio_setup.py#L586)) and *before* the PM is asked to decide. It compares the scanner's input against the filtered candidate list and hard-fails when there's an unaccountable drop.

**Inputs (already in `PortfolioManagerState`):**
- `scan_summary.equity_candidates` — what the scanner sent (length `N_in`)
- `ticker_analyses` — the per-ticker trading-graph results (each carries `analysis_status` and `final_trade_decision_structured.status`)
- `prioritized_candidates` — what the PM is about to consume (length `N_out`)

**Logic:**

```
N_in       = len(scan_summary.equity_candidates)
N_out      = len(prioritized_candidates)
N_extr_fail = count(t in ticker_analyses where structured.status == "extraction_failed")
N_other_fail = count(t in ticker_analyses where analysis_status == "failed"
                     and structured.status != "extraction_failed")
N_not_buy  = count(t in ticker_analyses where structured.status == "completed"
                   and structured.action in {"HOLD","SELL"})
N_no_deepdive = count(scan candidates with no ticker_analyses entry)

accounted_drop = N_extr_fail + N_other_fail + N_not_buy + N_no_deepdive

if N_in > 0 and N_in - N_out != accounted_drop:
    raise CandidateHandoffError(...)   # unexplained drop — silent break
if N_in > 0 and N_out == 0 and N_extr_fail > 0 and N_extr_fail == N_in:
    raise CandidateHandoffError("all_candidates_extraction_failed", ...)
```

**Two distinct hard-fail conditions:**

1. **Unaccountable drop** (`N_in - N_out != accounted_drop`): something dropped a candidate without recording a reason. This is the classic silent-pipe break. Hard-fail.
2. **Total extraction failure** (`N_in > 0`, `N_out == 0`, every candidate has `extraction_failed`): every trading-graph PM decision was unparseable. The system has *opinions* (the PM prose exists for each ticker) but cannot *use* them. Hard-fail rather than silently abstain to 100% cash.

**What "hard-fail" means here:**
- Raise `CandidateHandoffError` from the guard node.
- The portfolio graph terminates with `analysis_status: "failed"` and `abort_reason: "<condition>"`.
- `pm_decision`, `cash_sweep`, `execute_trades` do not run (no phantom abstain, no failed-SGOV-sweep noise).
- `run_log.jsonl` records `candidate_handoff_failed` with full diagnostic payload (`N_in`, `N_out`, per-ticker statuses, scanner candidate tickers).
- The portfolio's existing state (cash, holdings) is unchanged. The next run can resume.

**What total-failure does *not* trigger:**
- A scanner that legitimately produced zero candidates (`N_in == 0`) is allowed — the guard short-circuits on `N_in > 0`. The PM still runs and may decide to hold/sweep. This preserves the existing "no opportunities today" path.
- A scanner that produced candidates where every trading-graph PM legitimately said HOLD or SELL (`N_not_buy == N_in`) is allowed — the system *does* have decisions, they just aren't BUYs. PM still runs.

**New exception:**

```python
class CandidateHandoffError(Exception):
    def __init__(self, kind: Literal["unaccountable_drop", "all_extraction_failed"],
                 n_in: int, n_out: int, per_ticker_status: dict[str, str]): ...
```

**Telemetry:**

| Event | When | Payload |
|---|---|---|
| `candidate_handoff_ok` | Guard passes | `{n_in, n_out, n_extraction_failed, n_not_buy}` |
| `candidate_handoff_failed` | Guard raises | `{kind, n_in, n_out, per_ticker_status}` |

The `_ok` event is also valuable — it confirms the guard ran and the handoff is healthy, which is the signal you'd grep for after the fix lands.

### 7.5 Why the guard belongs in this spec (not deferred)

The Q3-(i) "continue without failed tickers" rule is incomplete without the total-failure case, and the guard catches both that and the original silent-pipe bug from the audit. Building only the extractor without the guard would re-create the failure-mode it's trying to fix: a *different* upstream change (e.g., a future regression in `_completed_scan_candidates`'s filter) could once again drop all candidates without explanation, and the system would once again silently abstain to 91% cash.

The guard is small, mechanical, and depends only on state that already exists. Including it now closes the loop that the audit opened.

## 8. Telemetry

Two new event types written to the existing `run_log.jsonl` (via the existing logger):

| Event | When | Payload |
|---|---|---|
| `action_extraction_llm_fallback` | Regex misses, LLM rescues (any confidence ≥ med) | `{ticker, builder, llm_action, llm_confidence, evidence_quote}` |
| `action_extraction_failed` | Both regex and LLM fail | `{ticker, builder, text_excerpt}` |

The `_llm_fallback` event is the **prompt-drift sensor**: if it starts firing on every run, the upstream PM/trader/RM/risk prompt has drifted and the regex needs an update (or the (c) follow-up should be promoted).

## 9. Testing

Four new test files (three for the extractor, one for the PM entry guard):

### 9.1 `test_action_extraction_regex.py`
Table-driven, ~15–20 cases:
- Existing six patterns (`FINAL TRANSACTION PROPOSAL: BUY`, etc.) — preserve coverage
- New markdown-header variants (`**Rating**\n**Buy**`, `**1. Rating**\n**Buy**`, `### Rating\nBuy`)
- Edge cases: trailing whitespace, mixed bold/italic, hyphen vs em-dash, leading numbers
- Negative cases: ambiguous prose that must miss (regex returns `None`)

### 9.2 `test_action_extraction_llm.py`
Mocks the LLM client. Verifies:
- High/med/low confidence routing
- JSON parse failure → low
- Timeout → low
- Schema mismatch (e.g. `action: "MAYBE"`) → low
- Evidence quote propagation

### 9.3 `test_action_extraction_integration.py`
Real artifacts from the audit run plus synthetic cases:
- OWL `complete_report.md` §IV → must extract BUY (LLM path)
- TEAM `complete_report.md` §IV → must extract BUY (LLM path)
- 2–3 well-formed PM samples → must extract via regex (no LLM call)
- Deliberately mangled prose → must raise `ActionExtractionError`

### 9.4 `tests/portfolio/test_candidate_handoff_guard.py`
Covers the §7.3 PM entry guard:
- `N_in == 0` → guard short-circuits, PM proceeds (no opportunities today)
- `N_in == 2`, both extracted, both BUY, `N_out == 2` → pass
- `N_in == 2`, both extracted, both HOLD, `N_out == 0` → pass (`N_not_buy == N_in`)
- `N_in == 2`, one extracted-BUY, one extraction-failed, `N_out == 1` → pass with `_ok` telemetry recording the partial failure
- `N_in == 2`, both extraction-failed, `N_out == 0` → raise `CandidateHandoffError(kind="all_extraction_failed")`
- `N_in == 2`, deliberate state corruption (drop one candidate without reason), `N_out == 0` → raise `CandidateHandoffError(kind="unaccountable_drop")`
- Verify `pm_decision`, `cash_sweep`, `execute_trades` do *not* execute when guard raises
- Verify portfolio cash/holdings unchanged after a guard-raise

### 9.5 Existing tests
Grep all callers of `_infer_recommendation` and update assertions:
- Tests that previously asserted `"HOLD"` on a malformed input must flip to `pytest.raises(ActionExtractionError)`.
- The other four `build_*_structured` tests need new cases for the `status == "extraction_failed"` branch.

Existing portfolio-graph tests (`tests/graph/test_portfolio_decision_snapshot.py`, `tests/portfolio/test_portfolio_setup.py`) need a check that the new guard node is wired into the graph and that the existing happy-path snapshots still pass.

Per `feedback_env_isolation_tests` and `feedback_vendor_methods_mocking`: mock the LLM client at the module attribute level, not via env vars; never `importlib.reload` with real `.env` loaded.

## 10. Migration & Rollout

1. Land helper + caller updates + new PM entry guard + all tests in a single change — they are interdependent (the guard only makes sense once builders stop defaulting to HOLD; conversely, the new builder failure path only routes correctly when the guard is in place).
2. Re-run the audited 2026-05-01 portfolio job (it is idempotent) and verify three things:
   - `prioritized_candidates` now contains OWL and TEAM (regex extends would have caught it; if LLM fallback is used, telemetry will say so).
   - `candidate_handoff_ok` event is logged with `n_in == 2, n_out == 2`.
   - The portfolio decision actually deploys capital instead of abstaining.
3. Negative-path verification: synthetically corrupt the OWL trading-graph output to force `extraction_failed`, re-run, and verify (a) TEAM still flows through, (b) telemetry records the OWL failure, (c) the guard does not raise (partial failure is allowed).
4. Watch `action_extraction_llm_fallback` telemetry on the next 1–2 production runs. If it fires regularly, escalate to the (c) follow-up (require explicit `RECOMMENDATION_LINE` in upstream prompts).
5. Watch `candidate_handoff_failed` telemetry. Any occurrence is a signal the upstream pipeline has a bug — investigate immediately, don't tune the guard.

## 11. Open Questions / Risks

- **LLM cost on production runs:** the fallback should be cold most of the time once the regex covers known formats. If we underestimated and it fires on every run, costs increase by one quick-thinking-model call per builder per ticker. Mitigation: telemetry will surface this immediately and the (c) follow-up retires the LLM path entirely.
- **Determinism on parse-miss path:** when LLM fallback fires, the same input could in principle yield a different action across runs. Acceptable because (a) it only fires when regex misses, (b) `confidence == low` hard-fails so the only non-deterministic outputs are high/med-confidence ones, and (c) those will be visible in telemetry for review.
- **Existing tests:** several may be silently relying on the HOLD default. The grep + flip in §9.4 has to be exhaustive — if any caller currently expects HOLD on a parse-miss, we want that to flip to a raise, not be papered over.

## 12. Out of Scope (re-stated)

- (c) follow-up: explicit `RECOMMENDATION_LINE` in upstream prompts.
- Cross-stage disagreement guard.
- Cash-sweep constraint awareness — separate small plan.
- Phantom zero-share sells — separate small plan.
