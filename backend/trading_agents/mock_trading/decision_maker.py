"""AI decision maker using TradingAgentsGraph."""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

from .async_analyzer import AsyncAnalyzer
from .order_manager import PriceType

logger = logging.getLogger(__name__)


class AIDecisionMaker:
    """Make trading decisions using TradingAgentsGraph analysis."""
    
    def __init__(self, analyzer: AsyncAnalyzer, trading_graph = None):
        """Initialize decision maker.
        
        Args:
            analyzer: AsyncAnalyzer instance for background analysis
            trading_graph: TradingAgentsGraph instance for AI analysis
        """
        self.analyzer = analyzer
        self.trading_graph = trading_graph  # TradingAgentsGraph to be provided
        self.analysis_cache = {}  # task_id -> decision result
    
    def set_trading_graph(self, trading_graph):
        """Set or update TradingAgentsGraph instance.
        
        Args:
            trading_graph: TradingAgentsGraph instance
        """
        self.trading_graph = trading_graph
        logger.info("TradingAgentsGraph configured")
    
    def queue_analysis(self, ticker: str, date: str) -> Optional[str]:
        """Queue analysis for a ticker.
        
        Args:
            ticker: Stock ticker
            date: Analysis date (YYYY-MM-DD)
            
        Returns:
            Task ID or None if analysis not available
        """
        if not self.trading_graph:
            logger.error("TradingAgentsGraph not configured")
            return None
        
        def analysis_wrapper():
            """Wrapper to call TradingAgentsGraph.propagate()."""
            try:
                _, decision = self.trading_graph.propagate(ticker, date)
                return decision
            except Exception as e:
                logger.error(f"Error in TradingAgentsGraph.propagate({ticker}, {date}): {e}")
                return None
        
        task_id = self.analyzer.queue_analysis(ticker, date, analysis_wrapper)
        return task_id
    
    def get_decision(self, task_id: str, timeout_sec: float = 600.0) -> Optional[Dict]:
        """Get decision from analysis task.
        
        Args:
            task_id: Analysis task ID
            timeout_sec: Maximum wait time
            
        Returns:
            Decision dictionary or None
        """
        result = self.analyzer.wait_for_result(task_id, timeout_sec)
        if result:
            self.analysis_cache[task_id] = result
        return result
    
    def get_cached_decision(self, task_id: str) -> Optional[Dict]:
        """Get cached decision without waiting.
        
        Args:
            task_id: Analysis task ID
            
        Returns:
            Cached decision or None
        """
        return self.analyzer.get_cached_decision(task_id) or self.analysis_cache.get(task_id)
    
    def convert_decision_to_action(self, decision: Dict, portfolio_mgr) -> Optional[Dict]:
        """Convert AI decision to trading action.
        
        Args:
            decision: Decision from TradingAgentsGraph
            portfolio_mgr: PortfolioManager instance
            
        Returns:
            Trading action (BUY, SELL, HOLD) or None
        """
        if not decision:
            return None
        
        # Extract decision signal from response
        # TradingAgentsGraph typically returns structured decision with recommendation
        
        try:
            # Assuming decision has structure like:
            # {
            #     "recommendation": "BUY" or "SELL" or "HOLD",
            #     "confidence": float,
            #     "target_price": float,
            #     "reasoning": str,
            # }
            
            recommendation = decision.get("recommendation", "HOLD").upper()
            confidence = decision.get("confidence", 0.5)
            ticker = decision.get("ticker")
            
            if recommendation not in ("BUY", "SELL", "HOLD"):
                logger.warning(f"Unknown recommendation: {recommendation}")
                recommendation = "HOLD"
            
            return {
                "action": recommendation,
                "ticker": ticker,
                "confidence": confidence,
                "target_price": decision.get("target_price"),
                "reasoning": decision.get("reasoning"),
                "original_decision": decision,
            }
        
        except Exception as e:
            logger.error(f"Error converting decision: {e}")
            return None
    
    def calculate_position_size(self, action: Dict, portfolio_mgr,
                               max_risk_per_trade_pct: float = 2.0,
                               position_limit_pct: float = 10.0) -> float:
        """Calculate position size based on portfolio risk.
        
        Args:
            action: Trading action from convert_decision_to_action
            portfolio_mgr: PortfolioManager instance
            max_risk_per_trade_pct: Max risk per trade as % of portfolio (default 2%)
            position_limit_pct: Max position size as % of portfolio (default 10%)
            
        Returns:
            Quantity to trade
        """
        if action["action"] == "HOLD":
            return 0.0
        
        portfolio_value = portfolio_mgr.initial_capital + portfolio_mgr.get_unrealized_pl()
        
        # For BUY orders
        if action["action"] == "BUY":
            # Position size based on available cash
            available_capital = portfolio_mgr.cash_available
            max_position = portfolio_value * (position_limit_pct / 100)
            trade_size = min(available_capital * (max_risk_per_trade_pct / 100), max_position)
        
        # For SELL orders
        else:  # SELL
            ticker = action["ticker"]
            holding = portfolio_mgr.get_holding(ticker)
            if not holding:
                logger.warning(f"No position in {ticker} to sell")
                return 0.0
            
            trade_size = min(holding["quantity_held"], 
                           portfolio_value * (position_limit_pct / 100))
        
        return trade_size
    
    def prepare_trade_request(self, action: Dict, portfolio_mgr,
                             current_price: float, price_type: PriceType = PriceType.CLOSE) -> Optional[Dict]:
        """Prepare trade request with all parameters.
        
        Args:
            action: Trading action
            portfolio_mgr: PortfolioManager instance
            current_price: Current market price
            price_type: Price reference type
            
        Returns:
            Trade request dictionary or None
        """
        if action["action"] == "HOLD":
            return None
        
        quantity = self.calculate_position_size(action, portfolio_mgr)
        if quantity <= 0:
            logger.warning(f"Position size calculation resulted in 0: {action}")
            return None
        
        return {
            "ticker": action["ticker"],
            "action": action["action"],
            "quantity": quantity,
            "reference_price": current_price,
            "price_type": price_type,
            "confidence": action.get("confidence", 0.5),
            "target_price": action.get("target_price"),
            "reasoning": action.get("reasoning"),
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_analysis_status(self, task_id: str) -> Optional[str]:
        """Get analysis status.
        
        Args:
            task_id: Analysis task ID
            
        Returns:
            Status string or None
        """
        return self.analyzer.get_task_status(task_id)
    
    def get_pending_decisions(self) -> list:
        """Get all pending analysis tasks.
        
        Returns:
            List of pending task IDs
        """
        return [t.task_id for t in self.analyzer.get_pending_tasks()]
    
    def get_completed_decisions(self) -> list:
        """Get all completed analysis tasks.
        
        Returns:
            List of completed task IDs
        """
        return [t.task_id for t in self.analyzer.get_completed_tasks()]
    
    def get_analysis_summary(self) -> Dict:
        """Get analysis execution summary.
        
        Returns:
            Summary dictionary
        """
        return self.analyzer.get_summary()
