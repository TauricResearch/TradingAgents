from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph


ROOT = Path(__file__).resolve().parents[1]
FACTOR_RULES_MODULE_PATH = (
    ROOT / "tradingagents" / "agents" / "utils" / "factor_rules.py"
)
FACTOR_RULE_ANALYST_MODULE_PATH = (
    ROOT / "tradingagents" / "agents" / "analysts" / "factor_rule_analyst.py"
)


def load_module(name: str, path: Path):
    assert path.exists(), f"Missing module under test: {path.relative_to(ROOT)}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyStateGraph:
    def __init__(self, _state_type):
        self.nodes = {}
        self.conditional_edges = {}

    def add_node(self, name, node):
        self.nodes[name] = node

    def add_edge(self, *_args, **_kwargs):
        return None

    def add_conditional_edges(self, source, condition, destinations):
        self.conditional_edges[source] = {
            "condition": condition,
            "destinations": destinations,
        }

    def compile(self):
        return {
            "nodes": self.nodes,
            "conditional_edges": self.conditional_edges,
        }


class DummyMemory:
    def get_memories(self, _situation, n_matches=2):
        return []


class DummyResponse:
    def __init__(self, content):
        self.content = content


class RecordingLLM:
    def __init__(self, content):
        self.content = content
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return DummyResponse(self.content)


def make_factory(recorded_llms, node_name):
    def factory(llm, *_args):
        recorded_llms[node_name] = llm
        return node_name

    return factory


def test_load_factor_rules_uses_expected_precedence_and_shapes(tmp_path, monkeypatch):
    factor_rules = load_module("factor_rules", FACTOR_RULES_MODULE_PATH)
    project_dir = tmp_path / "tradingagents"
    examples_dir = project_dir / "examples"
    examples_dir.mkdir(parents=True)

    explicit_path = tmp_path / "explicit_factor_rules.json"
    env_path = tmp_path / "env_factor_rules.json"
    examples_path = examples_dir / "factor_rules.json"
    project_path = project_dir / "factor_rules.json"

    explicit_payload = [{"name": "Explicit rule", "signal": "bullish"}]
    env_payload = {"rules": [{"name": "Env rule", "signal": "bearish"}]}
    examples_payload = [{"name": "Example rule", "signal": "neutral"}]
    project_payload = {"rules": [{"name": "Project rule", "signal": "bullish"}]}

    explicit_path.write_text(json.dumps(explicit_payload), encoding="utf-8")
    env_path.write_text(json.dumps(env_payload), encoding="utf-8")
    examples_path.write_text(json.dumps(examples_payload), encoding="utf-8")
    project_path.write_text(json.dumps(project_payload), encoding="utf-8")

    monkeypatch.setenv("TRADINGAGENTS_FACTOR_RULES_PATH", str(env_path))

    rules, loaded_path = factor_rules.load_factor_rules(
        {
            "project_dir": str(project_dir),
            "factor_rules_path": str(explicit_path),
        }
    )
    assert rules == explicit_payload
    assert Path(loaded_path) == explicit_path.resolve()

    rules, loaded_path = factor_rules.load_factor_rules({"project_dir": str(project_dir)})
    assert rules == env_payload["rules"]
    assert Path(loaded_path) == env_path.resolve()

    monkeypatch.delenv("TRADINGAGENTS_FACTOR_RULES_PATH")
    rules, loaded_path = factor_rules.load_factor_rules({"project_dir": str(project_dir)})
    assert rules == examples_payload
    assert Path(loaded_path) == examples_path.resolve()

    examples_path.unlink()
    rules, loaded_path = factor_rules.load_factor_rules({"project_dir": str(project_dir)})
    assert rules == project_payload["rules"]
    assert Path(loaded_path) == project_path.resolve()


def test_load_factor_rules_raises_on_malformed_payload(tmp_path):
    factor_rules = load_module("factor_rules_invalid", FACTOR_RULES_MODULE_PATH)
    project_dir = tmp_path / "tradingagents"
    examples_dir = project_dir / "examples"
    examples_dir.mkdir(parents=True)

    bad_payload_path = examples_dir / "factor_rules.json"
    bad_payload_path.write_text(json.dumps({"unexpected": []}), encoding="utf-8")

    with pytest.raises(ValueError):
        factor_rules.load_factor_rules({"project_dir": str(project_dir)})


def test_load_factor_rules_raises_on_non_mapping_rule_entries(tmp_path):
    factor_rules = load_module("factor_rules_bad_entries", FACTOR_RULES_MODULE_PATH)
    project_dir = tmp_path / "tradingagents"
    examples_dir = project_dir / "examples"
    examples_dir.mkdir(parents=True)

    bad_payload_path = examples_dir / "factor_rules.json"
    bad_payload_path.write_text(json.dumps(["bad-rule"]), encoding="utf-8")

    with pytest.raises(ValueError):
        factor_rules.load_factor_rules({"project_dir": str(project_dir)})


def test_factor_rule_analyst_returns_summary_without_llm_when_no_rules(tmp_path, monkeypatch):
    factor_rule_analyst = load_module(
        "factor_rule_analyst",
        FACTOR_RULE_ANALYST_MODULE_PATH,
    )

    monkeypatch.setattr(
        factor_rule_analyst,
        "get_config",
        lambda: {"project_dir": str(tmp_path / "tradingagents")},
    )

    llm = RecordingLLM("unused")
    node = factor_rule_analyst.create_factor_rule_analyst(llm)

    result = node(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-03-24",
        }
    )

    assert result["messages"] == []
    assert "No factor rules were loaded for NVDA on 2026-03-24" in result[
        "factor_rules_report"
    ]
    assert llm.prompts == []


def test_graph_setup_adds_factor_rules_only_when_selected(monkeypatch):
    recorded_llms = {}

    monkeypatch.setattr("tradingagents.graph.setup.StateGraph", DummyStateGraph)
    monkeypatch.setattr("tradingagents.graph.setup.create_msg_delete", lambda: "delete")
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_market_analyst",
        make_factory(recorded_llms, "Market Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_social_media_analyst",
        make_factory(recorded_llms, "Social Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_news_analyst",
        make_factory(recorded_llms, "News Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_fundamentals_analyst",
        make_factory(recorded_llms, "Fundamentals Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_macro_analyst",
        make_factory(recorded_llms, "Macro Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_factor_rule_analyst",
        make_factory(recorded_llms, "Factor_rules Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bull_researcher",
        make_factory(recorded_llms, "Bull Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bear_researcher",
        make_factory(recorded_llms, "Bear Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_research_manager",
        make_factory(recorded_llms, "Research Manager"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_trader",
        make_factory(recorded_llms, "Trader"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_aggressive_debator",
        make_factory(recorded_llms, "Aggressive Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_neutral_debator",
        make_factory(recorded_llms, "Neutral Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_conservative_debator",
        make_factory(recorded_llms, "Conservative Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_portfolio_manager",
        make_factory(recorded_llms, "Portfolio Manager"),
    )

    class PartialConditionalLogic:
        def should_continue_market(self, _state):
            return "Msg Clear Market"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={
            "market": "market-tools",
            "social": "social-tools",
            "news": "news-tools",
            "fundamentals": "fundamentals-tools",
            "macro": "macro-tools",
        },
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"factor_rules": "factor-rules-llm"},
    )

    default_graph = setup.setup_graph()
    selected_graph = setup.setup_graph(selected_analysts=["market", "factor_rules"])

    assert "Factor_rules Analyst" not in default_graph["nodes"]
    assert recorded_llms["Factor_rules Analyst"] == "factor-rules-llm"
    assert selected_graph["nodes"]["Factor_rules Analyst"] == "Factor_rules Analyst"
    assert "tools_factor_rules" not in selected_graph["nodes"]
    assert selected_graph["conditional_edges"]["Factor_rules Analyst"][
        "destinations"
    ] == ["Msg Clear Factor_rules"]


def test_downstream_nodes_include_factor_rules_report_in_prompts_and_outputs(
    monkeypatch,
):
    monkeypatch.setattr(
        "tradingagents.agents.managers.research_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )
    monkeypatch.setattr(
        "tradingagents.agents.managers.portfolio_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    state.update(
        {
            "market_report": "Market report",
            "sentiment_report": "Sentiment report",
            "news_report": "News report",
            "fundamentals_report": "Fundamentals report",
            "factor_rules_report": "Factor rules summary",
            "investment_plan": "Existing investment plan",
        }
    )

    bull_llm = RecordingLLM("Bull case")
    create_bull_researcher(bull_llm, DummyMemory())(deepcopy(state))
    assert "Factor rules summary" in bull_llm.prompts[0]

    bear_llm = RecordingLLM("Bear case")
    create_bear_researcher(bear_llm, DummyMemory())(deepcopy(state))
    assert "Factor rules summary" in bear_llm.prompts[0]

    research_llm = RecordingLLM("Research manager output")
    create_research_manager(research_llm, DummyMemory())(deepcopy(state))
    assert "Factor rules summary" in research_llm.prompts[0]

    portfolio_llm = RecordingLLM("Portfolio manager output")
    create_portfolio_manager(portfolio_llm, DummyMemory())(deepcopy(state))
    assert "Factor rules summary" in portfolio_llm.prompts[0]


def test_factor_rules_report_is_seeded_in_state_and_logged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert DEFAULT_CONFIG["factor_rules_path"] is None

    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    assert state["factor_rules_report"] == ""

    state.update(
        {
            "factor_rules_report": "Factor rules summary",
            "trader_investment_plan": "Trader plan",
            "investment_plan": "Investment plan",
            "final_trade_decision": "Buy",
        }
    )

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.log_states_dict = {}
    graph.ticker = "NVDA"

    TradingAgentsGraph._log_state(graph, "2026-03-24", state)

    assert graph.log_states_dict["2026-03-24"]["factor_rules_report"] == (
        "Factor rules summary"
    )

    log_path = (
        tmp_path
        / "eval_results"
        / "NVDA"
        / "TradingAgentsStrategy_logs"
        / "full_states_log_2026-03-24.json"
    )
    logged = json.loads(log_path.read_text(encoding="utf-8"))
    assert logged["2026-03-24"]["factor_rules_report"] == "Factor rules summary"
