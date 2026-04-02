"""Scanner Report Summarizer Node.

Pure-reasoning LLM node that compresses raw scanner reports into clinical
summaries using the SCANNER_REPORT_SUMMARY ruleset.
"""

from __future__ import annotations

import logging
from tradingagents.agents.managers.summary_rules import (
    SCANNER_REPORT_SUMMARY,
    generate_summary_prompt,
)

logger = logging.getLogger(__name__)


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


def create_scanner_summarizer(llm, report_key: str, summary_key: str):
    """Create a node that summarizes a specific scanner report.

    Args:
        llm: LangChain chat model.
        report_key: The key in the state containing the raw report.
        summary_key: The key in the state to store the summary.
    """

    def summarizer_node(state: dict) -> dict:
        raw_report = state.get(report_key, "")
        if not raw_report or raw_report == "Not available":
            return {summary_key: "No data available for summarization."}

        prompt = _build_scanner_summary_prompt(report_key, raw_report)

        result = llm.invoke(prompt)
        summary = result.content or ""

        return {
            summary_key: summary,
            "sender": f"summarizer_{report_key}",
        }

    return summarizer_node
