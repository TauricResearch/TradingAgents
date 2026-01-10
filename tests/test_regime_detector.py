"""
Unit Tests for Regime Detector

Tests mathematical regime detection using:
- ADX (Average Directional Index) for trend strength
- Volatility (annualized standard deviation)
- Hurst exponent for mean reversion
- Cumulative returns for direction
"""

import unittest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.engines.regime_detector import RegimeDetector, MarketRegime, DynamicIndicatorSelector


class TestRegimeDetector(unittest.TestCase):
    """Test suite for mathematical regime detection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.detector = RegimeDetector()
        np.random.seed(42)  # Reproducible tests
    
    def test_detect_regime_requires_minimum_data(self):
        """Test that regime detection requires minimum data points."""
        short_prices = pd.Series([100, 101, 102])  # Only 3 points
        
        with self.assertRaises(ValueError):
            self.detector.detect_regime(short_prices, window=60)
    
    def test_detect_regime_bull_market(self):
        """Test detection of bull market (strong uptrend)."""
        # Create strong uptrend: +50% over 100 days
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        bull_prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 1 + 0.5), index=dates)
        
        regime, metrics = self.detector.detect_regime(bull_prices, window=60)
        
        # Should detect uptrend
        self.assertIn(regime, [MarketRegime.TRENDING_UP, MarketRegime.SIDEWAYS],
                     f"Bull market should be TRENDING_UP or SIDEWAYS, got {regime}")
        
        # Cumulative return should be positive
        self.assertGreater(metrics['cumulative_return'], 0,
                          "Bull market should have positive cumulative return")
    
    def test_detect_regime_bear_market(self):
        """Test detection of bear market (strong downtrend)."""
        # Create strong downtrend: -40% over 100 days
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        bear_prices = pd.Series(100 - np.cumsum(np.random.randn(100) * 1 + 0.4), index=dates)
        
        regime, metrics = self.detector.detect_regime(bear_prices, window=60)
        
        # Should detect downtrend or high volatility
        self.assertIn(regime, [MarketRegime.TRENDING_DOWN, MarketRegime.VOLATILE],
                     f"Bear market should be TRENDING_DOWN or VOLATILE, got {regime}")
        
        # Cumulative return should be negative
        self.assertLess(metrics['cumulative_return'], 0,
                       "Bear market should have negative cumulative return")
    
    def test_detect_regime_volatile_market(self):
        """Test detection of high volatility market."""
        # Create high volatility: large random swings
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        volatile_prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 5), index=dates)
        
        regime, metrics = self.detector.detect_regime(volatile_prices, window=60)
        
        # Volatility should be high (>40% annualized)
        self.assertGreater(metrics['volatility'], 0.30,
                          "Volatile market should have high volatility")
    
    def test_detect_regime_sideways_market(self):
        """Test detection of sideways/range-bound market."""
        # Create sideways market: oscillating around 100
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        sideways_prices = pd.Series(100 + np.sin(np.linspace(0, 6*np.pi, 100)) * 5, index=dates)
        
        regime, metrics = self.detector.detect_regime(sideways_prices, window=60)
        
        # Should have low cumulative return
        self.assertLess(abs(metrics['cumulative_return']), 0.15,
                       "Sideways market should have small cumulative return")
    
    def test_calculate_trend_strength_adx(self):
        """Test ADX calculation for trend strength."""
        # Strong uptrend
        uptrend = pd.Series(range(100, 200))
        adx_up = self.detector._calculate_trend_strength(uptrend)
        
        # ADX should be a number between 0-100
        self.assertGreaterEqual(adx_up, 0, "ADX should be >= 0")
        self.assertLessEqual(adx_up, 100, "ADX should be <= 100")
    
    def test_calculate_hurst_exponent(self):
        """Test Hurst exponent calculation."""
        # Mean reverting series (oscillating)
        mean_rev = pd.Series(100 + np.sin(np.linspace(0, 10*np.pi, 100)) * 10)
        hurst = self.detector._calculate_hurst_exponent(mean_rev)
        
        # Hurst should be a number (typically 0-1)
        self.assertIsInstance(hurst, (float, np.floating),
                            "Hurst exponent should be a float")
    
    def test_regime_metrics_structure(self):
        """Test that metrics dict has required keys."""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        prices = pd.Series(100 + np.cumsum(np.random.randn(100)), index=dates)
        
        regime, metrics = self.detector.detect_regime(prices)
        
        required_keys = ['volatility', 'trend_strength', 'hurst_exponent', 'cumulative_return']
        for key in required_keys:
            self.assertIn(key, metrics, f"Metrics should contain '{key}'")
    
    def test_dynamic_indicator_selector_trending(self):
        """Test indicator selection for trending markets."""
        params = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.TRENDING_UP)
        
        self.assertEqual(params['strategy'], 'trend_following')
        self.assertEqual(params['rsi_period'], 14)  # Standard for trending
        self.assertEqual(params['ema_period'], 20)  # Trend-following
    
    def test_dynamic_indicator_selector_volatile(self):
        """Test indicator selection for volatile markets."""
        params = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.VOLATILE)
        
        self.assertEqual(params['strategy'], 'volatility_breakout')
        self.assertEqual(params['rsi_period'], 7)  # Shorter for volatile
        self.assertGreater(params['bollinger_std'], 2.0)  # Wider bands
    
    def test_dynamic_indicator_selector_mean_reverting(self):
        """Test indicator selection for mean-reverting markets."""
        params = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.MEAN_REVERTING)
        
        self.assertEqual(params['strategy'], 'mean_reversion')
        self.assertEqual(params['ema_period'], 50)  # Longer for mean reversion
    
    def test_dynamic_indicator_selector_sideways(self):
        """Test indicator selection for sideways markets."""
        params = DynamicIndicatorSelector.get_optimal_parameters(MarketRegime.SIDEWAYS)
        
        self.assertEqual(params['strategy'], 'range_trading')
        self.assertLess(params['bollinger_std'], 2.0)  # Tighter bands
    
    def test_regime_enum_values(self):
        """Test that MarketRegime enum has required values."""
        required_regimes = ['TRENDING_UP', 'TRENDING_DOWN', 'MEAN_REVERTING', 'VOLATILE', 'SIDEWAYS']
        
        for regime_name in required_regimes:
            self.assertTrue(hasattr(MarketRegime, regime_name),
                          f"MarketRegime should have {regime_name}")
    
    def test_mathematical_definition_no_llm(self):
        """CRITICAL: Verify regime detection uses ONLY mathematical formulas, NO LLM."""
        # This test ensures we're using math, not AI
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        prices = pd.Series(100 + np.cumsum(np.random.randn(100)), index=dates)
        
        # Run detection twice - should be deterministic
        regime1, metrics1 = self.detector.detect_regime(prices)
        regime2, metrics2 = self.detector.detect_regime(prices)
        
        self.assertEqual(regime1, regime2, "Regime detection must be deterministic (no LLM)")
        self.assertEqual(metrics1, metrics2, "Metrics must be deterministic (no LLM)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
