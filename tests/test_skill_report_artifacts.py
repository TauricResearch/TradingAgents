from __future__ import annotations

import pytest

from tradingagents.agents.schemas import (
    SentimentBand,
    SentimentReport,
    render_sentiment_report,
)
from tradingagents.analysts import ANALYST_CONFIG
from tradingagents.skills.artifacts import (
    FundamentalsMethodologyArtifact,
    SentimentRealityGapArtifact,
)
from tradingagents.skills.registry import (
    SkillRegistry,
    build_role_report_contract,
    finalize_role_report,
)

pytestmark = pytest.mark.unit


def test_registry_exposes_code_owned_schema_for_each_analyst_role():
    schema = SkillRegistry().report_artifact_schema("fundamentals_analyst")

    assert schema is FundamentalsMethodologyArtifact
    assert "dupont_components" in schema.model_fields
    assert "altman_z_score" in schema.model_fields
    assert "beneish_m_score" in schema.model_fields
    assert "cycle_stage_probabilities" in schema.model_fields


def test_analyst_registry_declares_the_code_owned_skill_role():
    assert {definition.skill_role for definition in ANALYST_CONFIG} == {
        "fundamentals_analyst",
        "news_analyst",
        "market_analyst",
        "sentiment_analyst",
    }


def test_finalizer_validates_public_marker_and_keeps_historical_prose_shape():
    report, artifact = finalize_role_report(
        "market_analyst",
        "Market report prose.\n```methodology-artifact\n"
        '{"health_score":{"value":72,"unit":"score","availability":"available"},'
        '"trend_regime":"uptrend","limitations":["sector data unavailable"]}\n```',
    )

    assert report == "Market report prose."
    assert artifact == {
        "schema_version": "1",
        "data_as_of": None,
        "limitations": ["sector data unavailable"],
        "health_score": {
            "value": 72.0,
            "unit": "score",
            "source_ref": None,
            "availability": "available",
        },
        "trend_regime": "uptrend",
        "volatility_regime": None,
        "participation": None,
        "invalidation_levels": [],
        "rotation_signals": [],
    }


def test_finalizer_drops_no_text_when_the_optional_marker_is_invalid():
    raw = "Legacy report\n```methodology-artifact\n{not json}\n```"

    assert finalize_role_report("news_analyst", raw) == (raw, None)


def test_artifact_rejects_private_reasoning_and_unavailable_metric_values():
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        FundamentalsMethodologyArtifact.model_validate({"private_reasoning": "hidden"})
    with pytest.raises(ValueError, match="must not include a value"):
        FundamentalsMethodologyArtifact.model_validate(
            {
                "altman_z_score": {
                    "value": 2.1,
                    "availability": "unavailable",
                }
            }
        )


def test_sentiment_report_renders_optional_public_reality_gap_without_breaking_old_output():
    report = SentimentReport(
        overall_band=SentimentBand.MIXED,
        overall_score=5.0,
        confidence="low",
        narrative="Sources disagree.",
        reality_gap=SentimentRealityGapArtifact(
            narrative="Retail narrative is optimistic.",
            reality_check="No supplied operating metric confirms it.",
            divergence="indeterminate",
            reality_gap_score=20.0,
            limitations=["fundamental release unavailable"],
        ),
    )

    rendered = render_sentiment_report(report)
    assert "**Overall Sentiment:** **Mixed**" in rendered
    assert "**Sentiment Reality Gap**: indeterminate (score: +20.0)" in rendered


def test_contract_explicitly_excludes_private_reasoning_and_names_schema_fields():
    contract = build_role_report_contract("news_analyst")

    assert "private reasoning" in contract
    assert "alpha_hypotheses" in contract
