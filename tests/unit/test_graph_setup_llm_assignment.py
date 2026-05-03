from unittest.mock import MagicMock, patch

from tradingagents.graph.setup import GraphSetup


def test_market_analyst_uses_quick_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")

    news_evidence_store = MagicMock(name="news_evidence_store")

    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        bull_memory=None,
        bear_memory=None,
        trader_memory=None,
        invest_judge_memory=None,
        portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    with patch("tradingagents.graph.setup.create_market_analyst") as mock_create:
        with (
            patch("tradingagents.graph.setup.create_social_media_analyst"),
            patch("tradingagents.graph.setup.create_news_analyst"),
            patch("tradingagents.graph.setup.create_news_fact_checker"),
            patch("tradingagents.graph.setup.create_fundamentals_analyst"),
            patch("tradingagents.graph.setup.create_bull_researcher"),
            patch("tradingagents.graph.setup.create_bear_researcher"),
            patch("tradingagents.graph.setup.create_research_manager"),
            patch("tradingagents.graph.setup.create_trader"),
            patch("tradingagents.graph.setup.create_aggressive_debator"),
            patch("tradingagents.graph.setup.create_neutral_debator"),
            patch("tradingagents.graph.setup.create_conservative_debator"),
            patch("tradingagents.graph.setup.create_risk_synthesis"),
            patch("tradingagents.graph.setup.create_risk_round_barrier"),
            patch("tradingagents.graph.setup.create_critical_abort_terminal"),
            patch("tradingagents.graph.setup.create_portfolio_manager"),
        ):
            setup.setup_graph(selected_analysts=["market"])
            mock_create.assert_called_once_with(quick_llm)


def test_social_analyst_uses_quick_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")

    news_evidence_store = MagicMock(name="news_evidence_store")

    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        bull_memory=None,
        bear_memory=None,
        trader_memory=None,
        invest_judge_memory=None,
        portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    with patch("tradingagents.graph.setup.create_social_media_analyst") as mock_create:
        with (
            patch("tradingagents.graph.setup.create_market_analyst"),
            patch("tradingagents.graph.setup.create_news_analyst"),
            patch("tradingagents.graph.setup.create_news_fact_checker"),
            patch("tradingagents.graph.setup.create_fundamentals_analyst"),
            patch("tradingagents.graph.setup.create_bull_researcher"),
            patch("tradingagents.graph.setup.create_bear_researcher"),
            patch("tradingagents.graph.setup.create_research_manager"),
            patch("tradingagents.graph.setup.create_trader"),
            patch("tradingagents.graph.setup.create_aggressive_debator"),
            patch("tradingagents.graph.setup.create_neutral_debator"),
            patch("tradingagents.graph.setup.create_conservative_debator"),
            patch("tradingagents.graph.setup.create_risk_synthesis"),
            patch("tradingagents.graph.setup.create_risk_round_barrier"),
            patch("tradingagents.graph.setup.create_critical_abort_terminal"),
            patch("tradingagents.graph.setup.create_portfolio_manager"),
        ):
            setup.setup_graph(selected_analysts=["social"])
            mock_create.assert_called_once_with(quick_llm)


def test_fundamentals_analyst_uses_quick_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")

    # Mock other dependencies
    news_evidence_store = MagicMock(name="news_evidence_store")

    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        bull_memory=None,
        bear_memory=None,
        trader_memory=None,
        invest_judge_memory=None,
        portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    # We need to mock create_fundamentals_analyst to see what LLM it was called with
    with patch("tradingagents.graph.setup.create_fundamentals_analyst") as mock_create:
        # Also need to mock other analysts created in setup_graph
        with (
            patch("tradingagents.graph.setup.create_market_analyst"),
            patch("tradingagents.graph.setup.create_social_media_analyst"),
            patch("tradingagents.graph.setup.create_news_analyst"),
            patch("tradingagents.graph.setup.create_news_fact_checker"),
            patch("tradingagents.graph.setup.create_bull_researcher"),
            patch("tradingagents.graph.setup.create_bear_researcher"),
            patch("tradingagents.graph.setup.create_research_manager"),
            patch("tradingagents.graph.setup.create_trader"),
            patch("tradingagents.graph.setup.create_aggressive_debator"),
            patch("tradingagents.graph.setup.create_neutral_debator"),
            patch("tradingagents.graph.setup.create_conservative_debator"),
            patch("tradingagents.graph.setup.create_risk_synthesis"),
            patch("tradingagents.graph.setup.create_risk_round_barrier"),
            patch("tradingagents.graph.setup.create_critical_abort_terminal"),
            patch("tradingagents.graph.setup.create_portfolio_manager"),
        ):
            setup.setup_graph(selected_analysts=["fundamentals"])
            mock_create.assert_called_once_with(quick_llm)


def test_news_analyst_and_fact_checker_share_injected_evidence_store():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    news_evidence_store = MagicMock(name="news_evidence_store")

    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        bull_memory=None,
        bear_memory=None,
        trader_memory=None,
        invest_judge_memory=None,
        portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    with (
        patch("tradingagents.graph.setup.create_news_analyst") as mock_news_analyst,
        patch("tradingagents.graph.setup.create_news_fact_checker") as mock_fact_checker,
        patch("tradingagents.graph.setup.create_market_analyst"),
        patch("tradingagents.graph.setup.create_social_media_analyst"),
        patch("tradingagents.graph.setup.create_fundamentals_analyst"),
        patch("tradingagents.graph.setup.create_bull_researcher"),
        patch("tradingagents.graph.setup.create_bear_researcher"),
        patch("tradingagents.graph.setup.create_research_manager"),
        patch("tradingagents.graph.setup.create_trader"),
        patch("tradingagents.graph.setup.create_aggressive_debator"),
        patch("tradingagents.graph.setup.create_neutral_debator"),
        patch("tradingagents.graph.setup.create_conservative_debator"),
        patch("tradingagents.graph.setup.create_risk_synthesis"),
        patch("tradingagents.graph.setup.create_risk_round_barrier"),
        patch("tradingagents.graph.setup.create_critical_abort_terminal"),
        patch("tradingagents.graph.setup.create_portfolio_manager"),
    ):
        setup.setup_graph(selected_analysts=["news"])

    mock_news_analyst.assert_called_once_with(quick_llm, news_evidence_store)
    mock_fact_checker.assert_called_once_with(news_evidence_store)


def _make_setup(quick_llm, mid_llm, deep_llm):
    """Build a GraphSetup with the given LLM mocks."""
    return GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        bull_memory=MagicMock(),
        bear_memory=MagicMock(),
        trader_memory=MagicMock(),
        invest_judge_memory=MagicMock(),
        portfolio_manager_memory=MagicMock(),
        conditional_logic=MagicMock(),
        news_evidence_store=MagicMock(),
    )


_ALL_ANALYST_PATCHES = [
    "tradingagents.graph.setup.create_market_analyst",
    "tradingagents.graph.setup.create_social_media_analyst",
    "tradingagents.graph.setup.create_news_analyst",
    "tradingagents.graph.setup.create_news_fact_checker",
    "tradingagents.graph.setup.create_fundamentals_analyst",
    "tradingagents.graph.setup.create_bull_researcher",
    "tradingagents.graph.setup.create_bear_researcher",
    "tradingagents.graph.setup.create_research_manager",
    "tradingagents.graph.setup.create_trader",
    "tradingagents.graph.setup.create_aggressive_debator",
    "tradingagents.graph.setup.create_neutral_debator",
    "tradingagents.graph.setup.create_conservative_debator",
    "tradingagents.graph.setup.create_risk_synthesis",
    "tradingagents.graph.setup.create_risk_round_barrier",
    "tradingagents.graph.setup.create_critical_abort_terminal",
    "tradingagents.graph.setup.create_portfolio_manager",
]


def _patches_except(*keep: str):
    """Return all patch targets except those in *keep."""
    return [p for p in _ALL_ANALYST_PATCHES if not any(p.endswith(k) for k in keep)]


# ---------------------------------------------------------------------------
# LLM tier assignments for high-stakes nodes
# ---------------------------------------------------------------------------


def test_bull_researcher_uses_mid_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_bull_researcher") as mock_create:
        patches = [patch(p) for p in _patches_except("create_bull_researcher")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    # Bull researcher should receive mid_llm, not quick or deep
    call_args = mock_create.call_args
    assert call_args[0][0] is mid_llm, (
        f"Bull researcher got {call_args[0][0].name!r}, expected mid_llm"
    )


def test_bear_researcher_uses_mid_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_bear_researcher") as mock_create:
        patches = [patch(p) for p in _patches_except("create_bear_researcher")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    call_args = mock_create.call_args
    assert call_args[0][0] is mid_llm, (
        f"Bear researcher got {call_args[0][0].name!r}, expected mid_llm"
    )


def test_trader_uses_mid_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_trader") as mock_create:
        patches = [patch(p) for p in _patches_except("create_trader")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    call_args = mock_create.call_args
    assert call_args[0][0] is mid_llm, (
        f"Trader got {call_args[0][0].name!r}, expected mid_llm"
    )


def test_research_manager_uses_deep_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_research_manager") as mock_create:
        patches = [patch(p) for p in _patches_except("create_research_manager")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    call_args = mock_create.call_args
    assert call_args[0][0] is deep_llm, (
        f"Research manager got {call_args[0][0].name!r}, expected deep_llm"
    )


def test_risk_synthesis_uses_mid_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_risk_synthesis") as mock_create:
        patches = [patch(p) for p in _patches_except("create_risk_synthesis")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    call_args = mock_create.call_args
    assert call_args[0][0] is mid_llm, (
        f"Risk synthesis got {call_args[0][0].name!r}, expected mid_llm"
    )


def test_portfolio_manager_uses_deep_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = _make_setup(quick_llm, mid_llm, deep_llm)

    with patch("tradingagents.graph.setup.create_portfolio_manager") as mock_create:
        patches = [patch(p) for p in _patches_except("create_portfolio_manager")]
        for p in patches:
            p.start()
        try:
            setup.setup_graph(selected_analysts=["market"])
        finally:
            for p in patches:
                p.stop()

    call_args = mock_create.call_args
    assert call_args[0][0] is deep_llm, (
        f"Portfolio manager got {call_args[0][0].name!r}, expected deep_llm"
    )


def test_resolve_next_analyst_node_skips_preloaded_market_report():
    state = {"market_report": "saved market report"}

    next_node = GraphSetup._resolve_next_analyst_node(
        state,
        ["market", "news", "fundamentals"],
        0,
    )

    assert next_node == "News Analyst"


def test_resolve_next_analyst_node_falls_through_to_bull_researcher_when_all_selected_are_seeded():
    state = {"market_report": "saved market report"}

    next_node = GraphSetup._resolve_next_analyst_node(
        state,
        ["market"],
        0,
    )

    assert next_node == "Bull Researcher"


