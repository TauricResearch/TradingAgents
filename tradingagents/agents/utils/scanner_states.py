"""State definitions for the Global Macro Scanner graph."""

from typing import Annotated
from langgraph.graph import MessagesState


class ScannerState(MessagesState):
    """
    State for the macro scanner workflow.
    
    The scanner discovers interesting stocks through multiple phases:
    - Phase 1: Parallel scanners (geopolitical, market movers, sectors)
    - Phase 2: Industry deep dive (cross-references phase 1 outputs)
    - Phase 3: Macro synthesis (produces final top-10 watchlist)
    """
    
    # Input
    scan_date: Annotated[str, "Date of the scan in YYYY-MM-DD format"]
    
    # Phase 1: Parallel scanner outputs
    geopolitical_report: Annotated[
        str, 
        "Report from Geopolitical Scanner analyzing global news, geopolitical events, and macro trends"
    ]
    market_movers_report: Annotated[
        str, 
        "Report from Market Movers Scanner analyzing top gainers, losers, most active stocks, and index performance"
    ]
    sector_performance_report: Annotated[
        str, 
        "Report from Sector Scanner analyzing all 11 GICS sectors performance and trends"
    ]
    
    # Phase 2: Deep dive output
    industry_deep_dive_report: Annotated[
        str, 
        "Report from Industry Deep Dive agent analyzing specific industries within top performing sectors"
    ]
    
    # Phase 3: Final output
    macro_scan_summary: Annotated[
        str, 
        "Final macro scan summary with top-10 stock watchlist and market overview"
    ]
    
    # Optional: Sender tracking (for debugging/logging)
    sender: Annotated[str, "Agent that sent the current message"] = ""
