from langgraph.prebuilt import ToolNode
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.xau_config import XAU_CONFIG

# Import XAU-specific tools
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_correlation,
    get_dxy_data,
    get_real_yields,
    get_inflation_data,
    get_fred_series,
    get_news,
    get_global_news,
    get_cot_positioning,
    analyze_cot_extremes,
    get_gold_etf_summary,
    get_gold_etf_flows,
)

class XAUTradingGraph(TradingAgentsGraph):
    """
    A specialized trading graph for XAU (Gold) trading.

    This graph uses a custom set of agents and tools tailored for macroeconomic
    and positioning analysis relevant to gold.
    """

    def __init__(self, debug=False, config=None):
        # Use XAU-specific config and analyst team
        """
        Initialize the XAUTradingGraph with XAU-specific configuration and analyst team.
        
        Parameters:
            debug (bool): Enable debug mode when True.
            config (dict | None): Optional configuration dictionary to override the default XAU_CONFIG; the analyst team is taken from this config's "analyst_team" key if present.
        """
        xau_config = config or XAU_CONFIG
        xau_analysts = xau_config.get("analyst_team", [])

        super().__init__(
            selected_analysts=xau_analysts,
            debug=debug,
            config=xau_config
        )

    def _create_tool_nodes(self):
        """
        Constructs the XAU-specific mapping of tool nodes used by the trading graph.
        
        Groups related analysis tools into four ToolNode entries for market data, macroeconomic indicators, news, and positioning/ETF flows.
        
        Returns:
            dict: Mapping of tool node names to ToolNode instances:
                - "xau_market": market data and indicator tools
                - "xau_macro": macroeconomic and FRED-series tools
                - "xau_news": news aggregation tools
                - "xau_positioning": positioning, COT analysis, and gold ETF tools
        """
        return {
            "xau_market": ToolNode([
                get_stock_data,       # For XAU/USD price data from yfinance (e.g., "GC=F")
                get_indicators,       # Standard technical indicators
                get_correlation,      # For correlation with DXY, etc.
            ]),
            "xau_macro": ToolNode([
                get_dxy_data,
                get_real_yields,
                get_inflation_data,
                get_fred_series,      # For VIX, etc.
            ]),
            "xau_news": ToolNode([
                get_news,             # For general and gold-specific news
                get_global_news,
            ]),
            "xau_positioning": ToolNode([
                get_cot_positioning,
                analyze_cot_extremes,
                get_gold_etf_summary,
                get_gold_etf_flows,
            ]),
        }