import pytest

from tradingagents.graph._graph_utils import assert_regime_consistent


def test_consistent_regime_passes_silently():
    analyst = "Macro Regime: RISK-ON (+5/6) suppressed VIX..."
    canonical = {"label": "RISK-ON", "score": 5}
    assert assert_regime_consistent(analyst, canonical) is None


@pytest.mark.parametrize(
    "analyst",
    [
        "Macro Regime: **RISK-ON** (score +5/6, confidence: high).",
        "Macro Regime: RISK-ON score +5/6",
    ],
)
def test_score_keyword_without_of_passes_silently(analyst):
    canonical = {"label": "RISK-ON", "score": 5}
    assert assert_regime_consistent(analyst, canonical) is None


def test_label_mismatch_raises():
    analyst = "Macro Regime: TRANSITION (+2/6) mixed signals..."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*label"):
        assert_regime_consistent(analyst, canonical)


def test_score_mismatch_raises():
    analyst = "Macro Regime: RISK-ON (+3/6) ..."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*score"):
        assert_regime_consistent(analyst, canonical)


def test_missing_regime_in_analyst_raises():
    analyst = "Some analysis without a regime line."
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"could not parse regime"):
        assert_regime_consistent(analyst, canonical)


def test_uses_macro_regime_pair_not_prior_context():
    analyst = (
        "Canonical brief said RISK-ON (+5/6) before the final answer.\n"
        "Macro Regime: TRANSITION (+2/6) mixed signals..."
    )
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*label"):
        assert_regime_consistent(analyst, canonical)


def test_macro_regime_context_does_not_mask_statement():
    analyst = (
        "Macro Regime Context: canonical brief said RISK-ON (+5/6)\n"
        "Macro Regime: TRANSITION (+2/6) mixed signals..."
    )
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError, match=r"regime drift.*label"):
        assert_regime_consistent(analyst, canonical)


def test_missing_canonical_score_raises():
    analyst = "Macro Regime: TRANSITION (+0/6) neutral setup..."
    canonical = {"label": "TRANSITION"}
    with pytest.raises(ValueError, match=r"malformed canonical regime.*score"):
        assert_regime_consistent(analyst, canonical)


def test_malformed_canonical_score_raises():
    analyst = "Macro Regime: TRANSITION (+0/6) neutral setup..."
    canonical = {"label": "TRANSITION", "score": "zero"}
    with pytest.raises(ValueError, match=r"malformed canonical regime.*score"):
        assert_regime_consistent(analyst, canonical)


@pytest.mark.parametrize("score", ["5", 5.9, True, 7, -7])
def test_non_integer_or_out_of_range_canonical_score_raises(score):
    analyst = f"Macro Regime: RISK-ON ({int(score):+d}/6) aligned setup..."
    canonical = {"label": "RISK-ON", "score": score}
    with pytest.raises(ValueError, match=r"malformed canonical regime.*score"):
        assert_regime_consistent(analyst, canonical)


def test_missing_canonical_label_raises():
    analyst = "Macro Regime: TRANSITION (+0/6) neutral setup..."
    canonical = {"score": 0}
    with pytest.raises(ValueError, match=r"malformed canonical regime.*label"):
        assert_regime_consistent(analyst, canonical)


def test_non_dict_canonical_raises_value_error():
    analyst = "Macro Regime: TRANSITION (+0/6) neutral setup..."
    canonical = ["TRANSITION", 0]
    with pytest.raises(ValueError, match=r"malformed canonical regime"):
        assert_regime_consistent(analyst, canonical)


def test_negative_score_passes_silently():
    analyst = "Macro Regime: RISK-OFF (-4/6) volatility expanding..."
    canonical = {"label": "RISK-OFF", "score": -4}
    assert assert_regime_consistent(analyst, canonical) is None


def test_replay_qcom_failed_run_drift():
    """Reproduce the QCOM Market Analyst output from run 01KQHDVJB2R19S4D7Z7Z6DP9F7."""
    drifted = (
        "FINAL TRANSACTION PROPOSAL: HOLD\n"
        "* Macro Regime: The environment is classified as TRANSITION with a score of +2/6"
    )
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(
        ValueError,
        match=r"canonical label 'RISK-ON' != analyst label 'TRANSITION'",
    ):
        assert_regime_consistent(drifted, canonical)


def test_validator_node_skips_when_canonical_absent():
    """When canonical_regime missing from state, validator must skip silently."""
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_market_regime_check_node()
    state = {"market_report": "Macro Regime: TRANSITION (+2/6)"}
    result = node(state)
    assert result == {"sender": "market_regime_check"}


def test_validator_node_raises_when_canonical_present_and_drift():
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_market_regime_check_node()
    state = {
        "market_report": "Macro Regime: TRANSITION (+2/6)",
        "canonical_regime": {"label": "RISK-ON", "score": 5},
    }
    with pytest.raises(ValueError, match=r"regime drift"):
        node(state)


def test_validator_node_raises_when_canonical_present_but_empty():
    from tradingagents.graph.setup import GraphSetup

    node = GraphSetup._make_market_regime_check_node()
    state = {
        "market_report": "Macro Regime: TRANSITION (+2/6)",
        "canonical_regime": {},
    }
    with pytest.raises(ValueError, match=r"malformed canonical regime"):
        node(state)
