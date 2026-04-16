import json
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG, get_default_config, load_project_env, normalize_runtime_llm_config
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


def test_get_default_config_prefers_runtime_minimax_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "MiniMax-M2.7-highspeed")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_BACKEND_URL", raising=False)

    config = get_default_config()

    assert config["llm_provider"] == "anthropic"
    assert config["backend_url"] == "https://api.minimaxi.com/anthropic"
    assert config["deep_think_llm"] == "MiniMax-M2.7-highspeed"
    assert config["quick_think_llm"] == "MiniMax-M2.7-highspeed"
    assert config["api_key"] == "test-minimax-key"
    assert config["llm_timeout"] == 60.0
    assert config["llm_max_retries"] == 1
    assert config["minimax_retry_attempts"] == 2


def test_load_project_env_overrides_stale_shell_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://stale.example.com/api")
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic\n", encoding="utf-8")

    load_project_env(env_file)

    assert Path(env_file).exists()
    assert Path(env_file).read_text(encoding="utf-8")
    assert Path(env_file).name == ".env"
    assert __import__("os").environ["ANTHROPIC_BASE_URL"] == "https://api.minimaxi.com/anthropic"


def test_normalize_runtime_llm_config_keeps_model_and_canonicalizes_minimax_url():
    normalized = normalize_runtime_llm_config(
        {
            "llm_provider": "anthropic",
            "backend_url": "https://api.minimaxi.com/anthropic/",
            "deep_think_llm": "MiniMax-M2.7-highspeed",
            "quick_think_llm": "MiniMax-M2.7-highspeed",
        }
    )

    assert normalized["backend_url"] == "https://api.minimaxi.com/anthropic"
    assert normalized["deep_think_llm"] == "MiniMax-M2.7-highspeed"
    assert normalized["quick_think_llm"] == "MiniMax-M2.7-highspeed"
    assert normalized["llm_timeout"] == 60.0
    assert normalized["llm_max_retries"] == 1
    assert normalized["minimax_retry_attempts"] == 2


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


def test_normalize_decision_outputs_repairs_invalid_final_report():
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    final_state = {
        "portfolio_context": "Current account is crowded in growth beta.",
        "peer_context": "Within the same theme, this name ranks near the top on quality.",
        "investment_plan": "RECOMMENDATION: BUY\nSimple execution plan: build on weakness.",
        "trader_investment_plan": "TRADER_RATING: BUY\nFINAL TRANSACTION PROPOSAL: **BUY**",
        "risk_debate_state": {
            "judge_decision": "",
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "Judge",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 3,
        },
        "final_trade_decision": 'I will gather more market data. <tool_call>name="stock_data"</tool_call>',
    }

    normalized = TradingAgentsGraph._normalize_decision_outputs(graph, final_state)

    assert normalized["final_trade_decision"] == "BUY"
    assert normalized["final_trade_decision_structured"]["rating_source"] == "trader_plan"
    assert normalized["final_trade_decision_structured"]["portfolio_context_used"] is True
    assert normalized["final_trade_decision_structured"]["peer_context_used"] is True
    assert normalized["final_trade_decision_report"].startswith("## Normalized Portfolio Decision")
    assert normalized["risk_debate_state"]["judge_decision"] == normalized["final_trade_decision_report"]
