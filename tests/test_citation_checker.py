import pytest

from tradingagents.evidence import EvidenceLedger
from tradingagents.evidence.citation_checker import (
    extract_citation_refs,
    verify_citations,
)


@pytest.mark.unit
def test_extract_citation_refs_finds_evd_tokens_without_trailing_punctuation():
    text = "Revenue accelerated [EVD-ABC123], but margins lagged (EVD-MKT-202406)."

    assert extract_citation_refs(text) == ["EVD-ABC123", "EVD-MKT-202406"]


@pytest.mark.unit
def test_known_citation_passes_against_ledger():
    ledger = EvidenceLedger()
    ledger.register(
        source="market_data",
        title="NVDA June close",
        as_of_date="2024-06-01",
        payload={"close": 189.5},
        evidence_id="EVD-MKT-202406",
    )

    result = verify_citations("Close improved to 189.5. EVD-MKT-202406", ledger)

    assert result.passed is True
    assert result.cited_ids == ["EVD-MKT-202406"]
    assert result.unknown_ids == []
    assert result.missing_required is False
    assert result.warnings == []


@pytest.mark.unit
def test_unknown_citation_fails_and_warns():
    result = verify_citations(
        "Claim cites unavailable evidence EVD-UNKNOWN-1",
        EvidenceLedger(),
    )

    assert result.passed is False
    assert result.cited_ids == ["EVD-UNKNOWN-1"]
    assert result.unknown_ids == ["EVD-UNKNOWN-1"]
    assert result.missing_required is False
    assert result.warnings == ["Unknown evidence citation: EVD-UNKNOWN-1"]


@pytest.mark.unit
def test_require_citation_flags_missing_citations():
    result = verify_citations(
        "A high-impact claim with no evidence token.",
        EvidenceLedger(),
        require_citation=True,
    )

    assert result.passed is False
    assert result.cited_ids == []
    assert result.unknown_ids == []
    assert result.missing_required is True
    assert result.warnings == ["Citation required but none found."]


@pytest.mark.unit
def test_non_evd_aliases_resolve_but_are_not_citation_tokens_in_free_text():
    ledger = EvidenceLedger()
    ledger.register(
        source="filing",
        title="NVDA 10-K",
        as_of_date="2024-02-21",
        payload={"form": "10-K"},
        aliases=["latest-filing"],
        evidence_id="EVD-FILING-20240221",
    )

    result = verify_citations(
        "The latest-filing handle supports lookup but is not a citation.",
        ledger,
    )

    assert ledger.resolve("latest-filing") == "EVD-FILING-20240221"
    assert result.passed is True
    assert result.cited_ids == []
    assert result.warnings == []
