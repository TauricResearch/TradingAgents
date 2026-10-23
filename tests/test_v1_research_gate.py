"""AI recommendations alone may not create orders under the legacy paper runner."""
import sys
from types import ModuleType, SimpleNamespace

from tradingagents.paper.cli import run_agents
from tradingagents.paper.engine import Book, Bar


def test_legacy_rating_is_research_only(monkeypatch, tmp_path):
    class FakeGraph:
        def __init__(self, **kwargs):
            pass

        def propagate(self, ticker, day, portfolio):
            return {"final_trade_decision": "Rating: Overweight"}, "Overweight"

        def save_reports(self, state, ticker):
            pass

    defaults = ModuleType("tradingagents.default_config")
    defaults.DEFAULT_CONFIG = {}
    graph_module = ModuleType("tradingagents.graph.trading_graph")
    graph_module.TradingAgentsGraph = FakeGraph
    portfolio_module = ModuleType("tradingagents.portfolio")
    portfolio_module.Position = lambda **kwargs: kwargs
    portfolio_module.PortfolioContext = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "tradingagents.default_config", defaults)
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", graph_module)
    monkeypatch.setitem(sys.modules, "tradingagents.portfolio", portfolio_module)
    day = "2026-10-21"
    b = Book.new(day).step(day, {}, .75, .75, 600)
    out, count = run_agents(b, {"NVDA": {day: Bar(220, 225, 219, 222)}},
                            ["NVDA"], tmp_path / "paper.json", 8.0)
    assert count == 1
    assert out.orders == [] and out.positions == {}
    assert [x["type"] for x in out.events][-2:] == [
        "AGENT_RATING", "V1_UNSTRUCTURED_ENTRY_BLOCKED"
    ]
