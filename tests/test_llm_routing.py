from copy import deepcopy

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
