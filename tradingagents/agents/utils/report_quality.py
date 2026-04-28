"""Deterministic report quality assessment for scanner node outputs.

Pure functions — no LLM calls, no external services.  Used to tag scanner
reports with inline quality headers so downstream summarizers and synthesis
nodes can distinguish real evidence from placeholder/failed outputs.
"""

from __future__ import annotations

import re

# Phrases that indicate the report describes planned actions rather than
# observed data.
_PLACEHOLDER_PHRASES = (
    r"\bpending\b",
    r"\bawaiting\b",
    r"\bstand by\b",
    r"\bi will call\b",
    r"\bwill be retrieved\b",
    r"\bwill be fetched\b",
    r"\bno data provided\b",
    r"\bscanner tool pending\b",
    r"\blacks sufficient\b",
)

# Pre-compiled regex for all placeholder phrases with word boundaries
_PLACEHOLDER_RE = re.compile(
    "|".join(_PLACEHOLDER_PHRASES),
    re.IGNORECASE,
)

# Patterns indicating the model emitted a tool call as text rather than
# executing it through the structured tool-calling API.
_TOOL_CALL_TEXT_RE = re.compile(
    r"(?:"
    r'\{"(?:name|type)":\s*"(?:function|get_)'  # OpenAI-style JSON
    r"|get_\w+\("  # Python-style invocation
    r")",
)

# Counts numeric evidence tokens: dates (YYYY-MM-DD), percentages, dollar
# amounts, and plain numbers with decimal points.
_NUMERIC_EVIDENCE_RE = re.compile(
    r"(?:"
    r"\d{4}-\d{2}-\d{2}"  # dates
    r"|[+-]?\d+\.?\d*%"  # percentages
    r"|\$[\d,]+\.?\d*"  # dollar amounts
    r"|(?<!\w)\d+\.\d+(?!\w)"  # decimal numbers
    r")",
)

# Minimum report length (chars) below which a scanner report is "empty".
_MIN_SCANNER_LENGTH = 100

# The structured prefix emitted by tool_runner when tools are required but
# none succeeded.
_INSUFFICIENT_EVIDENCE_PREFIX = "[INSUFFICIENT_EVIDENCE]"


def assess_report_quality(
    text: str,
    *,
    node_name: str = "",
    requires_tools: bool = True,
) -> dict:
    """Assess the quality of a scanner node report.

    Returns a dict with:
        quality: "ok" | "degraded" | "empty"
        issues: list of string issue codes
        evidence_count: count of numeric evidence tokens found
    """
    issues: list[str] = []

    if not text or not text.strip():
        return {"quality": "empty", "issues": ["no_output"], "evidence_count": 0}

    stripped = text.strip()

    # Check for structured insufficient-evidence marker from tool_runner.
    # Some nodes add provenance around the model body; the marker must still
    # dominate quality assessment so scan dates are not misread as evidence.
    if _INSUFFICIENT_EVIDENCE_PREFIX in stripped:
        return {
            "quality": "empty",
            "issues": ["insufficient_evidence_marker"],
            "evidence_count": 0,
        }

    # Check degenerate outputs
    if stripped in ("Completed.", "N/A", "Not available", "{}"):
        return {"quality": "empty", "issues": ["degenerate_output"], "evidence_count": 0}

    # Length check
    if len(stripped) < _MIN_SCANNER_LENGTH:
        issues.append("too_short")

    # Placeholder language
    if _PLACEHOLDER_RE.search(stripped):
        issues.append("placeholder_language")

    # Bare tool-call JSON in report text
    if _TOOL_CALL_TEXT_RE.search(stripped):
        issues.append("tool_call_as_text")

    # Count numeric evidence
    evidence_count = len(_NUMERIC_EVIDENCE_RE.findall(stripped))

    if requires_tools and evidence_count == 0:
        issues.append("no_numeric_evidence")

    # Determine quality level
    if "too_short" in issues and evidence_count == 0:
        quality = "empty"
    elif issues:
        quality = "degraded"
    else:
        quality = "ok"

    return {
        "quality": quality,
        "issues": issues,
        "evidence_count": evidence_count,
    }


def format_quality_header(
    assessment: dict,
    *,
    tools_used: str = "",
) -> str:
    """Format an inline quality header from an assessment dict.

    Example outputs:
        [QUALITY: ok | evidence=7 | tools=get_market_indices]
        [QUALITY: empty | issues=no_tool_results,placeholder_language | evidence=0]
    """
    parts = [f"QUALITY: {assessment['quality']}"]

    if assessment.get("issues"):
        parts.append(f"issues={','.join(assessment['issues'])}")

    parts.append(f"evidence={assessment['evidence_count']}")

    if tools_used:
        parts.append(f"tools={tools_used}")

    return "[" + " | ".join(parts) + "]"


def tag_report(report: str, *, node_name: str = "", tools_used: str = "") -> str:
    """Assess a scanner report and prepend an inline quality header.

    Convenience wrapper that calls :func:`assess_report_quality` and
    :func:`format_quality_header`, returning the tagged report text.
    """
    assessment = assess_report_quality(report, node_name=node_name)
    header = format_quality_header(assessment, tools_used=tools_used)
    return f"{header}\n{report}"


def parse_quality_header(text: str) -> dict | None:
    """Parse an inline [QUALITY: ...] header from report text.

    Returns None if no header is found.
    """
    if not text:
        return None

    match = re.match(r"^\[QUALITY:\s*(\w+)\s*(?:\|.*)?\]", text.strip())
    if not match:
        return None

    quality = match.group(1)

    # Parse evidence count
    evidence_match = re.search(r"evidence=(\d+)", text)
    evidence_count = int(evidence_match.group(1)) if evidence_match else 0

    # Parse issues
    issues_match = re.search(r"issues=([^\]|]+)", text)
    issues = issues_match.group(1).strip().split(",") if issues_match else []

    return {
        "quality": quality,
        "issues": issues,
        "evidence_count": evidence_count,
    }
