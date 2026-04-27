"""Unit tests for news fact-checker canonical contract normalization."""

from unittest.mock import MagicMock

from tradingagents.agents.managers.news_fact_checker import create_news_fact_checker
from tradingagents.agents.utils.critical_abort import raise_abort
from tradingagents.memory.news_evidence import NewsEvidenceRecord


class TestNewsFactCheckerCanonicalContract:
    """Test fact-checker branch coverage for canonical contract normalization."""

    def test_fact_checker_returns_completed_contract_after_sanitization(self):
        """Test fact-checker returns completed contract after successful sanitization."""
        # Mock evidence store with known records
        mock_store = MagicMock()
        mock_record = NewsEvidenceRecord(
            run_id="test_run",
            evidence_id="art_123",
            ticker="MRVL",
            trade_date="2026-04-10",
            section_label="Company News",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-10",
            title="Test Article",
            url="https://example.com/article",
            summary="Test summary",
            raw_json="{}",
        )
        mock_store.fetch_records.return_value = [mock_record]

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "MRVL",
            "trade_date": "2026-04-10",
            "news_report": "Some news report",
            "news_report_structured": {
                "ticker": "MRVL",
                "report_title": "MRVL News Analysis",
                "claims": [
                    {
                        "claim": "MRVL announced new product",
                        "source": "Reuters",
                        "published_at": "2026-04-10",
                        "evidence_id": "art_123",
                    }
                ],
                "summary_table": [],
            },
        }

        result = fact_checker(state)

        assert "news_report_structured" in result
        structured = result["news_report_structured"]
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "news_report_v1"
        assert structured["key_metrics"]["claim_count"] >= 0
        assert isinstance(structured["key_metrics"], dict)

    def test_fact_checker_aborts_when_all_claims_removed(self):
        """Test fact-checker raises structured abort when all claims are removed."""
        # Mock evidence store with records that do not support the submitted claim
        mock_store = MagicMock()
        mock_record = NewsEvidenceRecord(
            run_id="test_run",
            evidence_id="art_123",
            ticker="MRVL",
            trade_date="2026-04-10",
            section_label="Company News",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-10",
            title="Test Article",
            url="https://example.com/article",
            summary="Test summary",
            raw_json="{}",
        )
        mock_store.fetch_records.return_value = [mock_record]

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "MRVL",
            "trade_date": "2026-04-10",
            "news_report": "Some news report",
            "news_report_structured": {
                "ticker": "MRVL",
                "claims": [
                    {
                        "claim": "Unverified claim",
                        "source": "UnknownSource",
                        "published_at": "2026-04-10",
                        "evidence_id": "bad_id",
                    }
                ],
                "summary_table": [],
            },
        }

        result = fact_checker(state)

        assert result["abort_signal"]["source"] == "news_fact_checker"
        assert result["abort_signal"]["reason"] == "news_evidence_missing"
        assert "All structured claims were removed" in result["abort_signal"]["detail"]
        assert "news_report_structured" in result
        structured = result["news_report_structured"]
        assert structured["status"] == "aborted"
        assert structured["contract_version"] == "news_report_v1"

    def test_fact_checker_missing_payload_has_canonical_contract(self):
        """Test fact-checker returns canonical contract when payload is missing but evidence exists."""
        # Mock evidence store with records (so it doesn't return empty due to no evidence)
        mock_store = MagicMock()
        mock_record = NewsEvidenceRecord(
            run_id="test_run",
            evidence_id="art_456",
            ticker="MRVL",
            trade_date="2026-04-10",
            section_label="Company News",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-10",
            title="Test Article",
            url="https://example.com/article",
            summary="Test summary",
            raw_json="{}",
        )
        mock_store.fetch_records.return_value = [mock_record]

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "MRVL",
            "trade_date": "2026-04-10",
            "news_report": "Some report",
            "news_report_structured": None,  # Missing
        }

        result = fact_checker(state)

        assert result["abort_signal"]["source"] == "news_fact_checker"
        assert result["abort_signal"]["reason"] == "news_schema_invalid"
        assert "No structured payload" in result["abort_signal"]["detail"]
        assert "news_report_structured" in result
        structured = result["news_report_structured"]
        assert structured["status"] == "aborted"
        assert structured["contract_version"] == "news_report_v1"

    def test_fact_checker_invalid_payload_has_canonical_contract(self):
        """Test fact-checker returns canonical contract for invalid payload without critical abort."""
        # Provide evidence records to avoid early empty return
        mock_store = MagicMock()
        mock_record = NewsEvidenceRecord(
            run_id="test_run",
            evidence_id="art_789",
            ticker="MRVL",
            trade_date="2026-04-10",
            section_label="Company News",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-10",
            title="Test Article",
            url="https://example.com/article",
            summary="Test summary",
            raw_json="{}",
        )
        mock_store.fetch_records.return_value = [mock_record]

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "MRVL",
            "trade_date": "2026-04-10",
            "news_report": "Some report",
            "news_report_structured": {
                "ticker": "WRONG",  # Wrong ticker
                "claims": [],
            },
        }

        result = fact_checker(state)

        assert result["abort_signal"]["source"] == "news_fact_checker"
        assert result["abort_signal"]["reason"] == "news_schema_invalid"
        assert "ticker_mismatch" in result["abort_signal"]["detail"]
        assert "news_report_structured" in result
        structured = result["news_report_structured"]
        assert structured["status"] == "aborted"
        assert structured["contract_version"] == "news_report_v1"
        assert not result["news_report"].startswith("[CRITICAL ABORT]")

    def test_fact_checker_end_to_end_contract_shape(self):
        """Test fact-checker always returns complete contract shape."""
        mock_store = MagicMock()
        mock_store.fetch_records.return_value = []

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "TEST",
            "trade_date": "2026-04-10",
            "news_report": "",
            "news_report_structured": {},
        }

        result = fact_checker(state)

        assert result["abort_signal"]["source"] == "news_fact_checker"
        assert result["abort_signal"]["reason"] == "news_evidence_missing"
        structured = result["news_report_structured"]
        # All required fields must be present
        assert "status" in structured
        assert "contract_version" in structured
        assert "as_of_date" in structured
        assert "abort_reason" in structured
        assert "key_metrics" in structured
        assert "claims" in structured
        assert "summary_table" in structured

    def test_fact_checker_abort_signal_has_canonical_contract(self):
        """Test fact-checker preserves structured abort and returns canonical contract."""
        mock_store = MagicMock()
        mock_store.fetch_records.return_value = []

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "TEST",
            "trade_date": "2026-04-10",
            "news_report": "TEST News Analysis\n\n- Analyst timeout.",
            "news_report_structured": {},
            **raise_abort(
                source="news_analyst",
                reason="news_prefetch_failed",
                detail="Analyst timeout",
                recoverable=True,
            ),
        }

        result = fact_checker(state)

        assert result["news_report"] == "TEST News Analysis\n\n- Analyst timeout."

        structured = result["news_report_structured"]
        assert structured["status"] == "aborted"
        assert structured["contract_version"] == "news_report_v1"
        assert "news_prefetch_failed" in structured["abort_reason"]
        assert "timeout" in structured["abort_reason"].lower()

    def test_fact_checker_blank_report_with_valid_structured_payload_completes(self):
        """Test fact-checker validates structured payload even when markdown report is blank."""
        mock_store = MagicMock()
        mock_record = NewsEvidenceRecord(
            run_id="test_run",
            evidence_id="art_999",
            ticker="TEST",
            trade_date="2026-04-10",
            section_label="News",
            ordinal=1,
            source="Reuters",
            published_at="2026-04-10",
            title="Valid Article",
            url="https://example.com/article",
            summary="Summary",
            raw_json="{}",
        )
        mock_store.fetch_records.return_value = [mock_record]

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "TEST",
            "trade_date": "2026-04-10",
            "news_report": "",  # Blank markdown
            "news_report_structured": {
                "ticker": "TEST",
                "claims": [
                    {
                        "claim": "Valid claim",
                        "source": "Reuters",
                        "published_at": "2026-04-10",
                        "evidence_id": "art_999",
                    }
                ],
                "summary_table": [],
            },
        }

        result = fact_checker(state)

        # Should validate and render from canonical claims
        structured = result["news_report_structured"]
        assert structured["status"] == "completed"
        assert structured["contract_version"] == "news_report_v1"
        # Should have rendered a non-empty report
        assert result["news_report"] != ""

    def test_fact_checker_no_evidence_records_aborts(self):
        """Test fact-checker raises structured abort when no evidence records exist."""
        mock_store = MagicMock()
        mock_store.fetch_records.return_value = []

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "TEST",
            "trade_date": "2026-04-10",
            "news_report": "Some non-abort report",
            "news_report_structured": {},
        }

        result = fact_checker(state)

        assert result["abort_signal"]["source"] == "news_fact_checker"
        assert result["abort_signal"]["reason"] == "news_evidence_missing"
        structured = result["news_report_structured"]
        assert structured["status"] == "aborted"
        assert structured["contract_version"] == "news_report_v1"
        assert structured["key_metrics"]["claim_count"] == 0

    def test_fact_checker_preserves_scanner_claims_without_evidence_records(self):
        """Scanner claims are valid even when no article evidence records exist."""
        mock_store = MagicMock()
        mock_store.fetch_records.return_value = []

        fact_checker = create_news_fact_checker(MagicMock(), evidence_store=mock_store)

        state = {
            "run_id": "test_run",
            "company_of_interest": "RIG",
            "trade_date": "2026-04-10",
            "news_report": "RIG News Analysis",
            "news_report_structured": {
                "ticker": "RIG",
                "report_title": "RIG News Analysis",
                "claims": [
                    {
                        "claim": "RIG appeared in the smart money scanner on 2026-04-10 with +5.0% relative volume.",
                        "source": "Finviz Smart Money Scanner",
                        "scan_date": "2026-04-10",
                    }
                ],
                "summary_table": [
                    {
                        "date": "2026-04-10",
                        "event": "Scanner inclusion",
                        "metric": "Relative volume",
                        "value": "+5.0%",
                        "source": "Finviz Smart Money Scanner",
                        "scan_date": "2026-04-10",
                    }
                ],
            },
        }

        result = fact_checker(state)

        structured = result["news_report_structured"]
        assert structured["status"] == "completed"
        assert structured["key_metrics"]["claim_count"] == 1
        assert structured["claims"][0]["source"] == "Finviz Smart Money Scanner"
        assert structured["claims"][0]["scan_date"] == "2026-04-10"
        assert "Finviz Smart Money Scanner" in result["news_report"]


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


def test_news_fact_checker_aborts_when_any_structured_claim_is_unsupported():
    node = create_news_fact_checker(MagicMock(), evidence_store=FakeEvidenceStore(_records()))
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
    assert result["abort_signal"]["source"] == "news_fact_checker"
    assert result["abort_signal"]["reason"] == "news_evidence_missing"
    assert "structured claims were removed" in result["abort_signal"]["detail"]
    structured = result["news_report_structured"]
    assert structured["status"] == "aborted"
    assert structured["key_metrics"]["claim_count"] == 2
    assert structured["key_metrics"]["removed_claims"] == 1
    assert structured["removed_claims"][0]["source"] == "Scout Money"
    assert structured["removed_claims"][0]["evidence_id"] == "art_fake_001"
    assert not result["news_report"].startswith("[CRITICAL ABORT]")


def test_news_fact_checker_aborts_when_only_fake_structured_claims_remain():
    node = create_news_fact_checker(MagicMock(), evidence_store=FakeEvidenceStore(_records()))
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
    assert result["abort_signal"]["source"] == "news_fact_checker"
    assert result["abort_signal"]["reason"] == "news_evidence_missing"
    assert "All structured claims were removed" in result["abort_signal"]["detail"]
    assert not result["news_report"].startswith("[CRITICAL ABORT]")
    assert result["news_report_structured"]["status"] == "aborted"


def test_news_fact_checker_aborts_when_payload_missing():
    node = create_news_fact_checker(MagicMock(), evidence_store=FakeEvidenceStore(_records()))
    state = {
        "run_id": "run-001",
        "company_of_interest": "CSTM",
        "trade_date": "2026-04-02",
        "news_report": "CSTM News Analysis",
        "news_report_structured": {},
    }

    result = node(state)

    structured = result["news_report_structured"]
    assert result["abort_signal"]["source"] == "news_fact_checker"
    assert result["abort_signal"]["reason"] == "news_schema_invalid"
    assert structured["ticker"] == "CSTM"
    assert structured["claims"] == []
    assert structured["summary_table"] == []
    assert structured["status"] == "aborted"
    assert "No validated structured news claims are available" in result["news_report"]


def test_news_fact_checker_aborts_when_payload_invalid():
    node = create_news_fact_checker(MagicMock(), evidence_store=FakeEvidenceStore(_records()))
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
    assert result["abort_signal"]["source"] == "news_fact_checker"
    assert result["abort_signal"]["reason"] == "news_schema_invalid"
    assert structured["ticker"] == "CSTM"
    assert structured["claims"] == []
    assert structured["summary_table"] == []
    assert structured["status"] == "aborted"
    assert not result["news_report"].startswith("[CRITICAL ABORT]")
    assert "No validated structured news claims are available" in result["news_report"]
