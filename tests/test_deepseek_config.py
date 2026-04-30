import pytest

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.openai_client import OpenAIClient


@pytest.mark.unit
class TestDeepSeekThinkingConfig:
    def test_deepseek_thinking_defaults_to_disabled(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.delenv("DEEPSEEK_THINKING", raising=False)

        llm = OpenAIClient("deepseek-v4-flash", provider="deepseek").get_llm()

        assert llm.extra_body == {"thinking": {"type": "disabled"}}

    def test_deepseek_thinking_can_be_enabled_explicitly(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        llm = OpenAIClient(
            "deepseek-v4-pro",
            provider="deepseek",
            deepseek_thinking="enabled",
        ).get_llm()

        assert llm.extra_body == {"thinking": {"type": "enabled"}}

    def test_deepseek_thinking_rejects_invalid_value(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")

        with pytest.raises(ValueError, match="deepseek_thinking"):
            OpenAIClient(
                "deepseek-v4-pro",
                provider="deepseek",
                deepseek_thinking="max",
            ).get_llm()

    def test_graph_passes_deepseek_thinking_config(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {
            "llm_provider": "deepseek",
            "deepseek_thinking": "enabled",
        }

        assert graph._get_provider_kwargs() == {"deepseek_thinking": "enabled"}
