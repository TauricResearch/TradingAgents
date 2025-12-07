"""
Paper Trading Integration - Webull API

Connects to Webull's paper trading environment to execute trades.
Requires Webull credentials and 2FA setup.

Installation:
    pip install webull

Usage:
    from tradingagents.agents.trader.paper_trading import PaperTrader
    
    trader = PaperTrader(
        email="your_email@example.com",
        password="your_password",
        is_paper=True,
    )
    
    # Buy
    result = trader.place_buy_order("AAPL", 10, limit_price=150.0)
    
    # Sell
    result = trader.place_sell_order("AAPL", 5, limit_price=152.0)
    
    # Get positions
    positions = trader.get_positions()
"""

import os
import json
from typing import Optional, Dict, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    Webull Paper Trading Interface
    
    Handles buy/sell orders, position tracking, and account management
    in Webull's paper trading environment.
    """
    
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        is_paper: bool = True,
        mfa_code: Optional[str] = None,
    ):
        """
        Initialize Webull paper trader.
        
        Args:
            email: Webull account email
            password: Webull account password
            is_paper: Use paper trading (True) or live (False)
            mfa_code: 2FA code if required
        """
        self.email = email or os.getenv("WEBULL_EMAIL")
        self.password = password or os.getenv("WEBULL_PASSWORD")
        self.is_paper = is_paper
        self.mfa_code = mfa_code
        
        self.client = None
        self.is_authenticated = False
        self.positions: Dict[str, Dict] = {}
        self.orders: List[Dict] = []
        self.account_info: Dict = {}
        
        if self.email and self.password:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Webull client"""
        try:
            if self.is_paper:
                from webull import paper_webull as WebullClass
            else:
                from webull import webull as WebullClass
            
            self.client = WebullClass()
            logger.info("Webull client initialized (paper mode)")
        except ImportError:
            logger.error(
                "Webull package not installed. "
                "Run: pip install webull"
            )
            self.client = None
    
    def login(self) -> bool:
        """
        Login to Webull account.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.client or not self.email or not self.password:
            logger.error("Client not initialized or credentials missing")
            return False
        
        try:
            self.client.login(self.email, self.password)
            self.is_authenticated = True
            logger.info(f"Logged into Webull as {self.email}")
            return True
        except Exception as e:
            logger.error(f"Failed to login to Webull: {e}")
            return False
    
    def get_trade_token(self, pin: str) -> bool:
        """
        Get trade token (required for placing orders).
        
        Args:
            pin: Trading PIN from Webull account
        
        Returns:
            True if successful
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return False
        
        try:
            self.client.get_trade_token(pin)
            logger.info("Trade token obtained")
            return True
        except Exception as e:
            logger.error(f"Failed to get trade token: {e}")
            return False
    
    def place_buy_order(
        self,
        ticker: str,
        quantity: int,
        limit_price: Optional[float] = None,
        order_type: str = "LMT",  # LMT or MKT
    ) -> Optional[Dict]:
        """
        Place a buy order.
        
        Args:
            ticker: Stock symbol
            quantity: Number of shares
            limit_price: Limit price (None for market order)
            order_type: "LMT" for limit, "MKT" for market
        
        Returns:
            Order confirmation dict or None if failed
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return None
        
        try:
            order_result = self.client.place_order(
                stock=ticker,
                price=limit_price or 0,
                qty=quantity,
                orderType=order_type,
                timeInForce="DAY",  # Good for day
            )
            
            logger.info(f"Buy order placed: {ticker} x {quantity} @ ${limit_price}")
            
            order_info = {
                "action": "BUY",
                "ticker": ticker,
                "quantity": quantity,
                "price": limit_price,
                "order_type": order_type,
                "timestamp": datetime.now().isoformat(),
                "result": order_result,
            }
            
            self.orders.append(order_info)
            return order_info
        
        except Exception as e:
            logger.error(f"Failed to place buy order: {e}")
            return None
    
    def place_sell_order(
        self,
        ticker: str,
        quantity: int,
        limit_price: Optional[float] = None,
        order_type: str = "LMT",
    ) -> Optional[Dict]:
        """
        Place a sell order.
        
        Args:
            ticker: Stock symbol
            quantity: Number of shares
            limit_price: Limit price (None for market order)
            order_type: "LMT" for limit, "MKT" for market
        
        Returns:
            Order confirmation dict or None if failed
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return None
        
        try:
            order_result = self.client.place_order(
                stock=ticker,
                price=limit_price or 0,
                qty=quantity,
                orderType=order_type,
                timeInForce="DAY",
            )
            
            logger.info(f"Sell order placed: {ticker} x {quantity} @ ${limit_price}")
            
            order_info = {
                "action": "SELL",
                "ticker": ticker,
                "quantity": quantity,
                "price": limit_price,
                "order_type": order_type,
                "timestamp": datetime.now().isoformat(),
                "result": order_result,
            }
            
            self.orders.append(order_info)
            return order_info
        
        except Exception as e:
            logger.error(f"Failed to place sell order: {e}")
            return None
    
    def get_positions(self) -> Dict[str, Dict]:
        """
        Get current positions from Webull.
        
        Returns:
            Dict of {ticker: position_info}
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return {}
        
        try:
            positions = self.client.get_positions()
            self.positions = {p["ticker"]: p for p in positions}
            return self.positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {}
    
    def get_account_balance(self) -> Optional[Dict]:
        """
        Get account balance and cash.
        
        Returns:
            Dict with balance info or None if failed
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return None
        
        try:
            account = self.client.get_account()
            self.account_info = account
            return {
                "account_value": account.get("account_value"),
                "cash": account.get("cash"),
                "buying_power": account.get("buying_power"),
            }
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return None
    
    def get_orders(self) -> List[Dict]:
        """
        Get current open orders.
        
        Returns:
            List of open orders
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return []
        
        try:
            orders = self.client.get_current_orders()
            return orders
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if successful
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return False
        
        try:
            self.client.cancel_order(order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.
        
        Returns:
            True if successful
        """
        if not self.client or not self.is_authenticated:
            logger.error("Not authenticated")
            return False
        
        try:
            self.client.cancel_all_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False
    
    def get_stock_quote(self, ticker: str) -> Optional[Dict]:
        """
        Get current stock quote.
        
        Args:
            ticker: Stock symbol
        
        Returns:
            Quote dict with price info or None if failed
        """
        if not self.client:
            logger.error("Client not initialized")
            return None
        
        try:
            quote = self.client.get_stock(ticker)
            return {
                "ticker": ticker,
                "price": quote.get("price"),
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get quote for {ticker}: {e}")
            return None
    
    def to_dict(self) -> Dict:
        """Serialize trader state"""
        return {
            "is_authenticated": self.is_authenticated,
            "is_paper": self.is_paper,
            "positions": self.positions,
            "orders": self.orders,
            "account_info": self.account_info,
        }
    
    def save_state(self, filepath: str):
        """Save trader state to JSON"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @staticmethod
    def demo_mode() -> "PaperTrader":
        """Create a demo paper trader (no auth required)"""
        trader = PaperTrader(is_paper=True)
        trader.is_authenticated = True  # Simulate auth for demo
        return trader
