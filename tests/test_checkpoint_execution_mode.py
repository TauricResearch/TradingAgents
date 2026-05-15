import importlib.util
import sys
import types
from pathlib import Path


def _load_graph_module():
    tradingagents_pkg = types.ModuleType("tradingagents")
    tradingagents_pkg.__path__ = []
    sys.modules["tradingagents"] = tradingagents_pkg

    graph_pkg = types.ModuleType("tradingagents.graph")
    graph_pkg.__path__ = []
    sys.modules["tradingagents.graph"] = graph_pkg

    fake_langgraph_prebuilt = types.ModuleType("langgraph.prebuilt")
    fake_langgraph_prebuilt.ToolNode = object
    sys.modules["langgraph.prebuilt"] = fake_langgraph_prebuilt

    fake_llm_clients = types.ModuleType("tradingagents.llm_clients")

    class _FakeClient:
        def get_llm(self):
            return object()

    fake_llm_clients.create_llm_client = lambda *args, **kwargs: _FakeClient()
    sys.modules["tradingagents.llm_clients"] = fake_llm_clients

    fake_agents = types.ModuleType("tradingagents.agents")
    fake_agents.__all__ = []
    sys.modules["tradingagents.agents"] = fake_agents

    fake_default_config = types.ModuleType("tradingagents.default_config")
    fake_default_config.DEFAULT_CONFIG = {}
    sys.modules["tradingagents.default_config"] = fake_default_config

    fake_memory = types.ModuleType("tradingagents.utils.memory")
    fake_memory.TradingMemoryLog = lambda config: object()
    sys.modules["tradingagents.utils.memory"] = fake_memory

    fake_utils = types.ModuleType("tradingagents.dataflows.utils")
    fake_utils.safe_ticker_component = lambda ticker: ticker
    sys.modules["tradingagents.dataflows.utils"] = fake_utils

    fake_states = types.ModuleType("tradingagents.agents.utils.agent_states")
    fake_states.AgentState = dict
    fake_states.InvestDebateState = dict
    fake_states.RiskDebateState = dict
    sys.modules["tradingagents.agents.utils.agent_states"] = fake_states

    fake_config = types.ModuleType("tradingagents.dataflows.config")
    fake_config.set_config = lambda config: None
    sys.modules["tradingagents.dataflows.config"] = fake_config

    fake_agent_utils = types.ModuleType("tradingagents.agents.utils.agent_utils")
    for name in [
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_insider_transactions",
        "get_global_news",
    ]:
        setattr(fake_agent_utils, name, object())
    sys.modules["tradingagents.agents.utils.agent_utils"] = fake_agent_utils

    fake_checkpointer = types.ModuleType("tradingagents.graph.checkpointer")
    fake_checkpointer.checkpoint_step = lambda *args, **kwargs: None
    fake_checkpointer.clear_checkpoint = lambda *args, **kwargs: None
    fake_checkpointer.get_checkpointer = lambda *args, **kwargs: None
    fake_checkpointer.thread_id = lambda ticker, date: "tid"
    sys.modules["tradingagents.graph.checkpointer"] = fake_checkpointer

    fake_conditional = types.ModuleType("tradingagents.graph.conditional_logic")
    fake_conditional.ConditionalLogic = lambda *args, **kwargs: object()
    sys.modules["tradingagents.graph.conditional_logic"] = fake_conditional

    fake_setup = types.ModuleType("tradingagents.graph.setup")

    class _FakeWorkflow:
        def compile(self, **kwargs):
            return object()

    class _FakeGraphSetup:
        def __init__(self, *args, **kwargs):
            pass

        def setup_graph(self, *args, **kwargs):
            return _FakeWorkflow()

    fake_setup.GraphSetup = _FakeGraphSetup
    sys.modules["tradingagents.graph.setup"] = fake_setup

    fake_propagation = types.ModuleType("tradingagents.graph.propagation")
    fake_propagation.Propagator = lambda *args, **kwargs: object()
    sys.modules["tradingagents.graph.propagation"] = fake_propagation

    fake_reflection = types.ModuleType("tradingagents.graph.reflection")
    fake_reflection.Reflector = lambda *args, **kwargs: object()
    sys.modules["tradingagents.graph.reflection"] = fake_reflection

    fake_signal = types.ModuleType("tradingagents.graph.signal_processing")
    fake_signal.SignalProcessor = lambda *args, **kwargs: object()
    sys.modules["tradingagents.graph.signal_processing"] = fake_signal

    module_path = (
        Path(__file__).resolve().parents[1]
        / "tradingagents"
        / "graph"
        / "trading_graph.py"
    )
    spec = importlib.util.spec_from_file_location(
        "tradingagents.graph.trading_graph_test_module",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_checkpoint_mode_uses_sync_runner():
    module = _load_graph_module()
    graph = module.TradingAgentsGraph.__new__(module.TradingAgentsGraph)
    graph.config = {"checkpoint_enabled": True}
    graph._run_graph_sync = lambda company_name, trade_date: ("sync", company_name, trade_date)
    graph._run_graph_async = lambda company_name, trade_date: ("async", company_name, trade_date)

    result = graph._run_graph("SHOP", "2026-05-15")

    assert result == ("sync", "SHOP", "2026-05-15")
