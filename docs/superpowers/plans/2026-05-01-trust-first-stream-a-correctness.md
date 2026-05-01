# Trust-First Stream A — Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate two silent correctness bugs in the trading graph: macro regime drift between Market Analyst and the canonical macro brief, and Research Manager numeric claims that contradict the fundamentals report.

**Architecture:** Three sequential PRs against the trading graph. PR-A1 adds a fail-loud assertion after the Market Analyst. PR-A2 adds a numeric-consistency guard between Research Manager and Trader, with one corrective re-prompt and a flag-only fallback for low-confidence claims. PR-A3 routes the canonical macro brief into the trading graph state so Market Analyst reads it instead of inferring; this turns PR-A1's assertion into a regression guard.

**Tech Stack:** Python 3.11+, LangGraph StateGraph, pytest. Existing code in `tradingagents/graph/setup.py` and `tradingagents/graph/_graph_utils.py`. New helpers in `tradingagents/graph/_consistency_guard.py`.

**Spec:** `docs/superpowers/specs/2026-05-01-trading-agents-trust-first-fixes-design.md`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `tradingagents/graph/_graph_utils.py` | Modify | Add `assert_regime_consistent()` |
| `tradingagents/graph/_consistency_guard.py` | Create | Pure functions: `extract_numeric_claims`, `verify_against_fundamentals` |
| `tradingagents/graph/setup.py` | Modify | Wire post-Market-Analyst assertion (A1), post-RM guard (A2), canonical regime input (A3) |
| `tradingagents/agents/utils/agent_states.py` | Modify | Add `canonical_regime` field to `AgentState` (A3) |
| `tradingagents/agents/analysts/market_analyst.py` | Modify | Read `canonical_regime` and inject into prompt (A3) |
| `agent_os/backend/services/langgraph_engine.py` | Modify | Populate `canonical_regime` when invoking trading graph (A3) |
| `tests/graph/test_regime_assertion.py` | Create | Unit tests for A1 |
| `tests/graph/test_consistency_guard.py` | Create | Unit tests for A2 |
| `tests/graph/test_regime_routing.py` | Create | Integration test for A3 |

---

## Phase A1: Regime drift assertion

### Task A1.1: Helper `assert_regime_consistent`

**Files:**
- Modify: `tradingagents/graph/_graph_utils.py`
- Create: `tests/graph/test_regime_assertion.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph/test_regime_assertion.py
import pytest
from tradingagents.graph._graph_utils import assert_regime_consistent


def test_consistent_regime_passes_silently():
    analyst = "Macro Regime: RISK-ON (+5/6) suppressed VIX..."
    canonical = {"label": "RISK-ON", "score": 5}
    assert assert_regime_consistent(analyst, canonical) is None


def test_label_mismatch_raises():
    analyst = "Macro Regime: TRANSITION (+2/6) mixed signals..."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*label"):
        assert_regime_consistent(analyst, canonical)


def test_score_mismatch_raises():
    analyst = "Macro Regime: RISK-ON (+3/6) ..."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*score"):
        assert_regime_consistent(analyst, canonical)


def test_missing_regime_in_analyst_raises():
    analyst = "Some analysis without a regime line."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"could not parse regime"):
        assert_regime_consistent(analyst, canonical)


def test_replay_qcom_failed_run_drift():
    """Reproduce the QCOM Market Analyst output from run 01KQHDVJB2R19S4D7Z7Z6DP9F7."""
    drifted = (
        "FINAL TRANSACTION PROPOSAL: HOLD\n"
        "* Macro Regime: The environment is classified as TRANSITION with a score of +2/6"
    )
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError):
        assert_regime_consistent(drifted, canonical)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/graph/test_regime_assertion.py -v
```
Expected: ImportError or AttributeError on `assert_regime_consistent`.

- [ ] **Step 3: Implement helper**

Append to `tradingagents/graph/_graph_utils.py`:

```python
import re

_REGIME_LABEL_RE = re.compile(r"\b(RISK-ON|RISK-OFF|TRANSITION)\b", re.IGNORECASE)
_REGIME_SCORE_RE = re.compile(r"\(\s*([+-]?\d+)\s*/\s*6\s*\)")


def assert_regime_consistent(analyst_output: str, canonical: dict) -> None:
    """Compare regime label/score in analyst output against the canonical brief.

    Raises ValueError if the analyst output disagrees with the canonical regime.
    Returns None on match.
    """
    text = analyst_output or ""
    label_match = _REGIME_LABEL_RE.search(text)
    score_match = _REGIME_SCORE_RE.search(text)
    if not label_match or not score_match:
        raise ValueError(
            f"could not parse regime from analyst output (first 200 chars): "
            f"{text[:200]!r}"
        )
    analyst_label = label_match.group(1).upper()
    analyst_score = int(score_match.group(1))
    canonical_label = str(canonical.get("label", "")).upper()
    canonical_score = int(canonical.get("score", 0))
    if analyst_label != canonical_label:
        raise ValueError(
            f"regime drift: canonical label {canonical_label!r} != "
            f"analyst label {analyst_label!r}"
        )
    if analyst_score != canonical_score:
        raise ValueError(
            f"regime drift: score canonical={canonical_score} != analyst={analyst_score}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/graph/test_regime_assertion.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/_graph_utils.py tests/graph/test_regime_assertion.py
git commit -m "feat(graph): add assert_regime_consistent helper (PR-A1)"
```

---

### Task A1.2: Wire validator node into trading graph

**Files:**
- Modify: `tradingagents/graph/setup.py`

- [ ] **Step 1: Write integration test**

Append to `tests/graph/test_regime_assertion.py`:

```python
def test_validator_node_skips_when_canonical_absent():
    """When canonical_regime missing from state, validator must skip silently."""
    from tradingagents.graph.setup import GraphSetup
    node = GraphSetup._make_market_regime_check_node()
    state = {"market_report": "Macro Regime: TRANSITION (+2/6)"}
    result = node(state)
    assert result == {"sender": "market_regime_check"}


def test_validator_node_raises_when_canonical_present_and_drift():
    from tradingagents.graph.setup import GraphSetup
    node = GraphSetup._make_market_regime_check_node()
    state = {
        "market_report": "Macro Regime: TRANSITION (+2/6)",
        "canonical_regime": {"label": "RISK-ON", "score": 5},
    }
    with pytest.raises(ValueError, match=r"regime drift"):
        node(state)
```

- [ ] **Step 2: Run; expect FAIL** (`_make_market_regime_check_node` not yet defined).

- [ ] **Step 3: Add validator node and wire it in**

In `tradingagents/graph/setup.py`:

(a) Add import near the top:
```python
from tradingagents.graph._graph_utils import assert_regime_consistent
```

(b) Add a static factory inside `class GraphSetup`:
```python
@staticmethod
def _make_market_regime_check_node() -> Callable[[AgentState], dict[str, Any]]:
    def market_regime_check_node(state: AgentState) -> dict[str, Any]:
        canonical = state.get("canonical_regime")
        if not canonical:
            return {"sender": "market_regime_check"}
        assert_regime_consistent(state.get("market_report") or "", canonical)
        return {"sender": "market_regime_check"}
    return market_regime_check_node
```

(c) In `setup_graph()`, after the Market Analyst's `msg_clear` exit and before the next analyst, register the node and rewire the edge. Find the line `workflow.add_node("Msg Clear Market", ...)` and the edge that follows it; insert `Market Regime Check` between them. Use `workflow.add_node("Market Regime Check", self._make_market_regime_check_node())` and adjust the conditional/edge to point through it.

- [ ] **Step 4: Run unit + smoke tests**

```
pytest tests/graph/test_regime_assertion.py -v
pytest tests/ -v -m "not integration" -k "graph"
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/setup.py tests/graph/test_regime_assertion.py
git commit -m "feat(graph): wire regime drift validator after Market Analyst (PR-A1)"
```

**PR-A1 acceptance gate:** Replay any pre-A3 run; validator skips silently because `canonical_regime` is absent. After A3 lands, validator activates and reproduces the QCOM drift as a hard failure.

---

## Phase A2: RM ↔ fundamentals numeric guard

### Task A2.1: Pure extraction + verification module

**Files:**
- Create: `tradingagents/graph/_consistency_guard.py`
- Create: `tests/graph/test_consistency_guard.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/graph/test_consistency_guard.py
import pytest
from tradingagents.graph._consistency_guard import (
    NumericClaim, extract_numeric_claims, verify_against_fundamentals
)


def test_extract_high_confidence_percent_claim():
    rm_text = "- EBITDA margin expanded +3.8% YoY coinciding with..."
    claims = extract_numeric_claims(rm_text)
    assert any(
        c.metric.lower().startswith("ebitda margin") and c.value == 3.8 and c.unit == "%"
        and c.direction == "expansion"
        for c in claims
    )


def test_extract_bps_claim():
    rm_text = "- net leverage declined 320bps to 3.8x"
    claims = extract_numeric_claims(rm_text)
    bps = [c for c in claims if c.unit == "bps"]
    assert bps and bps[0].value == 320 and bps[0].direction == "compression"


def test_verify_detects_sign_disagreement():
    """RM claims margin expansion; fundamentals shows compression."""
    fundamentals = (
        "Operating margin Q4 2025: 9.3% vs Q2 2025: 12.0% — 270bps compression"
    )
    claims = [NumericClaim(
        metric="EBITDA margin", value=3.8, unit="%", direction="expansion",
        confidence="high",
    )]
    result = verify_against_fundamentals(claims, fundamentals)
    assert len(result["violations"]) == 1
    assert "expansion" in result["violations"][0].reason.lower()


def test_verify_passes_when_within_tolerance():
    fundamentals = "Operating margin compressed 270bps over 2 quarters"
    claims = [NumericClaim(
        metric="operating margin", value=270, unit="bps", direction="compression",
        confidence="high",
    )]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []


def test_unmappable_claim_downgrades_to_flag():
    """Metric not in fundamentals → flag-only, not a violation."""
    fundamentals = "Operating margin compressed 270bps"
    claims = [NumericClaim(
        metric="DCF coverage ratio", value=1.2, unit="x", direction=None,
        confidence="low",
    )]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []
    assert claims[0] in result["flags"]


def test_replay_et_rm_violations():
    """ET RM from run 01KQHDVJB2R19S4D7Z7Z6DP9F7 vs fundamentals report."""
    rm_text = (
        "- EBITDA margin expanded +3.8% YoY coinciding with U.S. sovereign...\n"
        "- Free cash flow conversion improved +14.2bps quarter-over-quarter "
        "while net leverage declined 320bps to 3.8x"
    )
    fundamentals = (
        "Operating margins peaked at 12.0% in Q2 2025 and have since declined to "
        "9.3% in Q4 2025, a 270bps compression. "
        "Free cash flow turned negative in Q4 2025 (-$225M). "
        "Total debt increased by $6.119B in Q4 2025 (+9.6% QoQ)."
    )
    claims = extract_numeric_claims(rm_text)
    result = verify_against_fundamentals(claims, fundamentals)
    # All three claims contradict fundamentals → 3 high-confidence violations.
    assert len(result["violations"]) >= 2  # at least margin + leverage
```

- [ ] **Step 2: Run; expect FAIL** (module doesn't exist).

- [ ] **Step 3: Implement module**

Create `tradingagents/graph/_consistency_guard.py`:

```python
"""Numeric-consistency guard between Research Manager and fundamentals.

Extracts numeric claims from RM bullets (regex over free text) and verifies
each one against the fundamentals report. High-confidence violations block
the graph (after one corrective re-prompt); low-confidence claims are flagged
only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

Direction = Optional[Literal["expansion", "compression", "increase", "decrease"]]
Confidence = Literal["high", "low"]
Unit = Literal["%", "bps", "x", "B", "M"]


@dataclass(frozen=True)
class NumericClaim:
    metric: str
    value: float
    unit: Unit
    direction: Direction
    confidence: Confidence


@dataclass(frozen=True)
class Violation:
    claim: NumericClaim
    reason: str


# Map verb keywords to a normalized direction.
_DIRECTION_WORDS = {
    "expanded": "expansion", "expansion": "expansion", "expand": "expansion",
    "improved": "expansion", "improvement": "expansion",
    "rose": "increase", "increased": "increase", "increase": "increase",
    "declined": "compression", "decline": "compression",
    "compressed": "compression", "compression": "compression",
    "fell": "decrease", "decreased": "decrease",
}

# Known metric noun-phrases that map cleanly to fundamentals report sections.
_KNOWN_METRICS = {
    "ebitda margin", "operating margin", "gross margin", "net margin",
    "net leverage", "leverage", "debt to equity",
    "fcf conversion", "free cash flow", "fcf",
    "revenue", "net income", "eps", "interest expense",
}

_NUM_RE = re.compile(
    r"([+-]?\d+(?:\.\d+)?)\s*(%|bps|x|B|M)\b",
    re.IGNORECASE,
)


def _classify_confidence(metric: str) -> Confidence:
    m = metric.lower().strip()
    return "high" if any(k in m for k in _KNOWN_METRICS) else "low"


def _infer_direction(left_context: str) -> Direction:
    lc = left_context.lower()
    for word, direction in _DIRECTION_WORDS.items():
        if word in lc:
            return direction  # type: ignore[return-value]
    return None


def _infer_metric(left_context: str) -> str:
    """Find the metric noun-phrase preceding a numeric token."""
    lc = left_context.lower()
    for known in sorted(_KNOWN_METRICS, key=len, reverse=True):
        if known in lc:
            return known
    # Fallback: take the last 4 words before the number.
    words = left_context.strip().split()
    return " ".join(words[-4:]) if words else ""


def extract_numeric_claims(rm_text: str) -> list[NumericClaim]:
    """Extract structured numeric claims from RM bullet text."""
    claims: list[NumericClaim] = []
    text = rm_text or ""
    for match in _NUM_RE.finditer(text):
        value = float(match.group(1))
        unit = match.group(2)
        # Look back ~80 chars for the metric noun-phrase and direction.
        left = text[max(0, match.start() - 80) : match.start()]
        metric = _infer_metric(left)
        direction = _infer_direction(left)
        confidence = _classify_confidence(metric)
        if not metric:
            continue
        claims.append(NumericClaim(
            metric=metric, value=value, unit=unit,  # type: ignore[arg-type]
            direction=direction, confidence=confidence,
        ))
    return claims


# Keywords in fundamentals text that signal each direction for a given metric.
_DIRECTION_KEYWORDS = {
    "expansion": ("expand", "improv", "rose", "increas"),
    "compression": ("compress", "declin", "fell", "decreas", "negative"),
    "increase": ("increas", "rose", "up "),
    "decrease": ("decreas", "decline", "fell", "down "),
}


def _fundamentals_says_direction(metric: str, direction: Direction, fundamentals: str) -> bool:
    """Heuristic: is the fundamentals text consistent with this (metric, direction)?"""
    if direction is None:
        return True  # nothing to check
    f = fundamentals.lower()
    m = metric.lower()
    # Find sentences mentioning the metric.
    sentences = re.split(r"(?<=[.!?])\s+", fundamentals)
    relevant = [s for s in sentences if m in s.lower()]
    if not relevant:
        # Metric not mentioned — neither confirm nor deny.
        return True
    keywords = _DIRECTION_KEYWORDS.get(direction, ())
    return any(any(kw in s.lower() for kw in keywords) for s in relevant)


def verify_against_fundamentals(
    claims: list[NumericClaim], fundamentals: str
) -> dict:
    """Diff claims against the fundamentals report.

    Returns ``{"violations": [...], "flags": [...]}``. Violations are
    high-confidence claims that contradict the fundamentals; flags are
    low-confidence claims surfaced for review.
    """
    violations: list[Violation] = []
    flags: list[NumericClaim] = []
    for claim in claims:
        if claim.confidence == "low":
            flags.append(claim)
            continue
        if not _fundamentals_says_direction(claim.metric, claim.direction, fundamentals):
            violations.append(Violation(
                claim=claim,
                reason=(
                    f"RM claims {claim.metric} {claim.direction} of {claim.value}{claim.unit}; "
                    f"fundamentals report indicates the opposite or no support."
                ),
            ))
    return {"violations": violations, "flags": flags}
```

- [ ] **Step 4: Run tests**

```
pytest tests/graph/test_consistency_guard.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/_consistency_guard.py tests/graph/test_consistency_guard.py
git commit -m "feat(graph): add RM/fundamentals numeric consistency guard (PR-A2)"
```

---

### Task A2.2: Wire post-RM guard with one corrective re-prompt

**Files:**
- Modify: `tradingagents/graph/setup.py`
- Modify: RM agent prompt builder (locate via `grep -rn "create_research_manager" tradingagents/agents/`)

- [ ] **Step 1: Write integration test**

Append to `tests/graph/test_consistency_guard.py`:

```python
def test_guard_node_passes_clean_rm_output():
    """Clean RM output → no violations, no re-prompt, sender set."""
    from tradingagents.graph.setup import GraphSetup
    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- Operating margin compressed 270bps over 2 quarters",
        "fundamentals_report": "Operating margins compressed 270bps from Q2 to Q4 2025.",
        "_rm_consistency_attempt": 0,
    }
    result = node(state)
    assert "violations" not in result.get("rm_consistency_status", "ok")


def test_guard_node_raises_after_second_offense():
    """Second-pass RM still violates → hard fail."""
    from tradingagents.graph.setup import GraphSetup
    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- EBITDA margin expanded +3.8% YoY",
        "fundamentals_report": "Operating margin compressed 270bps.",
        "_rm_consistency_attempt": 1,
    }
    with pytest.raises(ValueError, match=r"unresolved.*violations"):
        node(state)


def test_guard_node_routes_to_reprompt_on_first_offense():
    """First-pass RM violates → return signal to re-prompt RM."""
    from tradingagents.graph.setup import GraphSetup
    node = GraphSetup._make_rm_consistency_guard_node()
    state = {
        "investment_plan": "- EBITDA margin expanded +3.8% YoY",
        "fundamentals_report": "Operating margin compressed 270bps.",
        "_rm_consistency_attempt": 0,
    }
    result = node(state)
    assert result.get("rm_consistency_status") == "reprompt"
    assert "consistency_violations" in result
    assert result["_rm_consistency_attempt"] == 1
```

- [ ] **Step 2: Run; expect FAIL.**

- [ ] **Step 3: Implement guard node**

In `tradingagents/graph/setup.py`:

(a) Add imports:
```python
from tradingagents.graph._consistency_guard import (
    extract_numeric_claims, verify_against_fundamentals,
)
```

(b) Add static factory:
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
                    {"metric": f.metric, "value": f.value, "unit": f.unit}
                    for f in flags
                ],
                "sender": "rm_consistency_guard",
            }
        if attempt >= 1:
            details = "; ".join(v.reason for v in violations)
            raise ValueError(
                f"rm_consistency_guard: unresolved numeric violations after "
                f"corrective re-prompt — {details}"
            )
        return {
            "rm_consistency_status": "reprompt",
            "consistency_violations": [
                {"metric": v.claim.metric, "claim_value": v.claim.value,
                 "claim_unit": v.claim.unit, "reason": v.reason}
                for v in violations
            ],
            "_rm_consistency_attempt": attempt + 1,
            "sender": "rm_consistency_guard",
        }
    return rm_consistency_guard_node
```

(c) Wire into graph: add node `"RM Consistency Guard"` after `"Research Manager"`. Add a conditional edge: if `rm_consistency_status == "reprompt"`, route back to `"Research Manager"`; otherwise proceed to `"Trader"`.

```python
workflow.add_node("RM Consistency Guard", self._make_rm_consistency_guard_node())
workflow.add_edge("Research Manager", "RM Consistency Guard")
workflow.add_conditional_edges(
    "RM Consistency Guard",
    lambda s: "Research Manager" if s.get("rm_consistency_status") == "reprompt" else "Trader",
    {"Research Manager": "Research Manager", "Trader": "Trader"},
)
```

(d) Update RM prompt builder: when `state.get("consistency_violations")` is present, include a section in the prompt instructing RM to address each violation. Locate via `grep -rn "create_research_manager" tradingagents/agents/`. Add to the prompt construction:

```python
violations = state.get("consistency_violations") or []
if violations:
    correction_block = (
        "\n## CORRECTION REQUIRED\n"
        "Your previous response contained numeric claims that contradict the "
        "fundamentals report. Address each violation below by either correcting "
        "the number to match the fundamentals report or removing the claim:\n"
        + "\n".join(f"- {v['metric']}: {v['reason']}" for v in violations)
    )
    system_message += correction_block
```

- [ ] **Step 4: Run tests**

```
pytest tests/graph/test_consistency_guard.py -v
pytest tests/ -v -m "not integration" -k "graph"
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/setup.py tradingagents/agents/researchers/research_manager.py tests/graph/test_consistency_guard.py
git commit -m "feat(graph): wire RM consistency guard with one corrective re-prompt (PR-A2)"
```

**PR-A2 acceptance gate:** Replay ET RM output from run `01KQHDVJB2R19S4D7Z7Z6DP9F7`; with mocked RM that corrects on re-prompt, run continues; with RM that repeats the same numbers, run hard-fails with the violations listed.

---

## Phase A3: Canonical regime routing

### Task A3.1: Add `canonical_regime` to AgentState

**Files:**
- Modify: `tradingagents/agents/utils/agent_states.py`
- Create: `tests/graph/test_regime_routing.py`

- [ ] **Step 1: Write failing test**

```python
# tests/graph/test_regime_routing.py
def test_agent_state_supports_canonical_regime():
    from tradingagents.agents.utils.agent_states import AgentState
    state: AgentState = {"canonical_regime": {"label": "RISK-ON", "score": 5}}
    assert state["canonical_regime"]["label"] == "RISK-ON"
```

- [ ] **Step 2: Run; expect FAIL** (TypedDict total or mypy on CI may fail; runtime test should pass since TypedDict isn't enforced — instead verify via `__annotations__`).

Better runtime check:
```python
def test_agent_state_declares_canonical_regime():
    from tradingagents.agents.utils.agent_states import AgentState
    assert "canonical_regime" in AgentState.__annotations__
```

- [ ] **Step 3: Add field to AgentState**

In `tradingagents/agents/utils/agent_states.py`, find the `AgentState` TypedDict and add:
```python
canonical_regime: dict  # {"label": str, "score": int} from macro_regime_brief
```

- [ ] **Step 4: Run test; expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/utils/agent_states.py tests/graph/test_regime_routing.py
git commit -m "feat(graph): declare canonical_regime field in AgentState (PR-A3)"
```

---

### Task A3.2: Market Analyst reads `canonical_regime` from state

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py` (locate via `grep -rn "create_market_analyst" tradingagents/agents/`)

- [ ] **Step 1: Write failing test**

Append to `tests/graph/test_regime_routing.py`:

```python
def test_market_analyst_prompt_includes_canonical_regime(monkeypatch):
    """Confirm the prompt builder substitutes canonical regime when present."""
    from tradingagents.agents.analysts.market_analyst import _build_market_prompt
    state = {
        "company_of_interest": "QCOM",
        "trade_date": "2026-04-30",
        "canonical_regime": {"label": "RISK-ON", "score": 5,
                             "brief": "RISK-ON (+5/6) suppressed VIX"},
    }
    prompt = _build_market_prompt(state)
    assert "RISK-ON" in prompt
    assert "+5/6" in prompt
    assert "infer the regime" not in prompt.lower()
```

(`_build_market_prompt` may not exist yet as a separable function; if so, refactor the prompt construction inside `create_market_analyst` into this helper as part of this task.)

- [ ] **Step 2: Run; expect FAIL.**

- [ ] **Step 3: Refactor + implement**

In `market_analyst.py`:
- Extract the prompt-building portion into `_build_market_prompt(state) -> str`.
- When `state.get("canonical_regime")` is truthy, prepend a "CANONICAL MACRO REGIME" section with the label, score, and any brief text. Replace any prior wording that asks the analyst to "infer the regime" with "contextualize the ticker against the canonical regime above."

```python
def _build_market_prompt(state: dict) -> str:
    base = "..."  # existing prompt text
    canonical = state.get("canonical_regime") or {}
    if canonical:
        regime_block = (
            f"\n## CANONICAL MACRO REGIME (do not redefine)\n"
            f"- Label: {canonical.get('label')}\n"
            f"- Score: +{canonical.get('score')}/6\n"
            f"{canonical.get('brief', '')}\n\n"
            "Contextualize the ticker against this regime; do not classify a different one."
        )
        return regime_block + base
    return base
```

- [ ] **Step 4: Run test; expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add tradingagents/agents/analysts/market_analyst.py tests/graph/test_regime_routing.py
git commit -m "feat(market-analyst): consume canonical_regime from state (PR-A3)"
```

---

### Task A3.3: Engine populates `canonical_regime` per ticker

**Files:**
- Modify: `agent_os/backend/services/langgraph_engine.py`

- [ ] **Step 1: Write integration test**

Append to `tests/graph/test_regime_routing.py`:

```python
def test_engine_routes_canonical_regime_into_trading_state(monkeypatch):
    """When invoking trading graph for a ticker, canonical_regime must be set
    from the same source make_pm_decision uses."""
    from agent_os.backend.services.langgraph_engine import _build_trading_graph_initial_state
    macro_brief = "Macro Regime: RISK-ON (+5/6)\nVIX 17.10..."
    state = _build_trading_graph_initial_state(
        ticker="QCOM",
        analysis_date="2026-05-01",
        macro_brief=macro_brief,
    )
    assert state["canonical_regime"]["label"] == "RISK-ON"
    assert state["canonical_regime"]["score"] == 5
    assert state["canonical_regime"]["brief"].startswith("Macro Regime:")
```

- [ ] **Step 2: Run; expect FAIL.**

- [ ] **Step 3: Implement helper + wire into invocation**

In `langgraph_engine.py`:

(a) Add helper:
```python
import re

_REGIME_LABEL_RE = re.compile(r"\b(RISK-ON|RISK-OFF|TRANSITION)\b")
_REGIME_SCORE_RE = re.compile(r"\(\s*([+-]?\d+)\s*/\s*6\s*\)")


def _parse_canonical_regime(macro_brief: str) -> dict:
    label_m = _REGIME_LABEL_RE.search(macro_brief or "")
    score_m = _REGIME_SCORE_RE.search(macro_brief or "")
    if not label_m or not score_m:
        return {}
    return {
        "label": label_m.group(1),
        "score": int(score_m.group(1)),
        "brief": macro_brief,
    }


def _build_trading_graph_initial_state(
    ticker: str, analysis_date: str, macro_brief: str
) -> dict:
    return {
        "company_of_interest": ticker,
        "trade_date": analysis_date,
        "canonical_regime": _parse_canonical_regime(macro_brief),
    }
```

(b) At the call-site where the trading graph is invoked per ticker, replace the inline initial-state dict with `_build_trading_graph_initial_state(ticker, date, macro_brief)`. The macro_brief value is the same string already passed to `make_pm_decision`. Locate via `grep -n "trading_graph.*invoke\|graph.invoke" agent_os/backend/services/langgraph_engine.py`.

- [ ] **Step 4: Run unit + smoke**

```
pytest tests/graph/test_regime_routing.py -v
pytest tests/ -v -m "not integration" -k "graph or engine"
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add agent_os/backend/services/langgraph_engine.py tests/graph/test_regime_routing.py
git commit -m "feat(engine): route canonical macro regime into trading graph state (PR-A3)"
```

**PR-A3 acceptance gate:** Run trading graph for QCOM with the macro brief that emitted "RISK-ON +5/6"; Market Analyst output's regime line is exactly "RISK-ON +5/6". The PR-A1 validator no longer skips silently — it activates and stays silent because the analyst is now grounded.

---

## Stream A self-review checklist

- [ ] All five spec items in §"PR-A1", §"PR-A2", §"PR-A3" have at least one task.
- [ ] No "TBD"/"TODO"/placeholder strings in any task body.
- [ ] Helper names match across tasks (`assert_regime_consistent`, `_make_market_regime_check_node`, `_make_rm_consistency_guard_node`, `_parse_canonical_regime`, `_build_trading_graph_initial_state`).
- [ ] Each PR ends with a commit and an acceptance-gate sentence.
- [ ] Tests reference the actual run id `01KQHDVJB2R19S4D7Z7Z6DP9F7` for replay scenarios.
