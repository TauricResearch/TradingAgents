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
