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

class TestGatekeeperV2_6(unittest.TestCase):
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
    def test_pulse_check_drift_abort(self, mock_pulse):
        """Abort if market drifts > 3% from ledger."""
        # Ledger Price is 150.0. Drift 4% = 156.0
        mock_pulse.return_value = 156.0
        
        res = self.gatekeeper.run(self.base_state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_STALE_DATA)
        logger.info(f"✅ Pulse Check Abort Verified (status: {status})")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    def test_pulse_check_safe_pass(self, mock_pulse):
        """Pass if market drifts < 3% from ledger."""
        # Ledger Price is 150.0. Drift 1% = 151.5
        mock_pulse.return_value = 151.5
        
        res = self.gatekeeper.run(self.base_state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.APPROVED)
        logger.info(f"✅ Pulse Check Pass Verified (status: {status})")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    def test_insider_data_gap_abort(self, mock_pulse):
        """Abort if insider data is None (Pessimistic Data)."""
        mock_pulse.return_value = 150.0 # Stable price
        state = self.base_state.copy()
        state["fact_ledger"]["insider_data"] = None # Explicit NULL from Registrar
        
        res = self.gatekeeper.run(state)
        status = res["final_trade_decision"]["status"]
        self.assertEqual(status, ExecutionResult.ABORT_DATA_GAP)
        logger.info(f"✅ Insider Data Gap Abort Verified (status: {status})")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    def test_insider_veto_compliance(self, mock_pulse):
        """Veto if heavy selling into downtrend."""
        mock_pulse.return_value = 120.0
        state = self.base_state.copy()
        # Mock Downtrend: Price < 50SMA
        state["fact_ledger"]["technicals"]["current_price"] = 120.0
        state["fact_ledger"]["technicals"]["sma_50"] = 130.0
        state["fact_ledger"]["insider_data"] = "INSIDER SELL $100,000,000 BY CEO"
        state["fact_ledger"]["regime"] = "TRENDING_DOWN"
        
        res = self.gatekeeper.run(state)
        status = res["final_trade_decision"]["status"]
        # Should hit Insider Veto (ABORT_COMPLIANCE) inside _check_insider_veto
        # Wait, in the code _check_insider_veto is only checked for ABORT_DATA_GAP at step 3.
        # But for compliance, it might hit step 2 or later.
        # Actually, in run():
        # Step 2: _check_compliance (this calls _check_insider_veto or similar check)
        # Wait, I added it in step 3 as insider_res.
        # Ah, I see.
        
        self.assertEqual(status, ExecutionResult.ABORT_COMPLIANCE)
        logger.info(f"✅ Insider Veto Verified (status: {status})")

    @patch("tradingagents.agents.execution_gatekeeper.ExecutionGatekeeper._fetch_pulse_price")
    def test_rule_72_stop_loss_override(self, mock_pulse):
        """Force SELL if -10% Stop Loss triggered."""
        mock_pulse.return_value = 150.0
        state = self.base_state.copy()
        # Portfolio: Cost 180.0, Current 150.0 => -16.6% PnL
        state["portfolio"] = {"AAPL": {"average_cost": 180.0, "quantity": 100}}
        state["trader_decision"]["action"] = "BUY" # Agent tries to average down
        
        res = self.gatekeeper.run(state)
        decision = res["final_trade_decision"]
        self.assertEqual(decision["status"], ExecutionResult.APPROVED)
        self.assertEqual(decision["action"], "SELL")
        self.assertIn("Stop Loss", decision["details"]["reason"])
        logger.info(f"✅ Rule 72 Stop Loss Override Verified (action: {decision['action']})")

if __name__ == "__main__":
    unittest.main()
