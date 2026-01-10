"""
Deterministic Risk Gate - Mathematical Enforcement Layer

This module provides HARD MATHEMATICAL CONSTRAINTS that override LLM decisions.
No more "vibes" - only math.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class TradeProposal:
    """Structured trade proposal."""
    ticker: str
    action: str  # BUY, SELL, HOLD
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    confidence: float = 0.0
    reasoning: str = ""


class DeterministicRiskGate:
    """
    Mathematical risk enforcement layer.
    
    This class OVERRIDES LLM decisions if they violate hard constraints.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # Risk parameters
        self.max_position_risk = config.get("max_position_risk", 0.02)  # 2% per trade
        self.max_portfolio_heat = config.get("max_portfolio_heat", 0.10)  # 10% total
        self.max_drawdown_circuit_breaker = config.get("circuit_breaker", 0.15)  # 15%
        self.atr_stop_loss_multiple = config.get("atr_stop_multiple", 2.0)
        
        # Position sizing method
        self.position_sizing_method = config.get("position_sizing", "fixed_fractional")
    
    def validate_and_adjust_trade(
        self,
        proposal: TradeProposal,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate trade against hard constraints and adjust if needed.
        
        Args:
            proposal: LLM-generated trade proposal
            portfolio_state: Current portfolio (equity, positions, drawdown)
            market_data: Market data (price, ATR, volatility)
        
        Returns:
            {
                "approved": bool,
                "adjusted_proposal": TradeProposal,
                "rejection_reason": str or None,
                "risk_metrics": dict
            }
        """
        # Check 1: Circuit Breaker
        if portfolio_state["current_drawdown"] >= self.max_drawdown_circuit_breaker:
            return {
                "approved": False,
                "adjusted_proposal": None,
                "rejection_reason": f"CIRCUIT BREAKER: Drawdown {portfolio_state['current_drawdown']:.1%} >= {self.max_drawdown_circuit_breaker:.1%}",
                "risk_metrics": {}
            }
        
        # Check 2: Data Quality
        if not self._validate_data_quality(market_data):
            return {
                "approved": False,
                "adjusted_proposal": None,
                "rejection_reason": "DATA QUALITY FAILURE: Insufficient or invalid market data",
                "risk_metrics": {}
            }
        
        # Check 3: Calculate position size
        if proposal.action == "BUY":
            position_size, risk_metrics = self._calculate_position_size(
                portfolio_state=portfolio_state,
                market_data=market_data
            )
            
            # Check 4: Portfolio heat
            current_heat = self._calculate_portfolio_heat(portfolio_state)
            trade_risk = risk_metrics["trade_risk_pct"]
            
            if current_heat + trade_risk > self.max_portfolio_heat:
                return {
                    "approved": False,
                    "adjusted_proposal": None,
                    "rejection_reason": f"PORTFOLIO HEAT EXCEEDED: Current {current_heat:.1%} + Trade {trade_risk:.1%} > Limit {self.max_portfolio_heat:.1%}",
                    "risk_metrics": risk_metrics
                }
            
            # Adjust proposal with calculated values
            adjusted_proposal = TradeProposal(
                ticker=proposal.ticker,
                action=proposal.action,
                quantity=position_size,
                entry_price=market_data["close"],
                stop_loss=risk_metrics["stop_loss"],
                confidence=proposal.confidence,
                reasoning=proposal.reasoning
            )
            
            # Check if LLM proposed quantity differs from calculated
            override_msg = None
            if proposal.quantity and proposal.quantity != position_size:
                override_msg = f"RISK OVERRIDE: LLM proposed {proposal.quantity} shares, adjusted to {position_size} based on risk limits"
            
            return {
                "approved": True,
                "adjusted_proposal": adjusted_proposal,
                "rejection_reason": None,
                "override_message": override_msg,
                "risk_metrics": risk_metrics
            }
        
        elif proposal.action == "SELL":
            # Validate sell against current positions
            if proposal.ticker not in portfolio_state.get("positions", {}):
                return {
                    "approved": False,
                    "adjusted_proposal": None,
                    "rejection_reason": f"INVALID SELL: No position in {proposal.ticker}",
                    "risk_metrics": {}
                }
            
            return {
                "approved": True,
                "adjusted_proposal": proposal,
                "rejection_reason": None,
                "risk_metrics": {}
            }
        
        else:  # HOLD
            return {
                "approved": True,
                "adjusted_proposal": proposal,
                "rejection_reason": None,
                "risk_metrics": {}
            }
    
    def _calculate_position_size(
        self,
        portfolio_state: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> tuple[int, Dict]:
        """
        Calculate position size using configured method.
        
        Returns:
            (position_size_shares, risk_metrics)
        """
        portfolio_value = portfolio_state["equity"]
        entry_price = market_data["close"]
        atr = market_data.get("atr", entry_price * 0.02)  # Default 2% if ATR missing
        
        # Calculate stop-loss (ATR-based)
        stop_loss = entry_price - (self.atr_stop_loss_multiple * atr)
        risk_per_share = entry_price - stop_loss
        
        if self.position_sizing_method == "fixed_fractional":
            # Risk fixed % of portfolio per trade
            max_risk_dollars = portfolio_value * self.max_position_risk
            position_size = int(max_risk_dollars / risk_per_share)
        
        elif self.position_sizing_method == "kelly":
            # Kelly Criterion (requires win rate and avg win/loss)
            win_rate = portfolio_state.get("win_rate", 0.55)  # Default 55%
            avg_win = portfolio_state.get("avg_win", 0.03)  # Default 3%
            avg_loss = portfolio_state.get("avg_loss", 0.02)  # Default 2%
            
            kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
            kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
            
            max_risk_dollars = portfolio_value * kelly_fraction
            position_size = int(max_risk_dollars / risk_per_share)
        
        else:
            raise ValueError(f"Unknown position sizing method: {self.position_sizing_method}")
        
        # Calculate risk metrics
        position_value = position_size * entry_price
        trade_risk_dollars = position_size * risk_per_share
        trade_risk_pct = trade_risk_dollars / portfolio_value
        
        risk_metrics = {
            "position_size": position_size,
            "position_value": position_value,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "atr": atr,
            "risk_per_share": risk_per_share,
            "trade_risk_dollars": trade_risk_dollars,
            "trade_risk_pct": trade_risk_pct,
        }
        
        return position_size, risk_metrics
    
    def _calculate_portfolio_heat(self, portfolio_state: Dict[str, Any]) -> float:
        """
        Calculate total risk across all open positions.
        
        Returns:
            Portfolio heat as percentage of equity
        """
        total_risk = 0.0
        for ticker, position in portfolio_state.get("positions", {}).items():
            position_risk = position.get("risk_dollars", 0)
            total_risk += position_risk
        
        return total_risk / portfolio_state["equity"]
    
    def _validate_data_quality(self, market_data: Dict[str, Any]) -> bool:
        """
        Validate market data quality.
        
        Returns:
            True if data is sufficient, False otherwise
        """
        required_fields = ["close", "volume"]
        
        # Check required fields exist
        for field in required_fields:
            if field not in market_data or market_data[field] is None:
                return False
        
        # Check for reasonable values
        if market_data["close"] <= 0:
            return False
        
        if market_data.get("volume", 0) == 0:
            return False  # Zero volume = suspicious
        
        # Check for NaN/Inf
        if np.isnan(market_data["close"]) or np.isinf(market_data["close"]):
            return False
        
        return True


# Example usage
if __name__ == "__main__":
    config = {
        "max_position_risk": 0.02,
        "max_portfolio_heat": 0.10,
        "circuit_breaker": 0.15,
        "atr_stop_multiple": 2.0,
        "position_sizing": "fixed_fractional"
    }
    
    risk_gate = DeterministicRiskGate(config)
    
    # LLM proposes a trade
    llm_proposal = TradeProposal(
        ticker="AAPL",
        action="BUY",
        quantity=1000,  # LLM thinks 1000 shares is good
        confidence=0.85,
        reasoning="Strong technical setup with RSI oversold"
    )
    
    portfolio_state = {
        "equity": 100000,
        "current_drawdown": 0.05,
        "positions": {},
        "win_rate": 0.55,
        "avg_win": 0.03,
        "avg_loss": 0.02
    }
    
    market_data = {
        "close": 150.0,
        "atr": 3.0,
        "volume": 50000000
    }
    
    result = risk_gate.validate_and_adjust_trade(llm_proposal, portfolio_state, market_data)
    
    print(f"Approved: {result['approved']}")
    if result['approved']:
        print(f"Adjusted Position Size: {result['adjusted_proposal'].quantity} shares")
        print(f"Stop Loss: ${result['adjusted_proposal'].stop_loss:.2f}")
        print(f"Risk Metrics: {result['risk_metrics']}")
        if result.get('override_message'):
            print(f"⚠️  {result['override_message']}")
    else:
        print(f"Rejected: {result['rejection_reason']}")
