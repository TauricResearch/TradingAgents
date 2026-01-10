"""
Regime Detection Engine - Dynamic Market Classification

Detects market regime to enable adaptive indicator selection.
Replaces static 1980s parameters with regime-aware dynamic settings.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from enum import Enum


class MarketRegime(Enum):
    """Market regime classifications."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    SIDEWAYS = "sideways"


class RegimeDetector:
    """Detect market regime using statistical methods."""
    
    @staticmethod
    def detect_regime(prices: pd.Series, window: int = 60) -> Tuple[MarketRegime, Dict]:
        """
        Detect current market regime.
        
        Args:
            prices: Price series (must have at least 'window' data points)
            window: Lookback period for regime detection
        
        Returns:
            (regime, metrics) tuple where metrics contains diagnostic info
        """
        if len(prices) < window:
            raise ValueError(f"Need at least {window} data points, got {len(prices)}")
        
        # Calculate regime metrics
        returns = prices.pct_change().dropna()
        recent_returns = returns.tail(window)
        
        # 1. Volatility (annualized)
        volatility = recent_returns.std() * np.sqrt(252)
        
        # 2. Trend strength (ADX approximation)
        trend_strength = RegimeDetector._calculate_trend_strength(prices.tail(window))
        
        # 3. Mean reversion tendency (Hurst exponent)
        hurst = RegimeDetector._calculate_hurst_exponent(prices.tail(window))
        
        # 4. Directional bias
        cumulative_return = (prices.iloc[-1] / prices.iloc[-window]) - 1
        
        # Classify regime
        metrics = {
            "volatility": volatility,
            "trend_strength": trend_strength,
            "hurst_exponent": hurst,
            "cumulative_return": cumulative_return,
        }
        
        # Decision tree for regime classification
        if volatility > 0.40:  # High volatility (>40% annualized)
            regime = MarketRegime.VOLATILE
        elif trend_strength > 25:  # Strong trend (ADX > 25)
            if cumulative_return > 0:
                regime = MarketRegime.TRENDING_UP
            else:
                regime = MarketRegime.TRENDING_DOWN
        elif hurst < 0.5:  # Mean reverting (Hurst < 0.5)
            regime = MarketRegime.MEAN_REVERTING
        else:  # Low volatility, no clear trend
            regime = MarketRegime.SIDEWAYS
        
        return regime, metrics
    
    @staticmethod
    def _calculate_trend_strength(prices: pd.Series) -> float:
        """
        Calculate trend strength (ADX approximation).
        
        Returns value 0-100, where >25 indicates strong trend.
        """
        high = prices.rolling(2).max()
        low = prices.rolling(2).min()
        
        # True Range
        tr = high - low
        
        # Directional Movement
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Smooth with 14-period EMA
        atr = pd.Series(tr).ewm(span=14, adjust=False).mean()
        plus_di = 100 * pd.Series(plus_dm).ewm(span=14, adjust=False).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).ewm(span=14, adjust=False).mean() / atr
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=14, adjust=False).mean()
        
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0
    
    @staticmethod
    def _calculate_hurst_exponent(prices: pd.Series) -> float:
        """
        Calculate Hurst exponent.
        
        Returns:
            H < 0.5: Mean reverting
            H = 0.5: Random walk
            H > 0.5: Trending
        """
        lags = range(2, 20)
        tau = [np.std(np.subtract(prices[lag:], prices[:-lag])) for lag in lags]
        
        # Linear regression of log(tau) vs log(lags)
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        hurst = poly[0]
        
        return hurst


class DynamicIndicatorSelector:
    """Select optimal indicator parameters based on regime."""
    
    @staticmethod
    def get_optimal_parameters(regime: MarketRegime) -> Dict:
        """
        Get optimal indicator parameters for detected regime.
        
        Returns dict with recommended settings for RSI, MACD, Bollinger, etc.
        """
        if regime == MarketRegime.TRENDING_UP or regime == MarketRegime.TRENDING_DOWN:
            return {
                "rsi_period": 14,  # Standard for trending
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "bollinger_period": 20,
                "bollinger_std": 2.0,
                "ema_period": 20,  # Trend-following
                "strategy": "trend_following",
                "rationale": "Strong trend detected - use trend-following indicators"
            }
        
        elif regime == MarketRegime.VOLATILE:
            return {
                "rsi_period": 7,  # Shorter for volatile markets
                "macd_fast": 8,
                "macd_slow": 17,
                "macd_signal": 9,
                "bollinger_period": 10,  # Tighter bands
                "bollinger_std": 2.5,  # Wider to account for volatility
                "ema_period": 10,
                "strategy": "volatility_breakout",
                "rationale": "High volatility - use shorter periods and wider bands"
            }
        
        elif regime == MarketRegime.MEAN_REVERTING:
            return {
                "rsi_period": 14,
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "bollinger_period": 20,
                "bollinger_std": 2.0,
                "ema_period": 50,  # Longer for mean reversion
                "strategy": "mean_reversion",
                "rationale": "Mean reverting market - trade extremes back to average"
            }
        
        else:  # SIDEWAYS
            return {
                "rsi_period": 21,  # Longer to avoid noise
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "bollinger_period": 20,
                "bollinger_std": 1.5,  # Tighter for range-bound
                "ema_period": 50,
                "strategy": "range_trading",
                "rationale": "Sideways market - trade support/resistance levels"
            }


# Example usage
if __name__ == "__main__":
    # Simulate price data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # Trending market
    trend_prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5 + 0.3), index=dates)
    regime, metrics = RegimeDetector.detect_regime(trend_prices)
    params = DynamicIndicatorSelector.get_optimal_parameters(regime)
    
    print(f"Detected Regime: {regime.value}")
    print(f"Metrics: {metrics}")
    print(f"Recommended Parameters: {params}")
