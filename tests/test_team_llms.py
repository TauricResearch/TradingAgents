"""Per-team LLM clients: each team on the desk can run on its own key and models.

The desk groups its roles into five teams (analysts, research, trader, risk,
portfolio). ``team_llms`` lets a team use its own API key, endpoint, or models,
so a gateway that bills by key can split spend by team. These tests record
which client every role is built with; no model is called.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import setup, trading_graph

ROLE_FACTORIES = {
    "market": "create_market_analyst",
    "social": "create_sentiment_analyst",
    "news": "create_news_analyst",
    "fundamentals": "create_fundamentals_analyst",
    "bull": "create_bull_researcher",
    "bear": "create_bear_researcher",
    "research_manager": "create_research_manager",
    "trader": "create_trader",
    "aggressive": "create_aggressive_debator",
    "neutral": "create_neutral_debator",
    "conservative": "create_conservative_debator",
    "portfolio_manager": "create_portfolio_manager",
}

TEAM_ROLES = {
    "analysts": ("market", "social", "news", "fundamentals"),
    "research": ("bull", "bear", "research_manager"),
    "trader": ("trader",),
    "risk": ("aggressive", "neutral", "conservative"),
    "portfolio": ("portfolio_manager",),
}

KEY_ENVS = {team: f"TEST_{team.upper()}_KEY" for team in TEAM_ROLES}


class _Client:
    def __init__(self, model, base_url, kwargs):
        self._llm = SimpleNamespace(model=model, base_url=base_url, api_key=kwargs.get("api_key"))

    def get_llm(self):
        return self._llm


@pytest.fixture
def build(tmp_path, monkeypatch):
    """Build the graph with fake clients; return it and the LLM each role got."""
    roles: dict = {}

    monkeypatch.setattr(
        trading_graph, "create_llm_client",
        lambda provider, model, base_url=None, **kw: _Client(model, base_url, kw),
    )
    for role, name in ROLE_FACTORIES.items():
        monkeypatch.setattr(
            setup, name,
            lambda llm, _role=role: roles.__setitem__(_role, llm) or (lambda state: {}),
        )

    def _build(**config):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(
            results_dir=str(tmp_path / "results"), data_cache_dir=str(tmp_path / "cache"),
            memory_log_path=str(tmp_path / "log.md"),
            llm_provider="openai_compatible", backend_url="http://default/v1",
            quick_think_llm="quick-default", deep_think_llm="deep-default",
            **config,
        )
        graph = trading_graph.TradingAgentsGraph(config=cfg)
        return graph, roles

    return _build


@pytest.fixture
def team_keys(monkeypatch):
    for team, env in KEY_ENVS.items():
        monkeypatch.setenv(env, f"key-{team}")
    return {team: {"api_key_env": env} for team, env in KEY_ENVS.items()}


@pytest.mark.unit
def test_team_llms_unset_builds_shared_clients(build):
    graph, roles = build()

    deep_roles = {"research_manager", "portfolio_manager"}
    quick = {id(llm) for role, llm in roles.items() if role not in deep_roles}
    deep = {id(llm) for role, llm in roles.items() if role in deep_roles}
    assert quick == {id(graph.quick_thinking_llm)}
    assert deep == {id(graph.deep_thinking_llm)}
    assert graph.reflector.quick_thinking_llm is graph.quick_thinking_llm


@pytest.mark.unit
def test_each_team_bills_its_own_key(build, team_keys):
    _, roles = build(team_llms=team_keys)

    for team, members in TEAM_ROLES.items():
        for role in members:
            assert roles[role].api_key == f"key-{team}", role


@pytest.mark.unit
def test_team_keeps_quick_and_deep_split(build, monkeypatch):
    monkeypatch.setenv("TEST_RESEARCH_KEY", "key-research")
    _, roles = build(team_llms={"research": {
        "api_key_env": "TEST_RESEARCH_KEY",
        "quick_think_llm": "research-quick", "deep_think_llm": "research-deep",
        "backend_url": "http://research/v1",
    }})

    assert roles["bull"].model == "research-quick"
    assert roles["bear"].model == "research-quick"
    assert roles["research_manager"].model == "research-deep"
    assert roles["research_manager"].base_url == "http://research/v1"
    assert roles["research_manager"].api_key == "key-research"


@pytest.mark.unit
def test_reflector_uses_portfolio_team(build, team_keys):
    graph, _ = build(team_llms=team_keys)

    assert graph.reflector.quick_thinking_llm.api_key == "key-portfolio"


@pytest.mark.unit
def test_unlisted_team_uses_default_clients(build, monkeypatch):
    monkeypatch.setenv("TEST_TRADER_KEY", "key-trader")
    graph, roles = build(team_llms={"trader": {"api_key_env": "TEST_TRADER_KEY"}})

    assert roles["trader"].api_key == "key-trader"
    assert roles["market"] is graph.quick_thinking_llm
    assert roles["research_manager"] is graph.deep_thinking_llm
    assert roles["portfolio_manager"] is graph.deep_thinking_llm


@pytest.mark.unit
def test_unknown_team_rejected(build):
    with pytest.raises(ValueError, match="reserch") as exc:
        build(team_llms={"reserch": {"quick_think_llm": "m"}})
    for team in TEAM_ROLES:
        assert team in str(exc.value)


@pytest.mark.unit
def test_unknown_team_field_rejected(build):
    with pytest.raises(ValueError, match="api_key_evn"):
        build(team_llms={"trader": {"api_key_evn": "TEST_TRADER_KEY"}})


@pytest.mark.unit
def test_unset_key_env_fails_without_leaking(build, monkeypatch):
    monkeypatch.delenv("TEST_RISK_KEY", raising=False)
    monkeypatch.setenv("TEST_TRADER_KEY", "sentinel-secret-value")

    with pytest.raises(ValueError, match="TEST_RISK_KEY") as exc:
        build(team_llms={
            "trader": {"api_key_env": "TEST_TRADER_KEY"},
            "risk": {"api_key_env": "TEST_RISK_KEY"},
        })
    assert "sentinel-secret-value" not in str(exc.value)


@pytest.mark.unit
def test_empty_key_env_rejected(build, monkeypatch):
    monkeypatch.setenv("TEST_RISK_KEY", "")

    with pytest.raises(ValueError, match="TEST_RISK_KEY"):
        build(team_llms={"risk": {"api_key_env": "TEST_RISK_KEY"}})
