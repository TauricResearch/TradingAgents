"""Calculate rewards for Hindsight RL training."""

import logging
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime, timedelta
import math

logger = logging.getLogger(__name__)


class RewardType(Enum):
    """Types of reward calculations for Hindsight RL."""
    BENCHMARK_ALPHA = "BENCHMARK_ALPHA"           # Return - Benchmark Return (basis points)
    ABSOLUTE_RETURN = "ABSOLUTE_RETURN"           # Position return % 
    SHARPE_RATIO = "SHARPE_RATIO"                # Risk-adjusted return
    INFORMATION_RATIO = "INFORMATION_RATIO"      # Alpha / tracking error


class RewardCalculator:
    """Calculate rewards for decision quality evaluation."""
    
    def __init__(self, benchmark_ticker: str = "SPY"):
        """Initialize reward calculator.
        
        Args:
            benchmark_ticker: Benchmark ticker for comparison (default SPY)
        """
        self.benchmark_ticker = benchmark_ticker
        self.decision_outcomes = {}  # decision_id -> outcome dict
    
    def record_decision_outcome(self, decision_id: int, decision_type: str,
                               entry_price: float, entry_date: str,
                               exit_price: Optional[float] = None,
                               exit_date: Optional[str] = None,
                               quantity: float = 1.0):
        """Record decision outcome for reward calculation.
        
        Args:
            decision_id: AI decision ID
            decision_type: 'BUY' or 'SELL'
            entry_price: Entry price
            entry_date: Entry date (YYYY-MM-DD)
            exit_price: Exit price (None if position still open)
            exit_date: Exit date (None if position still open)
            quantity: Position size
        """
        self.decision_outcomes[decision_id] = {
            "decision_type": decision_type,
            "entry_price": entry_price,
            "entry_date": entry_date,
            "exit_price": exit_price,
            "exit_date": exit_date,
            "quantity": quantity,
            "entry_time": datetime.fromisoformat(entry_date) if isinstance(entry_date, str) else entry_date,
        }
    
    def calculate_absolute_return(self, decision_id: int) -> Optional[float]:
        """Calculate absolute return from a decision.
        
        Args:
            decision_id: AI decision ID
            
        Returns:
            Return as percentage or None if position not closed
        """
        outcome = self.decision_outcomes.get(decision_id)
        if not outcome or not outcome["exit_price"]:
            return None
        
        entry = outcome["entry_price"]
        exit_price = outcome["exit_price"]
        
        if outcome["decision_type"] == "BUY":
            return ((exit_price - entry) / entry) * 100
        else:  # SELL (short)
            return ((entry - exit_price) / entry) * 100
    
    def calculate_benchmark_alpha(self, decision_id: int,
                                 benchmark_returns: Dict[str, float]) -> Optional[float]:
        """Calculate alpha vs benchmark.
        
        Args:
            decision_id: AI decision ID
            benchmark_returns: Dict of date -> benchmark daily return %
            
        Returns:
            Alpha in basis points (1 bp = 0.01%) or None if position not closed
        """
        outcome = self.decision_outcomes.get(decision_id)
        if not outcome or not outcome["exit_price"]:
            return None
        
        # Decision return
        decision_return = self.calculate_absolute_return(decision_id)
        if decision_return is None:
            return None
        
        # Calculate benchmark return for holding period
        entry_date = outcome["entry_date"]
        exit_date = outcome["exit_date"]
        
        # Sum daily benchmark returns for period
        benchmark_return = 0.0
        current_date = datetime.fromisoformat(entry_date).date() if isinstance(entry_date, str) else entry_date
        end_date = datetime.fromisoformat(exit_date).date() if isinstance(exit_date, str) else exit_date
        
        while current_date <= end_date:
            date_str = current_date.isoformat()
            benchmark_return += benchmark_returns.get(date_str, 0.0)
            current_date += timedelta(days=1)
        
        # Calculate alpha in basis points
        alpha_pct = decision_return - benchmark_return
        alpha_bp = alpha_pct * 100
        
        return alpha_bp
    
    def calculate_sharpe_ratio(self, decision_returns: List[float],
                              risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio (risk-adjusted return).
        
        Args:
            decision_returns: List of daily returns (%)
            risk_free_rate: Annual risk-free rate (default 2%)
            
        Returns:
            Sharpe ratio
        """
        if not decision_returns or len(decision_returns) < 2:
            return 0.0
        
        # Calculate mean and std dev
        mean_return = sum(decision_returns) / len(decision_returns)
        variance = sum((r - mean_return) ** 2 for r in decision_returns) / len(decision_returns)
        std_dev = math.sqrt(variance)
        
        if std_dev == 0:
            return 0.0
        
        # Annualize (assuming 252 trading days)
        daily_risk_free = risk_free_rate / 252
        sharpe = ((mean_return - daily_risk_free) / std_dev) * math.sqrt(252)
        
        return sharpe
    
    def calculate_information_ratio(self, decision_returns: List[float],
                                   benchmark_returns: List[float]) -> float:
        """Calculate Information Ratio (active management quality).
        
        Args:
            decision_returns: List of strategy daily returns (%)
            benchmark_returns: List of benchmark daily returns (%)
            
        Returns:
            Information ratio
        """
        if len(decision_returns) != len(benchmark_returns) or len(decision_returns) < 2:
            return 0.0
        
        # Calculate active returns (strategy - benchmark)
        active_returns = [d - b for d, b in zip(decision_returns, benchmark_returns)]
        
        # Calculate mean and std dev of active returns
        mean_active = sum(active_returns) / len(active_returns)
        variance = sum((r - mean_active) ** 2 for r in active_returns) / len(active_returns)
        tracking_error = math.sqrt(variance)
        
        if tracking_error == 0:
            return 0.0
        
        # Information ratio = excess return / tracking error
        # Annualize
        ir = (mean_active / tracking_error) * math.sqrt(252)
        
        return ir
    
    def calculate_reward(self, decision_id: int, reward_type: RewardType,
                        benchmark_returns: Optional[Dict[str, float]] = None,
                        decision_daily_returns: Optional[List[float]] = None,
                        benchmark_daily_returns: Optional[List[float]] = None) -> Optional[float]:
        """Calculate reward for a decision based on specified type.
        
        Args:
            decision_id: AI decision ID
            reward_type: Type of reward to calculate
            benchmark_returns: Dict of date -> return % (for alpha calculation)
            decision_daily_returns: List of daily returns for Sharpe (%)
            benchmark_daily_returns: List of benchmark daily returns for IR (%)
            
        Returns:
            Reward score or None
        """
        if reward_type == RewardType.ABSOLUTE_RETURN:
            return self.calculate_absolute_return(decision_id)
        
        elif reward_type == RewardType.BENCHMARK_ALPHA:
            if not benchmark_returns:
                logger.warning("benchmark_returns required for BENCHMARK_ALPHA calculation")
                return None
            return self.calculate_benchmark_alpha(decision_id, benchmark_returns)
        
        elif reward_type == RewardType.SHARPE_RATIO:
            if not decision_daily_returns:
                logger.warning("decision_daily_returns required for SHARPE_RATIO calculation")
                return None
            return self.calculate_sharpe_ratio(decision_daily_returns)
        
        elif reward_type == RewardType.INFORMATION_RATIO:
            if not decision_daily_returns or not benchmark_daily_returns:
                logger.warning("Daily returns required for INFORMATION_RATIO calculation")
                return None
            return self.calculate_information_ratio(decision_daily_returns, benchmark_daily_returns)
        
        return None
    
    def evaluate_decision_outperformance(self, decision_id: int,
                                        benchmark_return: float) -> bool:
        """Check if decision outperformed benchmark.
        
        Args:
            decision_id: AI decision ID
            benchmark_return: Benchmark return for period (%)
            
        Returns:
            True if decision beat benchmark
        """
        decision_return = self.calculate_absolute_return(decision_id)
        if decision_return is None:
            return False
        return decision_return > benchmark_return
    
    def get_decision_quality_score(self, decision_id: int,
                                  benchmark_return: float) -> Dict:
        """Get comprehensive decision quality score.
        
        Args:
            decision_id: AI decision ID
            benchmark_return: Benchmark return for period (%)
            
        Returns:
            Dictionary with multiple quality metrics
        """
        outcome = self.decision_outcomes.get(decision_id)
        if not outcome:
            return {}
        
        decision_return = self.calculate_absolute_return(decision_id)
        outperformed = decision_return > benchmark_return if decision_return else None
        
        return {
            "decision_id": decision_id,
            "decision_type": outcome["decision_type"],
            "decision_return_pct": decision_return,
            "benchmark_return_pct": benchmark_return,
            "outperformed_benchmark": outperformed,
            "excess_return_pct": (decision_return - benchmark_return) if decision_return else None,
            "entry_price": outcome["entry_price"],
            "exit_price": outcome["exit_price"],
            "position_duration_days": (datetime.fromisoformat(outcome["exit_date"]) - 
                                       datetime.fromisoformat(outcome["entry_date"])).days if outcome["exit_date"] else None,
        }
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics of all decision outcomes.
        
        Returns:
            Summary dictionary
        """
        if not self.decision_outcomes:
            return {"total_decisions": 0}
        
        closed_positions = [o for o in self.decision_outcomes.values() if o["exit_price"]]
        returns = [self.calculate_absolute_return(did) for did, o in self.decision_outcomes.items() 
                  if o["exit_price"]]
        returns = [r for r in returns if r is not None]
        
        if not returns:
            return {
                "total_decisions": len(self.decision_outcomes),
                "closed_positions": len(closed_positions),
                "open_positions": len(self.decision_outcomes) - len(closed_positions),
            }
        
        return {
            "total_decisions": len(self.decision_outcomes),
            "closed_positions": len(closed_positions),
            "open_positions": len(self.decision_outcomes) - len(closed_positions),
            "avg_return_pct": sum(returns) / len(returns),
            "min_return_pct": min(returns),
            "max_return_pct": max(returns),
            "winning_trades": sum(1 for r in returns if r > 0),
            "losing_trades": sum(1 for r in returns if r < 0),
            "win_rate": sum(1 for r in returns if r > 0) / len(returns) * 100,
        }
