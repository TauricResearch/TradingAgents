from copy import deepcopy

import pytest
from langchain_core.messages import HumanMessage

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.observability.projections import (
    EVIDENCE_CONFIG_FIELDS,
    ROLE_STATE_FIELDS,
    EvidenceConfigDrift,
    RoleProjectionRunContext,
    assert_evidence_config_matches,
    evidence_config_snapshot,
    project_role_input,
)
from tradingagents.observability.roles import ROLES_BY_ACTOR_ID


def _complete_state():
    return {
        "messages": [HumanMessage(content="AAPL")],
        "company_of_interest": "AAPL",
        "instrument_context": "Ticker: AAPL; Apple Inc.",
        "trade_date": "2026-07-17",
        "asset_type": "stock",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "canonical_company_profile": {"ticker": "AAPL", "name": "Apple Inc."},
        "investment_debate_state": {"history": "bull then bear", "count": 2},
        "investment_plan": "hold",
        "trader_investment_plan": "hold 5%",
        "risk_debate_state": {"history": "risk debate", "count": 3},
        "past_context": "prior lesson",
        "unrelated_internal_value": "must not leak",
        "api_key": "must not leak",
    }


def test_projection_registry_covers_exactly_all_thirteen_roles():
    assert set(ROLE_STATE_FIELDS) == set(ROLES_BY_ACTOR_ID)
    assert len(ROLE_STATE_FIELDS) == 13


EXPECTED_FIELDS = {
    "analyst.market": {"instrument_context", "trade_date", "messages"},
    "analyst.sentiment": {
        "instrument_context",
        "company_of_interest",
        "trade_date",
        "messages",
    },
    "analyst.news": {"instrument_context", "asset_type", "trade_date", "messages"},
    "analyst.fundamentals": {"instrument_context", "trade_date", "messages"},
    "evidence.steward": {
        "company_of_interest",
        "canonical_company_profile",
        "trade_date",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
    },
    "researcher.bull": {
        "instrument_context",
        "asset_type",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_debate_state",
    },
    "researcher.bear": {
        "instrument_context",
        "asset_type",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_debate_state",
    },
    "manager.research": {"instrument_context", "investment_debate_state"},
    "trader": {"instrument_context", "company_of_interest", "investment_plan"},
    "risk.aggressive": {
        "instrument_context",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "trader_investment_plan",
        "risk_debate_state",
    },
    "risk.neutral": {
        "instrument_context",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "trader_investment_plan",
        "risk_debate_state",
    },
    "risk.conservative": {
        "instrument_context",
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "trader_investment_plan",
        "risk_debate_state",
    },
    "manager.portfolio": {
        "instrument_context",
        "investment_plan",
        "trader_investment_plan",
        "past_context",
        "risk_debate_state",
    },
}


@pytest.mark.parametrize("actor_id", sorted(ROLES_BY_ACTOR_ID))
def test_each_role_projection_contains_only_its_exact_state_fields(actor_id):
    run_context = RoleProjectionRunContext(
        effective_config=DEFAULT_CONFIG,
        effective_config_artifact_id="config:abc",
    )

    projection = project_role_input(actor_id, _complete_state(), run_context)

    assert set(projection.state_fields) == EXPECTED_FIELDS[actor_id]
    assert "unrelated_internal_value" not in projection.state_fields
    assert "api_key" not in projection.state_fields
    assert projection.node_id == ROLES_BY_ACTOR_ID[actor_id].node_id
    assert projection.effective_config_artifact_id == "config:abc"
    assert projection.projection_version == 1


def test_fundamentals_projection_shows_company_statement_tool_context_not_other_reports():
    projection = project_role_input(
        "analyst.fundamentals",
        _complete_state(),
        RoleProjectionRunContext(DEFAULT_CONFIG),
    )

    assert set(projection.state_fields) == {"instrument_context", "trade_date", "messages"}
    assert "market_report" not in projection.state_fields
    assert "investment_debate_state" not in projection.state_fields


def test_debate_roles_receive_reports_and_debate_state_without_downstream_plans():
    projection = project_role_input(
        "researcher.bull",
        _complete_state(),
        RoleProjectionRunContext(DEFAULT_CONFIG),
    )

    assert {
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "investment_debate_state",
    } <= projection.state_fields.keys()
    assert "investment_plan" not in projection.state_fields
    assert "risk_debate_state" not in projection.state_fields


def test_evidence_source_alignment_reaches_bull_and_bear_only_with_explicit_scores():
    state = _complete_state()
    state["evidence_ledger"] = {
        "evidence": [
            {"source_provider": "official", "direction_score": 0.8},
            {"source_provider": "wire", "direction_score": -0.6},
            {"source_provider": "invalid", "direction_score": "unknown"},
        ]
    }
    run_context = RoleProjectionRunContext(DEFAULT_CONFIG)

    for actor_id in ("researcher.bull", "researcher.bear"):
        alignment = project_role_input(actor_id, state, run_context).state_fields[
            "source_alignment"
        ]
        assert alignment["label"] == "Wide divergence"
        assert alignment["source_count"] == 2

    evidence_alignment = project_role_input(
        "evidence.steward", state, run_context
    ).state_fields["source_alignment"]
    assert evidence_alignment["mean_score"] == pytest.approx(0.1)


def test_instrument_context_fallback_only_adds_fields_the_helper_would_read():
    state = _complete_state()
    state["instrument_context"] = ""
    run_context = RoleProjectionRunContext(DEFAULT_CONFIG)

    market = project_role_input("analyst.market", state, run_context).state_fields
    sentiment = project_role_input("analyst.sentiment", state, run_context).state_fields
    news = project_role_input("analyst.news", state, run_context).state_fields

    assert {"company_of_interest", "asset_type"} <= market.keys()
    assert "company_of_interest" in sentiment and "asset_type" in sentiment
    assert "company_of_interest" in news and "asset_type" in news


def test_nested_debate_projection_excludes_fields_the_role_does_not_read():
    state = _complete_state()
    state["investment_debate_state"].update(
        {
            "bull_history": "bull",
            "bear_history": "bear",
            "current_response": "latest",
            "judge_decision": "poison",
        }
    )
    bull = project_role_input(
        "researcher.bull",
        state,
        RoleProjectionRunContext(DEFAULT_CONFIG),
    ).state_fields["investment_debate_state"]
    manager = project_role_input(
        "manager.research",
        state,
        RoleProjectionRunContext(DEFAULT_CONFIG),
    ).state_fields["investment_debate_state"]

    assert set(bull) == {"history", "bull_history", "bear_history", "current_response", "count"}
    assert set(manager) == {"history", "bear_history", "bull_history", "count"}
    assert "judge_decision" not in bull
    assert "current_response" not in manager


def test_evidence_config_snapshot_has_exact_fixed_whitelist_dynamic_tavily_and_no_secret():
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "backend_url": "HTTPS://User:pass@API.Example.COM:443/v1/?token=secret",
            "tavily_custom_budget": 7,
            "TAVILY_API_KEY": "super-secret",
            "results_dir": "/private/path",
        }
    )

    snapshot = evidence_config_snapshot(config)

    assert set(EVIDENCE_CONFIG_FIELDS) <= snapshot.values.keys()
    assert snapshot.values["backend_url"] == "https://api.example.com:443/v1"
    assert snapshot.values["tavily_custom_budget"] == 7
    assert snapshot.values["tavily_api_key"] == "[REDACTED]"
    assert "tavily_api_key" in snapshot.redaction_manifest
    assert "results_dir" not in snapshot.values
    assert "super-secret" not in str(snapshot.as_dict())


def test_evidence_config_match_ignores_unrelated_keys_but_rejects_effective_drift():
    expected = deepcopy(DEFAULT_CONFIG)
    actual = deepcopy(DEFAULT_CONFIG)
    actual["results_dir"] = "/another/local/path"

    expected_snapshot, actual_snapshot = assert_evidence_config_matches(expected, actual)
    assert expected_snapshot.sha256 == actual_snapshot.sha256

    actual["news_min_company_items"] += 1
    with pytest.raises(EvidenceConfigDrift) as exc_info:
        assert_evidence_config_matches(expected, actual)
    assert exc_info.value.differing_keys == ("news_min_company_items",)
    assert "super-secret" not in str(exc_info.value)
