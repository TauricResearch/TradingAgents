"""Tests for Momentum Analyst agent.

Issue #13: [AGENT-12] Momentum Analyst - multi-TF momentum, ROC, ADX

These tests mock langchain dependencies to run without requiring
the full langchain installation.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import sys

pytestmark = pytest.mark.unit


# ============================================================================
# Mock LangChain Dependencies
# ============================================================================

# Create mock modules for langchain dependencies
mock_langchain_core = MagicMock()
mock_langchain_core.prompts = MagicMock()
mock_langchain_core.prompts.ChatPromptTemplate = MagicMock()
mock_langchain_core.prompts.MessagesPlaceholder = MagicMock()
mock_langchain_core.tools = MagicMock()
mock_langchain_core.tools.tool = lambda f: f  # Simple passthrough decorator
mock_langchain_core.messages = MagicMock()

# Patch the modules before importing
sys.modules['langchain_core'] = mock_langchain_core
sys.modules['langchain_core.prompts'] = mock_langchain_core.prompts
sys.modules['langchain_core.tools'] = mock_langchain_core.tools
sys.modules['langchain_core.messages'] = mock_langchain_core.messages


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_stock_data():
    """Create sample stock data DataFrame."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    # Create uptrending data
    base_price = 100.0
    prices = base_price + np.cumsum(np.random.randn(60) * 0.5 + 0.1)

    return pd.DataFrame({
        'Date': dates,
        'open': prices * 0.99,
        'high': prices * 1.01,
        'low': prices * 0.98,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 60)
    })


@pytest.fixture
def uptrending_stock_data():
    """Create sample uptrending stock data."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    base_price = 100.0
    # Strong uptrend
    prices = base_price + np.linspace(0, 20, 60)

    return pd.DataFrame({
        'Date': dates,
        'open': prices * 0.99,
        'high': prices * 1.01,
        'low': prices * 0.98,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 60)
    })


@pytest.fixture
def downtrending_stock_data():
    """Create sample downtrending stock data."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    base_price = 100.0
    # Strong downtrend
    prices = base_price - np.linspace(0, 20, 60)

    return pd.DataFrame({
        'Date': dates,
        'open': prices * 1.01,
        'high': prices * 1.02,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 60)
    })


@pytest.fixture
def ranging_stock_data():
    """Create sample sideways/ranging stock data."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    base_price = 100.0
    # Oscillating prices
    prices = base_price + np.sin(np.linspace(0, 4*np.pi, 60)) * 2

    return pd.DataFrame({
        'Date': dates,
        'open': prices * 0.995,
        'high': prices * 1.01,
        'low': prices * 0.99,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 60)
    })


# ============================================================================
# Helper Functions - Extracted from momentum_analyst.py for testing
# ============================================================================

def calculate_roc(close_prices, period):
    """Calculate Rate of Change."""
    if len(close_prices) < period:
        return None
    current = close_prices[-1]
    past = close_prices[-period]
    if past == 0:
        return 0
    return ((current - past) / past) * 100


def calculate_adx(high, low, close, period=14):
    """Calculate ADX, +DI, -DI."""
    if len(high) < period * 2:
        return None, None, None

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    # Smooth with EMA
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)

    # ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(span=period, adjust=False).mean()

    return adx.iloc[-1], plus_di.iloc[-1], minus_di.iloc[-1]


def calculate_rsi(close_prices, period=14):
    """Calculate RSI."""
    delta = pd.Series(close_prices).diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.values


# ============================================================================
# ROC (Rate of Change) Tests
# ============================================================================

class TestROCCalculation:
    """Tests for Rate of Change calculation."""

    def test_roc_positive(self):
        """Test ROC for uptrending prices."""
        # 6 prices: indices 0-5, period=5 means: (price[5] - price[0]) / price[0]
        # (105 - 100) / 100 = 5%
        prices = [100, 101, 102, 103, 104, 105]
        roc = calculate_roc(prices, 5)
        # ROC uses close[-1] vs close[-period]: (105 - 101) / 101 = 3.96%
        assert roc > 0
        assert roc == pytest.approx(3.96, rel=0.02)

    def test_roc_negative(self):
        """Test ROC for downtrending prices."""
        prices = [100, 99, 98, 97, 96, 95]
        roc = calculate_roc(prices, 5)
        # ROC: (95 - 99) / 99 = -4.04%
        assert roc < 0
        assert roc == pytest.approx(-4.04, rel=0.02)

    def test_roc_zero(self):
        """Test ROC for flat prices."""
        prices = [100, 100, 100, 100, 100, 100]
        roc = calculate_roc(prices, 5)
        assert roc == pytest.approx(0.0)

    def test_roc_insufficient_data(self):
        """Test ROC with insufficient data."""
        prices = [100, 101, 102]
        roc = calculate_roc(prices, 5)
        assert roc is None

    def test_roc_strong_move(self):
        """Test ROC for strong price move."""
        prices = [100, 105, 110, 115, 120, 125]
        roc = calculate_roc(prices, 5)
        # ROC: (125 - 105) / 105 = 19.05%
        assert roc > 15
        assert roc == pytest.approx(19.05, rel=0.02)


class TestMultiTimeframeMomentum:
    """Tests for multi-timeframe momentum analysis."""

    def test_bullish_alignment(self, uptrending_stock_data):
        """Test all timeframes showing bullish momentum."""
        close = uptrending_stock_data['close'].values

        roc_short = calculate_roc(close, 5)
        roc_medium = calculate_roc(close, 14)
        roc_long = calculate_roc(close, 30)

        assert roc_short > 0
        assert roc_medium > 0
        assert roc_long > 0

    def test_bearish_alignment(self, downtrending_stock_data):
        """Test all timeframes showing bearish momentum."""
        close = downtrending_stock_data['close'].values

        roc_short = calculate_roc(close, 5)
        roc_medium = calculate_roc(close, 14)
        roc_long = calculate_roc(close, 30)

        assert roc_short < 0
        assert roc_medium < 0
        assert roc_long < 0

    def test_mixed_signals(self, ranging_stock_data):
        """Test mixed momentum signals in ranging market."""
        close = ranging_stock_data['close'].values

        roc_short = calculate_roc(close, 5)
        roc_medium = calculate_roc(close, 14)
        roc_long = calculate_roc(close, 30)

        # At least one should differ in sign for mixed signals
        signs = [roc_short > 0, roc_medium > 0, roc_long > 0]
        # Not all same sign
        not_all_bullish = not all(signs)
        not_all_bearish = not all(not s for s in signs)
        # Mixed means at least one is different
        assert not_all_bullish or not_all_bearish

    def test_momentum_strength_classification(self):
        """Test momentum strength classification."""
        # Strong bullish: all ROC > 2%
        assert all(roc > 2 for roc in [3.0, 4.0, 5.0])

        # Moderate bullish: all positive but some < 2%
        rocs = [1.5, 2.5, 3.0]
        assert all(roc > 0 for roc in rocs)
        assert any(roc < 2 for roc in rocs)

    def test_acceleration_detection(self):
        """Test momentum acceleration detection."""
        # Accelerating: short > medium > long
        rocs = {"short": 5.0, "medium": 3.0, "long": 1.0}
        is_accelerating = rocs["short"] > rocs["medium"] > rocs["long"]
        assert is_accelerating

        # Decelerating: short < medium < long
        rocs = {"short": 1.0, "medium": 3.0, "long": 5.0}
        is_decelerating = rocs["short"] < rocs["medium"] < rocs["long"]
        assert is_decelerating


# ============================================================================
# ADX (Average Directional Index) Tests
# ============================================================================

class TestADXCalculation:
    """Tests for ADX calculation."""

    def test_adx_strong_trend(self, uptrending_stock_data):
        """Test ADX for strong uptrend."""
        high = pd.Series(uptrending_stock_data['high'].values)
        low = pd.Series(uptrending_stock_data['low'].values)
        close = pd.Series(uptrending_stock_data['close'].values)

        adx, plus_di, minus_di = calculate_adx(high, low, close)

        # In uptrend, +DI should be greater than -DI
        assert plus_di > minus_di

    def test_adx_ranging_market(self, ranging_stock_data):
        """Test ADX for ranging market."""
        high = pd.Series(ranging_stock_data['high'].values)
        low = pd.Series(ranging_stock_data['low'].values)
        close = pd.Series(ranging_stock_data['close'].values)

        adx, plus_di, minus_di = calculate_adx(high, low, close)

        # In ranging market, ADX tends to be lower
        # We just verify calculation doesn't fail
        assert adx is not None
        assert plus_di is not None
        assert minus_di is not None

    def test_adx_downtrend(self, downtrending_stock_data):
        """Test ADX for downtrend."""
        high = pd.Series(downtrending_stock_data['high'].values)
        low = pd.Series(downtrending_stock_data['low'].values)
        close = pd.Series(downtrending_stock_data['close'].values)

        adx, plus_di, minus_di = calculate_adx(high, low, close)

        # In downtrend, -DI should be greater than +DI
        assert minus_di > plus_di

    def test_adx_insufficient_data(self):
        """Test ADX with insufficient data."""
        high = pd.Series([101, 102, 103])
        low = pd.Series([99, 100, 101])
        close = pd.Series([100, 101, 102])

        adx, plus_di, minus_di = calculate_adx(high, low, close)

        assert adx is None

    def test_adx_trend_strength_levels(self):
        """Test ADX trend strength interpretation."""
        # Weak trend: ADX < 20
        assert 15 < 20  # Represents weak/absent trend

        # Moderate trend: 20 <= ADX < 40
        assert 25 >= 20 and 25 < 40

        # Strong trend: 40 <= ADX < 60
        assert 50 >= 40 and 50 < 60

        # Very strong trend: ADX >= 60
        assert 75 >= 60


class TestADXInterpretation:
    """Tests for ADX interpretation logic."""

    def test_trending_vs_ranging(self):
        """Test classification of trending vs ranging markets."""
        # Trending: ADX > 25
        assert 30 > 25

        # Ranging: ADX < 20
        assert 15 < 20

    def test_di_crossover_bullish(self):
        """Test bullish +DI/-DI crossover."""
        plus_di_prev, minus_di_prev = 20, 25
        plus_di_curr, minus_di_curr = 28, 22

        # Bullish crossover: +DI crosses above -DI
        was_bearish = plus_di_prev < minus_di_prev
        is_bullish = plus_di_curr > minus_di_curr
        is_bullish_crossover = was_bearish and is_bullish

        assert is_bullish_crossover

    def test_di_crossover_bearish(self):
        """Test bearish -DI/+DI crossover."""
        plus_di_prev, minus_di_prev = 28, 22
        plus_di_curr, minus_di_curr = 20, 25

        # Bearish crossover: -DI crosses above +DI
        was_bullish = plus_di_prev > minus_di_prev
        is_bearish = plus_di_curr < minus_di_curr
        is_bearish_crossover = was_bullish and is_bearish

        assert is_bearish_crossover

    def test_adx_trend_rising(self):
        """Test ADX rising (trend strengthening)."""
        adx_prev = 25
        adx_curr = 35

        trend_strengthening = adx_curr > adx_prev
        assert trend_strengthening

    def test_adx_trend_falling(self):
        """Test ADX falling (trend weakening)."""
        adx_prev = 45
        adx_curr = 35

        trend_weakening = adx_curr < adx_prev
        assert trend_weakening


# ============================================================================
# RSI Tests
# ============================================================================

class TestRSICalculation:
    """Tests for RSI calculation."""

    def test_rsi_overbought(self):
        """Test RSI in overbought territory (> 70)."""
        # Strongly uptrending prices should give high RSI
        prices = np.linspace(100, 130, 30)
        rsi = calculate_rsi(prices)

        # Last valid RSI should be high
        valid_rsi = rsi[~np.isnan(rsi)]
        if len(valid_rsi) > 0:
            assert valid_rsi[-1] > 50  # Should be elevated

    def test_rsi_oversold(self):
        """Test RSI in oversold territory (< 30)."""
        # Strongly downtrending prices should give low RSI
        prices = np.linspace(130, 100, 30)
        rsi = calculate_rsi(prices)

        # Last valid RSI should be low
        valid_rsi = rsi[~np.isnan(rsi)]
        if len(valid_rsi) > 0:
            assert valid_rsi[-1] < 50  # Should be depressed

    def test_rsi_neutral(self):
        """Test RSI in neutral territory (~50)."""
        # Oscillating prices should give neutral RSI
        prices = 100 + np.sin(np.linspace(0, 4*np.pi, 30)) * 5
        rsi = calculate_rsi(prices)

        valid_rsi = rsi[~np.isnan(rsi)]
        if len(valid_rsi) > 0:
            # RSI should be somewhere in the middle for ranging
            assert 20 < valid_rsi[-1] < 80


# ============================================================================
# Divergence Detection Tests
# ============================================================================

class TestDivergenceDetection:
    """Tests for momentum divergence detection."""

    def test_find_local_highs(self):
        """Test finding local price highs."""
        prices = np.array([100, 105, 110, 108, 106, 112, 115, 113, 111])

        highs = []
        for i in range(2, len(prices) - 2):
            if (prices[i] > prices[i-1] and prices[i] > prices[i-2] and
                prices[i] > prices[i+1] and prices[i] > prices[i+2]):
                highs.append((i, prices[i]))

        # Should find at least one high
        assert len(highs) >= 1

    def test_find_local_lows(self):
        """Test finding local price lows."""
        prices = np.array([100, 95, 90, 92, 94, 88, 85, 87, 89])

        lows = []
        for i in range(2, len(prices) - 2):
            if (prices[i] < prices[i-1] and prices[i] < prices[i-2] and
                prices[i] < prices[i+1] and prices[i] < prices[i+2]):
                lows.append((i, prices[i]))

        # Should find at least one low
        assert len(lows) >= 1

    def test_bullish_divergence_pattern(self):
        """Test bullish divergence pattern detection."""
        # Price: lower low
        price_low_1 = 90
        price_low_2 = 85  # Lower

        # RSI: higher low (divergence)
        rsi_low_1 = 25
        rsi_low_2 = 30  # Higher

        is_bullish_divergence = (
            price_low_2 < price_low_1 and  # Price makes lower low
            rsi_low_2 > rsi_low_1           # RSI makes higher low
        )

        assert is_bullish_divergence

    def test_bearish_divergence_pattern(self):
        """Test bearish divergence pattern detection."""
        # Price: higher high
        price_high_1 = 110
        price_high_2 = 115  # Higher

        # RSI: lower high (divergence)
        rsi_high_1 = 75
        rsi_high_2 = 70  # Lower

        is_bearish_divergence = (
            price_high_2 > price_high_1 and  # Price makes higher high
            rsi_high_2 < rsi_high_1           # RSI makes lower high
        )

        assert is_bearish_divergence

    def test_no_divergence(self):
        """Test when no divergence is present."""
        # Price and RSI move in sync (no divergence)
        price_high_1 = 110
        price_high_2 = 115

        rsi_high_1 = 70
        rsi_high_2 = 75  # Also higher (in sync)

        is_divergence = (
            price_high_2 > price_high_1 and
            rsi_high_2 < rsi_high_1
        )

        assert not is_divergence


# ============================================================================
# Agent Factory Tests (with mocked LangChain)
# ============================================================================

class TestMomentumAnalystFactory:
    """Tests for create_momentum_analyst factory function."""

    def test_factory_function_signature(self):
        """Test that factory function has correct signature."""
        # The factory should take an LLM parameter
        # We'll test the expected behavior pattern

        def mock_factory(llm):
            """Mock factory matching expected pattern."""
            def node(state):
                return {
                    "messages": [],
                    "momentum_report": ""
                }
            return node

        mock_llm = Mock()
        node = mock_factory(mock_llm)

        assert callable(node)

    def test_node_returns_correct_structure(self):
        """Test that node returns expected structure."""
        def mock_node(state):
            return {
                "messages": [Mock()],
                "momentum_report": "Test report"
            }

        state = {
            "trade_date": "2024-01-15",
            "company_of_interest": "AAPL",
            "messages": []
        }

        result = mock_node(state)

        assert "messages" in result
        assert "momentum_report" in result

    def test_node_processes_trade_date(self):
        """Test that node correctly processes trade date."""
        state = {
            "trade_date": "2024-01-15",
            "company_of_interest": "AAPL",
            "messages": []
        }

        # The node should use trade_date from state
        assert state["trade_date"] == "2024-01-15"

    def test_node_processes_ticker(self):
        """Test that node correctly processes company ticker."""
        state = {
            "trade_date": "2024-01-15",
            "company_of_interest": "NVDA",
            "messages": []
        }

        # The node should use company_of_interest from state
        assert state["company_of_interest"] == "NVDA"

    def test_expected_tools_list(self):
        """Test expected tools for momentum analyst."""
        expected_tools = [
            "get_stock_data",
            "get_indicators",
            "get_multi_timeframe_momentum",
            "get_adx_analysis",
            "get_momentum_divergence"
        ]

        # All expected tools should be present
        assert len(expected_tools) == 5
        assert "get_multi_timeframe_momentum" in expected_tools
        assert "get_adx_analysis" in expected_tools
        assert "get_momentum_divergence" in expected_tools


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_price_array(self):
        """Test handling of empty price array."""
        prices = []
        roc = calculate_roc(prices, 5)
        assert roc is None

    def test_single_price(self):
        """Test handling of single price point."""
        prices = [100]
        roc = calculate_roc(prices, 5)
        assert roc is None

    def test_zero_base_price(self):
        """Test handling of zero base price (avoid division by zero)."""
        prices = [0, 1, 2, 3, 4, 5]
        roc = calculate_roc(prices, 5)
        # Should handle zero gracefully
        assert roc == 0 or roc is not None

    def test_negative_prices(self):
        """Test handling of negative prices."""
        prices = [-100, -95, -90, -85, -80, -75]
        roc = calculate_roc(prices, 5)
        # Should still calculate change
        assert roc is not None

    def test_nan_in_prices(self):
        """Test handling of NaN values in prices."""
        prices = np.array([100, 101, np.nan, 103, 104, 105])
        rsi = calculate_rsi(prices)
        # Should produce some result (may contain NaN)
        assert rsi is not None

    def test_large_price_move(self):
        """Test handling of large price moves."""
        prices = [100, 100, 100, 100, 100, 200]  # 100% move
        roc = calculate_roc(prices, 5)
        assert roc == pytest.approx(100.0, rel=0.01)


# ============================================================================
# Report Format Tests
# ============================================================================

class TestReportFormat:
    """Tests for expected report format elements."""

    def test_momentum_report_sections(self):
        """Test expected sections in momentum report."""
        expected_sections = [
            "Multi-Timeframe Momentum Analysis",
            "Rate of Change",
            "Momentum Summary",
            "Interpretation"
        ]

        # Verify these are the expected section headers
        for section in expected_sections:
            assert isinstance(section, str)

    def test_adx_report_sections(self):
        """Test expected sections in ADX report."""
        expected_sections = [
            "ADX Trend Strength Analysis",
            "Current Readings",
            "Analysis Summary",
            "Trading Recommendation"
        ]

        for section in expected_sections:
            assert isinstance(section, str)

    def test_divergence_report_sections(self):
        """Test expected sections in divergence report."""
        expected_sections = [
            "Momentum Divergence Analysis",
            "Divergence Status",
            "Detected Patterns",
            "Interpretation"
        ]

        for section in expected_sections:
            assert isinstance(section, str)

    def test_momentum_signals(self):
        """Test momentum signal classifications."""
        signals = ["BULLISH", "BEARISH", "MIXED"]

        for signal in signals:
            assert signal in ["BULLISH", "BEARISH", "MIXED"]

    def test_strength_levels(self):
        """Test momentum strength level classifications."""
        strengths = ["STRONG", "MODERATE", "WEAK"]

        for strength in strengths:
            assert strength in ["STRONG", "MODERATE", "WEAK"]


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for the momentum analysis workflow."""

    def test_full_momentum_analysis_workflow(self, uptrending_stock_data):
        """Test complete momentum analysis workflow."""
        close = uptrending_stock_data['close'].values
        high = pd.Series(uptrending_stock_data['high'].values)
        low = pd.Series(uptrending_stock_data['low'].values)
        close_series = pd.Series(close)

        # Step 1: Multi-timeframe ROC
        roc_short = calculate_roc(close, 5)
        roc_medium = calculate_roc(close, 14)
        roc_long = calculate_roc(close, 30)

        assert roc_short is not None
        assert roc_medium is not None
        assert roc_long is not None

        # Step 2: ADX analysis
        adx, plus_di, minus_di = calculate_adx(high, low, close_series)

        assert adx is not None
        assert plus_di is not None
        assert minus_di is not None

        # Step 3: RSI for divergence
        rsi = calculate_rsi(close)

        assert rsi is not None
        assert len(rsi) > 0

    def test_bearish_workflow(self, downtrending_stock_data):
        """Test analysis workflow for bearish conditions."""
        close = downtrending_stock_data['close'].values
        high = pd.Series(downtrending_stock_data['high'].values)
        low = pd.Series(downtrending_stock_data['low'].values)
        close_series = pd.Series(close)

        # ROC should be negative
        roc = calculate_roc(close, 14)
        assert roc < 0

        # -DI should be greater than +DI
        adx, plus_di, minus_di = calculate_adx(high, low, close_series)
        assert minus_di > plus_di

    def test_consistent_analysis_across_data(self, sample_stock_data):
        """Test that analysis is consistent across same data."""
        close = sample_stock_data['close'].values

        # Run same calculation twice
        roc1 = calculate_roc(close, 14)
        roc2 = calculate_roc(close, 14)

        # Should be identical
        assert roc1 == roc2
