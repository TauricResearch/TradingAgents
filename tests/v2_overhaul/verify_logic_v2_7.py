import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add project root to path
sys.path.append(os.getcwd())

from tradingagents.agents.execution_gatekeeper import ExecutionGatekeeper
from tradingagents.agents.utils.agent_states import ExecutionResult
from tradingagents.utils.logger import app_logger as logger

class TestGatekeeperV2_7(unittest.TestCase):
    def setUp(self):
        self.gatekeeper = ExecutionGatekeeper()
        self.base_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2026-01-15",
            "trader_decision": {"action": "BUY", "confidence": 0.9, "rationale": "Bullish"},
            "bull_confidence": 0.8,
            "bear_confidence": 0.2,
            "portfolio": {},
            "fact_ledger": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "regime": "TRENDING_UP",
                "freshness": {"price_age_sec": 10.0, "fundamentals_age_hours": 1.0, "news_age_hours": 1.0},
                "insider_data": "No major selling",
                "net_insider_flow_usd": 0.0,
                "technicals": {
                    "current_price": 150.0,
                    "sma_200": 100.0,
                    "sma_50": 130.0,
                    "rsi_14": 60.0,
                    "revenue_growth": 0.2
                }
            }
        }

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._is_market_open")
    def test_pulse_check_drift_abort(self, mock_open, mock_pulse):
        """Abort if market drifts > 3% from ledger."""
        mock_open.return_value = True
        mock_pulse.return_value = 156.0 # 4% drift
        
        res = self.gatekeeper.run(self.base_state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_STALE_DATA)
        logger.info(f"✅ Pulse Check Abort Verified (status: {status})")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._is_market_open")
    def test_massive_drift_abort(self, mock_open, mock_pulse):
        """Abort on massive drift (potential split)."""
        mock_open.return_value = True
        mock_pulse.return_value = 15.0 # 90% drift (Reverse Split?)
        
        res = self.gatekeeper.run(self.base_state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_STALE_DATA)
        self.assertIn("Massive Drift", res["final_trade_decision"]["details"]["reason"])
        logger.info(f"✅ Massive Drift (Split Check) Verified")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._is_market_open")
    def test_market_closed_abort(self, mock_open):
        """Abort if market is closed."""
        mock_open.return_value = False
        res = self.gatekeeper.run(self.base_state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_COMPLIANCE)
        self.assertIn("Market Closed", res["final_trade_decision"]["details"]["reason"])
        logger.info(f"✅ Market Closed Abort Verified")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._is_market_open")
    def test_insider_data_gap_abort(self, mock_open):
        """Abort if insider flow is None (Data Gap)."""
        mock_open.return_value = True
        state = self.base_state.copy()
        state["fact_ledger"]["net_insider_flow_usd"] = None 
        
        res = self.gatekeeper.run(state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_DATA_GAP)
        logger.info(f"✅ Insider Data Gap (NULL) Verified")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._is_market_open")
    def test_insider_veto_deterministic(self, mock_open):
        """Veto if flow < -$50M and into downtrend."""
        mock_open.return_value = True
        state = self.base_state.copy()
        state["fact_ledger"]["net_insider_flow_usd"] = -100_000_000.0
        state["fact_ledger"]["technicals"]["current_price"] = 120.0
        state["fact_ledger"]["technicals"]["sma_50"] = 130.0
        
        res = self.gatekeeper.run(state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_COMPLIANCE)
        self.assertIn("Insider Veto", res["final_trade_decision"]["details"]["reason"])
        logger.info(f"✅ Deterministic Insider Veto Verified")

if __name__ == "__main__":
    unittest.main()
