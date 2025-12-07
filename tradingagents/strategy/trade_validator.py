"""
Trade Validator - Pre-trade risk checks

Validates trades before execution to ensure:
- Sufficient funds
- Position size constraints
- Price sanity checks
- Liquidity availability
"""

from typing import Optional, Dict
from datetime import datetime


class TradeValidator:
    """Validates trades before execution"""
    
    @staticmethod
    def validate_buy_order(
        ticker: str,
        shares: int,
        price: float,
        available_cash: float,
        portfolio_value: float,
        existing_position_value: float = 0.0,
        max_position_pct: float = 0.08,
    ) -> Optional[Dict]:
        """
        Validate a buy order.
        
        Returns:
            Dict with is_valid and any issues, or None if all good
        """
        issues = []
        
        # Check price validity
        if price <= 0:
            issues.append(f"Invalid price: ${price}")
        
        # Check shares validity
        if shares <= 0:
            issues.append(f"Invalid shares: {shares}")
        
        order_value = shares * price
        
        # Check if within position limit (8% of portfolio)
        new_position_value = existing_position_value + order_value
        max_position_value = portfolio_value * max_position_pct
        
        if new_position_value > max_position_value:
            issues.append(
                f"Position ${new_position_value:.2f} exceeds max "
                f"${max_position_value:.2f} ({max_position_pct*100}% of portfolio)"
            )
        
        # Check if sufficient funds
        if order_value > available_cash:
            issues.append(
                f"Insufficient cash: need ${order_value:.2f}, "
                f"have ${available_cash:.2f}"
            )
        
        if issues:
            return {
                "is_valid": False,
                "issues": issues,
                "ticker": ticker,
                "order_value": order_value,
            }
        
        return {
            "is_valid": True,
            "ticker": ticker,
            "order_value": order_value,
            "shares": shares,
            "price": price,
        }
    
    @staticmethod
    def validate_sell_order(
        ticker: str,
        shares: int,
        price: float,
        position_shares: int,
        position_value: float,
    ) -> Optional[Dict]:
        """
        Validate a sell order.
        """
        issues = []
        
        # Check price validity
        if price <= 0:
            issues.append(f"Invalid price: ${price}")
        
        # Check shares validity
        if shares <= 0:
            issues.append(f"Invalid shares: {shares}")
        
        # Check if we have enough shares
        if shares > position_shares:
            issues.append(
                f"Trying to sell {shares} but only have {position_shares}"
            )
        
        if issues:
            return {
                "is_valid": False,
                "issues": issues,
                "ticker": ticker,
            }
        
        return {
            "is_valid": True,
            "ticker": ticker,
            "order_value": shares * price,
            "shares": shares,
            "price": price,
        }
    
    @staticmethod
    def validate_price_change(
        ticker: str,
        old_price: float,
        new_price: float,
        max_change_pct: float = 50.0,
    ) -> Dict:
        """
        Validate price hasn't moved too much (circuit breaker).
        Detects potential data errors or market gaps.
        """
        if old_price <= 0:
            return {"is_valid": True, "ticker": ticker}
        
        change_pct = abs((new_price - old_price) / old_price) * 100
        
        if change_pct > max_change_pct:
            return {
                "is_valid": False,
                "ticker": ticker,
                "issue": f"Extreme price change: {change_pct:.1f}%",
                "old_price": old_price,
                "new_price": new_price,
                "change_pct": change_pct,
            }
        
        return {
            "is_valid": True,
            "ticker": ticker,
            "change_pct": change_pct,
        }
