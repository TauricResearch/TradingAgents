"""
Momentum Dashboard - Real-time momentum analysis for trading

Features:
- 21 EMA Trend Filter (long above, short below)
- Bollinger Band Squeeze detection
- Volume Momentum confirmation
- Multi-timeframe analysis (1H/Daily/Weekly/Monthly/Quarterly)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

# Magnificent Seven stocks
MAGNIFICENT_SEVEN = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


class MomentumIndicator:
    """Core momentum indicators for the dashboard"""
    
    @staticmethod
    def ema(data: pd.Series, period: int = 21) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return data.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def bollinger_bands(data: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower
    
    @staticmethod
    def bollinger_squeeze(bb_upper: pd.Series, bb_lower: pd.Series, bb_mid: pd.Series, 
                           threshold: float = 0.1) -> pd.Series:
        """
        Detect Bollinger Band Squeeze (low volatility consolidation)
        Returns True when bandwidth is below threshold
        """
        bandwidth = (bb_upper - bb_lower) / bb_mid
        return bandwidth < threshold
    
    @staticmethod
    def volume_momentum(volume: pd.Series, period: int = 20) -> pd.Series:
        """Calculate Volume Momentum (current volume vs average)"""
        avg_volume = volume.rolling(window=period).mean()
        return volume / avg_volume
    
    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


class MomentumScanner:
    """Scan stocks for momentum signals"""
    
    def __init__(self, symbols: List[str] = None):
        self.symbols = symbols or MAGNIFICENT_SEVEN
        self.indicators = MomentumIndicator()
    
    def fetch_data(self, symbol: str, period: str = "3mo", interval: str = "1h") -> pd.DataFrame:
        """Fetch price data from yfinance"""
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        return df
    
    def analyze_symbol(self, symbol: str) -> Dict:
        """Analyze a single symbol for momentum signals"""
        try:
            df = self.fetch_data(symbol)
            if df.empty:
                return {"symbol": symbol, "error": "No data"}
            
            close = df['Close']
            volume = df['Volume']
            
            # Calculate indicators
            ema_21 = self.indicators.ema(close, 21)
            bb_upper, bb_mid, bb_lower = self.indicators.bollinger_bands(close)
            squeeze = self.indicators.bollinger_squeeze(bb_upper, bb_lower, bb_mid)
            vol_momentum = self.indicators.volume_momentum(volume)
            rsi = self.indicators.rsi(close)
            
            # Current values
            current_price = close.iloc[-1]
            current_ema = ema_21.iloc[-1]
            current_rsi = rsi.iloc[-1]
            current_vol_mom = vol_momentum.iloc[-1]
            is_squeeze = squeeze.iloc[-1]
            
            # Signal determination
            trend = "BULLISH" if current_price > current_ema else "BEARISH"
            signal_strength = self._calculate_signal_strength(
                current_price, current_ema, current_rsi, current_vol_mom, is_squeeze
            )
            
            return {
                "symbol": symbol,
                "price": round(current_price, 2),
                "ema_21": round(current_ema, 2),
                "trend": trend,
                "rsi": round(current_rsi, 2),
                "volume_momentum": round(current_vol_mom, 2),
                "squeeze": bool(is_squeeze),
                "signal_strength": signal_strength,
                "signal": self._get_signal(trend, signal_strength, is_squeeze)
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}
    
    def _calculate_signal_strength(self, price, ema, rsi, vol_mom, squeeze) -> float:
        """Calculate overall signal strength (0-100)"""
        score = 50  # Base score
        
        # Price vs EMA contribution
        price_ema_diff = (price - ema) / ema * 100
        score += min(max(price_ema_diff * 5, -20), 20)
        
        # RSI contribution (oversold/overbought)
        if rsi < 30:
            score += 15  # Oversold - potential buy
        elif rsi > 70:
            score -= 15  # Overbought - potential sell
        
        # Volume momentum contribution
        if vol_mom > 1.5:
            score += 10  # High volume confirms trend
        elif vol_mom < 0.5:
            score -= 10  # Low volume weakens signal
        
        return max(0, min(100, round(score)))
    
    def _get_signal(self, trend: str, strength: float, squeeze: bool) -> str:
        """Generate trading signal"""
        if squeeze and strength > 60:
            return "WATCH_FOR_BREAKOUT"
        elif trend == "BULLISH" and strength >= 70:
            return "STRONG_BUY"
        elif trend == "BULLISH" and strength >= 55:
            return "BUY"
        elif trend == "BEARISH" and strength <= 30:
            return "STRONG_SELL"
        elif trend == "BEARISH" and strength <= 45:
            return "SELL"
        else:
            return "HOLD"
    
    def scan_all(self) -> List[Dict]:
        """Scan all symbols and return results"""
        results = []
        for symbol in self.symbols:
            result = self.analyze_symbol(symbol)
            results.append(result)
        return results


def get_top_momentum_stocks(limit: int = 20) -> List[str]:
    """Get top momentum stocks (could be enhanced with real data source)"""
    # For now, return a static list of popular momentum stocks
    momentum_stocks = [
        "SMCI", "ARM", "PLTR", "SNOW", "DDOG", 
        "MDB", "NET", "CRWD", "ZS", "PANW",
        "AMD", "INTC", "QCOM", "AVGO", "TXN"
    ]
    return momentum_stocks[:limit]


if __name__ == "__main__":
    # Test the scanner
    scanner = MomentumScanner()
    results = scanner.scan_all()
    
    print("=" * 60)
    print("MOMENTUM DASHBOARD - MAGNIFICENT SEVEN")
    print("=" * 60)
    print(f"{'Symbol':<8} {'Price':<10} {'Trend':<10} {'RSI':<8} {'Signal':<20}")
    print("-" * 60)
    
    for r in results:
        if "error" not in r:
            print(f"{r['symbol']:<8} ${r['price']:<9} {r['trend']:<10} {r['rsi']:<8} {r['signal']:<20}")
    
    print("=" * 60)