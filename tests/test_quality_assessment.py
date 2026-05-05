from __future__ import annotations

from tradingagents_service.quality import assess_shadow_run_quality


def _source(source_id: str, source_type: str = "market") -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "label": f"{source_type.title()} analyst report",
        "state_key": f"{source_type}_report",
        "summary": f"{source_type.title()} evidence summary.",
        "bytes": 128,
    }


def _scorecard(suggested_rating: str, suggested_direction: str) -> dict[str, object]:
    return {
        "factors": [
            {
                "factor": "market",
                "label": "Market analyst report",
                "score": -2 if suggested_direction == "bearish" else 0,
                "available": True,
                "source_id": "SRC-MARKET-1",
                "positive_terms": [],
                "negative_terms": ["risk"] if suggested_direction == "bearish" else [],
            }
        ],
        "total_score": -2 if suggested_direction == "bearish" else 0,
        "suggested_rating": suggested_rating,
        "suggested_direction": suggested_direction,
        "method": "keyword-balance audit scaffold over analyst reports and risk debate",
        "claim_backed_factor_count": 1,
    }


def _claim_graph(source_ids: list[str] | None = None) -> dict[str, object]:
    source_ids = source_ids or ["SRC-MARKET-1"]
    return {
        "claim_objects": [
            {
                "claim_id": "CLM-0001",
                "text": "Market momentum is mixed.",
                "source_ids": source_ids,
            }
        ],
        "claim_ids": ["CLM-0001"],
        "claim_source_ids": source_ids,
    }


def test_quality_fails_unrelated_ticker_and_entity_mentions() -> None:
    assessment = assess_shadow_run_quality(
        ticker="AAPL",
        final_trade_decision=(
            "Rating: Buy AAPL. Marvell Technology Group Ltd. looks attractive, "
            "and AVLN should be maintained as a side holding."
        ),
        final_state={"market_report": "market", "news_report": "news"},
    )

    assert assessment.status == "failed"
    codes = {finding.code for finding in assessment.findings}
    assert "unrelated_ticker_mention" in codes
    assert "unrelated_entity_mention" in codes


def test_quality_warns_when_final_decision_has_no_explicit_sources() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Reduce exposure due to mixed analyst debate.",
        final_state={"market_report": "market", "news_report": "news"},
    )

    assert assessment.status == "warning"
    assert [finding.code for finding in assessment.findings] == ["no_explicit_source_reference"]
    assert assessment.recommendation_audit["final_rating"] == "Hold"
    assert assessment.recommendation_audit["alignment_status"] == "aligned"


def test_quality_passes_ticker_consistent_sourced_decision() -> None:
    assessment = assess_shadow_run_quality(
        ticker="MSFT",
        final_trade_decision="Rating: Hold. According to Yahoo Finance data, MSFT momentum is mixed.",
        final_state={
            "market_report": "market",
            "news_report": "news",
            "investment_plan": "**Recommendation**: Hold",
            "trader_investment_plan": "**Action**: Hold",
        },
    )

    assert assessment.status == "passed"
    assert assessment.findings == []
    assert assessment.recommendation_audit["alignment_status"] == "aligned"
    assert assessment.recommendation_audit["research_manager_rating"] == "Hold"
    assert assessment.recommendation_audit["trader_action"] == "Hold"


def test_quality_passes_with_valid_structured_source_object_citations() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision=(
            "Rating: Hold. Market momentum is mixed [SRC-MARKET-1], while news flow "
            "remains balanced [SRC-NEWS-1]."
        ),
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "news_report": "News analyst report shows balanced risk.",
            "investment_plan": "**Recommendation**: Hold",
            "trader_investment_plan": "**Action**: Hold",
            "source_objects": [
                _source("SRC-MARKET-1", "market"),
                _source("SRC-NEWS-1", "news"),
            ],
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
            "claim_graph": _claim_graph(["SRC-MARKET-1", "SRC-NEWS-1"]),
        },
    )

    assert assessment.status == "passed"
    assert assessment.findings == []
    assert assessment.recommendation_audit["cited_source_ids"] == ["SRC-MARKET-1", "SRC-NEWS-1"]
    assert assessment.recommendation_audit["available_source_ids"] == ["SRC-MARKET-1", "SRC-NEWS-1"]


def test_quality_fails_when_source_evidence_exists_without_claim_graph() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Market momentum is mixed [SRC-MARKET-1].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "source_objects": [_source("SRC-MARKET-1", "market")],
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
        },
    )

    assert assessment.status == "failed"
    findings = {finding.code: finding for finding in assessment.findings}
    assert findings["missing_claim_graph_evidence"].severity == "error"
    assert assessment.source_summary["source_object_count"] == 1
    assert assessment.source_summary["claim_count"] == 0


def test_quality_does_not_require_claim_graph_without_structured_evidence() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. According to Yahoo Finance data, NVDA momentum is mixed.",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "news_report": "News analyst report shows balanced risk.",
            "investment_plan": "**Recommendation**: Hold",
            "trader_investment_plan": "**Action**: Hold",
        },
    )

    assert "missing_claim_graph_evidence" not in {finding.code for finding in assessment.findings}
    assert assessment.source_summary["source_object_count"] == 0
    assert assessment.source_summary["raw_tool_output_count"] == 0
    assert assessment.source_summary["claim_count"] == 0


def test_quality_fails_when_raw_tool_sources_exist_without_claim_graph() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Market momentum is mixed [RAW-TOOL-0001].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "raw_tool_outputs": [
                {
                    "source_id": "RAW-TOOL-0001",
                    "source_type": "raw_tool_output",
                    "tool_name": "get_stock_data",
                    "output_sha256": "a" * 64,
                }
            ],
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
        },
    )

    assert assessment.status == "failed"
    codes = {finding.code for finding in assessment.findings}
    assert "missing_claim_graph_evidence" in codes
    assert assessment.source_summary["raw_tool_output_count"] == 1


def test_quality_fails_when_structured_source_objects_are_not_cited() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision=(
            "Rating: Hold. According to analyst evidence, market momentum is mixed "
            "and news flow remains balanced."
        ),
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "news_report": "News analyst report shows balanced risk.",
            "investment_plan": "**Recommendation**: Hold",
            "trader_investment_plan": "**Action**: Hold",
            "source_objects": [
                _source("SRC-MARKET-1", "market"),
                _source("SRC-NEWS-1", "news"),
            ],
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
        },
    )

    assert assessment.status == "failed"
    findings = {finding.code: finding for finding in assessment.findings}
    assert findings["missing_source_object_citation"].severity == "error"
    assert "source object" in findings["missing_source_object_citation"].message.lower()


def test_quality_fails_invalid_structured_source_object_citation() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Momentum is mixed [SRC-MARKET-1] but risk is elevated [SRC-RISK-99].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "news_report": "News analyst report shows balanced risk.",
            "investment_plan": "**Recommendation**: Hold",
            "trader_investment_plan": "**Action**: Hold",
            "source_objects": [
                _source("SRC-MARKET-1", "market"),
                _source("SRC-NEWS-1", "news"),
            ],
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
        },
    )

    assert assessment.status == "failed"
    findings = {finding.code: finding for finding in assessment.findings}
    assert findings["invalid_source_object_citation"].severity == "error"
    assert findings["invalid_source_object_citation"].evidence == "SRC-RISK-99"


def test_quality_warns_when_final_rating_diverges_from_scorecard_without_reconciliation() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision=(
            "Rating: Buy. Market weakness is temporary [SRC-MARKET-1], so exposure "
            "can increase."
        ),
        final_state={
            "market_report": "Market analyst report shows elevated risk and volatility.",
            "news_report": "News analyst report shows balanced risk.",
            "investment_plan": "**Recommendation**: Buy",
            "trader_investment_plan": "**Action**: Buy",
            "source_objects": [
                _source("SRC-MARKET-1", "market"),
                _source("SRC-NEWS-1", "news"),
            ],
            "recommendation_scorecard": _scorecard("Underweight", "bearish"),
        },
    )

    assert assessment.status == "failed"
    findings = {finding.code: finding for finding in assessment.findings}
    assert findings["scorecard_reconciliation_missing"].severity == "error"
    assert assessment.recommendation_audit["scorecard_alignment_status"] == "divergent"
    assert assessment.recommendation_audit["scorecard_suggested_rating"] == "Underweight"


def test_quality_warns_on_divergent_recommendation_chain() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Sell. According to Yahoo Finance data, risk is elevated.",
        final_state={
            "market_report": "market",
            "news_report": "news",
            "investment_plan": "**Recommendation**: Buy",
            "trader_investment_plan": "**Action**: Hold",
        },
    )

    assert assessment.status == "warning"
    assert assessment.recommendation_audit["alignment_status"] == "divergent"
    assert "recommendation_chain_divergent" in {finding.code for finding in assessment.findings}


def test_quality_warns_when_target_profile_is_not_addressed() -> None:
    assessment = assess_shadow_run_quality(
        ticker="NVDA",
        final_trade_decision="Rating: Hold. Market evidence is mixed [SRC-MARKET-1].",
        final_state={
            "market_report": "Market analyst report shows mixed momentum.",
            "news_report": "News analyst report shows balanced risk.",
            "source_objects": [
                _source("SRC-MARKET-1", "market"),
                _source("SRC-NEWS-1", "news"),
            ],
            "target_profile": {"investor_type": "growth", "horizon": "12m", "benchmark": "SPY", "risk_appetite": "moderate"},
            "recommendation_scorecard": _scorecard("Hold", "neutral"),
            "claim_graph": _claim_graph(["SRC-MARKET-1", "SRC-NEWS-1"]),
        },
    )

    assert assessment.status == "warning"
    findings = {finding.code for finding in assessment.findings}
    assert "target_profile_not_addressed" in findings
    assert assessment.recommendation_audit["target_profile_status"] == "not_addressed"


def test_quality_fails_pre_synthesis_scope_contamination() -> None:
    assessment = assess_shadow_run_quality(
        ticker="AAPL",
        final_trade_decision="Rating: Hold. According to [SRC-NEWS-1], Apple risk is balanced.",
        final_state={
            "news_report": "Apple report with unrelated Marvell evidence.",
            "source_objects": [_source("SRC-NEWS-1", "news")],
            "pre_synthesis_scope_audit": {
                "status": "failed",
                "findings": [
                    {
                        "code": "pre_synthesis_unrelated_entity",
                        "severity": "error",
                        "message": "News analyst report mentions issuer(s) unrelated to requested instrument AAPL.",
                        "evidence": "marvell (MRVL)",
                    }
                ],
            },
        },
    )

    assert assessment.status == "failed"
    assert "pre_synthesis_scope_contamination" in {finding.code for finding in assessment.findings}
