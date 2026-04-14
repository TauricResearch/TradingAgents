import json

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph, _merge_with_default_config


def test_merge_with_default_config_keeps_required_defaults():
    merged = _merge_with_default_config({
        "llm_provider": "anthropic",
        "backend_url": "https://example.com/api",
    })

    assert merged["llm_provider"] == "anthropic"
    assert merged["backend_url"] == "https://example.com/api"
    assert merged["project_dir"] == DEFAULT_CONFIG["project_dir"]
    assert merged["results_dir"] == DEFAULT_CONFIG["results_dir"]


def test_merge_with_default_config_merges_nested_vendor_settings():
    merged = _merge_with_default_config({
        "data_vendors": {
            "news_data": "alpha_vantage",
        },
        "tool_vendors": {
            "get_stock_data": "alpha_vantage",
        },
    })

    assert merged["data_vendors"]["news_data"] == "alpha_vantage"
    assert merged["data_vendors"]["core_stock_apis"] == DEFAULT_CONFIG["data_vendors"]["core_stock_apis"]
    assert merged["tool_vendors"]["get_stock_data"] == "alpha_vantage"


def test_log_state_persists_research_provenance(tmp_path):
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path)}
    graph.ticker = "AAPL"
    graph.log_states_dict = {}

    final_state = {
        "company_of_interest": "AAPL",
        "trade_date": "2026-04-11",
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "investment_debate_state": {
            "bull_history": "Bull Analyst: case",
            "bear_history": "Bear Analyst: case",
            "history": "Bull Analyst: case\nBear Analyst: case",
            "current_response": "Recommendation: HOLD",
            "judge_decision": "Recommendation: HOLD",
            "research_status": "degraded",
            "research_mode": "degraded_synthesis",
            "timed_out_nodes": ["Bull Researcher"],
            "degraded_reason": "bull_researcher_timeout",
            "covered_dimensions": ["market"],
            "manager_confidence": 0.0,
        },
        "trader_investment_plan": "",
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "judge_decision": "",
        },
        "investment_plan": "Recommendation: HOLD",
        "final_trade_decision": "HOLD",
    }

    TradingAgentsGraph._log_state(graph, "2026-04-11", final_state)

    log_path = tmp_path / "AAPL" / "TradingAgentsStrategy_logs" / "full_states_log_2026-04-11.json"
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["investment_debate_state"]["research_status"] == "degraded"
    assert payload["investment_debate_state"]["research_mode"] == "degraded_synthesis"
    assert payload["investment_debate_state"]["timed_out_nodes"] == ["Bull Researcher"]
    assert payload["investment_debate_state"]["manager_confidence"] == 0.0
