import pytest

from tradingagents.agents.managers.portfolio_manager import _append_measured_feature_contributions
from tradingagents.portfolio import (
    FeatureContribution,
    FeatureContributionArtifact,
    feature_contribution_artifact_from_dict,
    feature_contributions_from_dicts,
    rank_feature_contributions,
)


def test_contribution_is_deterministic_absolute_z_times_importance():
    ranked = rank_feature_contributions(
        [
            FeatureContribution("cash_flow", -2.0, 0.7, "risk", "fundamentals#cash-flow"),
            FeatureContribution("momentum", 1.1, 0.8, "positive", "market#momentum"),
        ]
    )

    assert ranked[0].feature == "cash_flow"
    assert ranked[0].contribution == pytest.approx(1.4)


def test_pm_only_renders_measured_feature_artifacts_not_free_text_guessing():
    rendered = _append_measured_feature_contributions(
        "**Rating**: Hold",
        [
            {
                "feature": "cash_flow",
                "z_score": -2.0,
                "importance": 0.7,
                "direction": "risk",
                "evidence_ref": "fundamentals#cash-flow",
            }
        ],
    )

    assert "|z|×importance=1.400" in rendered
    assert "evidence=fundamentals#cash-flow" in rendered
    assert _append_measured_feature_contributions("**Rating**: Hold", "unverified") == "**Rating**: Hold"


def test_pm_preserves_the_artifact_identifier_when_one_is_provided():
    rendered = _append_measured_feature_contributions(
        "**Rating**: Hold",
        [
            {
                "feature": "cash_flow",
                "z_score": -2.0,
                "importance": 0.7,
                "direction": "risk",
                "evidence_ref": "dataset:financials:2026-07-18",
                "source_artifact_id": "calc:factor-model:2026-07-18",
            }
        ],
    )

    assert "artifact=calc:factor-model:2026-07-18" in rendered


def test_feature_contribution_decoder_rejects_duplicate_features():
    values = feature_contributions_from_dicts(
        [
            {"feature": "x", "z_score": 1, "importance": 0.5, "direction": "positive", "evidence_ref": "a"},
            {"feature": "x", "z_score": 2, "importance": 0.5, "direction": "positive", "evidence_ref": "b"},
        ]
    )
    with pytest.raises(ValueError, match="duplicate"):
        rank_feature_contributions(values)


def test_versioned_artifact_stamps_each_contribution_with_its_numeric_source():
    artifact = feature_contribution_artifact_from_dict(
        {
            "schema_version": "measured-feature-contributions/v1",
            "artifact_id": "calc:factor-model:2026-07-18",
            "producer": "factor-model-v2",
            "methodology_ref": "docs/factor-model-v2.md#normalization",
            "as_of_date": "2026-07-18",
            "contributions": [
                {
                    "feature": "cash_flow",
                    "z_score": -2.0,
                    "importance": 0.7,
                    "direction": "risk",
                    "evidence_ref": "dataset:financials:2026-07-18",
                }
            ],
        }
    )

    assert artifact.to_state() == [
        {
            "feature": "cash_flow",
            "z_score": -2.0,
            "importance": 0.7,
            "direction": "risk",
            "evidence_ref": "dataset:financials:2026-07-18",
            "source_artifact_id": "calc:factor-model:2026-07-18",
        }
    ]


def test_artifact_rejects_unknown_schema_instead_of_accepting_free_text():
    with pytest.raises(ValueError, match="schema_version"):
        feature_contribution_artifact_from_dict(
            {
                "schema_version": "whatever-an-llm-wrote",
                "artifact_id": "x",
                "producer": "calculator",
                "methodology_ref": "method",
                "as_of_date": "2026-07-18",
                "contributions": [],
            }
        )

    with pytest.raises(ValueError, match="schema_version"):
        FeatureContributionArtifact(
            artifact_id="x",
            producer="calculator",
            methodology_ref="method",
            as_of_date="2026-07-18",
            contributions=(FeatureContribution("x", 1, 1, "positive", "evidence"),),
            schema_version="bad",  # type: ignore[arg-type]
        )
