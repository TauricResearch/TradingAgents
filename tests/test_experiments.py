import json

import pandas as pd
import pytest

from tradingagents.experiments.backtest import calculate_metrics, rating_to_target
from tradingagents.experiments.charts import render_technical_chart
from tradingagents.experiments.portfolio import allocate_risk_parity
from tradingagents.experiments.postmortem import StrategyRuleStore
from tradingagents.experiments.semantic_memory import SemanticMemory
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.graph.propagation import Propagator


def test_semantic_memory_returns_closest_resolved_situation(tmp_path):
    memory = SemanticMemory(tmp_path / "memory.db")
    memory.store_decision("NVDA", "2026-01-01", "Buy", "AI demand with price below 200 EMA")
    memory.resolve_outcome("NVDA", "2026-01-01", 0.12, 0.08, "Demand thesis worked.")
    memory.store_decision("XOM", "2026-01-01", "Sell", "Oil spike with price above 200 EMA")
    memory.resolve_outcome("XOM", "2026-01-01", -0.03, -0.01, "Energy call worked.")

    matches = memory.find_similar("NVDA", "AI demand while price below 200 EMA", limit=1)

    assert matches[0]["ticker"] == "NVDA"
    assert matches[0]["reflection"] == "Demand thesis worked."


def test_semantic_memory_pending_rows_are_not_returned(tmp_path):
    memory = SemanticMemory(tmp_path / "memory.db")
    memory.store_decision("NVDA", "2026-01-01", "Buy", "AI demand")

    assert memory.find_similar("NVDA", "AI demand") == []


def test_risk_parity_favors_lower_volatility_asset():
    returns = pd.DataFrame(
        {
            "LOW": [0.01, -0.01, 0.01, -0.01],
            "HIGH": [0.04, -0.04, 0.04, -0.04],
        }
    )

    weights = allocate_risk_parity(returns, {"LOW": "Buy", "HIGH": "Buy"})

    assert weights["LOW"] > weights["HIGH"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_risk_parity_rating_tilt_reduces_sell_weight():
    returns = pd.DataFrame({"A": [0.01, -0.01], "B": [0.01, -0.01]})

    weights = allocate_risk_parity(returns, {"A": "Buy", "B": "Sell"})

    assert weights["A"] > weights["B"]


def test_calculate_metrics_reports_drawdown_and_sharpe():
    metrics = calculate_metrics([100.0, 110.0, 88.0, 99.0])

    assert metrics["total_return"] == pytest.approx(-0.01)
    assert metrics["max_drawdown"] == pytest.approx(-0.2)
    assert "sharpe_ratio" in metrics


@pytest.mark.parametrize(
    ("rating", "target"),
    [("Buy", 1.0), ("Overweight", 0.75), ("Hold", 0.5), ("Underweight", 0.25), ("Sell", 0.0)],
)
def test_rating_to_target(rating, target):
    assert rating_to_target(rating) == target


def test_strategy_rule_store_round_trip(tmp_path):
    store = StrategyRuleStore(tmp_path / "rules.json")
    store.write(["Reduce exposure when RSI is extended.", "Respect broad drawdowns."])

    assert store.load() == ["Reduce exposure when RSI is extended.", "Respect broad drawdowns."]
    assert "Reduce exposure" in store.as_prompt()


def test_render_technical_chart_creates_png(tmp_path):
    index = pd.date_range("2026-01-01", periods=40, freq="D")
    frame = pd.DataFrame(
        {
            "Open": range(100, 140),
            "High": range(102, 142),
            "Low": range(98, 138),
            "Close": range(101, 141),
            "Volume": [1000] * 40,
        },
        index=index,
    )

    output = render_technical_chart(frame, "TEST", tmp_path / "chart.png")

    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG")


def test_initial_state_keeps_visual_report_and_strategy_rules():
    state = Propagator().create_initial_state(
        "NVDA", "2026-01-01", visual_report="Uptrend.", strategy_rules="Avoid chasing."
    )

    assert state["visual_report"] == "Uptrend."
    assert state["strategy_rules"] == "Avoid chasing."


def test_portfolio_manager_prompt_includes_strategy_rules():
    captured = {}
    structured = type(
        "Structured",
        (),
        {
            "invoke": lambda self, prompt: (
                captured.__setitem__("prompt", prompt)
                or PortfolioDecision(
                    rating=PortfolioRating.HOLD,
                    executive_summary="Wait.",
                    investment_thesis="Balanced.",
                )
            )
        },
    )()
    llm = type(
        "LLM",
        (),
        {
            "with_structured_output": lambda self, *args, **kwargs: structured,
            "invoke": lambda self, prompt: None,
        },
    )()
    state = Propagator().create_initial_state("NVDA", "2026-01-01", strategy_rules="Avoid chasing.")
    state.update(
        {
            "investment_plan": "Hold.",
            "trader_investment_plan": "Hold.",
            "risk_debate_state": {
                **state["risk_debate_state"],
                "history": "Mixed evidence.",
            },
        }
    )

    create_portfolio_manager(llm)(state)

    assert "Avoid chasing." in captured["prompt"]
