from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


def test_propagator_includes_max_concurrency_when_configured():
    propagator = Propagator(max_recur_limit=25, max_concurrency=1)

    args = propagator.get_graph_args()

    assert args["config"]["recursion_limit"] == 25
    assert args["config"]["max_concurrency"] == 1


def test_google_defaults_to_serial_llm_graph_concurrency():
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "google"
    config["llm_max_concurrency"] = None

    graph = object.__new__(TradingAgentsGraph)
    graph.config = config

    assert graph._resolve_llm_max_concurrency() == 1


def test_explicit_llm_concurrency_overrides_google_default():
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "google"
    config["llm_max_concurrency"] = 3

    graph = object.__new__(TradingAgentsGraph)
    graph.config = config

    assert graph._resolve_llm_max_concurrency() == 3


def test_non_google_preserves_default_graph_concurrency():
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"
    config["llm_max_concurrency"] = None

    graph = object.__new__(TradingAgentsGraph)
    graph.config = config

    assert graph._resolve_llm_max_concurrency() is None
