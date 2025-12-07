"""
Exit Strategy - Automated profit taking and stop loss management

Determines when to exit positions based on:
- Profit targets (% gains)
- Stop losses (% losses)
- Time-based holds
- Signal deterioration
"""

from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime, timedelta
from enum import Enum


class ExitReason(Enum):
    """Reasons for exiting a trade"""
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_LIMIT = "time_limit"
    SIGNAL_DETERIORATION = "signal_deterioration"
    MANUAL = "manual"


@dataclass
class ExitConfig:
    """Configuration for exit strategy"""
    profit_target_pct: float = 5.0      # Take profit at 5%
    stop_loss_pct: float = 2.0          # Stop loss at -2%
    max_hold_days: int = 5              # Max hold time
    trailing_stop_pct: float = 2.0      # Trailing stop at 2%
    min_signal_score: float = 40.0      # Exit if signal drops below 40


class ExitStrategy:
    """
    Manages exit points for trades.
    
    Uses multiple exit conditions:
    1. Profit Target - Exit when profit % is reached
    2. Stop Loss - Exit when loss % is exceeded
    3. Time Limit - Exit after holding max days
    4. Signal Deterioration - Exit if signal quality drops
    5. Trailing Stop - Exit if price drops from peak
    """
    
    def __init__(self, config: Optional[ExitConfig] = None):
        self.config = config or ExitConfig()
        self.position_peaks: Dict[str, float] = {}  # Track peak price per position
    
    def evaluate_exit(
        self,
        ticker: str,
        current_price: float,
        entry_price: float,
        entry_date: datetime,
        signal_score: float,
        position_type: str,
    ) -> Optional[Dict]:
        """
        Evaluate if position should be exited.
        
        Returns:
            Dict with exit_signal (True/False), reason, and price
            or None if no exit signal
        """
        
        # Track peak price for trailing stop
        if ticker not in self.position_peaks:
            self.position_peaks[ticker] = entry_price
        else:
            self.position_peaks[ticker] = max(
                self.position_peaks[ticker],
                current_price
            )
        
        current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        hold_days = (datetime.now() - entry_date).days
        
        # Check profit target
        if current_pnl_pct >= self.config.profit_target_pct:
            return {
                "exit_signal": True,
                "reason": ExitReason.PROFIT_TARGET.value,
                "exit_price": current_price,
                "pnl_pct": current_pnl_pct,
                "hold_days": hold_days,
            }
        
        # Check stop loss
        if current_pnl_pct <= -self.config.stop_loss_pct:
            return {
                "exit_signal": True,
                "reason": ExitReason.STOP_LOSS.value,
                "exit_price": current_price,
                "pnl_pct": current_pnl_pct,
                "hold_days": hold_days,
            }
        
        # Check time limit
        if hold_days >= self.config.max_hold_days:
            return {
                "exit_signal": True,
                "reason": ExitReason.TIME_LIMIT.value,
                "exit_price": current_price,
                "pnl_pct": current_pnl_pct,
                "hold_days": hold_days,
            }
        
        # Check signal deterioration (for momentum/pump trades)
        if position_type in ["momentum", "pump"]:
            if signal_score < self.config.min_signal_score:
                return {
                    "exit_signal": True,
                    "reason": ExitReason.SIGNAL_DETERIORATION.value,
                    "exit_price": current_price,
                    "pnl_pct": current_pnl_pct,
                    "hold_days": hold_days,
                    "signal_score": signal_score,
                }
        
        # Check trailing stop
        peak = self.position_peaks[ticker]
        peak_drawdown_pct = ((current_price - peak) / peak) * 100
        if peak_drawdown_pct <= -self.config.trailing_stop_pct:
            return {
                "exit_signal": True,
                "reason": "trailing_stop",
                "exit_price": current_price,
                "pnl_pct": current_pnl_pct,
                "hold_days": hold_days,
                "peak_drawdown_pct": peak_drawdown_pct,
            }
        
        return None
    
    def get_exit_targets(self, entry_price: float) -> Dict:
        """Get exit price targets"""
        return {
            "profit_target": entry_price * (1 + self.config.profit_target_pct / 100),
            "stop_loss": entry_price * (1 - self.config.stop_loss_pct / 100),
            "trailing_stop_trigger": entry_price * (1 - self.config.trailing_stop_pct / 100),
        }
    
    def clear_peak(self, ticker: str):
        """Clear peak price tracking for a ticker"""
        if ticker in self.position_peaks:
            del self.position_peaks[ticker]
    
    def to_dict(self) -> Dict:
        """Serialize exit strategy config"""
        return {
            "profit_target_pct": self.config.profit_target_pct,
            "stop_loss_pct": self.config.stop_loss_pct,
            "max_hold_days": self.config.max_hold_days,
            "trailing_stop_pct": self.config.trailing_stop_pct,
            "min_signal_score": self.config.min_signal_score,
        }
