"""Config isolation: get/set must not leak nested-dict references."""

import copy
import unittest

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import get_config, set_config


@pytest.mark.unit
class DataflowsConfigIsolationTests(unittest.TestCase):
    def setUp(self):
        set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))

    def test_get_config_returns_deep_copy(self):
        cfg = get_config()
        cfg["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        cfg["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "yfinance")
        self.assertNotIn("get_stock_data", fresh["tool_vendors"])

    def test_set_config_does_not_alias_caller_nested_dicts(self):
        custom = copy.deepcopy(default_config.DEFAULT_CONFIG)
        custom["data_vendors"]["core_stock_apis"] = "alpha_vantage"
        custom["tool_vendors"]["get_stock_data"] = "alpha_vantage"

        set_config(custom)

        custom["data_vendors"]["core_stock_apis"] = "yfinance"
        custom["tool_vendors"]["get_stock_data"] = "yfinance"

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")

    def test_partial_nested_update_preserves_existing_defaults(self):
        set_config(
            {
                "data_vendors": {
                    "core_stock_apis": "alpha_vantage",
                }
            }
        )

        fresh = get_config()
        self.assertEqual(fresh["data_vendors"]["core_stock_apis"], "alpha_vantage")
        self.assertEqual(fresh["data_vendors"]["technical_indicators"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["fundamental_data"], "yfinance")
        self.assertEqual(fresh["data_vendors"]["news_data"], "yfinance")

    def test_nested_dict_updates_merge_one_level_deep(self):
        set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
        set_config({"tool_vendors": {"get_news": "alpha_vantage"}})

        fresh = get_config()
        self.assertEqual(fresh["tool_vendors"]["get_stock_data"], "alpha_vantage")
        self.assertEqual(fresh["tool_vendors"]["get_news"], "alpha_vantage")


# --- the config of the run in progress (#1369) --------------------------------

def _graph(config):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    g = object.__new__(TradingAgentsGraph)
    g.config = config
    g._checkpointer_ctx = None
    return g


def _vendors_seen_by_a_run(graph, ticker="AAPL"):
    from tradingagents.dataflows.router import get_vendor

    seen = []

    def _run(*a, **k):
        seen.append(get_vendor("fundamental_data", "get_balance_sheet"))
        return {}, "Hold"

    graph._run_graph = _run
    graph.propagate(ticker, "2026-09-01")
    return seen


@pytest.mark.unit
def test_a_run_reads_its_own_graphs_vendors_not_the_last_graph_built():
    """Building a graph sets the process-wide config, and set_config merges, so
    a second graph built with the defaults was served the first one's vendors."""
    first = copy.deepcopy(default_config.DEFAULT_CONFIG)
    first["tool_vendors"] = {"get_balance_sheet": "sec_edgar,yfinance"}
    set_config(first)                                   # graph A is built
    second = _graph(copy.deepcopy(default_config.DEFAULT_CONFIG))

    assert _vendors_seen_by_a_run(second) == ["yfinance"]


@pytest.mark.unit
def test_a_graph_built_earlier_still_runs_with_its_own_config():
    """Scoping at construction would hand graph A graph B's config if B was built
    after A; the config must be bound when the run starts."""
    a_config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    a_config["tool_vendors"] = {"get_balance_sheet": "sec_edgar,yfinance"}
    a = _graph(a_config)
    set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))   # graph B is built

    assert _vendors_seen_by_a_run(a) == ["sec_edgar,yfinance"]


@pytest.mark.unit
def test_concurrent_runs_each_read_their_own_config():
    import threading

    barrier = threading.Barrier(2)
    results = {}

    def run(name, vendor):
        config = copy.deepcopy(default_config.DEFAULT_CONFIG)
        config["tool_vendors"] = {"get_balance_sheet": vendor}
        graph = _graph(config)
        from tradingagents.dataflows.router import get_vendor

        def _run(*a, **k):
            barrier.wait(timeout=5)                     # both runs are in flight
            results[name] = get_vendor("fundamental_data", "get_balance_sheet")
            return {}, "Hold"

        graph._run_graph = _run
        graph.propagate("AAPL", "2026-09-01")

    threads = [threading.Thread(target=run, args=("a", "alpha_vantage")),
               threading.Thread(target=run, args=("b", "sec_edgar,yfinance"))]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert results == {"a": "alpha_vantage", "b": "sec_edgar,yfinance"}


@pytest.mark.unit
def test_settling_reads_the_graphs_own_config(monkeypatch):
    from tradingagents.dataflows.router import get_vendor

    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config["tool_vendors"] = {"get_stock_data": "alpha_vantage"}
    graph = _graph(config)
    graph.memory_log = graph.reflector = None      # the settlement below is a stand-in
    seen = []
    from tradingagents.graph import settlement

    monkeypatch.setattr(settlement, "settle_pending",
                        lambda *a: seen.append(get_vendor("core_stock_apis", "get_stock_data")))

    graph.settle_pending("AAPL")

    assert seen == ["alpha_vantage"]


@pytest.mark.unit
def test_tools_inside_a_langgraph_run_see_the_run_config():
    """The fix rests on LangGraph carrying the caller's context into tool calls."""
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from tradingagents.dataflows.config import run_config
    from tradingagents.dataflows.router import get_vendor

    @tool
    def probe() -> str:
        """Report the vendor the run would use."""
        return get_vendor("fundamental_data", "get_balance_sheet")

    def call(state):
        return {"messages": [AIMessage("", tool_calls=[{"name": "probe", "args": {}, "id": "1"}])]}

    g = StateGraph(MessagesState)
    g.add_node("call", call)
    g.add_node("tools", ToolNode([probe]))
    g.add_edge(START, "call")
    g.add_edge("call", "tools")
    g.add_edge("tools", END)

    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config["tool_vendors"] = {"get_balance_sheet": "sec_edgar,yfinance"}
    with run_config(config):
        out = g.compile().invoke({"messages": [("user", "go")]})

    assert out["messages"][-1].content == "sec_edgar,yfinance"


@pytest.mark.unit
def test_a_run_config_missing_a_newer_key_still_reads_the_default():
    """A config saved before a key existed must not fail inside a run."""
    from tradingagents.dataflows.config import get_config, run_config

    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    del config["news_article_limit"]
    with run_config(config):
        assert get_config()["news_article_limit"] == default_config.DEFAULT_CONFIG["news_article_limit"]
