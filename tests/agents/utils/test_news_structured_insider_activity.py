from tradingagents.agents.utils.output_validation import build_news_report_structured


def test_insider_activity_populated_with_buy_sell_claims():
    """insider_activity must reflect net insider position when claims contain buy/sell keywords."""
    payload = {
        "claims": [
            {
                "claim": "CEO John Smith bought 10,000 shares at $5.00",
                "source": "Reuters",
                "published_at": "2026-05-01",
                "evidence_id": "E001",
            },
            {
                "claim": "Director Jane Doe sold 5,000 shares at $6.00",
                "source": "Reuters",
                "published_at": "2026-05-02",
                "evidence_id": "E002",
            },
        ],
        "summary_table": [],
        "report_title": "TEST News Analysis",
    }
    result = build_news_report_structured(
        ticker="TEST",
        as_of_date="2026-05-05",
        payload=payload,
        status="completed",
    )
    assert result["status"] == "completed"
    insider = result.get("insider_activity")
    assert insider is not None, "insider_activity must be present when claims have insider events"
    assert insider["buy_shares"] == 10000
    assert insider["sell_shares"] == 5000
    assert insider["net_shares"] == 5000
    assert insider["bias"] == "bullish"


def test_insider_activity_none_when_no_insider_claims():
    """insider_activity must be None when no insider events in claims."""
    payload = {
        "claims": [
            {
                "claim": "Company reports quarterly earnings beat.",
                "source": "Reuters",
                "published_at": "2026-05-01",
                "evidence_id": "E001",
            },
        ],
        "summary_table": [],
    }
    result = build_news_report_structured(
        ticker="TEST",
        as_of_date="2026-05-05",
        payload=payload,
        status="completed",
    )
    assert result.get("insider_activity") is None
