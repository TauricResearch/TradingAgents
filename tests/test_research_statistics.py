"""Dependence-aware formal research diagnostics."""

import math
import statistics

import pytest

from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    content_id,
)
from tradingagents.research_statistics import (
    deflated_sharpe_ratio,
    factor_attribution,
    formal_complete_readout,
    formal_primary_readout,
    formal_return_diagnostics,
    formal_secondary_readout,
    holm_bonferroni,
    newey_west_mean_test,
    probability_of_backtest_overfitting,
)


@pytest.mark.unit
def test_hac_mean_test_reports_positive_signal():
    result = newey_west_mean_test([0.01, 0.02, -0.005, 0.015, 0.01])
    assert result["mean"] > 0
    assert result["standard_error"] > 0
    assert result["t_statistic"] > 0


@pytest.mark.unit
def test_formal_diagnostics_adjust_for_registered_variations():
    result = formal_return_diagnostics(
        [0.01, -0.01, 0.02, 0.005, -0.002], tested_variations=8,
        bootstrap_trials=100,
    )
    assert result["familywise_alpha_bonferroni"] == pytest.approx(0.00625)
    assert result["moving_block_bootstrap"]["trials"] == 100
    assert result["status"] == "exploratory-legacy-not-for-promotion"


@pytest.mark.unit
def test_factor_attribution_accepts_multiple_synchronized_factors():
    market = [0.01, -0.01, 0.02, -0.02, 0.005, -0.005]
    qqq = [0.02, -0.01, 0.01, -0.01, 0.0, 0.005]
    portfolio = [0.5 * left + 0.25 * right for left, right in zip(market, qqq, strict=True)]
    result = factor_attribution(portfolio, {"market": market, "qqq": qqq})
    assert result["betas"]["market"] == pytest.approx(0.5)
    assert result["betas"]["qqq"] == pytest.approx(0.25)


@pytest.mark.unit
def test_multiple_testing_diagnostics_use_all_registered_strategies():
    returns = [0.01, -0.005, 0.02, 0.0, 0.01, -0.002, 0.005, 0.003]
    dsr = deflated_sharpe_ratio(returns, trial_sharpes=[0.1, 0.2, 0.3, 0.4])
    assert dsr["trials"] == 4
    pbo = probability_of_backtest_overfitting({
        "champion": returns,
        "baseline": [value / 2 for value in returns],
        "placebo": list(reversed(returns)),
    }, partitions=4)
    assert pbo["combinations"] + pbo["tied_train_combinations"] == 3
    assert 0 <= pbo["probability_overfit"] <= 1


@pytest.mark.unit
def test_pbo_fails_closed_instead_of_lexicographically_resolving_ties():
    result = probability_of_backtest_overfitting(
        {name: [0.0] * 252 for name in ("alpha", "beta", "gamma")},
        partitions=10,
    )

    assert result["combinations"] == 0
    assert result["tied_train_combinations"] == 126
    assert result["probability_overfit"] is None


@pytest.mark.unit
def test_confirmatory_readout_has_no_caller_tunable_parameters():
    market = [0.0001 if index % 2 else -0.0001 for index in range(252)]
    champion = [value + 0.0002 + (0.00002 if index % 3 else -0.00002)
                for index, value in enumerate(market)]

    result = formal_primary_readout(
        champion, market, successful_decision_sets=245, synchronized_marks=252
    )

    assert result["paired_intervals"] == 252
    assert result["newey_west"]["lags"] == 5
    assert result["moving_block_bootstrap"]["block_length"] == 5
    assert result["moving_block_bootstrap"]["trials"] == 10_000
    assert result["mean_difference_bps_per_session"] > 1.0
    assert result["passed"]


@pytest.mark.unit
def test_confirmatory_readout_rejects_incomplete_or_selected_windows():
    with pytest.raises(ValueError, match="exactly 252"):
        formal_primary_readout(
            [0.01] * 251, [0.0] * 251,
            successful_decision_sets=251, synchronized_marks=251,
        )

    result = formal_primary_readout(
        [0.0002] * 252, [0.0] * 252,
        successful_decision_sets=239, synchronized_marks=252,
    )
    assert not result["gates"]["completeness"]
    assert not result["passed"]


@pytest.mark.unit
def test_constant_confirmatory_differences_have_coherent_exact_p_values():
    positive = formal_primary_readout(
        [0.0002] * 252, [0.0] * 252,
        successful_decision_sets=252, synchronized_marks=252,
    )
    zero = formal_primary_readout(
        [0.0] * 252, [0.0] * 252,
        successful_decision_sets=252, synchronized_marks=252,
    )

    assert positive["one_sided_p_value"] == 0.0
    assert positive["passed"]
    assert zero["one_sided_p_value"] == 0.5
    assert not zero["passed"]


@pytest.mark.unit
def test_secondary_readout_requires_and_corrects_the_locked_family():
    names = [
        "champion_vs_without_public_reaction",
        "champion_vs_public_reaction_only",
        "champion_vs_equal_weight",
        "champion_vs_momentum",
        "champion_vs_stale_events_negative_control",
        "champion_vs_shuffled_events_negative_control",
        "champion_vs_spy",
    ]
    differences = {
        name: [0.0002 + (0.00001 if index % 2 else -0.00001)
               for index in range(252)]
        for name in names
    }

    result = formal_secondary_readout(differences)

    assert result["family"] == names
    assert result["holm"]["method"] == "Holm"
    assert set(result["hypotheses"]) == set(names)
    assert result["passed_secondary_gates"]
    assert result["can_rescue_failed_primary"] is False

    with pytest.raises(ValueError, match="exactly the seven"):
        formal_secondary_readout({name: values for name, values in differences.items()
                                  if name != "champion_vs_spy"})


@pytest.mark.unit
def test_holm_adjustment_is_fixed_and_step_down():
    result = holm_bonferroni({"a": 0.001, "b": 0.02, "c": 0.04})

    assert result["adjusted_p_values"] == pytest.approx({
        "a": 0.003, "b": 0.04, "c": 0.04,
    })
    assert result["rejected"] == {"a": True, "b": True, "c": True}


@pytest.mark.unit
def test_complete_readout_requires_exact_registered_synchronized_series():
    names = [
        "global_events_champion",
        "global_events_without_public_reaction",
        "public_reaction_only",
        "market_only",
        "equal_weight",
        "momentum",
        "stale_events_negative_control",
        "shuffled_events_negative_control",
    ]
    returns = {
        name: [0.0001 * ((index % 5) - 2) for index in range(252)]
        for name in names
    }

    result = formal_complete_readout(
        returns,
        [0.0] * 252,
        successful_decision_sets=252,
        synchronized_marks=252,
    )

    assert set(result["machine_gates"]) == {
        "primary",
        "secondary",
        "drawdown_disadvantage",
    }
    assert result["selection_bias_diagnostics"]["status"] == "not_identified"
    assert result["deflated_sharpe"]["status"] == "not_identified"
    assert result["probability_of_backtest_overfitting"]["status"] \
        == "not_identified"
    assert result["selection_bias_diagnostics"][
        "registered_forward_arms_used_as_development_trials"
    ] is False
    assert not result["machine_statistical_candidate"]
    assert result["live_capital_approved"] is False
    with pytest.raises(ValueError, match="exactly all registered"):
        formal_complete_readout(
            {name: values for name, values in returns.items() if name != "momentum"},
            [0.0] * 252,
            successful_decision_sets=252,
            synchronized_marks=252,
        )


@pytest.mark.unit
def test_complete_readout_uses_only_a_complete_pre_activity_selection_audit():
    names = [
        "global_events_champion", "global_events_without_public_reaction",
        "public_reaction_only", "market_only", "equal_weight", "momentum",
        "stale_events_negative_control", "shuffled_events_negative_control",
    ]
    returns = {
        name: [0.0001 * ((index % 5) - 2) for index in range(252)]
        for name in names
    }
    paths = {
        "candidate-a": [0.001 * ((index % 4) - 1) for index in range(20)],
        "candidate-b": [0.0008 * ((index % 5) - 2) for index in range(20)],
        "candidate-c": [0.0006 * ((index % 3) - 1) for index in range(20)],
        "candidate-d": [0.0004 * ((index % 6) - 2) for index in range(20)],
    }
    sharpes = {
        name: statistics.fmean(path) / statistics.stdev(path) * math.sqrt(252)
        for name, path in paths.items()
    }
    base = {
        "schema_version": 1,
        "audit_type": "complete-development-selection-universe",
        "protocol_id": GLOBAL_EVENT_V2_PROTOCOL_ID,
        "development_sample_id": "sample_fixture",
        "selected_candidate_id": "candidate-a",
        "candidate_ids": sorted(paths),
        "candidate_sharpes": sharpes,
        "candidate_return_paths": paths,
        "observation_count": 20,
        "periods_per_year": 252,
        "completeness_attested": True,
    }
    content = {
        **base,
        "audit_id": content_id(base, prefix="selection_audit_"),
    }
    envelope = {
        "artifact_id": content_id(
            {
                "artifact_type": "formal_development_selection_audit",
                "content": content,
            },
            prefix="artifact_",
        ),
        "artifact_type": "formal_development_selection_audit",
        "created_utc": 10.0,
        "first_formal_activity_utc": 11.0,
        "content": content,
    }

    result = formal_complete_readout(
        returns,
        [0.0] * 252,
        successful_decision_sets=252,
        synchronized_marks=252,
        development_selection_audit=envelope,
    )

    diagnostics = result["selection_bias_diagnostics"]
    assert diagnostics["status"] == "identified"
    assert diagnostics["development_candidates"] == 4
    assert diagnostics["development_selection_audit_id"] == content["audit_id"]
    assert diagnostics["registered_forward_arms_used_as_development_trials"] is False

    tampered = {**envelope, "first_formal_activity_utc": 9.0}
    invalid = formal_complete_readout(
        returns,
        [0.0] * 252,
        successful_decision_sets=252,
        synchronized_marks=252,
        development_selection_audit=tampered,
    )
    assert invalid["selection_bias_diagnostics"]["status"] == "not_identified"
