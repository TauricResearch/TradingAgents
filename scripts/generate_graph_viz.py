"""Utility script to generate graph visualizations for TradingAgents."""

import os
from unittest.mock import MagicMock

from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.graph.trading_graph import TradingAgentsGraph


def generate_trading_graph():
    print("Generating Trading Agents Graph...")
    
    # We use __new__ and manual setup to avoid requiring real API keys/LLMs
    ta = TradingAgentsGraph.__new__(TradingAgentsGraph)
    
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import GraphSetup
    
    mock_llm = MagicMock()
    setup = GraphSetup(
        quick_thinking_llm=mock_llm,
        mid_thinking_llm=mock_llm,
        deep_thinking_llm=mock_llm,
        bull_memory=MagicMock(),
        bear_memory=MagicMock(),
        trader_memory=MagicMock(),
        invest_judge_memory=MagicMock(),
        portfolio_manager_memory=MagicMock(),
        conditional_logic=ConditionalLogic(),
    )
    ta.graph = setup.setup_graph()
    
    # Save visualizations
    ta.visualize(output_path="docs/trading_graph.mermaid", format="mermaid")
    try:
        ta.visualize(output_path="trading_graph.png", format="png")
        print(" -> Saved trading_graph.png")
    except Exception as e:
        print(f" -> Could not save PNG: {e}")

def generate_scanner_graph():
    print("Generating Scanner Graph...")
    
    from tradingagents.graph.scanner_setup import ScannerGraphSetup
    agents = {node: MagicMock() for node in [
        "gatekeeper_scanner", "geopolitical_scanner", "market_movers_scanner", "sector_scanner",
        "factor_alignment_scanner", "drift_scanner", "smart_money_scanner", "industry_deep_dive",
        "macro_synthesis", "summarize_gatekeeper", "summarize_geopolitical", "summarize_market_movers",
        "summarize_sector", "summarize_factor_alignment", "summarize_drift", "summarize_smart_money",
        "summarize_industry_deep_dive"
    ]}
    
    sg = ScannerGraph.__new__(ScannerGraph)
    setup = ScannerGraphSetup(agents)
    sg.graph = setup.setup_graph()
    
    sg.visualize(output_path="docs/scanner_graph.mermaid", format="mermaid")
    try:
        sg.visualize(output_path="scanner_graph.png", format="png")
        print(" -> Saved scanner_graph.png")
    except Exception as e:
        print(f" -> Could not save PNG: {e}")

def generate_portfolio_graph():
    print("Generating Portfolio Graph...")
    
    from tradingagents.graph.portfolio_setup import PortfolioGraphSetup
    agents = {node: MagicMock() for node in [
        "review_holdings", "macro_summary", "micro_summary", "pm_decision"
    ]}
    
    pg = PortfolioGraph.__new__(PortfolioGraph)
    setup = PortfolioGraphSetup(
        agents=agents, 
        repo=MagicMock(), 
        config={}, 
        macro_memory=MagicMock(), 
        micro_memory=MagicMock()
    )
    pg.graph = setup.setup_graph()
    
    pg.visualize(output_path="docs/portfolio_graph.mermaid", format="mermaid")
    try:
        pg.visualize(output_path="portfolio_graph.png", format="png")
        print(" -> Saved portfolio_graph.png")
    except Exception as e:
        print(f" -> Could not save PNG: {e}")

if __name__ == "__main__":
    # Ensure docs directory exists
    os.makedirs("docs", exist_ok=True)
    
    generate_trading_graph()
    generate_scanner_graph()
    generate_portfolio_graph()
    print("\nGraph generation complete.")
