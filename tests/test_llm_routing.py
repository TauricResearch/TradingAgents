from copy import deepcopy
import json

from tradingagents.graph.trading_graph import TradingAgentsGraph


class DummyClient:
    def __init__(self, provider, model, base_url=None, **kwargs):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_llm(self):
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "kwargs": self.kwargs,
        }


def test_role_specific_llm_config_overrides_default(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.create_llm_client",
        lambda provider, model, base_url=None, **kwargs: DummyClient(
            provider, model, base_url, **kwargs
        ),
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.FinancialSituationMemory",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.GraphSetup.setup_graph",
        lambda self, selected_analysts: {"selected_analysts": selected_analysts},
    )

    config = {
        "llm_routing": {
            "default": {"provider": "openai", "model": "gpt-5-mini"},
            "roles": {
                "portfolio_manager": {
                    "provider": "openai",
                    "model": "gpt-5.2",
                }
            },
        }
    }

    graph = TradingAgentsGraph(
        selected_analysts=["market"],
        config=deepcopy(config),
    )

    assert graph.graph_setup.portfolio_manager_llm["model"] == "gpt-5.2"


def test_log_state_writes_json_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.ticker = "AAPL"
    graph.log_states_dict = {}

    final_state = {
        "company_of_interest": "Apple",
        "trade_date": "2026-03-24",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_debate_state": {
            "bull_history": "bull",
            "bear_history": "bear",
            "history": "debate history",
            "current_response": "current",
            "judge_decision": "judge",
        },
        "trader_investment_plan": "trader plan",
        "risk_debate_state": {
            "aggressive_history": "agg",
            "conservative_history": "cons",
            "neutral_history": "neutral",
            "history": "risk history",
            "judge_decision": "risk judge",
        },
        "investment_plan": "investment plan",
        "final_trade_decision": "buy",
    }

    graph._log_state("2026-03-24", final_state)

    output_path = (
        tmp_path
        / "eval_results"
        / "AAPL"
        / "TradingAgentsStrategy_logs"
        / "full_states_log_2026-03-24.json"
    )
    assert output_path.exists()
    assert json.loads(output_path.read_text())["2026-03-24"]["company_of_interest"] == "Apple"
