from unittest.mock import MagicMock, patch

import pytest


def _make_payload(claims: list[dict]) -> dict:
    return {"claims": claims, "summary": "test", "ticker": "AAPL", "date": "2026-05-05"}


def test_surviving_claims_have_verified_true():
    """Claims that pass sanitization must have verified set to True."""
    from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
    from tradingagents.memory.news_evidence import NewsEvidenceRecord, NewsEvidenceStore

    store = MagicMock(spec=NewsEvidenceStore)
    store.fetch_records.return_value = [
        MagicMock(
            spec=NewsEvidenceRecord,
            evidence_id="ev-001",
            source="MarketWatch",
            ticker="AAPL",
        )
    ]

    payload = _make_payload(
        [
            {
                "claim": "AAPL reported earnings beat",
                "evidence_id": "ev-001",
                "source": "MarketWatch",
                "published_at": "2026-05-05",
                "verified": None,
                "flagged": None,
            }
        ]
    )

    state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-05",
        "run_id": "RUN1",
        "news_report": "AAPL earnings beat.",
        "news_report_structured": payload,
        "abort_signal": None,
    }

    with patch(
        "tradingagents.agents.managers.news_fact_checker.sanitize_structured_news_payload",
        return_value=(payload, []),
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.validate_structured_news_payload",
        return_value=MagicMock(is_valid=True, payload=payload, code="ok", reason=""),
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.render_structured_news_payload",
        return_value="AAPL earnings beat.",
    ), patch(
        "tradingagents.agents.managers.news_fact_checker.validate_news_analysis_detailed",
        return_value=MagicMock(is_valid=True),
    ):
        node = create_news_fact_checker(MagicMock(), store)
        result = node(state)

    structured = result.get("news_report_structured") or {}
    claims = structured.get("claims") or []
    assert len(claims) == 1, f"expected 1 claim, got {len(claims)}"
    assert claims[0].get("verified") is True, (
        f"expected verified=True, got {claims[0].get('verified')!r}"
    )
