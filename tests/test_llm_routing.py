from copy import deepcopy
import json

import tradingagents.dataflows.config as dataflow_config
import tradingagents.default_config as default_config
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


class DummyStateGraph:
    def __init__(self, _state_type):
        self.nodes = {}

    def add_node(self, name, node):
        self.nodes[name] = node

    def add_edge(self, *_args, **_kwargs):
        return None

    def add_conditional_edges(self, *_args, **_kwargs):
        return None

    def compile(self):
        return {"nodes": self.nodes}


def _patch_graph_setup_wiring(monkeypatch, recorded_llms):
    monkeypatch.setattr("tradingagents.graph.setup.StateGraph", DummyStateGraph)
    monkeypatch.setattr("tradingagents.graph.setup.create_msg_delete", lambda: "delete")

    def make_factory(node_name):
        def factory(llm, *_args):
            recorded_llms[node_name] = llm
            return node_name

        return factory

    monkeypatch.setattr(
        "tradingagents.graph.setup.create_market_analyst",
        make_factory("Market Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_social_media_analyst",
        make_factory("Social Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_news_analyst",
        make_factory("News Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_fundamentals_analyst",
        make_factory("Fundamentals Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bull_researcher",
        make_factory("Bull Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bear_researcher",
        make_factory("Bear Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_research_manager",
        make_factory("Research Manager"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_trader",
        make_factory("Trader"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_aggressive_debator",
        make_factory("Aggressive Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_neutral_debator",
        make_factory("Neutral Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_conservative_debator",
        make_factory("Conservative Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_portfolio_manager",
        make_factory("Portfolio Manager"),
    )


def test_role_specific_llm_config_overrides_actual_graph_wiring(monkeypatch):
    recorded_llms = {}

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
    _patch_graph_setup_wiring(monkeypatch, recorded_llms)

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

    TradingAgentsGraph(
        selected_analysts=["market"],
        config=deepcopy(config),
    )

    assert recorded_llms["Market Analyst"]["model"] == "gpt-5-mini"
    assert recorded_llms["Portfolio Manager"]["model"] == "gpt-5.2"
    assert "News Analyst" not in recorded_llms


def test_unused_role_routes_do_not_instantiate_clients(monkeypatch):
    created_clients = []

    def fake_create_llm_client(provider, model, base_url=None, **kwargs):
        created_clients.append((provider, model))
        if provider == "bad-provider":
            raise AssertionError("unused role route should not be instantiated")
        return DummyClient(provider, model, base_url, **kwargs)

    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.create_llm_client",
        fake_create_llm_client,
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.FinancialSituationMemory",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.GraphSetup.setup_graph",
        lambda self, selected_analysts: {"selected_analysts": selected_analysts},
    )

    TradingAgentsGraph(
        selected_analysts=["market"],
        config={
            "llm_routing": {
                "default": {"provider": "openai", "model": "gpt-5-mini"},
                "roles": {
                    "news": {
                        "provider": "bad-provider",
                        "model": "unused-model",
                    }
                },
            }
        },
    )

    assert ("bad-provider", "unused-model") not in created_clients


def test_provider_normalization_avoids_duplicate_legacy_client_creation(monkeypatch):
    created_clients = []

    def fake_create_llm_client(provider, model, base_url=None, **kwargs):
        created_clients.append((provider, model))
        return DummyClient(provider, model, base_url, **kwargs)

    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.create_llm_client",
        fake_create_llm_client,
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.FinancialSituationMemory",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.GraphSetup.setup_graph",
        lambda self, selected_analysts: {"selected_analysts": selected_analysts},
    )

    TradingAgentsGraph(
        selected_analysts=["market"],
        config={
            "llm_provider": "OpenAI",
            "quick_think_llm": "gpt-5-mini",
            "llm_routing": {
                "roles": {
                    "market": {"provider": "openai", "model": "gpt-5-mini"},
                },
            },
        },
    )

    assert created_clients.count(("openai", "gpt-5-mini")) == 1


def test_dataflow_config_returns_isolated_nested_routing(monkeypatch):
    monkeypatch.setattr(dataflow_config, "_config", None)
    dataflow_config.initialize_config()

    config = dataflow_config.get_config()
    config["llm_routing"]["roles"]["portfolio_manager"] = {
        "provider": "openai",
        "model": "gpt-5.2",
    }

    assert dataflow_config.get_config()["llm_routing"]["roles"] == {}
    assert default_config.DEFAULT_CONFIG["llm_routing"]["roles"] == {}


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
    assert (
        json.loads(output_path.read_text())["2026-03-24"]["company_of_interest"]
        == "Apple"
    )
