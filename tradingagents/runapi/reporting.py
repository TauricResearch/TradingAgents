"""Trusted report body/envelope rendering for the shared run boundary."""

from __future__ import annotations

from tradingagents.reporting import _report_parts

from .checks import DISCLAIMER, NO_PORTFOLIO_NOTICE, render_provenance


def render_body(final_state: dict, context, redactor) -> tuple[str, list]:
    """Render narrative once, then redact it before checks and publication."""
    parts = _report_parts(final_state)
    sections = []
    for heading, _folder, written in parts:
        content = "\n\n".join(f"### {agent}\n{text}" for agent, _name, text in written)
        sections.append(f"## {heading}\n\n{content}")
    chunks = []
    if context.mode.value == "NO_PORTFOLIO":
        chunks.append(f"> {NO_PORTFOLIO_NOTICE}")
    if sections:
        chunks.extend(sections)
    else:
        chunks.append("## Analysis\n\nNo report sections were returned by the analysis workflow.")
    chunks.append(f"## Disclaimer\n\n{DISCLAIMER}")
    return redactor.scrub("\n\n".join(chunks)), parts


def build_envelope(metadata: dict, run_outcome: str, stop_reason: str | None,
                   final_rating: str | None, output_check: str,
                   findings: tuple, redactor) -> str:
    provenance = render_provenance(metadata)
    lines = [
        f"# Trading Analysis Report: {metadata['ticker']}", "", provenance,
        f"- Run outcome: {run_outcome}",
    ]
    if stop_reason:
        lines.append(f"- Stop reason: {stop_reason}")
    if final_rating is not None:
        lines.append(f"- Final Portfolio Manager rating: {final_rating}")
    lines.append(f"- Output check: {output_check}")
    if findings:
        lines.append("- Findings:")
        lines.extend(f"  - {finding.rule}: {finding.detail}" for finding in findings)
    return redactor.scrub("\n".join(lines) + "\n\n")


def verify_envelope_header_matches(envelope: str, trusted: dict) -> bool:
    """Check each trusted provenance line appears unchanged in the envelope."""
    return all(line in envelope.splitlines() for line in render_provenance(trusted).splitlines())
