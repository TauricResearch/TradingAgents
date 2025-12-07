"""
TradingAgentsX service integration
"""
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging

# Add parent directory to path to import tradingagents
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tradingagents.graph.trading_graph import TradingAgentsXGraph
from tradingagents.default_config import DEFAULT_CONFIG
from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class TradingService:
    """Service class for interacting with TradingAgentsX"""
    
    def __init__(self):
        self.default_config = DEFAULT_CONFIG.copy()
        
    def create_config(
        self,
        research_depth: int = 1,
        deep_think_llm: str = "gpt-5-mini-2025-08-07",
        quick_think_llm: str = "gpt-5-mini-2025-08-07",
    ) -> Dict[str, Any]:
        """Create configuration for TradingAgentsX"""
        config = self.default_config.copy()
        config["max_debate_rounds"] = research_depth
        config["max_risk_discuss_rounds"] = research_depth
        config["deep_think_llm"] = deep_think_llm
        config["quick_think_llm"] = quick_think_llm
        config["results_dir"] = settings.results_dir
        return config
    
    async def run_analysis(
        self,
        ticker: str,
        analysis_date: str,
        openai_api_key: Optional[str] = None,
        openai_base_url: str = "https://api.openai.com/v1",
        quick_think_base_url: str = "https://api.openai.com/v1",
        deep_think_base_url: str = "https://api.openai.com/v1",
        quick_think_api_key: Optional[str] = None,
        deep_think_api_key: Optional[str] = None,
        embedding_base_url: str = "https://api.openai.com/v1",
        embedding_api_key: Optional[str] = None,
        alpha_vantage_api_key: Optional[str] = None,
        analysts: Optional[List[str]] = None,
        research_depth: int = 1,
        deep_think_llm: str = "gpt-5-mini-2025-08-07",
        quick_think_llm: str = "gpt-5-mini-2025-08-07",
    ) -> Dict[str, Any]:
        """
        Run trading analysis for a given ticker and date with user-provided API keys
        
        Args:
            ticker: Stock ticker symbol
            analysis_date: Date in YYYY-MM-DD format
            openai_api_key: OpenAI API Key (required)
            openai_base_url: OpenAI API Base URL (optional, deprecated)
            quick_think_base_url: Base URL for Quick Thinking Model
            deep_think_base_url: Base URL for Deep Thinking Model
            alpha_vantage_api_key: Alpha Vantage API Key (optional)
            analysts: List of analyst types to include
            research_depth: Research depth (1-5)
            deep_think_llm: Deep thinking LLM model
            quick_think_llm: Quick thinking LLM model
            
        Returns:
            Dict containing analysis results
        """
        try:
            # Default analysts if not provided
            if analysts is None:
                analysts = ["market", "social", "news", "fundamentals"]
            
            # Dynamically set environment variables for this request
            import os
            original_openai_key = os.environ.get("OPENAI_API_KEY")
            original_alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
            
            try:
                # Set Alpha Vantage API key if provided
                if alpha_vantage_api_key:
                    os.environ["ALPHA_VANTAGE_API_KEY"] = alpha_vantage_api_key
                
                # Create configuration
                logger.info(f"Initializing TradingAgentsX for {ticker} on {analysis_date}")
                config = self.create_config(research_depth, deep_think_llm, quick_think_llm)
                
                # Normalize base URLs (ensure lowercase paths, common issue with custom endpoints)
                def normalize_base_url(url: str) -> str:
                    """Normalize base URL to ensure proper formatting"""
                    if url:
                        # Replace common case variations
                        url = url.replace("/V1", "/v1")
                        url = url.replace("/V2", "/v2")
                    return url
                
                # Override with user-provided settings
                config["llm_provider"] = "openai"
                # Use specific base URLs if provided, otherwise fallback to openai_base_url
                config["quick_think_base_url"] = normalize_base_url(
                    quick_think_base_url if quick_think_base_url != "https://api.openai.com/v1" else openai_base_url
                )
                config["deep_think_base_url"] = normalize_base_url(
                    deep_think_base_url if deep_think_base_url != "https://api.openai.com/v1" else openai_base_url
                )
                # Set backend_url as a fallback
                config["backend_url"] = normalize_base_url(openai_base_url)
                
                # Resolve API keys: Use specific key if provided, else fallback to openai_api_key (legacy/shared)
                # Note: For non-OpenAI providers, the user MUST provide the specific key if it differs from the shared one.
                config["quick_think_api_key"] = quick_think_api_key if quick_think_api_key else openai_api_key
                config["deep_think_api_key"] = deep_think_api_key if deep_think_api_key else openai_api_key
                config["embedding_base_url"] = normalize_base_url(embedding_base_url)
                config["embedding_api_key"] = embedding_api_key if embedding_api_key else openai_api_key
                
                # Initialize TradingAgentsX graph
                graph = TradingAgentsXGraph(analysts, config=config, debug=True)
                
                # Run analysis
                logger.info(f"Running analysis for {ticker}")
                final_state, decision = graph.propagate(ticker, analysis_date)
            
                # Extract reports from final state
                reports = {
                    "market_report": final_state.get("market_report"),
                    "sentiment_report": final_state.get("sentiment_report"),
                    "news_report": final_state.get("news_report"),
                    "fundamentals_report": final_state.get("fundamentals_report"),
                    "investment_plan": final_state.get("investment_plan"),
                    "trader_investment_plan": final_state.get("trader_investment_plan"),
                    "final_trade_decision": final_state.get("final_trade_decision"),
                    "investment_debate_state": final_state.get("investment_debate_state"),
                    "risk_debate_state": final_state.get("risk_debate_state"),
                }
                
                # Load price data
                from backend.app.services.price_service import PriceService
                price_data = None
                price_stats = None
                
                try:
                    price_df = PriceService.load_price_data(ticker, config.get("data_cache_dir"))
                    if price_df is not None:
                        price_data = PriceService.prepare_chart_data(price_df)
                        price_stats = PriceService.calculate_stats(price_df)
                        logger.info(f"Loaded {len(price_data)} price data points for {ticker}")
                except Exception as e:
                    logger.warning(f"Could not load price data for {ticker}: {e}")
                
                return {
                    "status": "success",
                    "ticker": ticker,
                    "analysis_date": analysis_date,
                    "decision": decision,
                    "reports": reports,
                    "price_data": price_data,
                    "price_stats": price_stats,
                }
                
            finally:
                # Clean up environment variables after request
                # Clean up environment variables after request
                if original_openai_key is not None:
                    os.environ["OPENAI_API_KEY"] = original_openai_key
                elif openai_api_key and "OPENAI_API_KEY" in os.environ:
                    # Only delete if we set it (and there was no original key)
                    del os.environ["OPENAI_API_KEY"]
                    
                if original_alpha_key is not None:
                    os.environ["ALPHA_VANTAGE_API_KEY"] = original_alpha_key
                elif "ALPHA_VANTAGE_API_KEY" in os.environ:
                    del os.environ["ALPHA_VANTAGE_API_KEY"]
            
        except Exception as e:
            logger.error(f"Analysis failed for {ticker}: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "ticker": ticker,
                "analysis_date": analysis_date,
                "error": str(e),
            }
    
    def get_available_analysts(self) -> List[str]:
        """Get list of available analyst types"""
        return ["market", "social", "news", "fundamentals"]
    
    def get_available_llms(self) -> List[str]:
        """Get list of available OpenAI LLM models"""
        return [
            # OpenAI
            "gpt-5.1-2025-11-13",
            "gpt-5-mini-2025-08-07",
            "gpt-5-nano-2025-08-07",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o4-mini-2025-04-16",
            # Anthropic
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "claude-sonnet-4-0",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
            # Google
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            # Grok
            "grok-4-1-fast-reasoning",
            "grok-4-1-fast-non-reasoning",
            "grok-4-fast-reasoning",
            "grok-4-fast-non-reasoning",
            "grok-4-0709",
            "grok-3",
            "grok-3-mini",
            # DeepSeek
            "deepseek-reasoner",
            "deepseek-chat",
            # Qwen
            "qwen3-max",
            "qwen-plus",
            "qwen-flash",
        ]
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "research_depth": 1,
            "deep_think_llm": "gpt-5-mini-2025-08-07",
            "quick_think_llm": "gpt-5-mini-2025-08-07",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }


# Global service instance
trading_service = TradingService()
