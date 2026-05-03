"""RM consistency guard: structural claim extraction + LLM-as-judge verification."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from tradingagents.agents.utils.json_utils import extract_json
from tradingagents.agents.utils.llm_guard import invoke_with_timeout, resolve_timeout

# Prefix format: - [HIGH] claim text  /  • (MED) claim text
_CLAIM_PREFIX_RE = re.compile(
    r"^\s*[-•*]\s*[\[\(](HIGH|MED|LOW)[\]\)]\s+(.+)",
    re.IGNORECASE | re.MULTILINE,
)

# Trailing format: - claim text [HIGH]  /  - claim text (MED)
_CLAIM_TRAILING_RE = re.compile(
    r"^\s*[-•*]\s+(.+?)\s+[\[\(](HIGH|MED|LOW)[\]\)]\s*$",
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

FUNDAMENTALS: "Q1 2025: $4.39B, Q2 2025: $4.55B, Q3 2025: $4.83B, Q4 2025: $6.13B"
CLAIM: "Revenue declined throughout 2025"
→ {"ok": false, "reason": "Fundamentals show revenue grew every quarter in 2025, not declined"}

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
    """Return claim strings from [HIGH]/[MED]/[LOW] bullet lines in RM investment plan.

    Handles both prefix format (- [HIGH] claim) and trailing format (- claim (HIGH)).
    Deduplicates while preserving order; prefix matches take priority.
    """
    seen: set[str] = set()
    claims: list[str] = []
    for m in _CLAIM_PREFIX_RE.finditer(rm_text):
        text = m.group(2).strip()
        if text not in seen:
            seen.add(text)
            claims.append(text)
    for m in _CLAIM_TRAILING_RE.finditer(rm_text):
        text = m.group(1).strip()
        if text not in seen:
            seen.add(text)
            claims.append(text)
    return claims


def check_claims_via_llm(
    claims: list[str],
    fundamentals: str,
    llm: Any,
) -> list[dict[str, Any]]:
    """Verdict each claim against fundamentals via a single LLM call.

    Returns only well-formed verdict entries: {index (int), ok (bool), reason (str if ok=False)}.
    Malformed entries (non-int index, non-bool ok, ok=False with empty reason) are dropped.
    Unvicted claims (no well-formed entry returned by LLM) are not included — callers treat
    absent claims as ok (fail-open for partial responses).
    Raises ValueError on unparseable or timed-out LLM response.
    """
    if not claims:
        return []

    payload = json.dumps({"claims": claims, "fundamentals": fundamentals}, ensure_ascii=False)
    timeout = resolve_timeout("quick")
    response, invoke_error = invoke_with_timeout(
        llm,
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=payload)],
        timeout_seconds=timeout,
    )
    if invoke_error is not None or response is None:
        raise ValueError(f"rm_consistency_guard: LLM judge call failed — {invoke_error}")
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

    well_formed: list[dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        idx = r.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(claims)):
            continue
        ok = r.get("ok")
        if not isinstance(ok, bool):
            continue
        if not ok and not str(r.get("reason", "")).strip():
            continue
        well_formed.append(r)

    return well_formed
