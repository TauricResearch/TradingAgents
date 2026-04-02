from unittest.mock import MagicMock, patch
from tradingagents.graph.setup import GraphSetup

def test_fundamentals_analyst_uses_mid_llm():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    
    # Mock other dependencies
    tool_nodes = {
        "market": MagicMock(),
        "social": MagicMock(),
        "news": MagicMock(),
        "fundamentals": MagicMock(),
    }
    news_evidence_store = MagicMock(name="news_evidence_store")
    
    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        tool_nodes=tool_nodes,
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
             patch("tradingagents.graph.setup.create_research_packet_summary"), \
             patch("tradingagents.graph.setup.create_investment_debate_summary"), \
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
            mock_create.assert_called_once_with(mid_llm)


def test_news_analyst_and_fact_checker_share_injected_evidence_store():
    quick_llm = MagicMock(name="quick")
    mid_llm = MagicMock(name="mid")
    deep_llm = MagicMock(name="deep")
    tool_nodes = {
        "market": MagicMock(),
        "social": MagicMock(),
        "news": MagicMock(),
        "fundamentals": MagicMock(),
    }
    news_evidence_store = MagicMock(name="news_evidence_store")

    setup = GraphSetup(
        quick_thinking_llm=quick_llm,
        mid_thinking_llm=mid_llm,
        deep_thinking_llm=deep_llm,
        tool_nodes=tool_nodes,
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
         patch("tradingagents.graph.setup.create_research_packet_summary"), \
         patch("tradingagents.graph.setup.create_investment_debate_summary"), \
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

    mock_news_analyst.assert_called_once_with(mid_llm, news_evidence_store)
    mock_fact_checker.assert_called_once_with(news_evidence_store)
