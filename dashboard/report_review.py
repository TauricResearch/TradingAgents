from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DASHBOARD_DISCLAIMER = (
    "This dashboard is for research and education only. It is not investment advice, "
    "a recommendation, an offer, or a solicitation to buy or sell securities. "
    "IndiaMarketAgents is not a SEBI-registered investment adviser or research analyst. "
    "Verify all data with official exchange/company filings and consult a qualified adviser before acting."
)

UNAVAILABLE_SECTION = "UNAVAILABLE: This report artifact was not found in the saved report bundle."


@dataclass(frozen=True)
class ReportArtifact:
    label: str
    filename: str
    kind: str = "markdown"
    companion_files: tuple[str, ...] = ()


REPORT_ARTIFACTS: tuple[ReportArtifact, ...] = (
    ReportArtifact("Complete", "complete_report.md"),
    ReportArtifact("Technical", "1_market_technical.md"),
    ReportArtifact("Fundamentals", "2_fundamentals.md"),
    ReportArtifact("News/Filings", "3_news_filings.md"),
    ReportArtifact("Macro/Policy", "4_macro_policy.md"),
    ReportArtifact("Flows", "5_flows_positioning.md"),
    ReportArtifact("Sentiment", "6_sentiment.md"),
    ReportArtifact("Research Debate", "7_research_debate.md"),
    ReportArtifact("Trader Research View", "trader_research_view.md"),
    ReportArtifact("Risk/Compliance", "8_risk.md", companion_files=("compliance.md", "disclaimer.md")),
    ReportArtifact("Portfolio Research View", "9_portfolio_decision.md"),
    ReportArtifact("Sources", "sources.md"),
    ReportArtifact("Data Quality", "data_quality.json", kind="data_quality_json"),
)


def report_root() -> Path:
    return Path("reports")


def list_symbols(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def list_dates(root: Path, symbol: str) -> list[str]:
    base = root / symbol
    if not base.exists():
        return []
    return sorted((path.name for path in base.iterdir() if path.is_dir()), reverse=True)


def report_bundle_path(root: Path, symbol: str, date: str) -> Path:
    return root / symbol / date


def read_text_artifact(path: Path) -> str:
    if not path.exists():
        return UNAVAILABLE_SECTION
    return path.read_text(encoding="utf-8", errors="replace")


def read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "UNAVAILABLE",
            "warning": "Saved JSON artifact could not be parsed.",
        }


def render_markdown_artifact(base: Path, artifact: ReportArtifact) -> str:
    parts = [read_text_artifact(base / artifact.filename)]
    for companion in artifact.companion_files:
        parts.append(read_text_artifact(base / companion))
    return "\n\n".join(part for part in parts if part)


def format_data_quality_markdown(data: dict[str, Any]) -> str:
    if not data:
        return "# Data Quality\n\nUNAVAILABLE: data_quality.json was not found in the saved report bundle."

    sections = data.get("sections") or {}
    lines = [
        "# Data Quality",
        "",
        f"- Symbol: {data.get('symbol', 'unknown')}",
        f"- Market scope: {data.get('market_scope', 'unknown')}",
        f"- Generated at: {data.get('generated_at', 'unknown')}",
        f"- Coverage method: {data.get('coverage_method', 'unknown')}",
        "",
        "| Section | Status | Source coverage | Data quality | Confidence | UNAVAILABLE marker |",
        "|---|---|---|---|---|---|",
    ]
    for title, record in sections.items():
        lines.append(
            "| {title} | {status} | {source} | {quality} | {confidence} | {unavailable} |".format(
                title=title,
                status=record.get("status", "unknown"),
                source=_yes_no(record.get("source_coverage_detected")),
                quality=_yes_no(record.get("data_quality_detected")),
                confidence=_yes_no(record.get("confidence_detected")),
                unavailable=_yes_no(record.get("contains_unavailable_marker")),
            )
        )

    limitations = data.get("limitations") or []
    if limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {limitation}" for limitation in limitations)

    warnings = _collect_section_warnings(sections)
    if warnings:
        lines.extend(["", "## Coverage Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    return "\n".join(lines)


def _yes_no(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def _collect_section_warnings(sections: dict[str, Any]) -> list[str]:
    warnings = []
    for title, record in sections.items():
        for warning in record.get("warnings") or []:
            warnings.append(f"{title}: {warning}")
    return warnings
