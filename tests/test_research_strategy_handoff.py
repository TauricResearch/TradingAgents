from tradingagents.agents.schemas import (
    PortfolioRating,
    ResearchPlan,
    ResearchStrategySignal,
    render_research_plan,
)


def test_research_plan_renders_deterministic_strategy_disagreement_for_pm():
    plan = ResearchPlan(
        recommendation=PortfolioRating.HOLD,
        rationale="The evidence conflicts.",
        strategic_actions="Wait for confirmation.",
        strategy_signals=[
            ResearchStrategySignal(
                strategy_id="market", conviction=0.8, confidence=0.8, rationale="trend"
            ),
            ResearchStrategySignal(
                strategy_id="fundamentals", conviction=-0.8, confidence=0.8, rationale="cash flow"
            ),
            ResearchStrategySignal(
                strategy_id="news", abstain=True, confidence=0.2, rationale="no primary source"
            ),
        ],
    )

    rendered = render_research_plan(plan)

    assert "**Strategy Consensus**: mixed; conviction +0.00" in rendered
    assert "mixed strategy views (high disagreement); conflicts=1" in rendered


def test_strategy_signal_rejects_missing_conviction_unless_explicitly_abstaining():
    try:
        ResearchStrategySignal(strategy_id="market", confidence=0.5)
    except ValueError as exc:
        assert "non-abstaining" in str(exc)
    else:
        raise AssertionError("missing conviction must not silently become neutral")
