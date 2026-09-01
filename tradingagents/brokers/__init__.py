"""
Broker Integration Module: Connect to live APIs for real market data and trade execution.
Supports: Zerodha (Kite), 5Paisa, and other Indian brokers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import json


@dataclass
class MarketData:
    """Real-time market data from broker."""
    symbol: str
    current_price: float
    bid: float
    ask: float
    high: float
    low: float
    open: float
    close: float
    volume: int
    rsi: Optional[float] = None
    atr: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    volume_trend: str = "neutral"
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Order:
    """Trading order specification."""
    symbol: str
    option_type: str  # "CALL" or "PUT"
    action: str  # "BUY" or "SELL"
    quantity: int
    price: float
    stop_loss: float
    target: float
    expiry: str  # e.g., "2026-09-08" or "1 week"
    order_id: Optional[str] = None
    status: str = "PENDING"
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class BrokerAPI(ABC):
    """Abstract broker API interface."""
    
    @abstractmethod
    def authenticate(self, credentials: Dict[str, str]) -> bool:
        """Authenticate with broker."""
        pass
    
    @abstractmethod
    def get_market_data(self, symbol: str) -> MarketData:
        """Fetch real-time market data."""
        pass
    
    @abstractmethod
    def get_technicals(self, symbol: str, lookback_days: int = 30) -> Dict[str, float]:
        """Calculate technical indicators (RSI, ATR, support, resistance)."""
        pass
    
    @abstractmethod
    def place_order(self, order: Order) -> str:
        """Place a new order. Returns order_id."""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of placed order."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass
    
    @abstractmethod
    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio positions."""
        pass


class ZerodhaKiteAPI(BrokerAPI):
    """Zerodha Kite API integration."""
    
    def __init__(self):
        self.session = None
        self.kite = None
        self.authenticated = False
    
    def authenticate(self, credentials: Dict[str, str]) -> bool:
        """
        Authenticate with Zerodha Kite.
        
        Required credentials:
        - api_key: Zerodha API key
        - access_token: Zerodha access token (from login)
        """
        try:
            from kiteconnect import KiteConnect
            
            api_key = credentials.get("api_key")
            access_token = credentials.get("access_token")
            
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
            
            # Test connection
            self.kite.profile()
            self.authenticated = True
            print("[OK] Zerodha Kite authenticated")
            return True
            
        except ImportError:
            print("[ERROR] kiteconnect library not installed")
            print("Install with: pip install kiteconnect")
            return False
        except Exception as e:
            print(f"[ERROR] Auth failed: {e}")
            return False
    
    def get_market_data(self, symbol: str) -> MarketData:
        """Fetch real-time market data from Zerodha."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            quote = self.kite.quote([symbol])
            data = quote[symbol]
            
            return MarketData(
                symbol=symbol,
                current_price=data['last_price'],
                bid=data['bid'],
                ask=data['ask'],
                high=data['high'],
                low=data['low'],
                open=data['open'],
                close=data['close'],
                volume=data['volume'],
            )
        except Exception as e:
            print(f"[ERROR] Market data fetch failed: {e}")
            raise
    
    def get_technicals(self, symbol: str, lookback_days: int = 30) -> Dict[str, float]:
        """Calculate technical indicators."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            data = self.kite.historical_data(
                instrument_token=self._get_token(symbol),
                from_date=f"-{lookback_days}d",
                to_date="now",
                interval="day"
            )
            
            prices = [d['close'] for d in data]
            highs = [d['high'] for d in data]
            lows = [d['low'] for d in data]
            volumes = [d['volume'] for d in data]
            
            rsi = self._calculate_rsi(prices)
            atr = self._calculate_atr(highs, lows, prices)
            support, resistance = self._calculate_sr_levels(highs, lows)
            volume_trend = self._calculate_volume_trend(volumes)
            
            return {
                "rsi": rsi,
                "atr": atr,
                "support": support,
                "resistance": resistance,
                "volume_trend": volume_trend,
            }
        except Exception as e:
            print(f"[ERROR] Technicals calc failed: {e}")
            raise
    
    def place_order(self, order: Order) -> str:
        """Place an order via Zerodha."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            order_response = self.kite.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol=order.symbol,
                transaction_type=order.action,
                quantity=order.quantity,
                price=order.price,
                order_type="LIMIT",
                product="MIS",
            )
            
            print(f"[OK] Order placed: {order_response}")
            return order_response
            
        except Exception as e:
            print(f"[ERROR] Order placement failed: {e}")
            raise
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            orders = self.kite.orders()
            for order in orders:
                if order['order_id'] == order_id:
                    return {
                        "order_id": order['order_id'],
                        "status": order['status'],
                        "price": order['price'],
                        "quantity": order['quantity'],
                        "filled_quantity": order['filled_quantity'],
                    }
            return None
        except Exception as e:
            print(f"[ERROR] Status check failed: {e}")
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            self.kite.cancel_order(order_id=order_id, variety="regular")
            print(f"[OK] Order cancelled: {order_id}")
            return True
        except Exception as e:
            print(f"[ERROR] Cancel failed: {e}")
            return False
    
    def get_portfolio(self) -> Dict[str, Any]:
        """Get portfolio positions."""
        if not self.authenticated:
            raise RuntimeError("Not authenticated")
        
        try:
            return {
                "positions": self.kite.positions(),
                "holdings": self.kite.holdings(),
            }
        except Exception as e:
            print(f"[ERROR] Portfolio fetch failed: {e}")
            raise
    
    @staticmethod
    def _get_token(symbol: str) -> int:
        """Map symbol to Zerodha token."""
        tokens = {"NIFTY50": 99926000, "NIFTY": 99926000}
        return tokens.get(symbol)
    
    @staticmethod
    def _calculate_rsi(prices: list, period: int = 14) -> float:
        """Calculate RSI."""
        if len(prices) < period:
            return None
        
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            gains.append(change if change > 0 else 0)
            losses.append(abs(change) if change < 0 else 0)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def _calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Calculate ATR."""
        if len(highs) < period:
            return None
        
        trs = []
        for i in range(len(highs)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )
            trs.append(tr)
        
        return sum(trs[-period:]) / period
    
    @staticmethod
    def _calculate_sr_levels(highs: list, lows: list) -> tuple:
        """Calculate support and resistance."""
        recent_highs = sorted(highs[-20:], reverse=True)[:3]
        recent_lows = sorted(lows[-20:])[:3]
        
        resistance = sum(recent_highs) / len(recent_highs)
        support = sum(recent_lows) / len(recent_lows)
        
        return support, resistance
    
    @staticmethod
    def _calculate_volume_trend(volumes: list) -> str:
        """Analyze volume trend."""
        if len(volumes) < 5:
            return "neutral"
        
        recent_avg = sum(volumes[-3:]) / 3
        older_avg = sum(volumes[-10:-3]) / 7
        
        if recent_avg > older_avg * 1.2:
            return "increasing"
        elif recent_avg < older_avg * 0.8:
            return "decreasing"
        return "neutral"


class MockBroker(BrokerAPI):
    """Mock broker for testing."""
    
    def __init__(self):
        self.authenticated = False
        self.orders = {}
    
    def authenticate(self, credentials: Dict[str, str]) -> bool:
        print("[MOCK] Authenticated")
        self.authenticated = True
        return True
    
    def get_market_data(self, symbol: str) -> MarketData:
        return MarketData(
            symbol=symbol,
            current_price=24087.65,
            bid=24086.00,
            ask=24089.00,
            high=24150.00,
            low=24050.00,
            open=24100.00,
            close=24087.65,
            volume=94990000,
            rsi=42.0,
            atr=150.00,
            support=24000.00,
            resistance=24500.00,
            volume_trend="increasing",
        )
    
    def get_technicals(self, symbol: str, lookback_days: int = 30) -> Dict[str, float]:
        return {
            "rsi": 42.0,
            "atr": 150.00,
            "support": 24000.00,
            "resistance": 24500.00,
            "volume_trend": "increasing",
        }
    
    def place_order(self, order: Order) -> str:
        order_id = f"MOCK-{len(self.orders) + 1:04d}"
        order.order_id = order_id
        order.status = "ACCEPTED"
        self.orders[order_id] = order
        print(f"[OK] Order placed: {order_id}")
        return order_id
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            order = self.orders[order_id]
            return {
                "order_id": order_id,
                "status": order.status,
                "price": order.price,
                "quantity": order.quantity,
            }
        return None
    
    def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id].status = "CANCELLED"
            print(f"[OK] Order cancelled: {order_id}")
            return True
        return False
    
    def get_portfolio(self) -> Dict[str, Any]:
        return {
            "cash": 100000.00,
            "positions": self.orders,
        }


def get_broker(broker_type: str = "mock") -> BrokerAPI:
    """Factory function to get broker instance."""
    if broker_type.lower() == "zerodha":
        return ZerodhaKiteAPI()
    elif broker_type.lower() == "mock":
        return MockBroker()
    else:
        raise ValueError(f"Unknown broker: {broker_type}")
