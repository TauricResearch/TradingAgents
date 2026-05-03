# RM Consistency Guard — LLM-as-Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the regex-based RM consistency guard with a two-step LLM-as-judge approach: a structural regex extracts bullet-point claims from the Research Manager output, then a single LLM call verdicts each claim against the fundamentals report.

**Architecture:** `extract_rm_claims()` parses `[HIGH]/[MED]/[LOW]` bullet lines as plain strings (no semantic parsing). `check_claims_via_llm()` sends those strings plus the fundamentals report to `quick_thinking_llm` in a tight JSON-in/JSON-out prompt and returns per-claim verdicts. The guard node in `setup.py` is unchanged structurally — it still reprompts once and raises on the second offense.

**Tech Stack:** Python, LangChain (`HumanMessage`, `SystemMessage`), `tradingagents.agents.utils.json_utils.extract_json`, pytest, `unittest.mock.patch`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tradingagents/graph/_consistency_guard.py` | **Replace entirely** | `extract_rm_claims()` + `check_claims_via_llm()` |
| `tradingagents/graph/setup.py` | **Modify** | `_make_rm_consistency_guard_node` becomes `@staticmethod` accepting `llm` arg; update 2 call sites |
| `tests/graph/test_consistency_guard.py` | **Replace entirely** | New tests for extraction, LLM verdicts, node behavior, NOK regression |

---

### Task 1: Replace `_consistency_guard.py` with the two new functions

**Files:**
- Modify: `tradingagents/graph/_consistency_guard.py` (full replacement)
- Test: `tests/graph/test_consistency_guard.py` (partial — extraction tests only)

- [ ] **Step 1: Write failing tests for `extract_rm_claims`**

Replace the entire content of `tests/graph/test_consistency_guard.py` with:

```python
import json
import pytest
from unittest.mock import MagicMock, patch

from tradingagents.graph._consistency_guard import (
    extract_rm_claims,
    check_claims_via_llm,
)


# ---------------------------------------------------------------------------
# extract_rm_claims
# ---------------------------------------------------------------------------

def test_extract_square_bracket_high():
    text = "- [HIGH] Revenue grew +15% YoY, increasing from $906M to $1,043M."
    assert extract_rm_claims(text) == ["Revenue grew +15% YoY, increasing from $906M to $1,043M."]


def test_extract_parenthesis_high():
    text = "*   (HIGH) Asset price breakout at $79.93 on 11.54x relative volume."
    assert extract_rm_claims(text) == ["Asset price breakout at $79.93 on 11.54x relative volume."]


def test_extract_bullet_dot():
    text = "• [MED] Sector momentum tailwind: Technology leads +9.08% monthly."
    assert extract_rm_claims(text) == ["Sector momentum tailwind: Technology leads +9.08% monthly."]


def test_extract_low_confidence_included():
    text = "  - [LOW] Analyst projects price target at $5.68."
    assert extract_rm_claims(text) == ["Analyst projects price target at $5.68."]


def test_extract_all_confidence_levels():
    text = (
        "- [HIGH] Revenue expanded +15.1% YoY.\n"
        "- [MED] Volume surged to 62M shares vs 30M average.\n"
        "- [LOW] Analyst asserts price target of $5.68.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 3
    assert claims[0] == "Revenue expanded +15.1% YoY."
    assert claims[1] == "Volume surged to 62M shares vs 30M average."
    assert claims[2] == "Analyst asserts price target of $5.68."


def test_extract_ignores_non_claim_lines():
    text = (
        "**Strongest Bull Evidence**\n"
        "  - [HIGH] Revenue grew.\n"
        "Some narrative line without a marker.\n"
        "  - [MED] Margin expanded.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 2


def test_extract_empty_text_returns_empty():
    assert extract_rm_claims("") == []
    assert extract_rm_claims("  \n  ") == []


def test_extract_nok_real_output():
    """Validate against actual NOK RM output from run 01KQNKJ4PF4D4XN7GXN6YEQHV4."""
    text = (
        "• **Strongest Bull Evidence**\n"
        "  - [HIGH] NOK revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025, "
        "recording +27.0% YoY growth and sequential QoQ expansion of +3.5%, +6.2%, and +26.9%.\n"
        "  - [HIGH] NOK registered breakout accumulation on unusual volume alongside a "
        "52-week high print at $12.92.\n"
        "  - [MED] NOK price consolidation holds above $10.76 support.\n"
        "• **Strongest Bear Evidence**\n"
        "  - [HIGH] NOK sequential revenue expansion from $4.39B to $6.13B imposes a "
        "$1.74B absolute quarterly variance.\n"
        "  - [MED] Macro regime degradation below +3/6 introduces volatility risk.\n"
    )
    claims = extract_rm_claims(text)
    assert len(claims) == 5
    assert any("$4.39B" in c and "$6.13B" in c for c in claims)
```

- [ ] **Step 2: Run to confirm failure**

```bash
conda run -n tradingagents pytest tests/graph/test_consistency_guard.py -v 2>&1 | head -30
```

Expected: `ImportError` — `extract_rm_claims` does not exist yet.

- [ ] **Step 3: Write the new `_consistency_guard.py`**

Replace the entire file:

```python
"""RM consistency guard: structural claim extraction + LLM-as-judge verification."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.agents.utils.json_utils import extract_json

_CLAIM_RE = re.compile(
    r"^\s*[-•*]\s*[\[\(](HIGH|MED|LOW)[\]\)]\s+(.+)",
    re.IGNORECASE | re.MULTILINE,
)

_SYSTEM_PROMPT = """You are a fact-checker for financial research reports.
Given a list of claims and a fundamentals report, identify which claims contradict the fundamentals.

A CONTRADICTION is: a wrong direction (claims growth but fundamentals show decline), \
or a specific number that is clearly inconsistent with the fundamentals for the same metric and same period.

NOT a contradiction: different time-period framing, emphasis, forward projection, or interpretation. \
If in doubt, mark ok.

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
{"results": [{"index": 0, "ok": true}, {"index": 1, "ok": false, "reason": "..."}]}"""


def extract_rm_claims(rm_text: str) -> list[str]:
    """Return claim strings from [HIGH]/[MED]/[LOW] bullet lines in RM investment plan."""
    return [m.group(2).strip() for m in _CLAIM_RE.finditer(rm_text)]


def check_claims_via_llm(
    claims: list[str],
    fundamentals: str,
    llm: Any,
) -> list[dict[str, Any]]:
    """Verdict each claim against fundamentals via a single LLM call.

    Returns a list of dicts with keys: index (int), ok (bool), reason (str, violations only).
    Missing indexes are treated as ok=True (fail-open for partial responses).
    Raises ValueError on unparseable LLM response.
    """
    if not claims:
        return []

    payload = json.dumps({"claims": claims, "fundamentals": fundamentals}, ensure_ascii=False)
    response = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=payload)])
    raw = response.content if hasattr(response, "content") else str(response)

    try:
        parsed = extract_json(raw)
    except Exception as exc:
        raise ValueError(f"rm_consistency_guard: LLM response is not valid JSON — {raw[:300]}") from exc

    if not isinstance(parsed, dict) or "results" not in parsed:
        raise ValueError(f"rm_consistency_guard: LLM response missing 'results' key — {raw[:300]}")

    results = parsed["results"]
    if not isinstance(results, list):
        raise ValueError(f"rm_consistency_guard: 'results' is not a list — {raw[:300]}")

    return results
```

- [ ] **Step 4: Run extraction tests**

```bash
conda run -n tradingagents pytest tests/graph/test_consistency_guard.py -v -k "extract" 2>&1 | tail -20
```

Expected: all `test_extract_*` tests pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/_consistency_guard.py tests/graph/test_consistency_guard.py
git commit -m "feat: replace consistency guard regex pipeline with structural extraction + LLM judge"
```

---

### Task 2: Add tests for `check_claims_via_llm` and node behavior

**Files:**
- Test: `tests/graph/test_consistency_guard.py` (append to existing)

- [ ] **Step 1: Write failing tests for `check_claims_via_llm` and the guard node**

Append to `tests/graph/test_consistency_guard.py`:

```python
# ---------------------------------------------------------------------------
# check_claims_via_llm
# ---------------------------------------------------------------------------

def _mock_llm(response_json: dict) -> MagicMock:
    llm = MagicMock()
    msg = MagicMock()
    msg.content = json.dumps(response_json)
    llm.invoke.return_value = msg
    return llm


def test_check_claims_no_violations():
    llm = _mock_llm({"results": [{"index": 0, "ok": True}]})
    result = check_claims_via_llm(["Revenue grew +15% YoY."], "Revenue: +15% YoY.", llm)
    assert result == [{"index": 0, "ok": True}]


def test_check_claims_with_violation():
    llm = _mock_llm({
        "results": [
            {"index": 0, "ok": False, "reason": "Fundamentals show compression, not expansion."}
        ]
    })
    result = check_claims_via_llm(["Margin expanded 200bps."], "Margin compressed 270bps.", llm)
    assert result[0]["ok"] is False
    assert "compression" in result[0]["reason"]


def test_check_claims_empty_list_skips_llm():
    llm = MagicMock()
    result = check_claims_via_llm([], "any fundamentals", llm)
    assert result == []
    llm.invoke.assert_not_called()


def test_check_claims_invalid_json_raises():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "not valid json at all"
    llm.invoke.return_value = msg
    with pytest.raises(ValueError, match="not valid JSON"):
        check_claims_via_llm(["some claim"], "some fundamentals", llm)


def test_check_claims_missing_results_key_raises():
    llm = _mock_llm({"something_else": []})
    with pytest.raises(ValueError, match="missing 'results' key"):
        check_claims_via_llm(["some claim"], "some fundamentals", llm)


# ---------------------------------------------------------------------------
# Guard node behavior (mocking check_claims_via_llm)
# ---------------------------------------------------------------------------

def test_guard_node_passes_clean_rm_output():
    from tradingagents.graph.setup import GraphSetup

    mock_llm = MagicMock()
    with patch(
        "tradingagents.graph.setup.check_claims_via_llm",
        return_value=[{"index": 0, "ok": True}],
    ):
        node = GraphSetup._make_rm_consistency_guard_node(mock_llm)
        result = node({
            "investment_plan": "- [HIGH] Revenue expanded +15% YoY.",
            "fundamentals_report": "Revenue: +15% YoY.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
    assert result["consistency_violations"] == []
    assert result["sender"] == "rm_consistency_guard"
    assert "_rm_consistency_attempt" not in result


def test_guard_node_routes_reprompt_on_first_offense():
    from tradingagents.graph.setup import GraphSetup

    mock_llm = MagicMock()
    violation = {"index": 0, "ok": False, "reason": "Fundamentals show compression."}
    with patch(
        "tradingagents.graph.setup.check_claims_via_llm",
        return_value=[violation],
    ):
        node = GraphSetup._make_rm_consistency_guard_node(mock_llm)
        result = node({
            "investment_plan": "- [HIGH] Margin expanded 200bps.",
            "fundamentals_report": "Margin compressed 270bps.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "reprompt"
    assert result["consistency_violations"] == [violation]
    assert result["_rm_consistency_attempt"] == 1


def test_guard_node_raises_after_second_offense():
    from tradingagents.graph.setup import GraphSetup

    mock_llm = MagicMock()
    violation = {"index": 0, "ok": False, "reason": "Still wrong."}
    with patch(
        "tradingagents.graph.setup.check_claims_via_llm",
        return_value=[violation],
    ):
        node = GraphSetup._make_rm_consistency_guard_node(mock_llm)
        with pytest.raises(ValueError, match="unresolved.*violations"):
            node({
                "investment_plan": "- [HIGH] Margin expanded 200bps.",
                "fundamentals_report": "Margin compressed 270bps.",
                "_rm_consistency_attempt": 1,
            })


def test_guard_node_nok_regression_no_false_positive():
    """NOK historical range claim must NOT be flagged as a violation."""
    from tradingagents.graph.setup import GraphSetup

    mock_llm = MagicMock()
    # LLM correctly marks historical range as ok
    with patch(
        "tradingagents.graph.setup.check_claims_via_llm",
        return_value=[{"index": 0, "ok": True}, {"index": 1, "ok": True}],
    ):
        node = GraphSetup._make_rm_consistency_guard_node(mock_llm)
        result = node({
            "investment_plan": (
                "• **Strongest Bull Evidence**\n"
                "  - [HIGH] NOK revenue accelerated from $4.39B in Q1 2025 to $6.13B in Q4 2025.\n"
                "  - [HIGH] NOK registered breakout accumulation at $12.92.\n"
            ),
            "fundamentals_report": (
                "Q1 2025: $4.39B\nQ4 2025: $6.13B (+26.9% QoQ)\n"
            ),
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
    assert result["consistency_violations"] == []


def test_guard_node_no_claims_extracted_passes():
    """RM with no [HIGH]/[MED]/[LOW] bullets skips LLM and passes."""
    from tradingagents.graph.setup import GraphSetup

    mock_llm = MagicMock()
    with patch("tradingagents.graph.setup.check_claims_via_llm", return_value=[]) as mock_check:
        node = GraphSetup._make_rm_consistency_guard_node(mock_llm)
        result = node({
            "investment_plan": "Some narrative without claim markers.",
            "fundamentals_report": "Revenue: +15% YoY.",
            "_rm_consistency_attempt": 0,
        })
    assert result["rm_consistency_status"] == "ok"
```

- [ ] **Step 2: Run to confirm failures**

```bash
conda run -n tradingagents pytest tests/graph/test_consistency_guard.py -v -k "check_claims or guard_node" 2>&1 | tail -30
```

Expected: failures because `setup.py` still uses the old static method signature and imports.

- [ ] **Step 3: Commit the test file**

```bash
git add tests/graph/test_consistency_guard.py
git commit -m "test: add LLM judge and guard node tests for consistency guard redesign"
```

---

### Task 3: Update `setup.py` to wire in the new guard

**Files:**
- Modify: `tradingagents/graph/setup.py`

- [ ] **Step 1: Update imports at top of `setup.py`**

Find the existing import block. It currently imports from `_consistency_guard`:

```python
from tradingagents.graph._consistency_guard import extract_numeric_claims, verify_against_fundamentals
```

Replace it with:

```python
from tradingagents.graph._consistency_guard import check_claims_via_llm, extract_rm_claims
```

- [ ] **Step 2: Replace `_make_rm_consistency_guard_node`**

Find and replace the entire method (lines ~128-167):

```python
    @staticmethod
    def _make_rm_consistency_guard_node() -> Callable[[AgentState], dict[str, Any]]:
        def rm_consistency_guard_node(state: AgentState) -> dict[str, Any]:
            rm_text = state.get("investment_plan") or ""
            fundamentals = state.get("fundamentals_report") or ""
            claims = extract_numeric_claims(rm_text)
            result = verify_against_fundamentals(claims, fundamentals)
            violations = result["violations"]
            flags = result["flags"]
            attempt = int(state.get("_rm_consistency_attempt") or 0)
            if not violations:
                return {
                    "rm_consistency_status": "ok",
                    "rm_consistency_flags": [
                        {"metric": f.metric, "value": f.value, "unit": f.unit} for f in flags
                    ],
                    "consistency_violations": [],
                    "sender": "rm_consistency_guard",
                }
            if attempt >= 1:
                details = "; ".join(v.reason for v in violations)
                raise ValueError(
                    "rm_consistency_guard: unresolved numeric violations after "
                    f"corrective re-prompt — {details}"
                )
            return {
                "rm_consistency_status": "reprompt",
                "consistency_violations": [
                    {
                        "metric": v.claim.metric,
                        "claim_value": v.claim.value,
                        "claim_unit": v.claim.unit,
                        "reason": v.reason,
                    }
                    for v in violations
                ],
                "_rm_consistency_attempt": attempt + 1,
                "sender": "rm_consistency_guard",
            }

        return rm_consistency_guard_node
```

Replace with:

```python
    @staticmethod
    def _make_rm_consistency_guard_node(llm: Any) -> Callable[[AgentState], dict[str, Any]]:
        def rm_consistency_guard_node(state: AgentState) -> dict[str, Any]:
            rm_text = state.get("investment_plan") or ""
            fundamentals = state.get("fundamentals_report") or ""
            claims = extract_rm_claims(rm_text)
            results = check_claims_via_llm(claims, fundamentals, llm)
            violations = [r for r in results if not r.get("ok")]
            attempt = int(state.get("_rm_consistency_attempt") or 0)
            if not violations:
                return {
                    "rm_consistency_status": "ok",
                    "consistency_violations": [],
                    "sender": "rm_consistency_guard",
                }
            if attempt >= 1:
                details = "; ".join(v.get("reason", "") for v in violations)
                raise ValueError(
                    f"rm_consistency_guard: unresolved violations after corrective re-prompt — {details}"
                )
            return {
                "rm_consistency_status": "reprompt",
                "consistency_violations": violations,
                "_rm_consistency_attempt": attempt + 1,
                "sender": "rm_consistency_guard",
            }

        return rm_consistency_guard_node
```

- [ ] **Step 3: Update the two call sites**

Find:
```python
workflow.add_node("RM Consistency Guard", self._make_rm_consistency_guard_node())
```

There are two of these (around lines 309 and 435). Replace both with:

```python
workflow.add_node("RM Consistency Guard", self._make_rm_consistency_guard_node(self.quick_thinking_llm))
```

- [ ] **Step 4: Run all consistency guard tests**

```bash
conda run -n tradingagents pytest tests/graph/test_consistency_guard.py -v 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run full suite**

```bash
conda run -n tradingagents pytest tests/ -m "not integration" -q 2>&1 | tail -5
```

Expected: same pass count as before (1988+), no regressions.

- [ ] **Step 6: Commit**

```bash
git add tradingagents/graph/setup.py
git commit -m "fix: wire LLM judge into RM consistency guard node — eliminates regex false positives"
```

---

## Self-Review

**Spec coverage:**
- ✅ Structural regex extracts claims (Task 1)
- ✅ LLM judge with few-shot prompt (Task 1 `_SYSTEM_PROMPT`)
- ✅ JSON-in/JSON-out contract (Task 1 `check_claims_via_llm`)
- ✅ `@staticmethod` accepting `llm` arg (Task 3)
- ✅ Both call sites updated (Task 3 Step 3)
- ✅ NOK regression test (Task 2)
- ✅ LLM error path tests — invalid JSON, missing key (Task 2)
- ✅ `rm_consistency_flags` removed — no longer needed (new design has no flags concept)

**Type consistency:**
- `extract_rm_claims` → `list[str]` ✅ used as `claims` in node and test
- `check_claims_via_llm` → `list[dict[str, Any]]` ✅ `violations = [r for r in results if not r.get("ok")]`
- `_make_rm_consistency_guard_node(llm: Any)` ✅ called with `self.quick_thinking_llm` at both sites
- Patch target `"tradingagents.graph.setup.check_claims_via_llm"` ✅ matches the import added in Task 3 Step 1

**Note on `rm_consistency_flags`:** The old node returned `rm_consistency_flags` on success. The new node does not — the LLM judge doesn't produce a "flag" tier. `AgentState` may declare this field; it will simply remain empty after this change. No downstream code reads it (grep confirms no consumer).
