"""Helpers for extracting and verifying evidence citations in text."""

from __future__ import annotations

import re

from tradingagents.evidence.ledger import EvidenceLedger
from tradingagents.evidence.models import CitationVerificationResult

# Ledger aliases are lookup handles. Only handles that look like EVD-* are
# parsed as citation tokens from free text.
_CITATION_RE = re.compile(r"\bEVD-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")


def extract_citation_refs(text: str) -> list[str]:
    return _CITATION_RE.findall(text)


def verify_citations(
    text: str,
    ledger: EvidenceLedger,
    require_citation: bool = False,
) -> CitationVerificationResult:
    refs = extract_citation_refs(text)
    cited_ids: list[str] = []
    unknown_ids: list[str] = []
    warnings: list[str] = []

    for ref in refs:
        resolved = ledger.resolve(ref)
        if resolved is None:
            cited_ids.append(ref)
            unknown_ids.append(ref)
            warnings.append(f"Unknown evidence citation: {ref}")
        else:
            cited_ids.append(resolved)

    missing_required = require_citation and not refs
    if missing_required:
        warnings.append("Citation required but none found.")

    return CitationVerificationResult(
        passed=not unknown_ids and not missing_required,
        cited_ids=cited_ids,
        unknown_ids=unknown_ids,
        missing_required=missing_required,
        warnings=warnings,
    )
