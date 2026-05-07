"""RM consistency guard: structural claim extraction + LLM-as-judge verification."""

from __future__ import annotations

import json
import re
from typing import Any

import logging

_logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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

Output schema (strictly enforced):
- Return exactly one result per claim, indexed 0 to claim_count-1 (claim_count is provided in the input)
- "ok" must be a JSON boolean: true or false (never the string "true" or "false")
- "reason" is required and must be non-empty when ok is false; omit it when ok is true
- No duplicate or missing indexes

Respond with ONLY valid JSON, no prose:
{"results": [{"index": 0, "ok": true}, {"index": 1, "ok": false, "reason": "..."}]}"""

_REPAIR_TEMPLATE = """\
Your previous response did not satisfy the required schema: {error}

Return exactly {n} result(s) — one per claim, indexes 0 to {last}:
- "ok" must be JSON boolean true or false (not a string)
- "reason" must be non-empty when ok is false
- No duplicate or missing indexes

Respond with ONLY valid JSON."""


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


def _parse_and_validate(raw: str, claim_count: int) -> list[dict[str, Any]]:
    """Parse raw LLM output and validate schema. Raises ValueError on any problem."""
    try:
        parsed = extract_json(raw)
    except Exception as exc:
        raise ValueError(
            f"rm_consistency_guard: LLM response is not valid JSON — {raw[:300]}"
        ) from exc

    if not isinstance(parsed, dict) or "results" not in parsed:
        raise ValueError(f"rm_consistency_guard: LLM response missing 'results' key — {raw[:300]}")

    results = parsed["results"]
    if not isinstance(results, list):
        raise ValueError(f"rm_consistency_guard: 'results' is not a list — {raw[:300]}")

    index_map: dict[int, dict[str, Any]] = {}
    schema_errors: list[str] = []

    for i, r in enumerate(results):
        if not isinstance(r, dict):
            schema_errors.append(f"result[{i}] is not a dict")
            continue
        idx = r.get("index")
        if type(idx) is not int or not (0 <= idx < claim_count):
            schema_errors.append(f"result[{i}] has invalid index {idx!r}")
            continue
        if idx in index_map:
            schema_errors.append(f"duplicate index {idx}")
            continue
        ok = r.get("ok")
        if not isinstance(ok, bool):
            schema_errors.append(f"result[{idx}] has non-bool ok: {ok!r}")
            continue
        reason = r.get("reason", "")
        if not ok and (not isinstance(reason, str) or not reason.strip()):
            schema_errors.append(f"result[{idx}] is ok=False but has no reason")
            continue
        index_map[idx] = r

    missing = [i for i in range(claim_count) if i not in index_map]
    if missing:
        schema_errors.append(f"missing verdicts for claim indexes: {missing}")

    if schema_errors:
        raise ValueError(
            f"rm_consistency_guard: malformed judge response — {'; '.join(schema_errors)} — {raw[:200]}"
        )

    return [index_map[i] for i in range(claim_count)]


def check_claims_via_llm(
    claims: list[str],
    fundamentals: str,
    llm: Any,
) -> list[dict[str, Any]]:
    """Verdict each claim against fundamentals via a single LLM call with one schema retry.

    Returns one {index, ok, reason?} dict per claim in index order.
    On schema errors, retries once with a repair prompt before raising ValueError.
    Raises ValueError if the response is unparseable, timed out, or fails schema
    validation after both attempts.
    """
    if not claims:
        return []

    payload = json.dumps(
        {"claim_count": len(claims), "claims": claims, "fundamentals": fundamentals},
        ensure_ascii=False,
    )
    messages: list[Any] = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=payload)]
    timeout = resolve_timeout("quick")

    response, invoke_error = invoke_with_timeout(llm, messages, timeout_seconds=timeout)
    if invoke_error is not None or response is None:
        raise ValueError(f"rm_consistency_guard: LLM judge call failed — {invoke_error}")
    raw = response.content if hasattr(response, "content") else str(response)

    try:
        return _parse_and_validate(raw, len(claims))
    except ValueError as first_err:
        repair_prompt = _REPAIR_TEMPLATE.format(
            error=first_err,
            n=len(claims),
            last=len(claims) - 1,
        )
        repair_messages = messages + [AIMessage(content=raw), HumanMessage(content=repair_prompt)]
        response2, invoke_error2 = invoke_with_timeout(
            llm, repair_messages, timeout_seconds=timeout
        )
        if invoke_error2 is not None or response2 is None:
            raise ValueError(
                f"rm_consistency_guard: repair retry failed — {invoke_error2}"
            ) from first_err
        raw2 = response2.content if hasattr(response2, "content") else str(response2)
        return _parse_and_validate(raw2, len(claims))


# ---------------------------------------------------------------------------
# Research Packet Summary Generation
# ---------------------------------------------------------------------------

_RATING_RE = re.compile(r"Rating:\s*(BUY|SELL|HOLD|STRONG\s*BUY|STRONG\s*SELL)", re.IGNORECASE)
_CONFIDENCE_RE = re.compile(r"Confidence:\s*([\d.]+%?)", re.IGNORECASE)
_ENTRY_PRICE_RE = re.compile(r"Entry\s*Price:\s*\$?([\d,.]+)", re.IGNORECASE)
_TARGET_PRICE_RE = re.compile(r"Target\s*Price:\s*\$?([\d,.]+)", re.IGNORECASE)
_BULL_SECTION_RE = re.compile(
    r"Bull\s*Points?:\s*\n((?:\s*\d+\.\s*.+\n?)+)", re.IGNORECASE
)
_BEAR_SECTION_RE = re.compile(
    r"Bear\s*Points?:\s*\n((?:\s*\d+\.\s*.+\n?)+)", re.IGNORECASE
)
_NUMBERED_ITEM_RE = re.compile(r"\d+\.\s*(.+)")


def generate_research_packet_summary(
    *,
    ticker: str,
    trade_date: str,
    investment_plan: str,
    fundamentals_report: str,
) -> str:
    """Generate a 200-500 char structured summary of the research packet.

    Contains: ticker, trade_date, top bull points (with numbers),
    top bear points (with numbers), final RM rating, confidence score,
    entry price, target price.

    Returns empty string if inputs are insufficient.
    """
    if not investment_plan or not investment_plan.strip():
        return ""

    # Extract rating
    rating_m = _RATING_RE.search(investment_plan)
    if not rating_m:
        return ""
    rating = rating_m.group(1).strip().upper()

    # Extract confidence
    confidence_m = _CONFIDENCE_RE.search(investment_plan)
    confidence = confidence_m.group(1).strip() if confidence_m else "N/A"

    # Extract entry/target price
    entry_m = _ENTRY_PRICE_RE.search(investment_plan)
    target_m = _TARGET_PRICE_RE.search(investment_plan)
    if not entry_m or not target_m:
        return ""
    entry_price = entry_m.group(1).strip()
    target_price = target_m.group(1).strip()

    # Extract bull points
    bull_section_m = _BULL_SECTION_RE.search(investment_plan)
    if not bull_section_m:
        return ""
    bull_items = _NUMBERED_ITEM_RE.findall(bull_section_m.group(1))
    if not bull_items:
        return ""

    # Extract bear points
    bear_section_m = _BEAR_SECTION_RE.search(investment_plan)
    if not bear_section_m:
        return ""
    bear_items = _NUMBERED_ITEM_RE.findall(bear_section_m.group(1))
    if not bear_items:
        return ""

    # Build summary
    header = f"{ticker} | {trade_date} | Rating: {rating} | Confidence: {confidence}"
    bull_line = "Bull: " + "; ".join(item.strip() for item in bull_items[:3])
    bear_line = "Bear: " + "; ".join(item.strip() for item in bear_items[:3])
    price_line = f"Entry: ${entry_price} | Target: ${target_price}"

    summary = f"{header}\n{bull_line}\n{bear_line}\n{price_line}"

    # Enforce length bounds: 200-500 characters
    if len(summary) < 200:
        # Pad with additional context if available — try adding more bull/bear points
        extra_bulls = bull_items[3:6]
        extra_bears = bear_items[3:6]
        if extra_bulls:
            bull_line = "Bull: " + "; ".join(item.strip() for item in bull_items[:6])
        if extra_bears:
            bear_line = "Bear: " + "; ".join(item.strip() for item in bear_items[:6])
        summary = f"{header}\n{bull_line}\n{bear_line}\n{price_line}"

    if len(summary) < 200:
        # Still too short — pad with fundamentals snippet
        remaining = 200 - len(summary)
        snippet = fundamentals_report.strip()[:remaining]
        if snippet:
            summary = f"{summary}\nContext: {snippet}"

    if len(summary) < 200:
        # Pad with spaces to meet minimum (last resort)
        summary = summary + " " * (200 - len(summary))

    if len(summary) > 500:
        # Truncate to 497 chars + ellipsis
        summary = summary[:497] + "..."

    return summary
