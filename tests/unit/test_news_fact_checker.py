from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
from tradingagents.memory.news_evidence import NewsEvidenceRecord


class FakeEvidenceStore:
    def __init__(self, records):
        self.records = records

    def fetch_records(self, *, run_id, ticker, trade_date=None):
        return self.records


def _records():
    return [
        NewsEvidenceRecord(
            run_id="run-001",
            evidence_id="art_reuters_001",
            ticker="CSTM",
            trade_date="2026-04-02",
            section_label="Company-Specific News (Last 7 Days)",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-02",
            title="CSTM company article",
            url="https://example.com/reuters",
            summary="Summary",
            raw_json="{}",
        ),
        NewsEvidenceRecord(
            run_id="run-001",
            evidence_id="art_bloomberg_001",
            ticker="CSTM",
            trade_date="2026-04-02",
            section_label="Company-Specific News (Last 7 Days)",
            ordinal=2,
            source="Bloomberg",
            published_at="2026-04-01",
            title="CSTM second article",
            url="https://example.com/bloomberg",
            summary="Summary",
            raw_json="{}",
        ),
    ]


def test_news_fact_checker_removes_unsupported_structured_claims():
    node = create_news_fact_checker(evidence_store=FakeEvidenceStore(_records()))
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": "CSTM News Analysis",
        "news_report_structured": {
            "ticker": "CSTM",
            "report_title": "CSTM News Analysis",
            "claims": [
                {
                    "claim": "CSTM demand improved 8% and CSTM held pricing support at $48.02.",
                    "source": "Reuters",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_reuters_001",
                },
                {
                    "claim": "CSTM faced undisclosed pressure despite CSTM strength at $48.02.",
                    "source": "Scout Money",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_fake_001",
                },
                {
                    "claim": "CSTM retained support while CSTM sentiment tracked $109.58 crude.",
                    "source": "Bloomberg",
                    "published_at": "2026-04-01",
                    "evidence_id": "art_bloomberg_001",
                },
            ],
            "summary_table": [],
        },
    }

    result = node(state)

    assert result["sender"] == "news_fact_checker"
    assert "Scout Money" not in result["news_report"]
    assert "[Source: Reuters | Published: 2026-04-02]" in result["news_report"]
    assert not result["news_report"].startswith("[CRITICAL ABORT]")


def test_news_fact_checker_returns_placeholder_when_only_fake_structured_claims_remain():
    node = create_news_fact_checker(evidence_store=FakeEvidenceStore(_records()))
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": "CSTM News Analysis",
        "news_report_structured": {
            "ticker": "CSTM",
            "report_title": "CSTM News Analysis",
            "claims": [
                {
                    "claim": "CSTM faced undisclosed pressure while CSTM traded near $48.02.",
                    "source": "Scout Money",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_fake_001",
                },
                {
                    "claim": "CSTM should be avoided while CSTM remained sensitive to $109.58 crude.",
                    "source": "Macro Regime Classification",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_fake_002",
                },
            ],
            "summary_table": [],
        },
    }

    result = node(state)

    assert result["sender"] == "news_fact_checker"
    assert not result["news_report"].startswith("[CRITICAL ABORT]")
    assert "No validated news claims remained" in result["news_report"]


def test_news_fact_checker_returns_structured_placeholder_when_payload_missing():
    node = create_news_fact_checker(evidence_store=FakeEvidenceStore(_records()))
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": "CSTM News Analysis",
        "news_report_structured": {},
    }

    result = node(state)

    structured = result["news_report_structured"]
    assert structured["ticker"] == "CSTM"
    assert structured["claims"] == []
    assert structured["summary_table"] == []
    assert structured["status"] == "missing_structured_payload"
    assert "No validated news claims were produced" in result["news_report"]


def test_news_fact_checker_returns_structured_placeholder_when_payload_invalid():
    node = create_news_fact_checker(evidence_store=FakeEvidenceStore(_records()))
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": "CSTM News Analysis",
        "news_report_structured": {
            "ticker": "OTHER",
            "report_title": "CSTM News Analysis",
            "claims": [
                {
                    "claim": "CSTM demand improved 8% and CSTM held pricing support at $48.02.",
                    "source": "Reuters",
                    "published_at": "2026-04-02",
                    "evidence_id": "art_reuters_001",
                }
            ],
            "summary_table": [],
        },
    }

    result = node(state)

    structured = result["news_report_structured"]
    assert structured["ticker"] == "CSTM"
    assert structured["claims"] == []
    assert structured["summary_table"] == []
    assert structured["status"] == "invalid_structured_payload"
    assert result["news_report"].startswith("[CRITICAL ABORT]")
