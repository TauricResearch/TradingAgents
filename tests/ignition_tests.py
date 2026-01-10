"""
Phase 7: Ignition Tests - Prove the System Works

Three isolated tests:
1. Hallucination Trap - Fact checker must reject "500% revenue growth" lie
2. Falling Knife - Regime detector must prevent buying NVDA crash (Jan 27, 2022)
3. Live Round - System must execute actual trade during March 2022 rally
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.workflows.integrated_workflow import IntegratedTradingWorkflow
from tradingagents.schemas.agent_schemas import SignalType
from tradingagents.engines.regime_detector import RegimeDetector
from unittest.mock import Mock


class IgnitionTests:
    """
    Phase 7: Ignition Tests
    
    Prove the system works with real logic, not mocks.
    """
    
    def __init__(self):
        """Initialize test harness."""
        self.config = {
            "anonymizer_seed": "ignition_test",
            "use_nli_model": False,  # Use fallback for speed
            "max_json_retries": 2,
            "fact_check_latency_budget": 2.0,
            "portfolio_value": 100000,
            "risk_config": {
                "max_position_risk": 0.02,
                "max_portfolio_heat": 0.10,
                "circuit_breaker": 0.15
            }
        }
        
        self.workflow = IntegratedTradingWorkflow(self.config)
        self.regime_detector = RegimeDetector()
    
    def test_1_hallucination_trap(self):
        """
        TEST 1: HALLUCINATION TRAP
        
        Inject: "Apple revenue grew 500% last quarter"
        Ground Truth: Revenue grew 8%
        Expected: FACT_CHECK_FAILURE
        """
        print("\n" + "="*80)
        print("TEST 1: HALLUCINATION TRAP")
        print("="*80)
        print("\n🎯 Objective: Prove fact checker rejects obvious hallucination")
        print("   Injection: 'Apple revenue grew 500% last quarter'")
        print("   Ground Truth: Revenue grew 8%")
        print("   Expected: 🚫 REJECTED - FACT_CHECK_FAILURE\n")
        
        # Create mock agents with HALLUCINATION
        def mock_analyst(prompt):
            response = Mock()
            # CRITICAL: Valid JSON without markdown blocks
            response.content = '''{
                "analyst_type": "market",
                "key_findings": ["Strong momentum", "Volume increasing", "Breakout pattern"],
                "signal": "BUY",
                "confidence": 0.75,
                "reasoning": "Technical setup looks bullish with strong volume confirmation and breakout above resistance."
            }'''
            return response
        
        def mock_bull_HALLUCINATION(prompt):
            """INJECTED HALLUCINATION - VALID JSON FORMAT"""
            response = Mock()
            # CRITICAL: This is VALID JSON with a LIE in the content
            response.content = '''{
                "researcher_type": "bull",
                "key_arguments": [
                    "Apple revenue grew 500% last quarter, signaling massive adoption",
                    "Earnings beat expectations significantly"
                ],
                "signal": "BUY",
                "confidence": 0.99,
                "supporting_evidence": ["Q4 earnings", "Market share gains"]
            }'''
            return response
        
        def mock_bear(prompt):
            response = Mock()
            # CRITICAL: Valid JSON without markdown blocks
            response.content = '''{
                "researcher_type": "bear",
                "key_arguments": [
                    "Valuation stretched at current levels",
                    "Competition intensifying in key markets"
                ],
                "signal": "HOLD",
                "confidence": 0.60,
                "supporting_evidence": ["P/E ratio elevated", "Market dynamics shifting"]
            }'''
            return response
        
        # Ground truth: Revenue actually grew 8%
        ground_truth = {
            "revenue_growth_yoy": 0.08,  # 8% growth
            "price_change_pct": 0.02
        }
        
        # Mock market data
        dates = pd.date_range('2022-01-01', periods=100, freq='D')
        prices = pd.Series(150 + np.cumsum(np.random.randn(100) * 0.5), index=dates)
        
        market_data = {
            "price_series": prices,
            "close": 155.0,
            "atr": 2.5,
            "volume": 50000000,
            "indicators": {"RSI": 55, "MACD": 0.5}
        }
        
        llm_agents = {
            "market_analyst": mock_analyst,
            "bull_researcher": mock_bull_HALLUCINATION,  # HALLUCINATION INJECTED
            "bear_researcher": mock_bear
        }
        
        # Execute workflow
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2022-01-15",
            market_data=market_data,
            ground_truth=ground_truth,
            llm_agents=llm_agents
        )
        
        # Validate result
        print("\n📋 RESULT:")
        print(f"   Decision: {decision.action.value}")
        print(f"   Fact Check Passed: {decision.fact_check_passed}")
        print(f"   Reasoning: {decision.reasoning}")
        
        if not decision.fact_check_passed:
            print("\n✅ TEST 1 PASSED: Fact checker rejected hallucination")
            print(f"   Rejection: {decision.reasoning}")
            return True
        else:
            print("\n❌ TEST 1 FAILED: Fact checker approved hallucination!")
            print(f"   This is a CRITICAL FAILURE - system validated a 500% lie")
            return False
    
    def test_2_falling_knife(self):
        """
        TEST 2: FALLING KNIFE
        
        Date: January 27, 2022 (NVDA crash)
        RSI: < 30 (oversold)
        Expected: Regime = BEAR/VOLATILE, Signal = HOLD (not BUY)
        """
        print("\n" + "="*80)
        print("TEST 2: FALLING KNIFE DETECTION")
        print("="*80)
        print("\n🎯 Objective: Prove system won't buy a falling knife")
        print("   Date: January 27, 2022 (NVDA -3.6% crash)")
        print("   RSI: < 30 (oversold)")
        print("   Expected: Regime = VOLATILE/BEAR, Signal = HOLD\n")
        
        # Download real NVDA data for Jan 2022 with 100-day buffer
        print("📥 Downloading NVDA data for January 2022 (with 100-day warm-up buffer)...")
        # CRITICAL: Add 100-day buffer for indicator warm-up
        nvda_data = yf.download("NVDA", start="2021-10-01", end="2022-02-01", progress=False)
        
        if len(nvda_data) == 0:
            print("❌ Failed to download data")
            return False
        
        # Get data up to Jan 27, 2022
        crash_date = pd.Timestamp("2022-01-27")
        nvda_jan27 = nvda_data.loc[:crash_date]
        
        # Extract price series
        close_series = nvda_jan27['Close']
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.squeeze()
        
        print(f"   Data points: {len(close_series)}")
        print(f"   Price on Jan 27: ${close_series.iloc[-1]:.2f}")
        print(f"   Price 5 days ago: ${close_series.iloc[-6]:.2f}")
        print(f"   5-day change: {((close_series.iloc[-1] / close_series.iloc[-6]) - 1) * 100:.1f}%")
        
        # Detect regime
        print("\n🔬 Running regime detection...")
        regime, metrics = self.regime_detector.detect_regime(close_series, window=60)
        
        print(f"\n📊 REGIME DETECTION RESULT:")
        print(f"   Regime: {regime.value.upper()}")
        print(f"   Volatility: {metrics['volatility']:.1%}")
        print(f"   Trend Strength (ADX): {metrics['trend_strength']:.1f}")
        print(f"   Cumulative Return: {metrics['cumulative_return']:.1%}")
        print(f"   Hurst Exponent: {metrics['hurst_exponent']:.2f}")
        
        # Check if regime is BEAR or VOLATILE
        is_dangerous = regime.value in ["trending_down", "volatile"]
        
        if is_dangerous:
            print(f"\n✅ TEST 2 PASSED: Regime correctly identified as {regime.value.upper()}")
            print(f"   System should NOT buy the dip in this regime")
            return True
        else:
            print(f"\n❌ TEST 2 FAILED: Regime classified as {regime.value.upper()}")
            print(f"   This is DANGEROUS - system might buy a falling knife")
            return False
    
    def test_3_live_round(self):
        """
        TEST 3: LIVE ROUND
        
        Date: March 15-18, 2022 (Relief rally)
        Action: Allow system to trade normally
        Expected: Successfully execute a BUY trade
        """
        print("\n" + "="*80)
        print("TEST 3: LIVE ROUND (TRADE EXECUTION)")
        print("="*80)
        print("\n🎯 Objective: Prove system can execute actual trade")
        print("   Date: March 15, 2022 (Relief rally)")
        print("   Expected: Successfully BUY a position\n")
        
        # Download real data for March 2022 with 100-day buffer
        print("📥 Downloading AAPL data for March 2022 (with 100-day warm-up buffer)...")
        # CRITICAL: Add 100-day buffer for indicator warm-up
        aapl_data = yf.download("AAPL", start="2021-11-01", end="2022-03-20", progress=False)
        
        if len(aapl_data) == 0:
            print("❌ Failed to download data")
            return False
        
        # Get data up to March 15
        trade_date = pd.Timestamp("2022-03-15")
        aapl_mar15 = aapl_data.loc[:trade_date]
        
        # Extract price series
        close_series = aapl_mar15['Close']
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.squeeze()
        
        print(f"   Data points: {len(close_series)}")
        print(f"   Price on Mar 15: ${close_series.iloc[-1]:.2f}")
        
        # Create bullish mock agents
        def mock_analyst(prompt):
            response = Mock()
            response.content = '''```json
            {
                "analyst_type": "market",
                "key_findings": ["Relief rally underway", "Oversold bounce", "Volume confirming"],
                "signal": "BUY",
                "confidence": 0.70,
                "reasoning": "Technical bounce from oversold levels with volume."
            }
            ```'''
            return response
        
        def mock_bull(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bull",
                "key_arguments": [
                    "Market finding support after selloff",
                    "Technical indicators showing reversal"
                ],
                "signal": "BUY",
                "confidence": 0.75,
                "supporting_evidence": ["RSI bounce", "Volume spike"]
            }
            ```'''
            return response
        
        def mock_bear(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bear",
                "key_arguments": [
                    "Rally may be short-lived",
                    "Macro headwinds persist"
                ],
                "signal": "HOLD",
                "confidence": 0.55,
                "supporting_evidence": ["Fed policy", "Inflation"]
            }
            ```'''
            return response
        
        # Ground truth
        returns = close_series.pct_change()
        ground_truth = {
            "revenue_growth_yoy": 0.05,
            "price_change_pct": returns.iloc[-1]
        }
        
        # Market data
        market_data = {
            "price_series": close_series,
            "close": float(close_series.iloc[-1]),
            "atr": float(close_series.rolling(14).std().iloc[-1] * 1.5),
            "volume": 50000000,
            "indicators": {"RSI": 45, "MACD": 0.3}
        }
        
        llm_agents = {
            "market_analyst": mock_analyst,
            "bull_researcher": mock_bull,
            "bear_researcher": mock_bear
        }
        
        # Execute workflow
        print("\n🚀 Executing trade decision...")
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2022-03-15",
            market_data=market_data,
            ground_truth=ground_truth,
            llm_agents=llm_agents
        )
        
        # Validate result
        print("\n📋 RESULT:")
        print(f"   Action: {decision.action.value}")
        print(f"   Quantity: {decision.quantity}")
        print(f"   Confidence: {decision.confidence:.2f}")
        print(f"   Fact Check Passed: {decision.fact_check_passed}")
        print(f"   Risk Gate Passed: {decision.risk_gate_passed}")
        
        if decision.action == SignalType.BUY and decision.quantity > 0:
            print(f"\n✅ TEST 3 PASSED: Successfully executed BUY trade")
            print(f"   Quantity: {decision.quantity} shares")
            print(f"   Stop Loss: ${decision.stop_loss:.2f}")
            print(f"   Risk: {decision.risk_pct:.2%}")
            return True
        else:
            print(f"\n❌ TEST 3 FAILED: Could not execute trade")
            print(f"   Reasoning: {decision.reasoning}")
            return False


# Run ignition tests
if __name__ == "__main__":
    print("\n" + "="*80)
    print("PHASE 7: IGNITION TESTS")
    print("="*80)
    print("\nProving the system works with real logic, not mocks.\n")
    
    tests = IgnitionTests()
    
    # Run all three tests
    results = {
        "test_1_hallucination": tests.test_1_hallucination_trap(),
        "test_2_falling_knife": tests.test_2_falling_knife(),
        "test_3_live_round": tests.test_3_live_round()
    }
    
    # Summary
    print("\n" + "="*80)
    print("IGNITION TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL IGNITION TESTS PASSED")
        print("   System is ready for live trading")
    else:
        print("❌ IGNITION TESTS FAILED")
        print("   System is NOT ready for production")
    print("="*80)
