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
        bull_memory=None, bear_memory=None, trader_memory=None,
        invest_judge_memory=None, portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    with patch("tradingagents.graph.setup.create_market_analyst") as mock_create:
        with patch("tradingagents.graph.setup.create_social_media_analyst"), \
             patch("tradingagents.graph.setup.create_news_analyst"), \
             patch("tradingagents.graph.setup.create_news_fact_checker"), \
             patch("tradingagents.graph.setup.create_fundamentals_analyst"), \
             patch("tradingagents.graph.setup.create_bull_researcher"), \
             patch("tradingagents.graph.setup.create_bear_researcher"), \
             patch("tradingagents.graph.setup.create_research_manager"), \
             patch("tradingagents.graph.setup.create_trader"), \
             patch("tradingagents.graph.setup.create_aggressive_debator"), \
             patch("tradingagents.graph.setup.create_neutral_debator"), \
             patch("tradingagents.graph.setup.create_conservative_debator"), \
             patch("tradingagents.graph.setup.create_risk_synthesis"), \
             patch("tradingagents.graph.setup.create_risk_round_barrier"), \
             patch("tradingagents.graph.setup.create_critical_abort_terminal"), \
             patch("tradingagents.graph.setup.create_portfolio_manager"):
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
        bull_memory=None, bear_memory=None, trader_memory=None,
        invest_judge_memory=None, portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )

    with patch("tradingagents.graph.setup.create_social_media_analyst") as mock_create:
        with patch("tradingagents.graph.setup.create_market_analyst"), \
             patch("tradingagents.graph.setup.create_news_analyst"), \
             patch("tradingagents.graph.setup.create_news_fact_checker"), \
             patch("tradingagents.graph.setup.create_fundamentals_analyst"), \
             patch("tradingagents.graph.setup.create_bull_researcher"), \
             patch("tradingagents.graph.setup.create_bear_researcher"), \
             patch("tradingagents.graph.setup.create_research_manager"), \
             patch("tradingagents.graph.setup.create_trader"), \
             patch("tradingagents.graph.setup.create_aggressive_debator"), \
             patch("tradingagents.graph.setup.create_neutral_debator"), \
             patch("tradingagents.graph.setup.create_conservative_debator"), \
             patch("tradingagents.graph.setup.create_risk_synthesis"), \
             patch("tradingagents.graph.setup.create_risk_round_barrier"), \
             patch("tradingagents.graph.setup.create_critical_abort_terminal"), \
             patch("tradingagents.graph.setup.create_portfolio_manager"):
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
        bull_memory=None, bear_memory=None, trader_memory=None,
        invest_judge_memory=None, portfolio_manager_memory=None,
        conditional_logic=MagicMock(),
        news_evidence_store=news_evidence_store,
    )
    
    # We need to mock create_fundamentals_analyst to see what LLM it was called with
    with patch("tradingagents.graph.setup.create_fundamentals_analyst") as mock_create:
        # Also need to mock other analysts created in setup_graph
        with patch("tradingagents.graph.setup.create_market_analyst"), \
             patch("tradingagents.graph.setup.create_social_media_analyst"), \
             patch("tradingagents.graph.setup.create_news_analyst"), \
             patch("tradingagents.graph.setup.create_news_fact_checker"), \
             patch("tradingagents.graph.setup.create_bull_researcher"), \
             patch("tradingagents.graph.setup.create_bear_researcher"), \
             patch("tradingagents.graph.setup.create_research_manager"), \
             patch("tradingagents.graph.setup.create_trader"), \
             patch("tradingagents.graph.setup.create_aggressive_debator"), \
             patch("tradingagents.graph.setup.create_neutral_debator"), \
             patch("tradingagents.graph.setup.create_conservative_debator"), \
             patch("tradingagents.graph.setup.create_risk_synthesis"), \
             patch("tradingagents.graph.setup.create_risk_round_barrier"), \
             patch("tradingagents.graph.setup.create_critical_abort_terminal"), \
             patch("tradingagents.graph.setup.create_portfolio_manager"):
            
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

    with patch("tradingagents.graph.setup.create_news_analyst") as mock_news_analyst, \
         patch("tradingagents.graph.setup.create_news_fact_checker") as mock_fact_checker, \
         patch("tradingagents.graph.setup.create_market_analyst"), \
         patch("tradingagents.graph.setup.create_social_media_analyst"), \
         patch("tradingagents.graph.setup.create_fundamentals_analyst"), \
         patch("tradingagents.graph.setup.create_bull_researcher"), \
         patch("tradingagents.graph.setup.create_bear_researcher"), \
         patch("tradingagents.graph.setup.create_research_manager"), \
         patch("tradingagents.graph.setup.create_trader"), \
         patch("tradingagents.graph.setup.create_aggressive_debator"), \
         patch("tradingagents.graph.setup.create_neutral_debator"), \
         patch("tradingagents.graph.setup.create_conservative_debator"), \
         patch("tradingagents.graph.setup.create_risk_synthesis"), \
         patch("tradingagents.graph.setup.create_risk_round_barrier"), \
         patch("tradingagents.graph.setup.create_critical_abort_terminal"), \
         patch("tradingagents.graph.setup.create_portfolio_manager"):
        setup.setup_graph(selected_analysts=["news"])

    mock_news_analyst.assert_called_once_with(quick_llm, news_evidence_store)
    mock_fact_checker.assert_called_once_with(news_evidence_store)


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


def test_build_debate_subgraph_skips_research_packet_summary_node():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = GraphSetup(
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

    with patch("tradingagents.graph.setup.create_bull_researcher", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_bear_researcher", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_research_manager", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_trader", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_aggressive_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_conservative_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_neutral_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_risk_round_barrier", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_risk_synthesis", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_critical_abort_terminal", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_portfolio_manager", return_value=MagicMock()):
        setup.build_debate_subgraph()


def test_build_risk_subgraph_skips_research_packet_summary_node():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    setup = GraphSetup(
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

    with patch("tradingagents.graph.setup.create_aggressive_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_conservative_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_neutral_debator", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_risk_round_barrier", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_risk_synthesis", return_value=MagicMock()), \
         patch("tradingagents.graph.setup.create_portfolio_manager", return_value=MagicMock()):
        setup.build_risk_subgraph()
