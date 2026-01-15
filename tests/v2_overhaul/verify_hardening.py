import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.utils.logger import app_logger as logger

def verify_institutional_hardening():
    """
    Verifies Phase 2.5 Refinements:
    1. FactLedger frozen indicators & regime.
    2. Structured output from Researchers/Trader.
    3. Consolidated Gatekeeper authorization.
    """
    logger.info("🧪 STARTING INSTITUTIONAL HARDENING VERIFICATION")
    
    # 1. Setup Graph with Simulation Mode
    os.environ["TRADING_MODE"] = "simulation"
    graph = TradingAgentsGraph(selected_analysts=["market"])
    
    # 2. Run a small session (using yfinance mock if possible, but simulation relies on it)
    ticker = "AAPL"
    trade_date = "2024-05-15"
    
    try:
        final_state, processed_signal = graph.propagate(ticker, trade_date)
        
        # --- CHECK 1: Epistemic Lock (FactLedger) ---
        ledger = final_state.get("fact_ledger")
        assert ledger is not None, "FactLedger missing!"
        assert "regime" in ledger, "Regime not frozen in Ledger!"
        assert "technicals" in ledger, "Technicals not frozen in Ledger!"
        
        technicals = ledger["technicals"]
        logger.info(f"✅ LEDGER CHECK: Regime={ledger['regime']}, SMA50={technicals.get('sma_50')}")
        assert technicals.get("sma_50") is not None, "SMA 50 missing from Ledger"
        
        # --- CHECK 2: Structured Confidence ---
        # bull_confidence and bear_confidence should be floats
        bull_c = final_state.get("bull_confidence")
        bear_c = final_state.get("bear_confidence")
        assert isinstance(bull_c, (float, int)), f"Bull confidence is not a number: {type(bull_c)}"
        assert isinstance(bear_c, (float, int)), f"Bear confidence is not a number: {type(bear_c)}"
        logger.info(f"✅ CONFIDENCE CHECK: Bull={bull_c}, Bear={bear_c}")
        
        # --- CHECK 3: Trader Output ---
        trader_decision = final_state.get("trader_decision")
        assert isinstance(trader_decision, dict), "Trader decision is not a dict"
        assert "action" in trader_decision, "Trader action missing"
        assert "confidence" in trader_decision, "Trader confidence missing"
        logger.info(f"✅ TRADER CHECK: Action={trader_decision['action']}, Conf={trader_decision['confidence']}")

        # --- CHECK 4: Consolidated Gatekeeper ---
        auth_decision = final_state.get("final_trade_decision")
        assert auth_decision is not None, "Gatekeeper decision missing!"
        status = auth_decision.get("status")
        logger.info(f"✅ GATEKEEPER CHECK: Status={status}")
        
        # Verify Shadow Gating is gone
        # The processed_signal should contain the status string
        assert str(status) in processed_signal.get("reason", ""), "Reasoning missing gatekeeper status"
        
        logger.info("🏆 ALL CORE HARDENING CHECKS PASSED!")
        
    except Exception as e:
        logger.error(f"❌ VERIFICATION FAILED: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    verify_institutional_hardening()
