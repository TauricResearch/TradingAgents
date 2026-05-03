# RM Consistency Guard — LLM-as-Judge Design

**Date:** 2026-05-03
**Status:** Approved for implementation

## Problem

The current `_consistency_guard.py` uses regex to extract numeric claims from the Research Manager's `investment_plan` and compare them against the `fundamentals_report`. This produces false positives because:

1. `[HIGH]/[MED]/[LOW]` confidence markers leak into extracted metric names
2. "from $X to $Y" range sentences emit only the starting value as a claim
3. Annual figures compared against quarterly fundamentals (different time granularities)

Result: legitimate runs fail with `rm_consistency_guard: unresolved numeric violations` even when the RM output is factually correct.

## Approach

Replace the regex semantic pipeline with two components:

1. **Structural regex** — extracts claim lines from the RM text (format-only, no semantic parsing)
2. **LLM judge** — receives the pre-extracted claims as JSON and verdicts each one against the fundamentals

The LLM has exactly one job: `true`/`false` per claim. It does not extract claims, summarize text, or infer facts.

## Claim Extraction

```python
CLAIM_RE = re.compile(
    r'^\s*[-•*]\s*[\[\(](HIGH|MED|LOW)[\]\)]\s+(.+)',
    re.IGNORECASE | re.MULTILINE,
)
```

Validated against 4 real RM outputs across different models and runs. Handles:
- Both `[HIGH]` (square bracket) and `(HIGH)` (parenthesis) formats
- Bullet styles: `-`, `*`, `•`
- All three confidence levels — none pre-filtered (LOW claims may still be factual)

Returns a list of claim text strings. Confidence level (`HIGH`/`MED`/`LOW`) is not forwarded — the LLM receives only the claim sentence.

## LLM Judge

### Model
`quick_thinking_llm` — already available in `GraphSetup`. Same tier as news analyst. No new infrastructure needed.

### Prompt

**System:**
```
You are a fact-checker for financial research reports.
Given a list of claims and a fundamentals report, identify which claims
contradict the fundamentals.

A CONTRADICTION is: a wrong direction (claims growth but fundamentals show
decline), or a specific number that is clearly inconsistent with the
fundamentals for the same metric and same period.

NOT a contradiction: different time-period framing, emphasis, forward
projection, or interpretation. If in doubt, mark ok.

Examples:

FUNDAMENTALS: "Q1 2025: $4.39B, Q4 2025: $6.13B (+26.9% QoQ)"
CLAIM: "Revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025"
→ {"ok": true}  ← historical range, both numbers match

FUNDAMENTALS: "Q1 2025: $4.39B, Q4 2025: $6.13B (+26.9% QoQ)"
CLAIM: "Revenue declined from $6.13B in Q4 2025 to $4.39B in Q1 2026"
→ {"ok": false, "reason": "Q1 2026 figure not in fundamentals; direction framed as decline but this period is not reported"}

FUNDAMENTALS: "Gross margin Q4 2025: 44.9% (+120bps QoQ)"
CLAIM: "Gross margin expanded +120bps QoQ in Q4 2025"
→ {"ok": true}  ← exact match

FUNDAMENTALS: "Gross margin Q4 2025: 44.9% (+120bps QoQ)"
CLAIM: "Gross margin compressed 200bps in Q4 2025"
→ {"ok": false, "reason": "Fundamentals show +120bps expansion, not compression"}

FUNDAMENTALS: "Q1 2026: $4.50B (-26.6% QoQ)"
CLAIM: "Revenue is on a strong multi-quarter acceleration trend"
→ {"ok": true}  ← interpretation/emphasis, not a factual claim

FUNDAMENTALS: "Net leverage 3.8x, down 320bps YoY"
CLAIM: "Leverage expanded significantly this year"
→ {"ok": false, "reason": "Fundamentals show leverage declined 320bps, not expanded"}

FUNDAMENTALS: "EPS: $0.08 in Q4 2025"
CLAIM: "EPS of $0.08 supports continued investment"
→ {"ok": true}  ← number matches, rest is interpretation

Respond with ONLY valid JSON, no prose:
{"results": [{"index": 0, "ok": true}, {"index": 1, "ok": false, "reason": "..."}]}
```

**User message:**
```json
{
  "claims": ["claim text 0", "claim text 1", "..."],
  "fundamentals": "<full fundamentals_report text>"
}
```

**Expected response:**
```json
{
  "results": [
    {"index": 0, "ok": true},
    {"index": 1, "ok": false, "reason": "Fundamentals show X, claim states Y"}
  ]
}
```

## Node Changes

### `_consistency_guard.py`

Replace entirely with two functions:

```python
def extract_rm_claims(rm_text: str) -> list[str]
    """Return claim strings extracted from [HIGH]/[MED]/[LOW] bullet lines."""

def check_claims_via_llm(
    claims: list[str],
    fundamentals: str,
    llm: Any,
) -> list[dict]:
    """Call LLM judge. Returns list of {index, ok, reason?} dicts."""
```

All dataclasses (`NumericClaim`, `Violation`), regexes, and helper functions are removed.

### `setup.py`

`_make_rm_consistency_guard_node` changes from `@staticmethod` to an instance method to access `self.quick_thinking_llm`:

```python
def _make_rm_consistency_guard_node(self) -> Callable[[AgentState], dict]:
    def rm_consistency_guard_node(state):
        claims = extract_rm_claims(state.get("investment_plan") or "")
        fundamentals = state.get("fundamentals_report") or ""
        results = check_claims_via_llm(claims, fundamentals, self.quick_thinking_llm)
        violations = [r for r in results if not r.get("ok")]
        attempt = int(state.get("_rm_consistency_attempt") or 0)
        if not violations:
            return {"rm_consistency_status": "ok", "consistency_violations": [], "sender": "rm_consistency_guard"}
        if attempt >= 1:
            details = "; ".join(v.get("reason", "") for v in violations)
            raise ValueError(f"rm_consistency_guard: unresolved violations — {details}")
        return {
            "rm_consistency_status": "reprompt",
            "consistency_violations": violations,
            "_rm_consistency_attempt": attempt + 1,
            "sender": "rm_consistency_guard",
        }
    return rm_consistency_guard_node
```

Both call sites at lines 309 and 435 change from `self._make_rm_consistency_guard_node()` (static) to the same — no call-site change needed since `self` is implicit.

## Error Handling

The `check_claims_via_llm` function must handle:
- `json.JSONDecodeError` on LLM response → raise `ValueError` with raw response for debugging
- Missing `results` key → raise `ValueError`
- Partial results (fewer items than claims) → treat missing indexes as `ok: true` (fail-open)

## Testing

Existing node behaviour tests (`test_consistency_guard.py`) are updated:
- Mock `check_claims_via_llm` instead of mocking `extract_numeric_claims` + `verify_against_fundamentals`
- Add one test per LLM error path (JSON decode failure, missing key)
- Add `test_extract_rm_claims` covering both bracket styles and all bullet formats

The NOK false-positive case becomes a regression test: the historical range claim should produce zero violations.

## Files Changed

| File | Change |
|------|--------|
| `tradingagents/graph/_consistency_guard.py` | Replace entirely |
| `tradingagents/graph/setup.py` | `@staticmethod` → instance method |
| `tests/graph/test_consistency_guard.py` | Update mocks, add regression test |
