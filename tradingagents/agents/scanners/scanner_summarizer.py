"""Scanner Report Summarizer Node.

Pure-reasoning LLM node that compresses raw scanner reports into clinical
summaries using the SCANNER_REPORT_SUMMARY ruleset.

Quality-aware: reports tagged with ``[QUALITY: empty]`` or
``[QUALITY: degraded]`` with zero evidence are short-circuited to a
deterministic ``[NO_EVIDENCE]`` marker without invoking the LLM.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from tradingagents.agents.managers.summary_rules import (
    SCANNER_REPORT_SUMMARY,
    generate_summary_prompt,
)
from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.agents.utils.report_quality import parse_quality_header
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    require_scan_context,
    save_node_report,
)
from tradingagents.agents.utils.scanner_states import ScannerState
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

# Degenerate outputs that should bypass the LLM entirely.
_DEGENERATE_OUTPUTS = frozenset({
    "Completed.",
    "N/A",
    "Not available",
    "{}",
})


def _build_scanner_summary_prompt(report_key: str, raw_report: str) -> str:
    prompt = generate_summary_prompt(SCANNER_REPORT_SUMMARY, raw_report)
    report_label = report_key.replace("_report", "").replace("_", " ").strip() or report_key
    return (
        "You are a Senior Quantitative Economist.\n"
        "Your persona is objective, data-dense, and clinically precise.\n"
        "Discard all conversational filler and roleplay elements from the input.\n\n"
        f"Scanner source: {report_label}.\n"
        "Write for downstream machine reuse, not for standalone human readability.\n"
        "Formatting requirements:\n"
        "- Use bullets only.\n"
        "- Prefer `TICKER | sector | signal | exact evidence | implication` rows.\n"
        "- For sector or macro reports, prefer `SECTOR/THEME | exact evidence | implication` rows.\n"
        "- Preserve dates exactly as written.\n"
        "- Preserve rankings, percentages, price levels, and conviction-like wording when present.\n\n"
        + prompt
    )


def create_scanner_summarizer(llm: Any, report_key: str, summary_key: str) -> Callable[[ScannerState], dict[str, Any]]:
    """Create a node that summarizes a specific scanner report.

    Args:
        llm: LangChain chat model.
        report_key: The key in the state containing the raw report.
        summary_key: The key in the state to store the summary.
    """

    def summarizer_node(state: ScannerState) -> dict[str, Any]:
        require_scan_context(state, node_name=f"summarizer_{report_key}")

        # 1. Idempotency Check
        existing_summary = check_and_load_report(state, summary_key)
        if existing_summary and existing_summary != "No data available for summarization.":
            return {
                summary_key: existing_summary,
                "sender": f"summarizer_{report_key}",
            }

        raw_report = state.get(report_key, "")
        report_label = report_key.replace("_report", "").replace("_", " ").strip() or report_key

        # Gate: skip LLM for empty, degenerate, or quality-tagged-empty reports.
        if not raw_report or raw_report.strip() in _DEGENERATE_OUTPUTS:
            raise RuntimeError(
                f"Summarizer missing usable upstream report for {report_key}; "
                "refusing to synthesize without graph evidence."
            )

        quality = parse_quality_header(raw_report)
        if quality and (
            quality["quality"] == "empty"
            or (quality["quality"] == "degraded" and quality["evidence_count"] == 0)
        ):
            issues = ", ".join(quality.get("issues", [])) or "unknown"
            no_ev = f"[NO_EVIDENCE] Source: {report_label}. Upstream quality: {quality['quality']} ({issues}). Exclude from synthesis."
            logger.info("Summarizer skipping LLM for %s: quality=%s", report_key, quality["quality"])
            return {summary_key: no_ev, "sender": f"summarizer_{report_key}"}

        prompt = _build_scanner_summary_prompt(report_key, raw_report)

        _summarizer_timeout = float(DEFAULT_CONFIG.get("scanner_summarizer_timeout") or 180.0)
        result, invoke_error = invoke_with_timeout(
            llm=llm,
            prompt_or_messages=prompt,
            timeout_seconds=_summarizer_timeout,
        )
        if invoke_error is not None:
            raise RuntimeError(
                f"Summarizer invoke failed for {report_key}: "
                f"{type(invoke_error).__name__}: {invoke_error}"
            ) from invoke_error

        summary = result.content or ""
        if not str(summary).strip():
            raise RuntimeError(
                f"Summarizer produced empty output for {report_key}; refusing fallback persistence."
            )

        # 3. Resumability: Save after completion
        if summary:
            save_node_report(state, summary_key, summary)

        return {
            summary_key: summary,
            "sender": f"summarizer_{report_key}",
        }

    return summarizer_node
