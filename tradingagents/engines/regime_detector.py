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
    def _ensure_series(data) -> pd.Series:
        """Robustly coerce input into a Price Series."""
        try:
            # 1. Already a Series
            if isinstance(data, pd.Series):
                return data
                
            # 2. DataFrame (Use 'Close' or first column)
            if isinstance(data, pd.DataFrame):
                # Flexible column search
                cols = [c.lower() for c in data.columns]
                if "close" in cols:
                    return data.iloc[:, cols.index("close")]
                return data.iloc[:, 0]
                
            # 3. String (CSV Parsing)
            if isinstance(data, str):
                import io
                # Check for standard headers or data
                if "Date" in data or "Close" in data or len(data) > 20:
                    # ROBUST DELIMITER DETECTION
                    # Sniff first few lines for the most likely delimiter
                    sample = data[:1000]
                    if "\t" in sample:
                        delimiter = "\t"
                    elif "," in sample:
                        delimiter = ","
                    else:
                        delimiter = r"\s+" # Fallback to whitespace
                    
                    # Don't parse dates - RegimeDetector only needs numeric Close prices
                    df = pd.read_csv(io.StringIO(data), sep=delimiter, index_col=0, 
                                    engine='python', # Required for regex \s+
                                    parse_dates=False, comment='#', on_bad_lines='skip')
                    # Recurse to handle the DataFrame case
                    return RegimeDetector._ensure_series(df)
                    
            return pd.Series(dtype=float)
        except Exception as e:
            print(f"RegimeDetector Input Parsing Error: {e}")
            return pd.Series(dtype=float)

    @staticmethod
    def detect_regime(prices_input, window: int = 60) -> Tuple[MarketRegime, Dict]:
        """
        Determines the market regime based on Volatility, ADX, and Returns.
        INCLUDES 'MOMENTUM EXCEPTION' for high-growth stocks.
        """
        try:
            # 0. Coerce Input
            prices = RegimeDetector._ensure_series(prices_input)
            
            # DEBUG LOGGING
            try:
                from tradingagents.utils.logger import app_logger as logger
                logger.debug(f"RegimeDetector Input: OriginalType={type(prices_input)} -> ParsedSize={len(prices)}")
            except ImportError:
                print(f"DEBUG: Regime Input: {type(prices_input)} -> {len(prices)}")

            if len(prices) < window:
                # Fallback for short history
                if len(prices) > 10:
                    window = len(prices) - 1
                else:
                    return MarketRegime.SIDEWAYS, {}

            # 1. Calculate Metrics
            # We use existing helper methods but adapt the call signature slightly if needed
            # The user provided logic assumes 'market_data' DataFrame but we take 'prices' Series
            # We will adapt the user's logic to work with the Series input or reconstruct DataFrame if needed
            # Actually, standardizing on the existing helper methods is safer, but implementing the LOGIC FLOD is key.
            
            # Reconstruct helpers calls based on existing class structure
            
            # Volatility
            returns = prices.pct_change().dropna()
            recent_returns = returns.tail(window)
            volatility = recent_returns.std() * np.sqrt(252)
            
            # ADX
            trend_strength = RegimeDetector._calculate_trend_strength(prices.tail(window))
            
            # Hurst
            hurst = RegimeDetector._calculate_hurst_exponent(prices.tail(window))
            
            # Simple Price Return
            start_price = prices.iloc[-window]
            end_price = prices.iloc[-1]
            price_change_pct = (end_price - start_price) / start_price
            
            # Full history return (keeping from previous logic as extra metric)
            # Handle edge cases: NaN values, zero prices, insufficient data
            try:
                first_price = prices.iloc[0]
                last_price = prices.iloc[-1]
                if pd.notnull(first_price) and pd.notnull(last_price) and first_price > 0:
                    full_history_return = (last_price / first_price) - 1
                else:
                    full_history_return = price_change_pct  # Fallback to window return
            except:
                full_history_return = price_change_pct

            # 2. DEFINE THRESHOLDS
            VOLATILITY_THRESHOLD = 0.40  # 40% Annualized Volatility
            ADX_STRONG_TREND = 25.0
            
            # Metrics dict
            metrics = {
                "volatility": volatility,
                "trend_strength": trend_strength,
                "hurst_exponent": hurst,
                "cumulative_return": price_change_pct,
                "overall_return": full_history_return
            }

            # 3. THE LOGIC CASCADE
            
            # 🛑 CRITICAL FIX: THE MOMENTUM EXCEPTION
            # If stock is volatile BUT going up strongly, it is BULLISH, not VOLATILE.
            if volatility > VOLATILITY_THRESHOLD:
                if price_change_pct > 0 and trend_strength > ADX_STRONG_TREND:
                     # "High Beta Breakout"
                    return MarketRegime.TRENDING_UP, metrics
                else:
                    # "Crashing / Chopping"
                    return MarketRegime.VOLATILE, metrics
            
            # Standard Logic for Lower Volatility
            if trend_strength > ADX_STRONG_TREND:
                regime = MarketRegime.TRENDING_UP if price_change_pct > 0 else MarketRegime.TRENDING_DOWN
                return regime, metrics
            
            # Mean Reverting Logic
            if hurst < 0.4:
                return MarketRegime.MEAN_REVERTING, metrics
                
            return MarketRegime.SIDEWAYS, metrics

        except Exception as e:
            print(f"Regime Detection Error: {e}")
            return MarketRegime.SIDEWAYS, {"error": str(e)}
    
    @staticmethod
    def _calculate_trend_strength(prices: pd.Series) -> float:
        """
        Calculate trend strength (ADX approximation).
        
        Returns value 0-100, where >25 indicates strong trend.
        """
        prices = prices.dropna()
        if len(prices) < 14:
            return 0.0

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
        
        # Avoid division by zero
        atr = atr.replace(0, np.nan).ffill().fillna(1e-9)

        # Reconstruct Series with correct index to align with ATR
        plus_di = 100 * pd.Series(plus_dm, index=prices.index).ewm(span=14, adjust=False).mean() / atr
        minus_di = 100 * pd.Series(minus_dm, index=prices.index).ewm(span=14, adjust=False).mean() / atr
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        # Handle DX NaNs (caused by 0 division if +DI and -DI are both 0)
        dx = dx.fillna(0)
        
        adx = dx.ewm(span=14, adjust=False).mean()
        
        return adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0.0
    
    @staticmethod
    def _calculate_hurst_exponent(prices: pd.Series) -> float:
        """
        Calculate Hurst exponent with safety checks.
        """
        try:
            lags = range(2, 20)
            tau = [np.std(np.subtract(prices[lag:], prices[:-lag].values)) for lag in lags]
            
            # Filter out non-positive values to avoid log errors
            valid_idx = [i for i, t in enumerate(tau) if t > 0]
            if len(valid_idx) < 2:
                return 0.5 # Random walk default
                
            valid_lags = [lags[i] for i in valid_idx]
            valid_tau = [tau[i] for i in valid_idx]
            
            # Linear regression of log(tau) vs log(lags)
            poly = np.polyfit(np.log(valid_lags), np.log(valid_tau), 1)
            hurst = poly[0]
            
            return hurst
        except Exception:
            return 0.5 # Default to random walk on error


class DynamicIndicatorSelector:
    """Select optimal indicator parameters based on regime."""
    
    @staticmethod
    def get_optimal_parameters(regime: MarketRegime, overrides: Dict = None) -> Dict:
        """
        Get optimal indicator parameters for detected regime.
        
        Returns dict with recommended settings for RSI, MACD, Bollinger, etc.
        Applies 'overrides' from runtime_config if provided.
        """
        if overrides is None:
            overrides = {}
            
        defaults = {}
        
        if regime == MarketRegime.TRENDING_UP or regime == MarketRegime.TRENDING_DOWN:
            defaults = {
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
            defaults = {
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
            defaults = {
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
            defaults = {
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
            
        # Apply Overrides
        if overrides:
            for key, val in overrides.items():
                if key in defaults:
                    print(f"🔄 TUNING: Overriding {key} from {defaults[key]} to {val}")
                    defaults[key] = val
                    
        return defaults


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
