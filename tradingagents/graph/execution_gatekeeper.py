import json
import hashlib
import pandas as pd
from io import StringIO
from typing import Dict, Any, Tuple
from tradingagents.utils.logger import app_logger as logger
from tradingagents.agents.utils.agent_states import ExecutionResult, FactLedger, FinalDecision
from tradingagents.agents.data_registrar import LedgerDomain # Assuming this is available, if not falling back to str

class ExecutionGatekeeper:
    """
    The Deterministic Authority.
    Enforces the 'Python Veto'.
    """
    def __init__(self):
        self.name = "Execution Gatekeeper"
        self.CONFIDENCE_THRESHOLD = 0.70
        self.MAX_DIVERGENCE = 0.4 # Strict divergence limit
    
    def _verify_ledger_integrity(self, ledger: FactLedger) -> bool:
        """Gate 1: Ensure Reality hasn't shifted."""
        if not ledger or "ledger_id" not in ledger:
            return False
        # In Phase 3, we will re-hash payload here. 
        # For Phase 2, existence check is sufficient.
        return True

    def check_compliance(self, ledger: FactLedger) -> bool:
        """Gate 2: Real Compliance Logic."""
        # Access safely via Enum or string key
        # Use str fallback if LedgerDomain not imported/available yet
        insider_key = "insider_data"
        if 'LedgerDomain' in globals():
             insider_key = LedgerDomain.INSIDER.value
        
        insider_data = ledger.get(insider_key, "")
        
        # Insider Flow Panic Check
        # If massive insider selling detected in raw data, block BUYs
        if isinstance(insider_data, str) and "Cluster Sale" in insider_data:
             logger.warning("COMPLIANCE: Cluster Sale detected.")
             return False
             
        return True

    def check_divergence(self, debate_state: Dict, confidence: float) -> bool:
        """Gate 3: Epistemic Uncertainty Check."""
        if not debate_state:
            return True # Pass if no debate data (Sim mode)
            
        # Note: Debate manager must populate these. Defaulting to 0.5 prevents crash.
        bull_score = debate_state.get("bull_score", 0.5)
        bear_score = debate_state.get("bear_score", 0.5)
        
        # Formula: |Bull - Bear| * Confidence
        divergence = abs(bull_score - bear_score) * confidence
        
        if divergence > self.MAX_DIVERGENCE:
            logger.warning(f"DIVERGENCE: {divergence:.2f} > {self.MAX_DIVERGENCE}")
            return False
            
        return True

    def check_trend_override(self, ledger: FactLedger, regime: str, action: str) -> Tuple[bool, str]:
        """
        Gate 4: Don't Fight The Tape.
        """
        if action != "SELL":
            return True, "" 

        # Only protect in clear BULL regimes
        if "TRENDING_UP" not in regime and "BULL" not in regime:
            return True, ""

        try:
            # Access safely
            price_key = "price_data"
            if 'LedgerDomain' in globals():
                 price_key = LedgerDomain.PRICE.value
            
            price_raw = ledger.get(price_key, "")
            
            if isinstance(price_raw, str):
                df = pd.read_csv(StringIO(price_raw), comment='#')
                if 'Close' in df.columns:
                    current_price = df['Close'].iloc[-1]
                    sma_200 = df['Close'].rolling(window=200).mean().iloc[-1]
                    
                    # LOGIC: Regime says UP AND Price says UP (Structure)
                    if current_price > (sma_200 * 1.05):
                        return False, f"BLOCKED_TREND: Regime ({regime}) + Price > 1.05*200SMA. Don't fight the tape."
        except Exception as e:
            logger.warning(f"Trend Check Error: {e}")
            
        return True, ""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("🛡️ GATEKEEPER: Validating Decision...")
        
        ledger = state.get("fact_ledger")
        if not ledger:
             return self._abort(ExecutionResult.ABORT_DATA_GAP, "FactLedger Missing")
             
        trader_decision = state.get("trader_decision", {"action": "HOLD", "confidence": 0.0})
        
        action = trader_decision["action"]
        confidence = trader_decision["confidence"]
        regime = state.get("market_regime", "UNKNOWN")

        # --- GATE 1: INTEGRITY ---
        if not self._verify_ledger_integrity(ledger):
             return self._abort(ExecutionResult.ABORT_DATA_GAP, "Ledger Integrity Failed")

        # --- GATE 2: COMPLIANCE ---
        if not self.check_compliance(ledger):
            return self._abort(ExecutionResult.ABORT_COMPLIANCE, "Insider/Restricted Flag")

        # --- GATE 3: CONFIDENCE ---
        if confidence < self.CONFIDENCE_THRESHOLD and action != "HOLD":
            return self._abort(ExecutionResult.ABORT_LOW_CONFIDENCE, f"Conf {confidence:.2f} < {self.CONFIDENCE_THRESHOLD}")

        # --- GATE 4: DIVERGENCE ---
        if not self.check_divergence(state.get("investment_debate_state", {}), confidence):
            return self._abort(ExecutionResult.ABORT_DIVERGENCE, "Analyst Divergence Too High")

        # --- GATE 5: TREND OVERRIDE ---
        allowed, reason = self.check_trend_override(ledger, regime, action)
        if not allowed:
            return self._block(reason, original_action=action)

        # ✅ APPROVED
        logger.info(f"✅ EXECUTION APPROVED: {action}")
        return {
            "final_trade_decision": {
                "status": ExecutionResult.APPROVED,
                "action": action,
                "confidence": confidence,
                "details": {"rationale": trader_decision.get("rationale")}
            }
        }

    def _abort(self, status: ExecutionResult, reason: str) -> Dict:
        logger.critical(f"⛔ {status.value}: {reason}")
        return {
            "final_trade_decision": {
                "status": status,
                "action": "NO_OP",
                "confidence": 0.0,
                "details": {"reason": reason}
            }
        }

    def _block(self, reason: str, original_action: str) -> Dict:
        logger.warning(f"🛡️ BLOCKED: {reason}")
        return {
            "final_trade_decision": {
                "status": ExecutionResult.BLOCKED_TREND,
                "action": "HOLD", 
                "confidence": 0.0,
                "details": {
                    "reason": reason,
                    "counterfactual": f"Intent: {original_action} -> Blocked by Regime"
                }
            }
        }

def create_execution_gatekeeper():
    gatekeeper = ExecutionGatekeeper()
    return gatekeeper.run
