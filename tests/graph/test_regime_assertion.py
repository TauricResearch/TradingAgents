import pytest

from tradingagents.graph._graph_utils import assert_regime_consistent


def test_consistent_regime_passes_silently():
    analyst = "Macro Regime: RISK-ON (+5/6) suppressed VIX..."
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


def test_replay_qcom_failed_run_drift():
    """Reproduce the QCOM Market Analyst output from run 01KQHDVJB2R19S4D7Z7Z6DP9F7."""
    drifted = (
        "FINAL TRANSACTION PROPOSAL: HOLD\n"
        "* Macro Regime: The environment is classified as TRANSITION with a score of +2/6"
    )
    canonical = {"label": "RISK-ON", "score": 5}
    with pytest.raises(ValueError):
        assert_regime_consistent(drifted, canonical)
