import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import get_fundamentals
from tradingagents.agents.utils.news_data_tools import get_news


def _run_scenario(tmp_path, scenario, model):
    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = str(tmp_path / "results")
    config["data_cache_dir"] = str(tmp_path / "cache")
    config["memory_log_path"] = str(tmp_path / "trading_memory.md")
    config["checkpoint_enabled"] = False
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1

    ta = TradingAgentsGraph(
        debug=False,
        config=config,
        selected_analysts=["market", "news", "fundamentals", "social"],
    )
    final_state, rating = ta.propagate(scenario["ticker"], scenario["trade_date"])
    assert rating == scenario["expected"]["rating"]
    assert "data_quality" in final_state
    assert "error_count" in final_state
    assert "confidence_score" in final_state
    assert final_state["data_quality"] in ("high", "medium", "low", "unknown")
    assert isinstance(final_state["error_count"], int)
    assert isinstance(final_state["confidence_score"], float)

    debate_history = final_state["investment_debate_state"]["history"]
    assert "Bull Analyst:" in debate_history
    assert "Bear Analyst:" in debate_history

    risk_history = final_state["risk_debate_state"]["history"]
    assert "Aggressive Analyst:" in risk_history
    assert "Conservative Analyst:" in risk_history
    assert "Neutral Analyst:" in risk_history

    pm_text = final_state["final_trade_decision"]
    assert parse_rating(pm_text) == scenario["expected"]["rating"]

    return final_state, rating, model


@pytest.mark.unit
@pytest.mark.parametrize(
    "scenario_name",
    [
        "divergence",
        "black_swan",
        "panic_selling",
        "noisy_sideways",
    ],
)
def test_scenarios_end_to_end(tmp_path, load_scenario, scenario_llm, scenario_name):
    model = scenario_llm(scenario_name)
    scenario = load_scenario(scenario_name)
    _run_scenario(tmp_path, scenario, model)


@pytest.mark.unit
def test_noisy_sideways_memory_context_is_injected(tmp_path, load_scenario, scenario_llm):
    model = scenario_llm("noisy_sideways")
    scenario = load_scenario("noisy_sideways")

    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})
    log.store_decision(scenario["ticker"], "2026-04-01", "**Rating**: Hold\n\nStay out.")
    log.update_with_outcome(
        scenario["ticker"],
        "2026-04-01",
        raw_return=0.0,
        alpha_return=0.0,
        holding_days=5,
        reflection="Standing aside avoided churn.",
    )

    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = str(tmp_path / "results")
    config["data_cache_dir"] = str(tmp_path / "cache")
    config["memory_log_path"] = str(tmp_path / "trading_memory.md")
    config["checkpoint_enabled"] = False
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1

    ta = TradingAgentsGraph(
        debug=False,
        config=config,
        selected_analysts=["market", "news", "fundamentals", "social"],
    )
    final_state, rating = ta.propagate(scenario["ticker"], scenario["trade_date"])
    assert rating == "Hold"

    combined_seen = "\n\n".join(model.seen)
    assert "Lessons from prior decisions and outcomes" in combined_seen
    assert "Standing aside avoided churn" in combined_seen
    assert parse_rating(final_state["final_trade_decision"]) == "Hold"


@pytest.mark.unit
def test_data_integrity_tools_do_not_crash_when_vendor_raises(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("vendor down")

    monkeypatch.setattr("tradingagents.agents.utils.core_stock_tools.route_to_vendor", _boom)
    monkeypatch.setattr("tradingagents.agents.utils.fundamental_data_tools.route_to_vendor", _boom)
    monkeypatch.setattr("tradingagents.agents.utils.news_data_tools.route_to_vendor", _boom)

    out1 = get_stock_data.invoke({"symbol": "AAPL", "start_date": "2026-01-01", "end_date": "2026-01-10"})
    out2 = get_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2026-01-10"})
    out3 = get_news.invoke({"ticker": "AAPL", "start_date": "2026-01-01", "end_date": "2026-01-10"})

    assert '"error": true' in out1 and '"type": "RuntimeError"' in out1 and "vendor down" in out1
    assert '"error": true' in out2 and '"type": "RuntimeError"' in out2 and "vendor down" in out2
    assert '"error": true' in out3 and '"type": "RuntimeError"' in out3 and "vendor down" in out3


@pytest.mark.unit
@pytest.mark.parametrize("scenario_name", ["missing_data", "irrelevant_news"])
def test_data_integrity_scenarios_end_to_end(tmp_path, load_scenario, scenario_llm, scenario_name):
    model = scenario_llm(scenario_name)
    scenario = load_scenario(scenario_name)
    _run_scenario(tmp_path, scenario, model)
