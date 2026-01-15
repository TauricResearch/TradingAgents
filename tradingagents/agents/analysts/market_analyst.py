from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta

from tradingagents.agents.utils.agent_utils import normalize_agent_output
from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector
from tradingagents.utils.anonymizer import TickerAnonymizer
from tradingagents.utils.logger import app_logger as logger
from tradingagents.dataflows.config import get_config

def _calculate_net_insider_flow(raw_data: str) -> float:
    """Calculate net insider transaction value from report string."""
    try:
        if not raw_data or "Error" in raw_data or "No insider" in raw_data:
            return 0.0
            
        # Robust CSV parsing - YFinance uses whitespace delimiter
        try:
            df = pd.read_csv(StringIO(raw_data), sep='\s+', comment='#')
        except:
             # Fallback: auto-detect separator
             df = pd.read_csv(StringIO(raw_data), sep=None, engine='python', comment='#')
        
        # Standardize columns
        df.columns = [c.strip().lower() for c in df.columns]
        
        if 'value' not in df.columns:
            return 0.0
            
        net_flow = 0.0
        
        # Iterate and sum
        for _, row in df.iterrows():
            # Check for sale/purchase in text or other columns
            text = str(row.get('text', '')).lower() + str(row.get('transaction', '')).lower()
            val = float(row['value']) if pd.notnull(row['value']) else 0.0
            
            if 'sale' in text or 'sold' in text:
                net_flow -= val
            elif 'purchase' in text or 'buy' in text or 'bought' in text:
                net_flow += val
                
        return net_flow
    except Exception as e:
        logger.warning(f"Failed to parse insider flow: {e}")
        return 0.0

def create_market_analyst(llm):
    # PARANOIA CHECK: Ensure we aren't passing a bind_tools wrapped LLM
    if hasattr(llm, "tools") and llm.tools:
        logger.critical("SECURITY VIOLATION: Market Analyst has access to tools! This violates Phase 1 Architecture.")

    def market_analyst_node(state):
        logger.info(f">>> STARTING MARKET ANALYST for {state.get('company_of_interest')} <<<")
        current_date = state["trade_date"]
        
        # 1. READ FROM LEDGER (No Tool Calls)
        ledger = state.get("fact_ledger")
        if not ledger:
            raise RuntimeError("CRITICAL: Market Analyst woke up but FactLedger is missing! Registrar failed.")

        # Extract Canonically Fetched Data
        raw_price_data = ledger.get("price_data")
        raw_insider_data = ledger.get("insider_data")
        
        # Initialize default state
        report = "Market Analysis Initialized..."
        regime_val = "UNKNOWN (Start)"
        metrics = {"volatility": 0.0}
        broad_market_regime = "UNKNOWN (Initialized)"
        net_insider_flow = 0.0
        volatility_score = 0.0
        result = None
        
        try:
            # Re-initialize or reload anonymizer state
            anonymizer = TickerAnonymizer()
            real_ticker = state["company_of_interest"]
            ticker = anonymizer.anonymize_ticker(real_ticker)
            
            optimal_params = {}
            regime_context = "REGIME DETECTION FAILED or DATA UNAVAILABLE"

            # --- PROCESS LEDGER DATA ---
            try:
                # RegimeDetector now handles all input types (DataFrame, Series, CSV String)
                # Just pass the raw data directly - no need to parse here
                if raw_price_data:
                    regime, metrics = RegimeDetector.detect_regime(raw_price_data)
                    regime_val = regime.value if hasattr(regime, "value") else str(regime)
                    
                    # Dynamic Tuning
                    overrides = {}
                    try:
                        config_path = get_config().get("runtime_config_relative_path", "data_cache/runtime_config.json")
                        import os
                        if os.path.exists(config_path):
                            with open(config_path, 'r') as f:
                                overrides = json.load(f)
                    except: 
                        pass

                    optimal_params = DynamicIndicatorSelector.get_optimal_parameters(regime, overrides)
                    volatility_score = metrics.get("volatility", 0.0)
                    
                    logger.info(f"SUCCESS: Detected Regime: {regime_val}")
                    
                    # Construct Context
                    regime_context = f"MARKET REGIME DETECTED: {regime_val}\n"
                    # Escape Braces for LangChain
                    metrics_str = json.dumps(metrics).replace("{", "{{").replace("}", "}}")
                    regime_context += f"METRICS: {metrics_str}\n"
                    regime_context += f"RECOMMENDED STRATEGY: {optimal_params.get('strategy', 'N/A')}\n"
                else:
                    regime_val = "UNKNOWN (Ledger Data Empty/Error)"
            except Exception as e:
                logger.warning(f"Regime detection failed from Ledger: {e}")
                # DEBUG: Print raw data on failure
                if isinstance(raw_price_data, str):
                     print(f"DEBUG: Parsing Failed. Raw Data Start: {raw_price_data[:250]}...")
                regime_val = f"UNKNOWN (Error: {str(e)})"

            # --- PROCESS INSIDER DATA ---
            try:
                # We trust the ledger's insider data
                if isinstance(raw_insider_data, str):
                    net_insider_flow = _calculate_net_insider_flow(raw_insider_data)
                logger.info(f"Insider Net Flow calculated from Ledger: ${net_insider_flow:,.2f}")
            except Exception as e_ins:
                net_insider_flow = 0.0

            # --- LLM CALL (NO TOOLS) ---
            system_message = (
                f"""ROLE: Quantitative Technical Analyst.
    CONTEXT: You are analyzing an ANONYMIZED ASSET (ASSET_XXX).
    DATA SOURCE: TRUSTED FACT LEDGER ID {ledger.get('ledger_id', 'UNKNOWN')}.
    
    DYNAMIC MARKET REGIME CONTEXT:
    {regime_context}
    
    TASK: Write a technical analysis report based on the PROVIDED DATA.
    DO NOT ATTEMPT TO CALL TOOLS. YOU HAVE NO TOOLS.
    Analyze the trends, volatility, and insider flow based on the metrics provided above.
    
    INDICATOR GUIDANCE:
    Use the regime metrics (volatility, slope, adx) to infer the technical state.
    
    STRICT COMPLIANCE:
    1. DO NOT HALLUCINATE DATA not present in the context.
    2. Cite "FactLedger" as your source.
    3. If data is missing, state "Insufficient Data".
    
    Make sure to append a Markdown table at the end of the report."""
            )
    
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_message),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )
            
            # NOTE: NO BIND TOOLS
            chain = prompt | llm 
            # Fix: Must pass dict to Chain when using MessagesPlaceholder
            result = chain.invoke({"messages": state["messages"]})
            report = result.content

        except Exception as e_fatal:
            logger.critical(f"CRITICAL ERROR in Market Analyst Node: {e_fatal}")
            if "UNKNOWN" in str(regime_val):
                regime_val = f"UNKNOWN (Fatal Crash: {str(e_fatal)})"
            report = f"Market Analyst Node crashed: {e_fatal}"
            risk_multiplier = 0.5

        # --- ALPHA CALCULATOR ---
        if "risk_multiplier" not in locals(): risk_multiplier = 1.0
        
        # Simple Regime Logic (since we lost live broad market for now)
        if "TRENDING_UP" in str(regime_val).upper():
            risk_multiplier = 1.2
        elif "TRENDING_DOWN" in str(regime_val).upper():
            risk_multiplier = 0.0
        elif "VOLATILE" in str(regime_val).upper():
            risk_multiplier = 0.5

        return {
            "messages": [result] if result else [],
            "market_report": normalize_agent_output(report),
            "market_regime": regime_val,
            "regime_metrics": metrics,
            "volatility_score": volatility_score,
            "broad_market_regime": broad_market_regime,
            "net_insider_flow": net_insider_flow,
            "risk_multiplier": risk_multiplier
        }
    
    return market_analyst_node
