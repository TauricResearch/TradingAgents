"""
Regime-Aware Quantitative Signal Engine

Replaces hardcoded retail logic (RSI < 30 = BUY) with regime-conditional signals.
Prevents "falling knife" trades in bear markets.
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from enum import Enum

# Import regime detector
import sys
sys.path.append('..')
from tradingagents.engines.regime_detector import RegimeDetector, MarketRegime, DynamicIndicatorSelector


class SignalStrength(Enum):
    """Signal strength classifications."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    HOLD = "hold"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class RegimeAwareSignalEngine:
    """
    Generate trading signals that adapt to market regime.
    
    NO MORE HARDCODED RETAIL LOGIC.
    """
    
    def __init__(self):
        self.regime_detector = RegimeDetector()
        self.indicator_selector = DynamicIndicatorSelector()
    
    def generate_rsi_signal(
        self,
        rsi: float,
        prices: pd.Series,
        regime: MarketRegime = None
    ) -> Dict:
        """
        Generate RSI signal CONDITIONAL on market regime.
        
        Args:
            rsi: Current RSI value
            prices: Price series for regime detection
            regime: Pre-detected regime (optional)
        
        Returns:
            {
                "signal": "BUY" | "SELL" | "HOLD",
                "strength": SignalStrength,
                "confidence": 0.0-1.0,
                "reasoning": str
            }
        """
        # Detect regime if not provided
        if regime is None:
            regime, _ = self.regime_detector.detect_regime(prices)
        
        # REGIME-CONDITIONAL LOGIC
        if regime == MarketRegime.TRENDING_UP:
            # Bull market: RSI < 30 = dip buying opportunity
            if rsi < 30:
                return {
                    "signal": "BUY",
                    "strength": SignalStrength.STRONG_BUY,
                    "confidence": 0.85,
                    "reasoning": f"RSI oversold ({rsi:.1f}) in bull market - dip buying opportunity"
                }
            elif rsi > 70:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.WEAK_SELL,
                    "confidence": 0.60,
                    "reasoning": f"RSI overbought ({rsi:.1f}) in bull market - take profits"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.50,
                    "reasoning": f"RSI neutral ({rsi:.1f}) in bull market"
                }
        
        elif regime == MarketRegime.TRENDING_DOWN:
            # Bear market: RSI < 30 = WAIT (falling knife!)
            if rsi < 30:
                return {
                    "signal": "HOLD",  # DO NOT BUY THE DIP IN BEAR MARKETS
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.75,
                    "reasoning": f"RSI oversold ({rsi:.1f}) in bear market - FALLING KNIFE, wait for regime change"
                }
            elif rsi > 70:
                # Rare in bear markets - potential short opportunity
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.STRONG_SELL,
                    "confidence": 0.80,
                    "reasoning": f"RSI overbought ({rsi:.1f}) in bear market - short bounce"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.60,
                    "reasoning": f"RSI neutral ({rsi:.1f}) in bear market - wait for reversal"
                }
        
        elif regime == MarketRegime.MEAN_REVERTING:
            # Mean reversion: Classic RSI logic works
            if rsi < 30:
                return {
                    "signal": "BUY",
                    "strength": SignalStrength.BUY,
                    "confidence": 0.70,
                    "reasoning": f"RSI oversold ({rsi:.1f}) in mean-reverting market - expect bounce"
                }
            elif rsi > 70:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.SELL,
                    "confidence": 0.70,
                    "reasoning": f"RSI overbought ({rsi:.1f}) in mean-reverting market - expect pullback"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.50,
                    "reasoning": f"RSI neutral ({rsi:.1f}) in mean-reverting market"
                }
        
        elif regime == MarketRegime.VOLATILE:
            # High volatility: Use wider bands
            if rsi < 20:  # More extreme threshold
                return {
                    "signal": "BUY",
                    "strength": SignalStrength.WEAK_BUY,
                    "confidence": 0.60,
                    "reasoning": f"RSI extremely oversold ({rsi:.1f}) in volatile market - cautious buy"
                }
            elif rsi > 80:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.WEAK_SELL,
                    "confidence": 0.60,
                    "reasoning": f"RSI extremely overbought ({rsi:.1f}) in volatile market - cautious sell"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.40,
                    "reasoning": f"RSI {rsi:.1f} in volatile market - wait for clearer signal"
                }
        
        else:  # SIDEWAYS
            # Range-bound: Tighter bands
            if rsi < 35:
                return {
                    "signal": "BUY",
                    "strength": SignalStrength.WEAK_BUY,
                    "confidence": 0.65,
                    "reasoning": f"RSI {rsi:.1f} near support in sideways market"
                }
            elif rsi > 65:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.WEAK_SELL,
                    "confidence": 0.65,
                    "reasoning": f"RSI {rsi:.1f} near resistance in sideways market"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.50,
                    "reasoning": f"RSI {rsi:.1f} in middle of range"
                }
    
    def generate_macd_signal(
        self,
        macd: float,
        signal_line: float,
        histogram: float,
        regime: MarketRegime
    ) -> Dict:
        """Generate MACD signal conditional on regime."""
        
        if regime == MarketRegime.TRENDING_UP:
            # Bull market: MACD crossovers are reliable
            if macd > signal_line and histogram > 0:
                return {
                    "signal": "BUY",
                    "strength": SignalStrength.BUY,
                    "confidence": 0.75,
                    "reasoning": f"MACD bullish crossover in uptrend (histogram: {histogram:.2f})"
                }
            elif macd < signal_line and histogram < 0:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.WEAK_SELL,
                    "confidence": 0.60,
                    "reasoning": f"MACD bearish crossover in uptrend - minor pullback"
                }
        
        elif regime == MarketRegime.TRENDING_DOWN:
            # Bear market: Only respect bearish signals
            if macd < signal_line and histogram < 0:
                return {
                    "signal": "SELL",
                    "strength": SignalStrength.SELL,
                    "confidence": 0.75,
                    "reasoning": f"MACD bearish crossover in downtrend (histogram: {histogram:.2f})"
                }
            else:
                return {
                    "signal": "HOLD",
                    "strength": SignalStrength.HOLD,
                    "confidence": 0.50,
                    "reasoning": "MACD bullish signal in bear market - likely false breakout"
                }
        
        # Default for other regimes
        return {
            "signal": "HOLD",
            "strength": SignalStrength.HOLD,
            "confidence": 0.50,
            "reasoning": f"MACD neutral in {regime.value} market"
        }


# Example usage
if __name__ == "__main__":
    # Simulate price data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # Bear market scenario
    bear_prices = pd.Series(100 - np.cumsum(np.random.randn(100) * 0.5 + 0.2), index=dates)
    
    engine = RegimeAwareSignalEngine()
    
    # Test RSI signal in bear market
    rsi_value = 25  # Oversold
    signal = engine.generate_rsi_signal(rsi_value, bear_prices)
    
    print(f"RSI: {rsi_value}")
    print(f"Signal: {signal['signal']}")
    print(f"Reasoning: {signal['reasoning']}")
    # Expected: HOLD (not BUY) - prevents falling knife
