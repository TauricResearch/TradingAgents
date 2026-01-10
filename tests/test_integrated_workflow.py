"""
Unit Tests for Integrated Workflow

Tests:
- JSON schema enforcement with retry loops
- Fact checker hard gating (reject on hallucination)
- Risk gate hard gating (reject on risk violation)
- End-to-end workflow execution
"""

import unittest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.workflows.integrated_workflow import IntegratedTradingWorkflow
from tradingagents.schemas.agent_schemas import AnalystOutput, ResearcherOutput, SignalType


class TestIntegratedWorkflow(unittest.TestCase):
    """Test suite for integrated workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "anonymizer_seed": "test_seed",
            "use_nli_model": False,  # Use fallback
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
        
        # Mock market data
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        self.prices = pd.Series(100 + np.cumsum(np.random.randn(100) * 0.5 + 0.3), index=dates)
        
        self.market_data = {
            "price_series": self.prices,
            "close": 105.0,
            "atr": 2.5,
            "volume": 50000000,
            "indicators": {"RSI": 55, "MACD": 0.5}
        }
        
        self.ground_truth = {
            "revenue_growth_yoy": 0.05,
            "price_change_pct": 0.03
        }
    
    def test_workflow_initialization(self):
        """Test that workflow initializes all components."""
        self.assertIsNotNone(self.workflow.anonymizer)
        self.assertIsNotNone(self.workflow.regime_detector)
        self.assertIsNotNone(self.workflow.fact_checker)
        self.assertIsNotNone(self.workflow.risk_gate)
        self.assertIsNotNone(self.workflow.json_retry)
    
    def test_fact_check_hard_gate_rejection(self):
        """CRITICAL: Test that fact check failure rejects trade."""
        # Create mock LLM agents that output contradictory claims
        mock_agents = self._create_mock_agents_with_contradictions()
        
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2024-01-15",
            market_data=self.market_data,
            ground_truth=self.ground_truth,
            llm_agents=mock_agents
        )
        
        # Trade should be rejected due to fact check failure
        self.assertIsNone(decision, "Trade should be rejected on fact check failure")
        self.assertGreater(metrics.fact_check_time, 0, "Fact check should have run")
    
    def test_risk_gate_hard_gate_rejection(self):
        """CRITICAL: Test that risk gate failure rejects trade."""
        # Create mock agents with valid facts but excessive risk
        mock_agents = self._create_mock_agents_valid()
        
        # Set portfolio in drawdown (exceeds circuit breaker)
        self.workflow.config["current_drawdown"] = 0.20  # 20% > 15% limit
        
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2024-01-15",
            market_data=self.market_data,
            ground_truth=self.ground_truth,
            llm_agents=mock_agents
        )
        
        # Trade should be rejected due to circuit breaker
        self.assertIsNone(decision, "Trade should be rejected on risk gate failure")
    
    def test_successful_trade_approval(self):
        """Test successful trade approval when all gates pass."""
        # Create mock agents with valid facts and reasonable risk
        mock_agents = self._create_mock_agents_valid()
        
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2024-01-15",
            market_data=self.market_data,
            ground_truth=self.ground_truth,
            llm_agents=mock_agents
        )
        
        # Trade should be approved
        self.assertIsNotNone(decision, "Trade should be approved")
        self.assertTrue(decision.fact_check_passed)
        self.assertTrue(decision.risk_gate_passed)
        self.assertIsNotNone(decision.quantity)
        self.assertIsNotNone(decision.stop_loss)
    
    def test_latency_tracking(self):
        """Test that workflow tracks latency for each component."""
        mock_agents = self._create_mock_agents_valid()
        
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2024-01-15",
            market_data=self.market_data,
            ground_truth=self.ground_truth,
            llm_agents=mock_agents
        )
        
        # All latency metrics should be tracked
        self.assertGreater(metrics.total_latency, 0)
        self.assertGreater(metrics.anonymization_time, 0)
        self.assertGreater(metrics.regime_detection_time, 0)
    
    def test_fact_check_latency_budget(self):
        """Test that fact check latency is monitored."""
        mock_agents = self._create_mock_agents_valid()
        
        decision, metrics = self.workflow.execute_trade_decision(
            ticker="AAPL",
            trading_date="2024-01-15",
            market_data=self.market_data,
            ground_truth=self.ground_truth,
            llm_agents=mock_agents
        )
        
        # Fact check time should be within budget (for this simple test)
        self.assertLess(metrics.fact_check_time, self.config["fact_check_latency_budget"])
    
    def _create_mock_agents_valid(self):
        """Create mock agents that output valid JSON with correct facts."""
        def mock_market_analyst(prompt):
            response = Mock()
            response.content = '''```json
            {
                "analyst_type": "market",
                "key_findings": [
                    "Price increased 3% this period",
                    "Volume above average",
                    "RSI at 55 (neutral)"
                ],
                "signal": "BUY",
                "confidence": 0.75,
                "reasoning": "Technical indicators show bullish momentum with strong volume confirmation."
            }
            ```'''
            return response
        
        def mock_bull_researcher(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bull",
                "key_arguments": [
                    "Revenue grew 5% year-over-year",
                    "Strong earnings momentum continues"
                ],
                "signal": "BUY",
                "confidence": 0.80,
                "supporting_evidence": ["Q4 earnings beat", "Guidance raised"]
            }
            ```'''
            return response
        
        def mock_bear_researcher(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bear",
                "key_arguments": [
                    "Valuation remains elevated",
                    "Market volatility increasing"
                ],
                "signal": "HOLD",
                "confidence": 0.60,
                "supporting_evidence": ["High P/E ratio", "Macro uncertainty"]
            }
            ```'''
            return response
        
        return {
            "market_analyst": mock_market_analyst,
            "bull_researcher": mock_bull_researcher,
            "bear_researcher": mock_bear_researcher
        }
    
    def _create_mock_agents_with_contradictions(self):
        """Create mock agents that output contradictory claims."""
        def mock_market_analyst(prompt):
            response = Mock()
            response.content = '''```json
            {
                "analyst_type": "market",
                "key_findings": [
                    "Price fell sharply",
                    "Volume declining",
                    "RSI oversold"
                ],
                "signal": "SELL",
                "confidence": 0.70,
                "reasoning": "Technical breakdown with declining volume."
            }
            ```'''
            return response
        
        def mock_bull_researcher(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bull",
                "key_arguments": [
                    "Revenue fell 5% year-over-year",
                    "Earnings declined significantly"
                ],
                "signal": "SELL",
                "confidence": 0.75,
                "supporting_evidence": ["Weak Q4", "Guidance lowered"]
            }
            ```'''
            return response
        
        def mock_bear_researcher(prompt):
            response = Mock()
            response.content = '''```json
            {
                "researcher_type": "bear",
                "key_arguments": [
                    "Fundamental deterioration evident",
                    "Market share declining"
                ],
                "signal": "SELL",
                "confidence": 0.80,
                "supporting_evidence": ["Competitor gains", "Margin pressure"]
            }
            ```'''
            return response
        
        return {
            "market_analyst": mock_market_analyst,
            "bull_researcher": mock_bull_researcher,
            "bear_researcher": mock_bear_researcher
        }


if __name__ == '__main__':
    unittest.main(verbosity=2)
