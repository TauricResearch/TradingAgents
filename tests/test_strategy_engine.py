import pytest

from tradingagents.research import StrategySignal, aggregate_strategy_signals


def test_abstentions_are_not_treated_as_neutral_votes():
    consensus = aggregate_strategy_signals(
        [
            StrategySignal("fundamentals", 0.8, 0.75),
            StrategySignal("news", None, 1.0, "insufficient primary sources"),
        ]
    )

    assert consensus.conviction == 0.8
    assert consensus.consensus_level == "unanimous"
    assert consensus.participating_strategy_ids == ("fundamentals",)
    assert consensus.abstained_strategy_ids == ("news",)


def test_strategy_engine_surfaces_opposing_views_and_severity():
    consensus = aggregate_strategy_signals(
        [
            StrategySignal("market", 0.9, 1.0),
            StrategySignal("fundamentals", -0.8, 1.0),
            StrategySignal("news", 0.2, 0.5),
        ]
    )

    assert consensus.consensus_level == "mixed"
    assert consensus.conflict_count == 2
    assert consensus.conflict_severity == "high"
    assert consensus.disagreement == "mixed strategy views (high disagreement)"


def test_all_abstain_has_no_numeric_conviction():
    consensus = aggregate_strategy_signals(
        [StrategySignal("market", None, 0.5), StrategySignal("news", None, 0.5)]
    )

    assert consensus.conviction is None
    assert consensus.consensus_level == "abstain"


def test_duplicate_strategy_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_strategy_signals(
            [StrategySignal("market", 0.5, 0.5), StrategySignal("market", 0.4, 0.4)]
        )
