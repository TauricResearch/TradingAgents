# Robust Action Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent HOLD-default in `_infer_recommendation` with a two-stage extractor (regex → LLM fallback → hard fail) and add a `candidate_handoff_guard` node to the portfolio graph to catch unaccountable candidate drops.

**Architecture:** New `extract_action()` public function wraps `_extract_action_regex()` + `_extract_action_llm()` with explicit `ActionExtractionError` on hard fail. All four `build_*_structured` callers get an `extraction_failed` status branch. A new `candidate_handoff_guard_node` runs after `prioritize_candidates` and raises `CandidateHandoffError` on unaccountable drops or total extraction failure.

**Tech Stack:** Python 3.12, LangChain messages (`SystemMessage`/`HumanMessage`), `invoke_with_timeout` / `resolve_timeout` from `tradingagents.agents.utils.llm_guard`, `extract_json` from `tradingagents.agents.utils.json_utils`, pytest, `unittest.mock`.

**Design spec:** `docs/agent/plans/026-robust-action-extraction-design.md`

---

## File Map

**Modified:**

- `tradingagents/agents/utils/output_validation.py` — new types, `extract_action`, updated `_infer_recommendation`, updated `build_*_structured` callers
- `tradingagents/graph/portfolio_setup.py` — new `candidate_handoff_guard` node wired between `prioritize_candidates` and the fan-out to `macro_summary`/`micro_summary`
- `tests/unit/test_output_validation.py` — existing tests updated for new raise behavior + new `extraction_failed` cases
- `tests/graph/test_portfolio_decision_snapshot.py` — guard-wiring smoke test
- `tests/portfolio/test_portfolio_setup.py` — guard-wiring smoke test

**Created:**

- `tests/unit/test_action_extraction_regex.py` — table-driven regex tests
- `tests/unit/test_action_extraction_llm.py` — mocked LLM tests
- `tests/unit/test_action_extraction_integration.py` — regex+LLM pipeline tests
- `tests/portfolio/test_candidate_handoff_guard.py` — guard logic tests

---

## Task 1: New types — `ExtractionResult`, `ActionExtractionError`, `CandidateHandoffError`

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py:30-40` (after existing `@dataclass` block at line 30)

- [ ] **Step 1.1: Write failing import test**

```python
# tests/unit/test_action_extraction_regex.py
def test_extraction_result_importable():
    from tradingagents.agents.utils.output_validation import (
        ActionExtractionError,
        ExtractionResult,
    )
    r = ExtractionResult(action="BUY", confidence="high", source="regex", evidence_quote=None)
    assert r.action == "BUY"
    assert r.confidence == "high"
    assert r.source == "regex"
    assert r.evidence_quote is None

def test_action_extraction_error_carries_context():
    from tradingagents.agents.utils.output_validation import (
        ActionExtractionError,
        ExtractionResult,
    )
    last = ExtractionResult(action="HOLD", confidence="low", source="llm", evidence_quote=None)
    exc = ActionExtractionError(text_excerpt="ambiguous text", last_attempt=last)
    assert "ambiguous text" in str(exc)
```

- [ ] **Step 1.2: Run to confirm failure**

```
pytest tests/unit/test_action_extraction_regex.py::test_extraction_result_importable \
       tests/unit/test_action_extraction_regex.py::test_action_extraction_error_carries_context \
       -v
```

Expected: `ImportError` — `ExtractionResult` not defined.

- [ ] **Step 1.3: Add the types to `output_validation.py`**

Find the `@dataclass` at line 30 and add immediately after the existing dataclass block (before `_SCRATCHPAD_PHRASES` or wherever the first block ends). Add these three types right after the `import` block (before line 18):

```python
# In output_validation.py — add after existing imports, before _SCRATCHPAD_PHRASES

from typing import Literal  # add to existing typing import if not present


@dataclass(frozen=True)
class ExtractionResult:
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: Literal["high", "med", "low"]
    source: Literal["regex", "llm"]
    evidence_quote: str | None


class ActionExtractionError(Exception):
    def __init__(self, text_excerpt: str, last_attempt: "ExtractionResult | None" = None):
        self.text_excerpt = text_excerpt
        self.last_attempt = last_attempt
        super().__init__(
            f"action_extraction_failed: could not determine BUY/SELL/HOLD from text "
            f"(first 300 chars): {text_excerpt!r}"
        )


class CandidateHandoffError(Exception):
    def __init__(
        self,
        kind: Literal["unaccountable_drop", "all_extraction_failed"],
        n_in: int,
        n_out: int,
        per_ticker_status: dict[str, str],
    ):
        self.kind = kind
        self.n_in = n_in
        self.n_out = n_out
        self.per_ticker_status = per_ticker_status
        super().__init__(
            f"candidate_handoff_error kind={kind} n_in={n_in} n_out={n_out} "
            f"per_ticker={per_ticker_status}"
        )
```

Note: `output_validation.py` already imports `dataclass` at line 10 and has `from typing import Any`. Add `Literal` to that import.

- [ ] **Step 1.4: Run tests to confirm pass**

```
pytest tests/unit/test_action_extraction_regex.py::test_extraction_result_importable \
       tests/unit/test_action_extraction_regex.py::test_action_extraction_error_carries_context \
       -v
```

Expected: PASS.

- [ ] **Step 1.5: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_action_extraction_regex.py
git commit -m "feat: add ExtractionResult, ActionExtractionError, CandidateHandoffError types"
```

---

## Task 2: `_extract_action_regex()` — extended pattern set returning `ExtractionResult | None`

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py` — replace `_infer_recommendation` core with new `_extract_action_regex`
- Modify: `tests/unit/test_action_extraction_regex.py`

- [ ] **Step 2.1: Write failing regex tests**

Add to `tests/unit/test_action_extraction_regex.py`:

```python
import pytest

# (test_extraction_result_importable and test_action_extraction_error_carries_context already here)

@pytest.mark.parametrize("text,expected_action", [
    # ── existing patterns ──────────────────────────────────────────────────
    ("FINAL TRANSACTION PROPOSAL: BUY", "BUY"),
    ("FINAL TRANSACTION PROPOSAL: **BUY**", "BUY"),
    ("FINAL RECOMMENDATION: SELL", "SELL"),
    ("RECOMMENDATION: HOLD", "HOLD"),
    ("BALANCED ASSESSMENT: BUY", "BUY"),
    ("RATING: SELL", "SELL"),
    ("ACTION: BUY", "BUY"),
    # ── new: numbered markdown headers ────────────────────────────────────
    ("**1. Rating**\n**Buy**", "BUY"),
    ("**2. Final Rating**\n**Sell**", "SELL"),
    # ── new: bold-line headers ────────────────────────────────────────────
    ("**Rating**\n**Buy**", "BUY"),
    ("**Rating**\n**SELL**", "SELL"),
    # ── new: ATX headers ─────────────────────────────────────────────────
    ("### Rating\nBuy", "BUY"),
    ("## Final Rating\nSELL", "SELL"),
    # ── new: numbered prefix variants ────────────────────────────────────
    ("1. Rating: Buy", "BUY"),
    ("1) Rating — Sell", "SELL"),
    # ── new: tolerant spacing / mixed bold ───────────────────────────────
    ("RATING:  **BUY**  ", "BUY"),
    ("RECOMMENDATION: *SELL*", "SELL"),
    # ── case insensitivity ───────────────────────────────────────────────
    ("rating: buy", "BUY"),
    ("final transaction proposal: sell", "SELL"),
])
def test_regex_extracts(text, expected_action):
    from tradingagents.agents.utils.output_validation import _extract_action_regex

    result = _extract_action_regex(text)
    assert result is not None, f"Expected match for {text!r}, got None"
    assert result.action == expected_action
    assert result.confidence == "high"
    assert result.source == "regex"
    assert result.evidence_quote is None


@pytest.mark.parametrize("text", [
    # ambiguous prose that must NOT match
    "The company performed a buyback and the outlook is cautious.",
    "Bears say sell the rally; bulls say buy the dip. Net: unclear.",
    "",
    "   ",
])
def test_regex_returns_none_on_miss(text):
    from tradingagents.agents.utils.output_validation import _extract_action_regex

    result = _extract_action_regex(text)
    assert result is None, f"Expected None for {text!r}, got {result}"
```

- [ ] **Step 2.2: Run to confirm failure**

```
pytest tests/unit/test_action_extraction_regex.py -v -k "test_regex"
```

Expected: `ImportError` — `_extract_action_regex` not defined.

- [ ] **Step 2.3: Implement `_extract_action_regex` in `output_validation.py`**

Add this function immediately above `_infer_recommendation` (around line 556). It replaces the six-pattern list inside `_infer_recommendation`:

```python
def _extract_action_regex(text: str) -> "ExtractionResult | None":
    """Return ExtractionResult via regex on known-format labels, or None on miss.

    Never returns a default — None means "no pattern matched".
    """
    raw = str(text or "")
    single_line_patterns = [
        # explicit proposal/recommendation labels (original six)
        r"FINAL\s+TRANSACTION\s+PROPOSAL\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"FINAL\s+RECOMMENDATION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"RECOMMENDATION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"BALANCED\s+ASSESSMENT\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"RATING\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        r"ACTION\s*:\s*[*_]*\s*(BUY|SELL|HOLD)\b",
        # numbered-prefix variants: "1. Rating: Buy" / "1) Rating — Sell"
        r"^\s*\d+[.)]\s+(?:Final\s+)?Rating\s*[:\-—]\s*[*_]*(BUY|SELL|HOLD)\b",
    ]
    for pattern in single_line_patterns:
        m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        if m:
            return ExtractionResult(
                action=m.group(1).upper(),
                confidence="high",
                source="regex",
                evidence_quote=None,
            )

    # Multi-line header patterns: bold/ATX header followed by action on next line
    # Covers: **1. Rating**\n**Buy**, **Rating**\n**Buy**, ### Rating\nBuy, etc.
    multi_line_pattern = re.compile(
        r"(?:#{1,3}\s*|[*_]{1,2})\d*[.)?\s]*(?:Final\s+)?Rating[*_]*\s*\n\s*[*_]*(BUY|SELL|HOLD)\b",
        re.IGNORECASE,
    )
    m = multi_line_pattern.search(raw)
    if m:
        return ExtractionResult(
            action=m.group(1).upper(),
            confidence="high",
            source="regex",
            evidence_quote=None,
        )

    return None
```

- [ ] **Step 2.4: Run regex tests**

```
pytest tests/unit/test_action_extraction_regex.py -v -k "test_regex"
```

Expected: all PASS. Investigate any failure — the pattern may need a tweak for that specific format.

- [ ] **Step 2.5: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_action_extraction_regex.py
git commit -m "feat: add _extract_action_regex with extended markdown-header patterns"
```

---

## Task 3: `_extract_action_llm()` — LLM fallback returning `ExtractionResult`

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py`
- Create: `tests/unit/test_action_extraction_llm.py`

The LLM fallback needs an `llm` argument injected at call time (so it can be mocked in tests and supplied by callers via `extract_action(text, llm=...)`). We will thread this through in Task 4.

- [ ] **Step 3.1: Write failing LLM fallback tests**

```python
# tests/unit/test_action_extraction_llm.py
"""Tests for _extract_action_llm — all LLM calls are mocked."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_llm_response(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(payload)
    return msg


def _make_llm(response_msg):
    llm = MagicMock()
    llm.invoke.return_value = response_msg
    return llm


def test_llm_high_confidence_buy():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "BUY", "confidence": "high", "evidence_quote": "Rating: Buy"}))
    result = _extract_action_llm("some text", llm=llm)
    assert result.action == "BUY"
    assert result.confidence == "high"
    assert result.source == "llm"
    assert result.evidence_quote == "Rating: Buy"


def test_llm_med_confidence_sell():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "SELL", "confidence": "med", "evidence_quote": "bearish view"}))
    result = _extract_action_llm("some text", llm=llm)
    assert result.action == "SELL"
    assert result.confidence == "med"


def test_llm_low_confidence_returns_sentinel():
    """Low confidence must return sentinel, not raise — caller decides."""
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "HOLD", "confidence": "low", "evidence_quote": None}))
    result = _extract_action_llm("ambiguous", llm=llm)
    assert result.confidence == "low"
    assert result.source == "llm"


def test_llm_invalid_json_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    msg = MagicMock()
    msg.content = "not json at all"
    llm = _make_llm(msg)
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"
    assert result.action == "HOLD"


def test_llm_invalid_action_enum_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = _make_llm(_make_llm_response({"action": "MAYBE", "confidence": "high", "evidence_quote": "x"}))
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"


def test_llm_timeout_returns_sentinel():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    llm = MagicMock()
    llm.invoke.side_effect = TimeoutError("timed out")
    result = _extract_action_llm("text", llm=llm)
    assert result.confidence == "low"


def test_llm_evidence_quote_propagated():
    from tradingagents.agents.utils.output_validation import _extract_action_llm

    quote = "The final rating is Buy given strong earnings momentum"
    llm = _make_llm(_make_llm_response({"action": "BUY", "confidence": "high", "evidence_quote": quote}))
    result = _extract_action_llm("...", llm=llm)
    assert result.evidence_quote == quote
```

- [ ] **Step 3.2: Run to confirm failure**

```
pytest tests/unit/test_action_extraction_llm.py -v
```

Expected: `ImportError` — `_extract_action_llm` not defined.

- [ ] **Step 3.3: Implement `_extract_action_llm` in `output_validation.py`**

Add this function immediately after `_extract_action_regex`. Add these imports at the top of the file (after existing imports):

```python
# Add to top-level imports in output_validation.py
from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout
```

Then add the function:

```python
_EXTRACTION_SYSTEM_PROMPT = """\
You extract the final trading action from a portfolio manager's report.
The action must be one of BUY, SELL, or HOLD.
Return strict JSON — no prose, no markdown fences:
{"action": "BUY"|"SELL"|"HOLD", "confidence": "high"|"med"|"low", "evidence_quote": "<verbatim ≤200 chars>"}
Set confidence to "low" if the text is ambiguous or the action is not clearly stated.
The evidence_quote must be a direct verbatim excerpt from the text that shows the action."""

_EXTRACTION_LOW_SENTINEL = None  # set lazily below after class definition


def _extract_action_llm(text: str, llm: Any) -> "ExtractionResult":
    """Call LLM to extract action. Never raises — returns low-confidence sentinel on any failure.

    The sentinel has confidence="low" so the caller's hard-fail path triggers uniformly.
    """
    _sentinel = ExtractionResult(action="HOLD", confidence="low", source="llm", evidence_quote=None)
    try:
        messages = [
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"TEXT:\n<<<{text}>>>"),
        ]
        timeout = resolve_timeout("quick")
        response, invoke_error = invoke_with_timeout(llm, messages, timeout_seconds=timeout)
        if invoke_error is not None or response is None:
            return _sentinel
        raw = response.content if hasattr(response, "content") else str(response)
        try:
            parsed = extract_json(raw)
        except Exception:
            return _sentinel
        if not isinstance(parsed, dict):
            return _sentinel
        action = str(parsed.get("action") or "").upper()
        if action not in {"BUY", "SELL", "HOLD"}:
            return _sentinel
        confidence = str(parsed.get("confidence") or "").lower()
        if confidence not in {"high", "med", "low"}:
            return _sentinel
        evidence_quote = parsed.get("evidence_quote")
        if isinstance(evidence_quote, str):
            evidence_quote = evidence_quote[:200] or None
        else:
            evidence_quote = None
        return ExtractionResult(
            action=action,  # type: ignore[arg-type]
            confidence=confidence,  # type: ignore[arg-type]
            source="llm",
            evidence_quote=evidence_quote,
        )
    except Exception:
        return _sentinel
```

- [ ] **Step 3.4: Run LLM fallback tests**

```
pytest tests/unit/test_action_extraction_llm.py -v
```

Expected: all PASS.

- [ ] **Step 3.5: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_action_extraction_llm.py
git commit -m "feat: add _extract_action_llm with low-confidence sentinel pattern"
```

---

## Task 4: `extract_action()` — public orchestrator

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py`
- Modify: `tests/unit/test_action_extraction_llm.py` (add integration tests for the orchestrator)
- Create: `tests/unit/test_action_extraction_integration.py`

- [ ] **Step 4.1: Write failing orchestrator tests**

Add to `tests/unit/test_action_extraction_llm.py`:

```python
def test_extract_action_uses_regex_first_no_llm_call():
    """When regex matches, LLM is never called."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = MagicMock()
    result = extract_action("FINAL TRANSACTION PROPOSAL: **BUY**", llm=llm)
    assert result.action == "BUY"
    assert result.source == "regex"
    llm.invoke.assert_not_called()


def test_extract_action_falls_back_to_llm_on_regex_miss():
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm(_make_llm_response({"action": "SELL", "confidence": "high", "evidence_quote": "sell"}))
    result = extract_action("Some prose without a clear label.", llm=llm)
    assert result.action == "SELL"
    assert result.source == "llm"


def test_extract_action_raises_on_low_confidence():
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    llm = _make_llm(_make_llm_response({"action": "HOLD", "confidence": "low", "evidence_quote": None}))
    with pytest.raises(ActionExtractionError) as exc_info:
        extract_action("ambiguous text", llm=llm)
    assert "ambiguous text" in str(exc_info.value)


def test_extract_action_raises_when_llm_errors():
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    llm = MagicMock()
    llm.invoke.side_effect = TimeoutError("timed out")
    with pytest.raises(ActionExtractionError):
        extract_action("ambiguous text", llm=llm)
```

- [ ] **Step 4.2: Run to confirm failure**

```
pytest tests/unit/test_action_extraction_llm.py -v -k "extract_action"
```

Expected: `ImportError` — `extract_action` not defined.

- [ ] **Step 4.3: Implement `extract_action` in `output_validation.py`**

Add immediately after `_extract_action_llm`:

```python
def extract_action(text: str, llm: Any = None) -> "ExtractionResult":
    """Two-stage action extractor. Raises ActionExtractionError on hard fail.

    Stage 1: regex (fast, deterministic, no LLM call).
    Stage 2: LLM fallback if regex misses (requires llm argument).

    Raises ActionExtractionError when:
    - regex misses AND llm is None (caller must provide llm for fallback)
    - regex misses AND LLM returns confidence=="low"
    - regex misses AND LLM errors (timeout, parse fail, etc.)
    """
    regex_result = _extract_action_regex(text)
    if regex_result is not None:
        return regex_result
    if llm is None:
        raise ActionExtractionError(text_excerpt=text[:300], last_attempt=None)
    llm_result = _extract_action_llm(text, llm=llm)
    if llm_result.confidence == "low":
        raise ActionExtractionError(text_excerpt=text[:300], last_attempt=llm_result)
    return llm_result
```

- [ ] **Step 4.4: Run orchestrator tests**

```
pytest tests/unit/test_action_extraction_llm.py -v
```

Expected: all PASS.

- [ ] **Step 4.5: Write integration tests against real audit-run text**

Create `tests/unit/test_action_extraction_integration.py`:

```python
"""Integration tests for extract_action against realistic PM report text."""
import json
from unittest.mock import MagicMock

import pytest


# Realistic PM output that bit us in audit run 01KQQGTQN98BZHTFECB8QXPTKA
# Multi-line markdown header format that the old regex missed
_OWL_PM_EXCERPT = """\
**IV. Final Portfolio Manager Decision**

**1. Rating**
**Buy**

**2. Entry**
Primary: $9.75 (current market price)
"""

_TEAM_PM_EXCERPT = """\
**IV. Portfolio Manager Decision**

**1. Rating**
**Buy**

**2. Entry Price Levels**
Tranche 1: $68.59 (current)
"""

_WELL_FORMED_PROPOSAL = (
    "- Research Manager's Verdict: BUY derived from validated upstream evidence (HIGH)\n"
    "- FINAL TRANSACTION PROPOSAL: **BUY**"
)

_MANGLED_PROSE = (
    "The committee considered the matter and reached no conclusion. "
    "Bears say caution. Bulls say proceed. Outcome: deferred."
)


def _make_llm_high(action: str) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps({"action": action, "confidence": "high", "evidence_quote": f"Rating: {action}"})
    llm = MagicMock()
    llm.invoke.return_value = msg
    return llm


def test_owl_excerpt_extracts_buy_via_llm_fallback():
    """OWL audit-run format: multi-line bold header — regex misses, LLM rescues."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm_high("BUY")
    result = extract_action(_OWL_PM_EXCERPT, llm=llm)
    assert result.action == "BUY"
    # LLM path used (regex missed the multi-line header)
    assert result.source == "llm"


def test_team_excerpt_extracts_buy():
    """TEAM audit-run format: same multi-line bold header pattern."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = _make_llm_high("BUY")
    result = extract_action(_TEAM_PM_EXCERPT, llm=llm)
    assert result.action == "BUY"


def test_well_formed_proposal_uses_regex_only():
    """Standard FINAL TRANSACTION PROPOSAL format: regex wins, no LLM call."""
    from tradingagents.agents.utils.output_validation import extract_action

    llm = MagicMock()
    result = extract_action(_WELL_FORMED_PROPOSAL, llm=llm)
    assert result.action == "BUY"
    assert result.source == "regex"
    llm.invoke.assert_not_called()


def test_mangled_prose_raises():
    """Truly ambiguous text must raise ActionExtractionError."""
    from tradingagents.agents.utils.output_validation import ActionExtractionError, extract_action

    msg = MagicMock()
    msg.content = json.dumps({"action": "HOLD", "confidence": "low", "evidence_quote": None})
    llm = MagicMock()
    llm.invoke.return_value = msg
    with pytest.raises(ActionExtractionError):
        extract_action(_MANGLED_PROSE, llm=llm)


def test_regex_covers_new_header_formats_without_llm():
    """After regex extension, numbered bold headers should match without LLM."""
    from tradingagents.agents.utils.output_validation import extract_action

    numbered_bold = "**1. Rating**\n**Sell**"
    llm = MagicMock()
    result = extract_action(numbered_bold, llm=llm)
    assert result.action == "SELL"
    # If regex catches it, LLM is never called
    if result.source == "regex":
        llm.invoke.assert_not_called()
```

Note: `test_owl_excerpt_extracts_buy_via_llm_fallback` and `test_team_excerpt_extracts_buy` will move to `source == "regex"` once the regex in Task 2 is tuned to catch those formats — that is intentional and the assertion is written to be forward-compatible (`result.action == "BUY"` regardless of source).

- [ ] **Step 4.6: Run integration tests**

```
pytest tests/unit/test_action_extraction_integration.py -v
```

Expected: all PASS (LLM is mocked throughout).

- [ ] **Step 4.7: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py \
        tests/unit/test_action_extraction_llm.py \
        tests/unit/test_action_extraction_integration.py
git commit -m "feat: add extract_action orchestrator with regex-first LLM-fallback"
```

---

## Task 5: Update `_infer_recommendation` shim to raise instead of default-HOLD

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py:556-572`
- Modify: `tests/unit/test_output_validation.py`

- [ ] **Step 5.1: Update tests that assert `HOLD` on empty/malformed input**

The current tests at these lines expect `HOLD` on `empty` status:
- Line 744: `assert structured["final_action"] == "HOLD"` (trader plan, empty)
- Line 828: `assert structured["action"] == "HOLD"` (final decision, empty)

Empty-string inputs (`status == "empty"`) should **not** call `extract_action` at all — the extraction path only runs when `status == "completed"`. So those tests remain valid. Verify this is true before changing anything.

Find and update only the tests that use **non-empty but malformed** input and currently expect `HOLD`. Search:

```bash
grep -n '"HOLD"\|== "HOLD"' tests/unit/test_output_validation.py
```

For each hit, determine: does the input text match a real format or is it malformed? If the text has no recognizable label and no LLM mock, it will now raise `ActionExtractionError`. Those tests need updating. (The `empty` path tests are fine as-is — empty means `status == "empty"`, not `extraction_failed`.)

Update `test_build_empty` cases: these pass `investment_plan=""` etc., so `status == "empty"` and `_infer_recommendation` is never called. No change needed for those.

Add a new test for the `extraction_failed` path for each builder. Example for `build_investment_plan_structured`:

```python
def test_build_investment_plan_extraction_failed():
    from tradingagents.agents.utils.output_validation import (
        ActionExtractionError,
        build_investment_plan_structured,
    )
    import pytest

    ambiguous = "The committee considered the matter. No clear direction was established."
    with pytest.raises(ActionExtractionError):
        build_investment_plan_structured(
            ticker="XYZ",
            as_of_date="2026-05-03",
            investment_plan=ambiguous,
            # no llm= argument → will raise on LLM-miss path
        )
```

Add analogous `test_build_trader_plan_extraction_failed`, `test_build_risk_synthesis_extraction_failed`, `test_build_final_decision_extraction_failed`.

- [ ] **Step 5.2: Run existing tests to capture baseline failures**

```
pytest tests/unit/test_output_validation.py -v
```

Record which tests fail after the upcoming shim change (most should pass until the shim is changed).

- [ ] **Step 5.3: Replace `_infer_recommendation` with a raising shim**

In `output_validation.py`, replace lines 556-572 with:

```python
def _infer_recommendation(text: str, llm: Any = None) -> str:
    """Back-compat shim. Raises ActionExtractionError on hard fail (no HOLD default)."""
    return extract_action(text, llm=llm).action
```

- [ ] **Step 5.4: Run all output_validation tests**

```
pytest tests/unit/test_output_validation.py -v
```

Expected: all existing PASS tests still pass (because their input texts use clear labels that the regex catches). Any tests that were relying on the HOLD default with ambiguous text will now fail — fix those now by either:
(a) changing the assertion to `pytest.raises(ActionExtractionError)`, or
(b) updating the input text to use a clear label like `"RECOMMENDATION: HOLD"` (if the test intent was "no clear action → treat as HOLD", that intent is now wrong — HOLD must be explicit).

- [ ] **Step 5.5: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_output_validation.py
git commit -m "fix: _infer_recommendation raises ActionExtractionError instead of defaulting to HOLD"
```

---

## Task 6: Update all four `build_*_structured` callers to handle `extraction_failed` status

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py` — four functions at lines ~938, ~986, ~1036, ~1091
- Modify: `tests/unit/test_output_validation.py`

All four `build_*_structured` functions call `_infer_recommendation(plan)` inside an `else: status = "completed"` branch. Replace that call with a try/except that adds the `extraction_failed` status.

The functions also need an optional `llm` parameter threaded through so callers can supply the quick-thinking model. The callers themselves (`portfolio_manager.py`, `research_manager.py`, `trader.py`, `risk_synthesis.py`) will be updated in Task 7.

- [ ] **Step 6.1: Write failing `extraction_failed` tests for all four builders**

In `tests/unit/test_output_validation.py`, add inside the relevant test class for each builder:

```python
# For TestInvestmentPlanStructuredContract
def test_build_investment_plan_extraction_failed_status(self):
    from tradingagents.agents.utils.output_validation import build_investment_plan_structured
    ambiguous = "The committee saw mixed signals. Outcome: uncertain."
    structured = build_investment_plan_structured(
        ticker="XYZ",
        as_of_date="2026-05-03",
        investment_plan=ambiguous,
        llm=None,  # no LLM → hard fail → extraction_failed
    )
    assert structured["status"] == "extraction_failed"
    assert structured["recommendation"] is None
    assert "action_extraction_failed" in structured["abort_reason"]

# For TestTraderPlanStructuredContract
def test_build_trader_plan_extraction_failed_status(self):
    from tradingagents.agents.utils.output_validation import build_trader_plan_structured
    ambiguous = "The committee saw mixed signals. Outcome: uncertain."
    structured = build_trader_plan_structured(
        ticker="XYZ",
        as_of_date="2026-05-03",
        trader_plan=ambiguous,
        llm=None,
    )
    assert structured["status"] == "extraction_failed"
    assert structured["final_action"] is None
    assert "action_extraction_failed" in structured["abort_reason"]

# For TestRiskSynthesisStructuredContract
def test_build_risk_synthesis_extraction_failed_status(self):
    from tradingagents.agents.utils.output_validation import build_risk_synthesis_structured
    ambiguous = "The committee saw mixed signals. Outcome: uncertain."
    structured = build_risk_synthesis_structured(
        ticker="XYZ",
        as_of_date="2026-05-03",
        risk_synthesis=ambiguous,
        llm=None,
    )
    assert structured["status"] == "extraction_failed"
    assert structured["consensus_direction"] is None

# For TestFinalDecisionStructuredContract
def test_build_final_decision_extraction_failed_status(self):
    from tradingagents.agents.utils.output_validation import build_final_decision_structured
    ambiguous = "The committee saw mixed signals. Outcome: uncertain."
    structured = build_final_decision_structured(
        ticker="XYZ",
        as_of_date="2026-05-03",
        final_decision=ambiguous,
        llm=None,
    )
    assert structured["status"] == "extraction_failed"
    assert structured["action"] is None
    assert "action_extraction_failed" in structured["abort_reason"]
```

- [ ] **Step 6.2: Run to confirm failure**

```
pytest tests/unit/test_output_validation.py -v -k "extraction_failed_status"
```

Expected: FAIL — the builders currently have no `extraction_failed` branch.

- [ ] **Step 6.3: Update all four `build_*_structured` functions**

For each function, wrap the `_infer_recommendation` call with try/except and add `llm` parameter. The pattern is identical for all four; the only difference is the action field name (`recommendation`, `final_action`, `consensus_direction`, `action`).

**`build_investment_plan_structured` (around line 921):**

```python
def build_investment_plan_structured(
    *,
    ticker: str,
    as_of_date: str,
    investment_plan: str,
    contract_version: str = "investment_plan_v1",
    is_timeout_fallback: bool = False,
    llm: Any = None,
) -> dict[str, Any]:
    plan = str(investment_plan or "").strip()
    timeout_detected = is_timeout_fallback or "timed out" in plan.lower()
    recommendation: str | None
    if not plan:
        status = "empty"
        abort_reason = ""
        recommendation = "HOLD"
    elif timeout_detected:
        status = "timeout_fallback"
        abort_reason = ""
        recommendation = "HOLD"
    else:
        try:
            recommendation = _infer_recommendation(plan, llm=llm)
            status = "completed"
            abort_reason = ""
        except ActionExtractionError as exc:
            recommendation = None
            status = "extraction_failed"
            abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
    # ... rest unchanged, but recommendation may now be None
```

Apply the same pattern to `build_trader_plan_structured` (field: `final_action`), `build_risk_synthesis_structured` (field: `consensus_direction`), and `build_final_decision_structured` (field: `action`).

Note: for `empty` and `timeout_fallback` branches, keep `"HOLD"` as the default — those are not decision-effecting extraction failures, they are structural failures (empty/timed-out LLM response) already handled upstream.

- [ ] **Step 6.4: Run all output_validation tests**

```
pytest tests/unit/test_output_validation.py -v
```

Expected: all PASS (including the new `extraction_failed_status` tests).

- [ ] **Step 6.5: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tests/unit/test_output_validation.py
git commit -m "feat: add extraction_failed status branch to all build_*_structured callers"
```

---

## Task 7: Thread `llm` through the four agent callers

**Files:**
- Modify: `tradingagents/agents/managers/portfolio_manager.py:162`
- Modify: `tradingagents/agents/managers/research_manager.py:134`
- Modify: `tradingagents/agents/trader/trader.py:196`
- Modify: `tradingagents/agents/risk_mgmt/risk_synthesis.py:109`

Each of these files already has an `llm` in scope (it's the `llm` bound to the agent node). We need to pass it through to the structured builder.

- [ ] **Step 7.1: Read each caller to find the llm variable name in scope**

In `portfolio_manager.py:162`:
```python
structured = build_final_decision_structured(
    ticker=state.get("company_of_interest", ""),
    as_of_date=state.get("trade_date", ""),
    final_decision=final_decision_text,
    llm=llm,  # add this — llm is in scope from node closure
)
```

In `research_manager.py:134`:
```python
structured = build_investment_plan_structured(
    ticker=state.get("company_of_interest", ""),
    as_of_date=state.get("trade_date", ""),
    investment_plan=investment_plan,
    llm=llm,  # add this
)
```

In `trader.py:196`:
```python
structured = build_trader_plan_structured(
    ticker=state.get("company_of_interest", ""),
    as_of_date=state.get("trade_date", ""),
    trader_plan=trader_decision,
    llm=llm,  # add this
)
```

In `risk_synthesis.py:109`:
```python
structured = build_risk_synthesis_structured(
    ticker=state.get("company_of_interest", ""),
    as_of_date=state.get("trade_date", ""),
    risk_synthesis=summary,
    is_timeout_fallback=is_timeout,
    llm=llm,  # add this
)
```

Before making changes, check the actual local variable name for the LLM in each file:

```bash
grep -n "llm\s*=" tradingagents/agents/managers/portfolio_manager.py | head -5
grep -n "llm\s*=" tradingagents/agents/managers/research_manager.py | head -5
grep -n "llm\s*=" tradingagents/agents/trader/trader.py | head -5
grep -n "llm\s*=" tradingagents/agents/risk_mgmt/risk_synthesis.py | head -5
```

Use the correct variable name found in each file.

- [ ] **Step 7.2: Make the changes**

Add `llm=<local_llm_var>` to each of the four `build_*_structured` calls identified above.

- [ ] **Step 7.3: Run the full test suite (non-integration)**

```
pytest tests/ -v -m "not integration" -x
```

Expected: all PASS. The `llm=` pass-through is a no-op in existing tests because those tests don't hit ambiguous text — they use clearly labeled inputs.

- [ ] **Step 7.4: Commit**

```bash
git add tradingagents/agents/managers/portfolio_manager.py \
        tradingagents/agents/managers/research_manager.py \
        tradingagents/agents/trader/trader.py \
        tradingagents/agents/risk_mgmt/risk_synthesis.py
git commit -m "feat: thread llm through to build_*_structured for LLM fallback path"
```

---

## Task 8: `candidate_handoff_guard_node` in `portfolio_setup.py`

**Files:**
- Modify: `tradingagents/graph/portfolio_setup.py`
- Create: `tests/portfolio/test_candidate_handoff_guard.py`

The new node runs after `prioritize_candidates` and before the fan-out to `macro_summary`/`micro_summary`. It uses `CandidateHandoffError` (already defined in `output_validation.py`).

- [ ] **Step 8.1: Write failing guard tests**

```python
# tests/portfolio/test_candidate_handoff_guard.py
"""Tests for candidate_handoff_guard_node in portfolio_setup.py."""
import json
from unittest.mock import MagicMock

import pytest


def _make_state(
    equity_candidates: list,
    ticker_analyses: dict,
    prioritized_candidates: list,
) -> dict:
    scan_summary = {"equity_candidates": equity_candidates}
    return {
        "scan_summary": scan_summary,
        "ticker_analyses": ticker_analyses,
        "prioritized_candidates": json.dumps(prioritized_candidates),
        "portfolio_id": "test-portfolio",
        "run_id": "test-run",
        "analysis_date": "2026-05-03",
    }


def _make_guard_node():
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    setup = PortfolioGraphSetup(
        agents={
            "review_holdings": MagicMock(),
            "macro_summary": MagicMock(),
            "micro_summary": MagicMock(),
            "pm_decision": MagicMock(),
        },
        repo=None,
        config={},
        macro_memory=None,
        micro_memory=None,
    )
    return setup._make_candidate_handoff_guard_node()


def test_guard_passes_when_n_in_zero():
    """No equity candidates from scanner → guard short-circuits, no error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[],
        ticker_analyses={},
        prioritized_candidates=[],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_when_all_buy_flow_through():
    """2 candidates, both extracted BUY, both in prioritized_candidates → pass."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
        },
        prioritized_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_when_all_hold():
    """2 candidates, both extracted HOLD → N_out == 0 is legitimate, no error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
        },
        prioritized_candidates=[],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_passes_on_partial_extraction_failure():
    """1 BUY, 1 extraction_failed → N_out == 1, accounted. No error."""
    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
        },
        prioritized_candidates=[{"ticker": "OWL"}],
    )
    result = guard(state)
    assert result.get("sender") == "candidate_handoff_guard"


def test_guard_raises_all_extraction_failed():
    """2 candidates, both extraction_failed, N_out == 0 → CandidateHandoffError."""
    from tradingagents.agents.utils.output_validation import CandidateHandoffError

    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
            "TEAM": {"final_trade_decision_structured": {"status": "extraction_failed", "action": None}},
        },
        prioritized_candidates=[],
    )
    with pytest.raises(CandidateHandoffError) as exc_info:
        guard(state)
    assert exc_info.value.kind == "all_extraction_failed"
    assert exc_info.value.n_in == 2
    assert exc_info.value.n_out == 0


def test_guard_raises_unaccountable_drop():
    """1 BUY, 1 HOLD, but N_out == 0 (HOLD not in candidates is fine, BUY drop is not)."""
    from tradingagents.agents.utils.output_validation import CandidateHandoffError

    guard = _make_guard_node()
    state = _make_state(
        equity_candidates=[{"ticker": "OWL"}, {"ticker": "TEAM"}],
        ticker_analyses={
            "OWL": {"final_trade_decision_structured": {"status": "completed", "action": "BUY"}},
            "TEAM": {"final_trade_decision_structured": {"status": "completed", "action": "HOLD"}},
        },
        # OWL should be in here (it's a BUY) but it isn't — unaccountable drop
        prioritized_candidates=[],
    )
    with pytest.raises(CandidateHandoffError) as exc_info:
        guard(state)
    assert exc_info.value.kind == "unaccountable_drop"
```

- [ ] **Step 8.2: Run to confirm failure**

```
pytest tests/portfolio/test_candidate_handoff_guard.py -v
```

Expected: `AttributeError` — `_make_candidate_handoff_guard_node` not defined.

- [ ] **Step 8.3: Implement `_make_candidate_handoff_guard_node` in `portfolio_setup.py`**

Add to `PortfolioGraphSetup` class, after `_make_prioritize_candidates_node` (around line 632):

```python
def _make_candidate_handoff_guard_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
    def candidate_handoff_guard_node(state: PortfolioManagerState) -> dict[str, Any]:
        from tradingagents.agents.utils.output_validation import CandidateHandoffError

        scan_summary = state.get("scan_summary") or {}
        ticker_analyses = state.get("ticker_analyses") or {}
        prioritized_raw = state.get("prioritized_candidates") or "[]"
        try:
            prioritized = json.loads(prioritized_raw) if isinstance(prioritized_raw, str) else prioritized_raw
        except (json.JSONDecodeError, TypeError):
            prioritized = []

        equity_candidates = (
            scan_summary.get("equity_candidates") or scan_summary.get("stocks_to_investigate") or []
        )
        n_in = len(equity_candidates)
        n_out = len(prioritized) if isinstance(prioritized, list) else 0

        if n_in == 0:
            return {"sender": "candidate_handoff_guard"}

        # Count each category of drop
        n_extr_fail = 0
        n_other_fail = 0
        n_not_buy = 0
        n_no_entry = 0
        per_ticker_status: dict[str, str] = {}

        for raw_candidate in equity_candidates:
            if isinstance(raw_candidate, dict):
                ticker = (raw_candidate.get("ticker") or raw_candidate.get("symbol") or "").upper()
            else:
                ticker = str(raw_candidate).upper()
            if not ticker:
                n_no_entry += 1
                continue

            analysis = ticker_analyses.get(ticker, {}) if isinstance(ticker_analyses, dict) else {}
            structured = analysis.get("final_trade_decision_structured") or {}
            analysis_status = str(analysis.get("analysis_status") or "").lower()
            status = str(structured.get("status") or "").lower()
            action = str(structured.get("action") or "").upper()

            if status == "extraction_failed":
                n_extr_fail += 1
                per_ticker_status[ticker] = "extraction_failed"
            elif analysis_status == "failed" and status != "extraction_failed":
                n_other_fail += 1
                per_ticker_status[ticker] = "analysis_failed"
            elif status == "completed" and action in {"HOLD", "SELL"}:
                n_not_buy += 1
                per_ticker_status[ticker] = f"completed:{action}"
            elif not analysis and not structured:
                n_no_entry += 1
                per_ticker_status[ticker] = "no_deep_dive"
            else:
                per_ticker_status[ticker] = f"completed:{action}"

        accounted_drop = n_extr_fail + n_other_fail + n_not_buy + n_no_entry

        if n_in > 0 and n_out == 0 and n_extr_fail == n_in:
            raise CandidateHandoffError(
                kind="all_extraction_failed",
                n_in=n_in,
                n_out=n_out,
                per_ticker_status=per_ticker_status,
            )

        if n_in - n_out != accounted_drop:
            raise CandidateHandoffError(
                kind="unaccountable_drop",
                n_in=n_in,
                n_out=n_out,
                per_ticker_status=per_ticker_status,
            )

        return {"sender": "candidate_handoff_guard"}

    return candidate_handoff_guard_node
```

- [ ] **Step 8.4: Wire the new node into the graph**

In `PortfolioGraphSetup.build_graph` (around line 986), add:

```python
workflow.add_node("candidate_handoff_guard", self._make_candidate_handoff_guard_node())
```

And change the edge from `prioritize_candidates` to go through the guard:

```python
# Before (line 1011):
# workflow.add_edge("prioritize_candidates", "macro_summary")
# workflow.add_edge("prioritize_candidates", "micro_summary")

# After:
workflow.add_edge("prioritize_candidates", "candidate_handoff_guard")
workflow.add_edge("candidate_handoff_guard", "macro_summary")
workflow.add_edge("candidate_handoff_guard", "micro_summary")
```

Also update the docstring comment at line 4-8 of the file to add `candidate_handoff_guard` to the flow:

```
START → load_portfolio → compute_risk → portfolio_integrity_guard → review_holdings
      → prioritize_candidates → candidate_handoff_guard → macro_summary (parallel)
                                                         → micro_summary  (parallel)
      → make_pm_decision → rescale_buys → cash_sweep → pm_decision_postcheck
      → execute_trades → record_pm_decisions → END
```

- [ ] **Step 8.5: Run guard tests**

```
pytest tests/portfolio/test_candidate_handoff_guard.py -v
```

Expected: all PASS.

- [ ] **Step 8.6: Commit**

```bash
git add tradingagents/graph/portfolio_setup.py tests/portfolio/test_candidate_handoff_guard.py
git commit -m "feat: add candidate_handoff_guard_node to portfolio graph after prioritize_candidates"
```

---

## Task 9: Smoke test — guard is wired in graph and existing snapshots pass

**Files:**
- Modify: `tests/graph/test_portfolio_decision_snapshot.py`
- Modify: `tests/portfolio/test_portfolio_setup.py`

- [ ] **Step 9.1: Add wiring smoke test**

In `tests/portfolio/test_portfolio_setup.py`, add:

```python
def test_candidate_handoff_guard_is_in_graph():
    """Verify candidate_handoff_guard node is wired between prioritize_candidates and summaries."""
    from unittest.mock import MagicMock
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup

    setup = PortfolioGraphSetup(
        agents={
            "review_holdings": MagicMock(),
            "macro_summary": MagicMock(),
            "micro_summary": MagicMock(),
            "pm_decision": MagicMock(),
        },
        repo=None,
        config={},
        macro_memory=None,
        micro_memory=None,
    )
    graph = setup.build_graph()
    # LangGraph graphs expose their nodes via the nodes attribute or graph dict
    node_names = set(graph.nodes.keys()) if hasattr(graph, "nodes") else set()
    assert "candidate_handoff_guard" in node_names, (
        "candidate_handoff_guard not found in portfolio graph nodes"
    )
```

- [ ] **Step 9.2: Run existing portfolio and graph tests**

```
pytest tests/portfolio/ tests/graph/ -v -m "not integration"
```

Expected: all PASS. If any snapshot test fails due to the new node being in the graph, update the snapshot — the topology changed intentionally.

- [ ] **Step 9.3: Commit**

```bash
git add tests/portfolio/test_portfolio_setup.py tests/graph/test_portfolio_decision_snapshot.py
git commit -m "test: verify candidate_handoff_guard wired in portfolio graph"
```

---

## Task 10: Full suite run and telemetry wiring

**Files:**
- Modify: `tradingagents/agents/utils/output_validation.py` — optional telemetry hook
- Modify: `tradingagents/graph/portfolio_setup.py` — optional telemetry in guard

The design spec (§8) calls for two telemetry events:
- `action_extraction_llm_fallback` — when regex misses and LLM rescues
- `action_extraction_failed` — when both fail
- `candidate_handoff_ok` / `candidate_handoff_failed` — from the guard

These use `RunLogger.log_warning(node, ticker, message, details)` from `tradingagents.observability`. However, `_extract_action_llm` and `extract_action` are utility functions that don't have access to `run_id` or `ticker`. The telemetry should be emitted by the callers (`build_*_structured` and the guard node), which do have state context.

- [ ] **Step 10.1: Add telemetry log call in `build_final_decision_structured`**

In the `extraction_failed` catch block of `build_final_decision_structured`:

```python
except ActionExtractionError as exc:
    action = None
    status = "extraction_failed"
    abort_reason = f"action_extraction_failed: {exc.text_excerpt}"
    logger.warning(
        "build_final_decision_structured: action extraction failed for ticker=%s excerpt=%r",
        ticker,
        exc.text_excerpt,
    )
```

The `logger` is already at module level (`logger = logging.getLogger(__name__)`). No new import needed.

Add analogous `logger.warning` calls to the other three builders on the `extraction_failed` path.

- [ ] **Step 10.2: Add `candidate_handoff_ok` logging in the guard node**

In `candidate_handoff_guard_node` just before the final `return`:

```python
logger.info(
    "candidate_handoff_guard: ok n_in=%d n_out=%d n_extraction_failed=%d n_not_buy=%d",
    n_in, n_out, n_extr_fail, n_not_buy,
)
```

The `logger` in `portfolio_setup.py` is already at module level.

- [ ] **Step 10.3: Run the full test suite**

```
pytest tests/ -v -m "not integration" -x
```

Expected: all PASS.

- [ ] **Step 10.4: Commit**

```bash
git add tradingagents/agents/utils/output_validation.py tradingagents/graph/portfolio_setup.py
git commit -m "feat: add telemetry logging to extraction failure paths and handoff guard"
```

---

## Task 11: Final verification

- [ ] **Step 11.1: Run the full non-integration suite**

```
pytest tests/ -v -m "not integration"
```

Expected: all PASS. Note total count before and after — the new tests should add roughly 30-40 new passing cases.

- [ ] **Step 11.2: Check no `_infer_recommendation` call sites accidentally bypass the new path**

```bash
grep -rn "_infer_recommendation\|extract_action" tradingagents/ --include="*.py" | grep -v "__pycache__"
```

Verify: `_infer_recommendation` appears only in its definition and the four `build_*_structured` bodies (as the internal call). All four `build_*_structured` should now call it with `llm=llm`. No other code should call `_infer_recommendation` directly.

- [ ] **Step 11.3: Check the old silent HOLD default is gone**

```bash
grep -n 'return "HOLD"' tradingagents/agents/utils/output_validation.py
```

Expected: 0 hits in `_infer_recommendation`. (The `empty` and `timeout_fallback` branches still return `"HOLD"` as a structural default — that is intentional and expected.)

- [ ] **Step 11.4: Verify `CandidateHandoffError` imports cleanly from `output_validation`**

```bash
python -c "from tradingagents.agents.utils.output_validation import CandidateHandoffError, ActionExtractionError, ExtractionResult, extract_action; print('OK')"
```

Expected: `OK`.

- [ ] **Step 11.5: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup — robust action extraction + candidate handoff guard complete"
```

---

## Post-implementation verification checklist

After landing this change, re-run the audited 2026-05-01 portfolio job:

1. `prioritized_candidates` now contains OWL and TEAM.
2. `candidate_handoff_ok` log event appears with `n_in=2, n_out=2`.
3. Portfolio PM deploys capital instead of abstaining.

Negative-path check: synthetically set one ticker's `final_trade_decision_structured.status = "extraction_failed"` and re-run. Verify:
- The other ticker still flows through.
- `logger.warning` fires for the failed ticker.
- Guard does not raise (partial failure is allowed).

Watch `action_extraction_llm_fallback` telemetry on next 1-2 production runs. If it fires on every run, escalate to the (c) follow-up: require explicit `RECOMMENDATION_LINE` in upstream prompts.

---

## Self-review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §5.1 ExtractionResult | Task 1 |
| §5.2 ActionExtractionError | Task 1 |
| §5.3 _extract_action_regex | Task 2 |
| §5.4 _extract_action_llm | Task 3 |
| §5.5 extract_action | Task 4 |
| §5.6 _infer_recommendation shim | Task 5 |
| §6 caller updates | Tasks 6-7 |
| §7.4 portfolio PM entry guard | Task 8 |
| §7.1 per-ticker exclusion | Task 6 (extraction_failed status → naturally excluded) |
| §8 telemetry | Task 10 |
| §9.1 regex tests | Task 2 |
| §9.2 LLM tests | Task 3 |
| §9.3 integration tests | Task 4 |
| §9.4 guard tests | Task 8 |
| §9.5 existing test updates | Tasks 5-6 |
| CandidateHandoffError | Task 1 |
| §10 migration/rollout | Task 11 |

**Placeholder scan:** None detected.

**Type consistency:**
- `ExtractionResult` used in `_extract_action_regex` → `extract_action` → `_infer_recommendation` → builders: consistent.
- `CandidateHandoffError` defined in `output_validation.py`, imported in `portfolio_setup.py`: consistent.
- Field names: `recommendation` (RM), `final_action` (trader), `consensus_direction` (risk), `action` (PM): match existing dict keys in each builder's return.
