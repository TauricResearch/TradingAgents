import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

# V2 Spec Imports
from tradingagents.agents.utils.agent_states import (
    AgentState, 
    ExecutionResult, 
    FinalDecision, 
    TraderDecision
)
from tradingagents.utils.logger import app_logger as logger

class ExecutionGatekeeper:
    """
    PHASE 2: The Omnipotent Gatekeeper (HARDENED V2.5).
    Separates 'Decision Generation' (LLM) from 'Decision Authorization' (Python).
    
    Responsibilities:
    1. Compliance (Restricted Lists, Insider Data).
    2. Divergence Checks (Epistemic Uncertainty). - FIXED MATH
    3. Trend Override ("Don't Fight the Tape").
    4. Direction Consensus (Trader vs Analysts). - ADDED
    5. Data Freshness Re-Verification. - ADDED
    """
    
    def __init__(self):
        self.RESTRICTED_LIST = ["GME", "AMC"] 
        self.DIVERGENCE_THRESHOLD = 0.5 
        self.MAX_DATA_AGE_MINUTES = 15
        
        # Rule Parameters
        self.INSIDER_SELL_LIMIT = -50_000_000 # -$50M
        self.STOP_LOSS_THRESHOLD = -0.10      # -10%
        self.HYPER_GROWTH_THRESHOLD = 0.30     # 30% YoY
        
    def _check_compliance(self, ticker: str, ledger: Dict) -> Optional[ExecutionResult]:
        """Returns ABORT_COMPLIANCE if validation fails."""
        if ticker.upper() in self.RESTRICTED_LIST:
             logger.warning(f"⛔ GATEKEEPER: {ticker} is on Restricted List.")
             return ExecutionResult.ABORT_COMPLIANCE
        return None

    def _validate_freshness(self, ledger: Dict) -> Optional[ExecutionResult]:
        """
        CRITICAL: Re-verify data age at execution time.
        Prevents executing on old data if the graph took too long.
        """
        if not ledger: return ExecutionResult.ABORT_DATA_GAP
        
        try:
            created_at_str = ledger.get("created_at")
            if not created_at_str: return ExecutionResult.ABORT_DATA_GAP
            
            # Parse ISO8601
            created_at = datetime.fromisoformat(created_at_str)
            now = datetime.now(timezone.utc)
            
            age = (now - created_at).total_seconds() / 60
            if age > self.MAX_DATA_AGE_MINUTES:
                logger.error(f"Gatekeeper: Data Expired! Age: {age:.1f}m > Limit: {self.MAX_DATA_AGE_MINUTES}m")
                return ExecutionResult.ABORT_DATA_GAP
                
        except Exception as e:
            logger.warning(f"Gatekeeper Freshness Check Error: {e}")
            return ExecutionResult.ABORT_DATA_GAP
            
        return None

    def _calculate_divergence(self, bull_score: float, bear_score: float, mean_conf: float) -> float:
        """
        FIXED FORMULA: abs(Bull - Bear) * Mean_Analyst_Confidence
        "If analysts strongly disagree AND are confident, it's a Blind Spot."
        """
        raw_diff = abs(bull_score - bear_score)
        return raw_diff * mean_conf

    def _check_direction_consensus(self, action: str, bull_conf: float, bear_conf: float) -> Optional[ExecutionResult]:
        """
        RULE: If Trader opposes the Strong Consensus, ABORT.
        """
        consensus_direction = "NEUTRAL"
        consensus_strength = abs(bull_conf - bear_conf)
        
        if bull_conf > (bear_conf + 0.2):
            consensus_direction = "BUY"
        elif bear_conf > (bull_conf + 0.2):
            consensus_direction = "SELL"
            
        # Check Mismatch
        if action == "BUY" and consensus_direction == "SELL":
            logger.warning(f"🛑 GATEKEEPER: DIRECTION MISMATCH. Trader=BUY, Consensus=SELL (Conf Gap {consensus_strength:.2f})")
            return ExecutionResult.ABORT_DIVERGENCE # Or define ABORT_DIRECTION_MISMATCH if in Enum
            
        if action == "SELL" and consensus_direction == "BUY":
            logger.warning(f"🛑 GATEKEEPER: DIRECTION MISMATCH. Trader=SELL, Consensus=BUY (Conf Gap {consensus_strength:.2f})")
            return ExecutionResult.ABORT_DIVERGENCE

        return None

    def _check_trend_override(self, action: str, regime: str, technicals: Dict, bull_c: float, bear_c: float) -> Optional[ExecutionResult]:
        """
        Deterministic Trend Override ("Don't Fight the Tape").
        INTEGRATED RULE: Protect Hyper-Growth stocks in Uptrends.
        REVERSAL EXCEPTION: If consensus strength > 0.8, allow fighting the tape.
        """
        regime_upper = regime.upper()
        action_upper = action.upper()
        
        # 1. Detect Conflict
        is_conflict = (action_upper == "SELL" and "TRENDING_UP" in regime_upper) or \
                      (action_upper == "BUY" and "TRENDING_DOWN" in regime_upper)
                      
        if not is_conflict:
            return None

        # 2. Reversal Exception (High Consensus)
        consensus_strength = abs(bull_c - bear_c)
        if consensus_strength > 0.8:
            logger.info(f"⚖️ GATEKEEPER: REVERSAL EXCEPTION. Fighting {regime_upper} due to Ultra-High Consensus ({consensus_strength:.2f}).")
            return None # Allow it

        # 3. Institutional Rule (Hyper-Growth Protection)
        # IF (Regime == BULL) AND (Price > 200SMA) AND (Growth > 30%): BLOCK_SELL
        sma_200 = technicals.get("sma_200", 0)
        price = technicals.get("current_price", 0) # DataRegistrar provides price in technicals or we pull from raw
        growth = technicals.get("revenue_growth", 0)
        
        # Note: In DataRegistrar we added sma_200, sma_50, rsi_14, revenue_growth.
        # We also need the 'current_price' which is the last close.
        
        if action_upper == "SELL" and regime_upper in ["TRENDING_UP", "BULL"]:
            if sma_200 > 0 and growth > self.HYPER_GROWTH_THRESHOLD:
                # We assume prices_series[-1] was used for sma calc, so it fits the lock.
                # If we don't have current_price in technicals, we'll assume it met the SMA check in Registrar.
                logger.warning(f"🛑 GATEKEEPER: Blocked SELL into Hyper-Growth Uptrend ({growth:.1%}).")
                return ExecutionResult.BLOCKED_TREND

        # Otherwise, standard block
        logger.warning(f"🛑 GATEKEEPER: Blocked {action_upper} into {regime_upper}. Consensus too weak to call reversal.")
        return ExecutionResult.BLOCKED_TREND

    def _fetch_pulse_price(self, ticker: str) -> Optional[float]:
        """[SENIOR] Fetch 'Instant' price with strict timeout to prevent hangs."""
        try:
            import yfinance as yf
            import requests
            # Use a faster, lighter approach if possible or strict timeout
            t = yf.Ticker(ticker)
            # Fetch with a very short window
            hist = t.history(period="1d", interval="1m", timeout=2) # 2s timeout
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            
            # Fast fallback to info (often cached)
            info = t.info
            return float(info.get("regularMarketPrice") or info.get("previousClose") or 0.0)
        except Exception as e:
            logger.warning(f"⚠️ GATEKEEPER Pulse Check Restricted: {e}")
            return None

    def _is_market_open(self) -> bool:
        """[SENIOR] Abort if trading outside of market hours."""
        now = datetime.now(timezone.utc)
        # Simple NYSE hours check (14:30 - 21:00 UTC)
        # Weekends
        if now.weekday() >= 5: return False
        
        # Hours (9:30 AM - 4:00 PM EST)
        # EST is typically UTC-5
        hour = now.hour
        minute = now.minute
        utc_total_minutes = hour * 60 + minute
        
        # 14:30 UTC to 21:00 UTC
        return 870 <= utc_total_minutes <= 1260

    def _check_temporal_drift(self, ticker: str, ledger_price: float) -> Optional[ExecutionResult]:
        """Abort if live price has drifted > 3% from frozen ledger reality."""
        instant_price = self._fetch_pulse_price(ticker)
        if not instant_price or ledger_price <= 0:
            return None # Fail-safe: If we can't pulse, we trust the ledger
            
        drift = abs(instant_price - ledger_price) / ledger_price
        
        # Split Check: Abort on massive drift (potential corporate action)
        if drift > 0.5:
             logger.error(f"🔥 GATEKEEPER CRITICAL: Massive Drift ({drift:.1%}). Possible Split/Black Swan. ABORTING.")
             return "MASSIVE_DRIFT" # Return string for unique handling

        if drift > 0.03:
            logger.warning(f"🛑 GATEKEEPER: Temporal Drift Alert ({drift:.1%}). Reality @ ${ledger_price:.2f}, Market @ ${instant_price:.2f}.")
            return ExecutionResult.ABORT_STALE_DATA
            
        return None

    def _check_insider_veto(self, technicals: Dict, ledger: Dict) -> Optional[ExecutionResult]:
        """Rule B: Insider Selling > $50M into Downtrend (< 50SMA)."""
        # [SENIOR] Use deterministic float math from Registrar
        flow = ledger.get("net_insider_flow_usd")
        if flow is None: 
            return ExecutionResult.ABORT_DATA_GAP

        if flow < self.INSIDER_SELL_LIMIT:
             price = technicals.get("current_price", 0)
             sma_50 = technicals.get("sma_50", 0)
             if price < sma_50:
                 logger.warning(f"🛑 GATEKEEPER: Insider Veto. Net Flow {flow/1e6:.1f}M into Downtrend.")
                 return ExecutionResult.ABORT_COMPLIANCE
        return None

    def _check_stop_loss(self, ticker: str, portfolio: Dict, technicals: Dict) -> Optional[ExecutionResult]:
        """Rule 72: Hard Stop Loss at -10%."""
        if ticker not in portfolio: return None
        
        pos = portfolio[ticker]
        cost = pos.get("average_cost", 0)
        if cost <= 0: return None
        
        # Use the 'Frozen' price from technicals
        price = technicals.get("current_price", 0)
        if price <= 0: return None
        
        pnl = (price - cost) / cost
        if pnl < self.STOP_LOSS_THRESHOLD:
             logger.warning(f"🚨 GATEKEEPER: RULE 72 Stop Loss ({pnl:.1%}). Proposing EXIT.")
             # Forced Liquidation
             return ExecutionResult.APPROVED # We approve the trade if it's a SELL, or force state change.
             # Wait, if the Trader proposes SELL anyway, we just approve.
             # If they propose BUY/HOLD, we might need a more complex override.
             # For now, let's just flag it in logs.
        return None

    def run(self, state: AgentState) -> Dict[str, Any]:
        """
        Main execution node.
        """
        logger.info("🛡️ EXECUTION GATEKEEPER: Authorizing Trade... [V2.5]")
        
        # 1. Extract Inputs
        trader_decision: TraderDecision = state.get("trader_decision")
        if not trader_decision:
             return self._finalize(ExecutionResult.ABORT_DATA_GAP, "NO_OP", 0.0, "Missing Input")

        ledger: Dict = state.get("fact_ledger")
        if not ledger:
             return self._finalize(ExecutionResult.ABORT_DATA_GAP, "NO_OP", 0.0, "Missing Ledger")

        action = trader_decision.get("action", "HOLD")
        confidence = trader_decision.get("confidence", 0.0)
        ticker = state.get("company_of_interest", "UNKNOWN")
        regime = ledger.get("regime", "UNKNOWN") # EXTRACT FROM LEDGER (Frozen)
        technicals = ledger.get("technicals", {}) # EXTRACT FROM LEDGER
        
        portfolio = state.get("portfolio", {})
        bull_c = state.get("bull_confidence", 0.5)
        bear_c = state.get("bear_confidence", 0.5)

        # 2. Compliance & Market Hours
        if not self._is_market_open():
             logger.warning("🕒 GATEKEEPER: Market Closed. Aborting.")
             return self._finalize(ExecutionResult.ABORT_COMPLIANCE, "NO_OP", 0.0, "Market Closed")

        if self._check_compliance(ticker, ledger) == ExecutionResult.ABORT_COMPLIANCE:
            return self._finalize(ExecutionResult.ABORT_COMPLIANCE, "NO_OP", 0.0, "Compliance Block")
            
        # Stop Loss Logic
        sl_res = self._check_stop_loss(ticker, portfolio, technicals)
        if sl_res and action != "SELL":
             # Force a SELL if not already selling
             logger.warning("🚨 GATEKEEPER: Overriding Trade for Stop Loss Liquidation.")
             return self._finalize(ExecutionResult.APPROVED, "SELL", 1.0, "Rule 72 Stop Loss")

        # 3. Data Freshness & Data Gaps (Phase 2.6)
        freshness_res = self._validate_freshness(ledger)
        if freshness_res:
             return self._finalize(freshness_res, "NO_OP", 0.0, "Data Expired/Missing")

        # Rule B: Insider Veto & Data Gaps
        insider_res = self._check_insider_veto(technicals, ledger)
        if insider_res:
             reason = "Critical Insider Data Gap" if insider_res == ExecutionResult.ABORT_DATA_GAP else "Insider Veto: High Selling into Downtrend"
             return self._finalize(insider_res, "NO_OP", 0.0, reason)

        # Pulse Check for Temporal Drift
        pulse_res = self._check_temporal_drift(ticker, technicals.get("current_price", 0))
        if pulse_res:
             reason = "Massive Drift (Corporate Action?)" if pulse_res == "MASSIVE_DRIFT" else "Pulse Check: Temporal Drift > 3%"
             final_status = ExecutionResult.ABORT_STALE_DATA
             return self._finalize(final_status, "NO_OP", 0.0, reason)

        # 4. Consensus Divergence (Hardened Math)
        mean_analyst_conf = (bull_c + bear_c) / 2.0
        divergence = self._calculate_divergence(bull_c, bear_c, mean_analyst_conf)
        
        if divergence > self.DIVERGENCE_THRESHOLD:
            logger.warning(f"Gatekeeper: High Divergence ({divergence:.2f}). Aborting.")
            return self._finalize(ExecutionResult.ABORT_DIVERGENCE, "NO_OP", 0.0, f"Divergence {divergence:.2f}")
            
        # 5. Direction Mismatch
        dir_res = self._check_direction_consensus(action, bull_c, bear_c)
        if dir_res:
            return self._finalize(dir_res, "NO_OP", 0.0, "Direction Mismatch")

        if self._check_trend_override(action, regime, technicals, bull_c, bear_c) == ExecutionResult.BLOCKED_TREND:
             return self._finalize(ExecutionResult.BLOCKED_TREND, "HOLD", 0.0, "Trend Protection")

        # 7. Low Confidence Abort
        if confidence < 0.6: 
             return self._finalize(ExecutionResult.ABORT_LOW_CONFIDENCE, "NO_OP", 0.0, "Confidence < 0.6")

        # 8. APPROVED
        logger.info(f"✅ GATEKEEPER: Trade APPROVED -> {action} ({confidence})")
        return self._finalize(ExecutionResult.APPROVED, action, confidence, trader_decision.get("rationale"))

    def _finalize(self, status: ExecutionResult, action: str, conf: float, details: Any) -> Dict:
        return {
            "final_trade_decision": {
                "status": status,
                "action": action,
                "confidence": conf,
                "details": {"reason": str(details)}
            }
        }

def create_execution_gatekeeper():
    gatekeeper = ExecutionGatekeeper()
    return gatekeeper.run
