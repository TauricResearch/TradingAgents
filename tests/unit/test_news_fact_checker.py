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


def test_news_fact_checker_removes_unknown_source_bullets(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.news_fact_checker.NewsEvidenceStore",
        lambda: FakeEvidenceStore(_records()),
    )

    node = create_news_fact_checker()
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": """
        CSTM News Analysis - 2026-04-02
        - Reuters reported on 2026-04-02 that CSTM demand improved 8% and CSTM held pricing support at $48.02. [Evidence ID: art_reuters_001]
        - Scout Money reported on 2026-04-02 that CSTM faced undisclosed pressure despite CSTM strength at $48.02.
        - Bloomberg reported on 2026-04-01 that CSTM retained support while CSTM sentiment tracked $109.58 crude. [Evidence ID: art_bloomberg_001]
        """,
    }

    result = node(state)

    assert result["sender"] == "news_fact_checker"
    assert "Scout Money" not in result["news_report"]
    assert "Reuters reported" in result["news_report"]
    assert not result["news_report"].startswith("[CRITICAL ABORT]")


def test_news_fact_checker_aborts_when_only_fake_sourced_claims_remain(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.news_fact_checker.NewsEvidenceStore",
        lambda: FakeEvidenceStore(_records()),
    )

    node = create_news_fact_checker()
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": """
        CSTM News Analysis - 2026-04-02
        - Scout Money reported on 2026-04-02 that CSTM faced undisclosed pressure while CSTM traded near $48.02.
        - Macro Regime Classification reported on 2026-04-02 that CSTM should be avoided while CSTM remained sensitive to $109.58 crude.
        - Scout Money noted on 2026-04-01 that CSTM demand weakened 8% even as CSTM held support near $48.02.
        """,
    }

    result = node(state)

    assert result["sender"] == "news_fact_checker"
    assert result["news_report"].startswith("[CRITICAL ABORT]")
