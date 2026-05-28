"""Handle corporate actions like stock splits and dividends."""

import logging
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CorporateActionType(Enum):
    """Types of corporate actions."""
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"


class CorporateAction:
    """Represents a corporate action."""
    
    def __init__(self, ticker: str, action_type: CorporateActionType,
                 action_date: str, ratio: Optional[float] = None,
                 dividend_per_share: Optional[float] = None):
        """Initialize a corporate action.
        
        Args:
            ticker: Stock ticker
            action_type: Type of action (STOCK_SPLIT, REVERSE_SPLIT, DIVIDEND)
            action_date: Date of action (YYYY-MM-DD)
            ratio: Ratio for stock splits (e.g., 0.1 for 10:1 split, 2.0 for 1:2 reverse)
            dividend_per_share: Cash dividend per share
        """
        self.ticker = ticker
        self.action_type = action_type
        self.action_date = action_date
        self.ratio = ratio
        self.dividend_per_share = dividend_per_share
        self.applied = False
    
    def __str__(self) -> str:
        if self.action_type == CorporateActionType.DIVIDEND:
            return f"{self.ticker}: ${self.dividend_per_share:.2f} dividend on {self.action_date}"
        elif self.action_type == CorporateActionType.STOCK_SPLIT:
            return f"{self.ticker}: 1:{1/self.ratio:.0f} split on {self.action_date}"
        else:  # REVERSE_SPLIT
            return f"{self.ticker}: {self.ratio:.0f}:1 reverse split on {self.action_date}"


class CorporateActionsHandler:
    """Manage corporate actions and their impact on holdings."""
    
    def __init__(self):
        """Initialize corporate actions handler."""
        self.actions = []  # List of CorporateAction objects
    
    def add_action(self, corporate_action: CorporateAction):
        """Add a corporate action.
        
        Args:
            corporate_action: CorporateAction object
        """
        self.actions.append(corporate_action)
        logger.info(f"Recorded corporate action: {corporate_action}")
    
    def apply_stock_split(self, holding: Dict, split_ratio: float) -> Dict:
        """Apply stock split to a holding.
        
        For a 10:1 split (1 share becomes 10):
        - split_ratio = 0.1 (multiply by this)
        - quantity *= 10 (divide by ratio)
        - avg_buy_price /= 10
        
        For a 1:2 reverse split (2 shares become 1):
        - split_ratio = 2.0 (multiply by this)
        - quantity /= 2 (divide by ratio)
        - avg_buy_price *= 2
        
        Args:
            holding: Holdings dictionary
            split_ratio: Ratio to apply (< 1 for splits, > 1 for reverse splits)
            
        Returns:
            Updated holding dictionary
        """
        holding_copy = holding.copy()
        
        # Inverse the ratio for quantity calculation
        quantity_multiplier = 1 / split_ratio if split_ratio != 0 else 1
        
        # Update quantity and average buy price
        holding_copy["quantity_held"] *= quantity_multiplier
        holding_copy["avg_buy_price"] /= quantity_multiplier
        
        # Recalculate unrealized P&L
        holding_copy["unrealized_pl"] = (holding_copy["current_price"] - holding_copy["avg_buy_price"]) * holding_copy["quantity_held"]
        
        # Track adjustment
        holding_copy["quantity_adjusted"] += abs(holding_copy["quantity_held"] - holding["quantity_held"])
        holding_copy["split_ratio"] = split_ratio
        holding_copy["last_split_date"] = datetime.now().isoformat()
        
        logger.info(f"Applied stock split to {holding['ticker']}: "
                   f"qty {holding['quantity_held']:.0f} → {holding_copy['quantity_held']:.0f}, "
                   f"avg_price ${holding['avg_buy_price']:.2f} → ${holding_copy['avg_buy_price']:.2f}")
        
        return holding_copy
    
    def apply_dividend(self, holding: Dict, dividend_per_share: float) -> float:
        """Calculate dividend cash received.
        
        Args:
            holding: Holdings dictionary
            dividend_per_share: Dividend amount per share
            
        Returns:
            Total dividend cash to add to portfolio
        """
        dividend_total = holding["quantity_held"] * dividend_per_share
        
        logger.info(f"Dividend for {holding['ticker']}: "
                   f"{holding['quantity_held']:.0f} shares × ${dividend_per_share:.2f} = ${dividend_total:.2f}")
        
        return dividend_total
    
    def process_corporate_actions_for_date(self, holdings: Dict[str, Dict],
                                          check_date: str) -> tuple:
        """Process all applicable corporate actions for a date.
        
        Args:
            holdings: Dictionary of ticker -> holding
            check_date: Date to check (YYYY-MM-DD)
            
        Returns:
            Tuple of (updated_holdings, total_dividend_cash)
        """
        updated_holdings = {ticker: holding.copy() for ticker, holding in holdings.items()}
        total_dividend_cash = 0.0
        
        for action in self.actions:
            if action.action_date > check_date or action.applied:
                continue
            
            if action.ticker not in updated_holdings:
                continue
            
            holding = updated_holdings[action.ticker]
            
            if action.action_type in (CorporateActionType.STOCK_SPLIT, CorporateActionType.REVERSE_SPLIT):
                updated_holdings[action.ticker] = self.apply_stock_split(holding, action.ratio)
                action.applied = True
            
            elif action.action_type == CorporateActionType.DIVIDEND:
                dividend_cash = self.apply_dividend(holding, action.dividend_per_share)
                total_dividend_cash += dividend_cash
                action.applied = True
        
        return updated_holdings, total_dividend_cash
    
    def get_actions_for_ticker(self, ticker: str) -> list:
        """Get all actions for a specific ticker.
        
        Args:
            ticker: Stock ticker
            
        Returns:
            List of CorporateAction objects
        """
        return [action for action in self.actions if action.ticker == ticker]
    
    def get_unapplied_actions(self) -> list:
        """Get all unapplied corporate actions.
        
        Returns:
            List of unapplied CorporateAction objects
        """
        return [action for action in self.actions if not action.applied]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "total_actions": len(self.actions),
            "applied": sum(1 for action in self.actions if action.applied),
            "unapplied": sum(1 for action in self.actions if not action.applied),
            "actions": [
                {
                    "ticker": action.ticker,
                    "type": action.action_type.value,
                    "date": action.action_date,
                    "ratio": action.ratio,
                    "dividend_per_share": action.dividend_per_share,
                    "applied": action.applied,
                }
                for action in self.actions
            ]
        }
