"""
Portfolio Manager - Position Sizing and Risk Management

Enforces portfolio constraints:
- Max 8% per stock
- Max X% in risky trades
- Position size based on signal strength
- Portfolio utilization tracking
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime
import json


@dataclass
class Position:
    """Represents a single position in the portfolio"""
    ticker: str
    shares: int
    entry_price: float
    entry_date: datetime
    signal_score: float  # 0-100
    position_type: str  # "momentum", "pump", "fundamentals"
    
    @property
    def market_value(self, current_price: float) -> float:
        return self.shares * current_price


class PortfolioManager:
    """
    Manages portfolio constraints and position sizing.
    
    Config options:
    - max_position_pct: Max % of portfolio in one stock (default: 8%)
    - max_risky_pct: Max % in high-risk trades (pump/momentum) (default: 25%)
    - max_positions: Max number of open positions (default: 10)
    - portfolio_cash: Starting cash (default: $10,000)
    - min_position_size: Minimum $ per trade (default: $100)
    - max_position_size: Maximum $ per trade (default: 2000)
    """
    
    def __init__(
        self,
        portfolio_cash: float = 10000.0,
        max_position_pct: float = 0.08,  # 8%
        max_risky_pct: float = 0.25,     # 25% in risky trades
        max_positions: int = 10,
        min_position_size: float = 100.0,
        max_position_size: float = 2000.0,
    ):
        self.initial_cash = portfolio_cash
        self.cash = portfolio_cash
        self.portfolio_value = portfolio_cash
        
        self.max_position_pct = max_position_pct
        self.max_risky_pct = max_risky_pct
        self.max_positions = max_positions
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
        
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[Dict] = []
        
    def calculate_position_size(
        self,
        current_price: float,
        signal_score: float,
        position_type: str = "momentum",
    ) -> Optional[Dict]:
        """
        Calculate position size based on signal strength and portfolio constraints.
        
        Args:
            current_price: Current stock price
            signal_score: Signal strength 0-100
            position_type: "momentum", "pump", "fundamentals"
        
        Returns:
            Dict with shares, position_value, or None if trade not allowed
        """
        
        # Check if we can trade
        if not self._can_enter_trade():
            return None
        
        # Calculate max position value
        max_position_value = self.portfolio_value * self.max_position_pct
        
        # Scale position size by signal strength
        # Stronger signals get bigger positions (up to max)
        signal_multiplier = signal_score / 100.0  # 0-1
        position_value = max_position_value * signal_multiplier
        
        # Enforce min/max position size
        position_value = max(self.min_position_size, position_value)
        position_value = min(self.max_position_size, position_value)
        
        # Check if we have enough cash
        if position_value > self.cash:
            position_value = self.cash
        
        # Check risky position limits
        risky_value = self._calculate_risky_exposure()
        if position_type in ["momentum", "pump"]:
            max_risky_value = self.portfolio_value * self.max_risky_pct
            if risky_value + position_value > max_risky_value:
                # Reduce position to fit within risky limit
                position_value = max(
                    self.min_position_size,
                    max_risky_value - risky_value
                )
        
        # Calculate shares
        shares = int(position_value / current_price)
        
        if shares < 1:
            return None
        
        return {
            "shares": shares,
            "position_value": shares * current_price,
            "signal_multiplier": signal_multiplier,
            "position_pct": (shares * current_price) / self.portfolio_value,
        }
    
    def add_position(
        self,
        ticker: str,
        shares: int,
        entry_price: float,
        signal_score: float,
        position_type: str,
    ) -> bool:
        """Add a new position to the portfolio"""
        position_value = shares * entry_price
        
        if ticker in self.positions:
            return False  # Already have position
        
        if position_value > self.cash:
            return False  # Not enough cash
        
        # Update cash
        self.cash -= position_value
        
        # Add position
        self.positions[ticker] = Position(
            ticker=ticker,
            shares=shares,
            entry_price=entry_price,
            entry_date=datetime.now(),
            signal_score=signal_score,
            position_type=position_type,
        )
        
        # Record trade
        self.trade_history.append({
            "action": "BUY",
            "ticker": ticker,
            "shares": shares,
            "price": entry_price,
            "timestamp": datetime.now().isoformat(),
            "signal_score": signal_score,
            "position_type": position_type,
        })
        
        return True
    
    def close_position(
        self,
        ticker: str,
        exit_price: float,
        reason: str,
    ) -> Optional[Dict]:
        """Close an existing position"""
        if ticker not in self.positions:
            return None
        
        position = self.positions[ticker]
        exit_value = position.shares * exit_price
        entry_value = position.shares * position.entry_price
        profit = exit_value - entry_value
        profit_pct = (profit / entry_value) * 100
        
        # Update cash
        self.cash += exit_value
        
        # Record trade
        self.trade_history.append({
            "action": "SELL",
            "ticker": ticker,
            "shares": position.shares,
            "price": exit_price,
            "timestamp": datetime.now().isoformat(),
            "profit": profit,
            "profit_pct": profit_pct,
            "hold_days": (datetime.now() - position.entry_date).days,
            "reason": reason,
        })
        
        # Remove position
        del self.positions[ticker]
        
        return {
            "ticker": ticker,
            "profit": profit,
            "profit_pct": profit_pct,
            "hold_days": (datetime.now() - position.entry_date).days,
        }
    
    def get_portfolio_status(self) -> Dict:
        """Get current portfolio status"""
        positions_value = sum(
            p.shares * p.entry_price for p in self.positions.values()
        )
        self.portfolio_value = self.cash + positions_value
        
        risky_value = self._calculate_risky_exposure()
        
        return {
            "total_value": self.portfolio_value,
            "cash": self.cash,
            "positions_value": positions_value,
            "num_positions": len(self.positions),
            "max_positions": self.max_positions,
            "cash_utilization": (positions_value / self.portfolio_value) * 100,
            "risky_exposure": (risky_value / self.portfolio_value) * 100,
            "max_risky_pct": self.max_risky_pct * 100,
            "positions": {
                t: {
                    "shares": p.shares,
                    "entry_price": p.entry_price,
                    "signal_score": p.signal_score,
                    "position_type": p.position_type,
                }
                for t, p in self.positions.items()
            },
        }
    
    def _can_enter_trade(self) -> bool:
        """Check if we can enter a new trade"""
        # Check max positions
        if len(self.positions) >= self.max_positions:
            return False
        
        # Check minimum cash buffer
        if self.cash < self.min_position_size:
            return False
        
        return True
    
    def _calculate_risky_exposure(self) -> float:
        """Calculate total value in risky positions (momentum/pump)"""
        risky_value = 0.0
        for ticker, pos in self.positions.items():
            if pos.position_type in ["momentum", "pump"]:
                risky_value += pos.shares * pos.entry_price
        return risky_value
    
    def to_dict(self) -> Dict:
        """Serialize portfolio to dict"""
        return {
            "cash": self.cash,
            "portfolio_value": self.portfolio_value,
            "positions": {
                t: {
                    "shares": p.shares,
                    "entry_price": p.entry_price,
                    "entry_date": p.entry_date.isoformat(),
                    "signal_score": p.signal_score,
                    "position_type": p.position_type,
                }
                for t, p in self.positions.items()
            },
            "trade_history": self.trade_history,
        }
    
    def save_portfolio(self, filepath: str):
        """Save portfolio state to JSON"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def load_portfolio(self, filepath: str):
        """Load portfolio state from JSON"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.cash = data["cash"]
        self.portfolio_value = data["portfolio_value"]
        self.trade_history = data["trade_history"]
        
        # Note: positions would need to be reconstructed from historical data
