"""Unit tests for summary context builders and news contract formatting."""

from tradingagents.agents.utils.output_validation import build_research_manager_fallback
from tradingagents.agents.utils.summary_context import (
    build_debate_evidence_brief,
    build_research_packet,
)


class TestNewsStructuredContextFormatting:
    """Test news_report_v1 contract formatting in downstream contexts."""
    
    def test_research_packet_includes_news_structured_for_invalid_status(self):
        """Test research packet includes news structured contract for invalid status but not raw report."""
        state = {
            "news_report_structured": {
                "status": "invalid_structured_payload",
                "contract_version": "news_report_v1",
                "ticker": "TEST",
                "as_of_date": "2026-04-10",
                "abort_reason": "Schema validation failed",
                "claims": [],
                "summary_table": [],
                "key_metrics": {
                    "claim_count": 0,
                    "summary_rows": 0,
                    "evidence_ids": 0,
                    "removed_claims": 2,
                    "below_min_claims": False,
                },
            },
            "news_report": "Some unverified markdown text",
        }
        
        packet = build_research_packet(state)
        
        # Should include structured contract
        assert "## News Structured Contract" in packet
        assert "status: invalid_structured_payload" in packet
        
        # Should NOT include raw news report for invalid status
        assert "## News Report" not in packet
        assert "unverified markdown" not in packet
    
    def test_research_packet_includes_raw_news_only_when_completed_with_claims(self):
        """Test research packet includes raw news only when status=completed and claim_count > 0."""
        state = {
            "news_report_structured": {
                "status": "completed",
                "contract_version": "news_report_v1",
                "ticker": "MRVL",
                "as_of_date": "2026-04-10",
                "abort_reason": "",
                "claims": [
                    {
                        "claim": "MRVL announced new product",
                        "source": "Reuters",
                        "published_at": "2026-04-10",
                        "evidence_id": "art_123",
                    }
                ],
                "summary_table": [],
                "key_metrics": {
                    "claim_count": 1,
                    "summary_rows": 0,
                    "evidence_ids": 1,
                    "removed_claims": 0,
                    "below_min_claims": False,
                },
            },
            "news_report": "- MRVL announced new product [Source: Reuters | Published: 2026-04-10] [Evidence ID: art_123]",
        }
        
        packet = build_research_packet(state)
        
        # Should include both structured contract and raw report
        assert "## News Structured Contract" in packet
        assert "status: completed" in packet
        assert "## News Report" in packet
        assert "MRVL announced new product" in packet
    
    def test_debate_evidence_brief_includes_news_metrics_without_claim_text(self):
        """Test debate brief includes news metrics but not individual claim text."""
        state = {
            "news_report_structured": {
                "status": "completed",
                "contract_version": "news_report_v1",
                "ticker": "MRVL",
                "as_of_date": "2026-04-10",
                "claims": [
                    {"claim": "Claim 1 with sensitive content", "source": "Reuters", "published_at": "2026-04-10", "evidence_id": "art_1"},
                    {"claim": "Claim 2 with more details", "source": "Bloomberg", "published_at": "2026-04-09", "evidence_id": "art_2"},
                ],
                "summary_table": [],
                "key_metrics": {
                    "claim_count": 2,
                    "summary_rows": 0,
                    "evidence_ids": 2,
                    "removed_claims": 1,
                    "below_min_claims": False,
                },
            },
        }
        
        brief = build_debate_evidence_brief(state)
        
        # Should include news section with metrics
        assert "## News" in brief
        assert "News status: completed" in brief
        assert "News claims: 2" in brief
        assert "Evidence IDs: 2" in brief
        assert "Removed claims: 1" in brief
        
        # Should NOT include individual claim text
        assert "sensitive content" not in brief
        assert "more details" not in brief
    
    def test_research_manager_fallback_gates_news_claim_iteration(self):
        """Test research manager fallback gates news claim iteration behind status check."""
        # Test with non-completed status
        state_invalid = {
            "company_of_interest": "MRVL",
            "news_report_structured": {
                "status": "invalid_structured_payload",
                "contract_version": "news_report_v1",
                "claims": [
                    {"claim": "Stale claim that should be ignored", "source": "Unknown", "published_at": "2026-04-10"},
                ],
                "key_metrics": {
                    "claim_count": 0,
                    "summary_rows": 0,
                    "evidence_ids": 0,
                    "removed_claims": 1,
                    "below_min_claims": False,
                },
            },
            "fundamentals_report_structured": {},
            "market_report_structured": {},
        }
        
        fallback = build_research_manager_fallback(state_invalid)
        
        # Should emit bear warning for invalid status
        assert "Bear:" in fallback
        assert "invalid_structured_payload" in fallback
        
        # Should NOT include the stale claim text
        assert "Stale claim" not in fallback
        
        # Test with completed status and claims
        state_completed = {
            "company_of_interest": "MRVL",
            "news_report_structured": {
                "status": "completed",
                "contract_version": "news_report_v1",
                "claims": [
                    {"claim": "Valid claim", "source": "Reuters", "published_at": "2026-04-10", "evidence_id": "art_123"},
                ],
                "key_metrics": {
                    "claim_count": 1,
                    "summary_rows": 0,
                    "evidence_ids": 1,
                    "removed_claims": 0,
                    "below_min_claims": False,
                },
            },
            "fundamentals_report_structured": {},
            "market_report_structured": {},
        }
        
        fallback_completed = build_research_manager_fallback(state_completed)
        
        # Should include valid claim text
        assert "Valid claim" in fallback_completed


class TestNewsStructuredContractEmptyState:
    """Test handling of empty/missing news structured contracts."""
    
    def test_research_packet_handles_missing_news_structured(self):
        """Test research packet handles missing news_report_structured gracefully."""
        state = {
            "news_report": "Some report text",
            # news_report_structured is missing
        }
        
        packet = build_research_packet(state)
        
        # Should not crash, should not include news structured section
        assert "## News Structured Contract" not in packet
    
    def test_debate_brief_handles_missing_news_structured(self):
        """Test debate brief handles missing news_report_structured gracefully."""
        state = {}
        
        brief = build_debate_evidence_brief(state)
        
        # Should not crash
        assert isinstance(brief, str)
