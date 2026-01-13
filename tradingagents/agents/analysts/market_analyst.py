from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators, get_insider_transactions
from tradingagents.dataflows.config import get_config



from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector
from tradingagents.utils.anonymizer import TickerAnonymizer
import pandas as pd
from io import StringIO
from io import StringIO
from datetime import datetime, timedelta
from tradingagents.utils.logger import app_logger as logger


# Initialize anonymizer (shared instance appropriate here or inside)

def _calculate_net_insider_flow(raw_data: str) -> float:
    """Calculate net insider transaction value from report string."""
    try:
        if not raw_data or "Error" in raw_data or "No insider" in raw_data:
            return 0.0
            
        # Robust CSV parsing
        try:
            df = pd.read_csv(StringIO(raw_data), comment='#')
        except:
             # Fallback for messy data
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

    def market_analyst_node(state):
        logger.info(f">>> STARTING MARKET ANALYST for {state.get('company_of_interest')} <<<")
        current_date = state["trade_date"]
        
        # Initialize default state
        report = state.get("market_report", "Market Analysis Initialized...")
        if report == "Market Analysis failed completely.":
             report = "Market Analysis in progress..." # Reset if stuck

        regime_val = "UNKNOWN (Fatal Node Failure)"
        metrics = {}
        broad_market_regime = "UNKNOWN (Initialized)"
        net_insider_flow = 0.0
        metrics = {"volatility": 0.0}
        volatility_score = 0.0
        tool_result_message = state["messages"] 
        
        try:
            # Re-initialize or reload anonymizer state
            anonymizer = TickerAnonymizer()
            real_ticker = state["company_of_interest"]
            ticker = anonymizer.anonymize_ticker(real_ticker)
            
            # NOTE: We continue to use 'ticker' variable name but it now holds 'ASSET_XXX'

            # REGIME DETECTION LOGIC
            regime_val = "UNKNOWN (Start)"
            optimal_params = {}
            regime_context = "REGIME DETECTION FAILED or DATA UNAVAILABLE"

            # ... [Existing Logic] ...
            try:
                # Calculate start date (1 year lookback for robust regime detection)
                dt_obj = datetime.strptime(current_date, "%Y-%m-%d")
                start_date = (dt_obj - timedelta(days=365)).strftime("%Y-%m-%d")

                # 1. Fetch data for TARGET ASSET
                raw_data = get_stock_data.invoke({
                    "symbol": real_ticker, 
                    "start_date": start_date,
                    "end_date": current_date,
                    "format": "csv"
                })
                
                # 2. Fetch data for BROAD MARKET (SPY)
                try:
                    spy_data_raw = get_stock_data.invoke({
                        "symbol": "SPY", 
                        "start_date": start_date,
                        "end_date": current_date,
                        "format": "csv"
                    })
                    
                    if isinstance(spy_data_raw, str) and len(spy_data_raw.strip()) > 50 and "Error" not in spy_data_raw:
                        df_spy = pd.read_csv(StringIO(spy_data_raw), comment='#')
                        # Basic cleaning for SPY
                        if 'Close' not in df_spy.columns:
                            col_map = {c.lower(): c for c in df_spy.columns}
                            if 'close' in col_map:
                                df_spy.rename(columns={col_map['close']: 'Close'}, inplace=True)
                        
                        if 'Close' in df_spy.columns and len(df_spy) > 10:
                            spy_regime, _ = RegimeDetector.detect_regime(df_spy['Close'])
                            broad_market_regime = spy_regime.value
                except Exception as e_spy:
                    logger.warning(f"Broad Market (SPY) detection failed: {e_spy}")
    
                
                # Parse TARGET data
                if isinstance(raw_data, str) and len(raw_data.strip()) > 50 and "Error" not in raw_data and "No data" not in raw_data:
                    # Parse data (Standardized CSV format with # comments)
                    df = pd.read_csv(StringIO(raw_data), comment='#')
                    
                    # Handle case-insensitive 'Close' column
                    if 'Close' not in df.columns:
                        # Try to find a column that matches 'close' case-insensitively
                        col_map = {c.lower(): c for c in df.columns}
                        if 'close' in col_map:
                            df.rename(columns={col_map['close']: 'Close'}, inplace=True)
                    
                    # Clean index/date
                    if 'Date' in df.columns:
                        df['Date'] = pd.to_datetime(df['Date'])
                        df.set_index('Date', inplace=True)
                    
                    # Sort by date
                    df.sort_index(inplace=True)
                    
                    # Check for sufficient data
                    # Ensure 'Close' column exists after potential renaming
                    if 'Close' in df.columns:
                        price_data = df['Close']
                    else:
                        price_data = pd.Series([]) # Empty series if 'Close' column is not found
    
                    if not price_data.empty and len(price_data) >= 5:
                        # DEBUG INJECTION FOR MARKET ANALYST
                        try:
                            debug_msg = f"DEBUG: Passing prices to detector. Type: {type(price_data)}, Length: {len(price_data)}"
                            logger.info(debug_msg)
                            
                            regime, metrics = RegimeDetector.detect_regime(price_data)
                            
                            # Handle Enum or String return
                            if hasattr(regime, "value"):
                                regime_val = regime.value
                            else:
                                regime_val = str(regime)
                                
                            # Load Runtime Overrides (Dynamic Parameter Tuning)
                            overrides = {}
                            try:
                                config_path = get_config().get("runtime_config_relative_path", "data_cache/runtime_config.json")
                                import os
                                if os.path.exists(config_path):
                                    with open(config_path, 'r') as f:
                                        overrides = json.load(f)
                                        logger.info(f"DYNAMIC TUNING ACTIVE: Loaded overrides: {overrides}")
                            except Exception as e_conf:
                                logger.warning(f"Failed to load runtime config: {e_conf}")
                                
                            optimal_params = DynamicIndicatorSelector.get_optimal_parameters(regime, overrides)
                            volatility_score = metrics.get("volatility", 0.0)
                            
                            logger.info(f"SUCCESS: Detected Regime: {regime_val}")
                            logger.info(f"DEBUG: Optimal Params: {json.dumps(optimal_params)}")
                            
                        except Exception as e_det:
                            err_msg = f"CRITICAL: Detector Call Failed. Data Snippet: {str(price_data.head())}. Error: {e_det}"
                            logger.critical(err_msg)
                            regime_val = "UNKNOWN (Detector Failed)"
                            metrics = {"volatility": 0.0}
                            optimal_params = {}
                        
                        # Construct Context String (Enhanced)
                        regime_context = f"MARKET REGIME DETECTED: {regime_val}\n"
                        regime_context += f"BROAD MARKET CONTEXT (SPY): {broad_market_regime}\n"
                        regime_context += f"METRICS: {json.dumps(metrics)}\n"
                        regime_context += f"RECOMMENDED STRATEGY: {optimal_params.get('strategy', 'N/A')}\n"
                        regime_context += f"RECOMMENDED INDICATORS: {json.dumps(optimal_params)}\n"
                        regime_context += f"RATIONALE: {optimal_params.get('rationale', '')}"
                    else:
                        msg = f"Insufficient price data for {ticker}. Len: {len(df)}"
                        logger.warning(msg)
                        regime_val = "UNKNOWN (Insufficient Data)"
                else:
                    msg = f"Market data retrieval failed for {ticker}. Snippet: {str(raw_data)[:100]}"
                    logger.warning(msg)
                    regime_val = "UNKNOWN (Data Fetch Error)"
            except Exception as e:
                logger.warning(f"Regime detection failed for {ticker}: {e}")
                regime_val = f"UNKNOWN (Error: {str(e)})"
    
            # --- INSIDER DATA FETCH (Hard Gate) ---
            try:
                insider_data = get_insider_transactions.invoke({
                    "ticker": real_ticker, 
                    "curr_date": current_date
                })
                net_insider_flow = _calculate_net_insider_flow(insider_data)
                logger.info(f"Insider Net Flow calculated: ${net_insider_flow:,.2f}")
            except Exception as e_ins:
                logger.warning(f"Insider data fetch failed: {e_ins}")
                net_insider_flow = 0.0

            # --- LLM CALL ---
            tools = [
                get_stock_data,
                get_indicators,
                get_insider_transactions,
            ]
    
            system_message = (
                f"""ROLE: Quantitative Technical Analyst.
    CONTEXT: You are analyzing an ANONYMIZED ASSET (ASSET_XXX).
    CRITICAL DATA CONSTRAINT:
    1. All Price Data is NORMALIZED to a BASE-100 INDEX starting at the beginning of the period.
    2. "Price 105.0" means +5% gain from start. It does NOT mean $105.00.
    3. DO NOT hallucinate real-world ticker prices. Treat this as a pure mathematical time series.
    
    DYNAMIC MARKET REGIME CONTEXT:
    {regime_context}
    
    TASK: Select relevant indicators and analyze trends. 
    Your role is to select the **most relevant indicators** for the DETECTED REGIME ({regime_val}).
    The goal is to choose up to **8 indicators** that provide complementary insights without redundancy.
    
    INDICATOR CATEGORIES:
    
    Moving Averages:
    - close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
    - close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
    - close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.
    
    MACD Related:
    - macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
    - macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
    - macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.
    
    Momentum Indicators:
    - rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.
    
    Volatility Indicators:
    - boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
    - boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
    - boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
    - atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.
    
    Volume-Based Indicators:
    - vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.
    
    - Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            )
    
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Use the provided tools to progress towards answering the question."
                        " If you are unable to fully answer, that's OK; another assistant with different tools"
                        " will help where you left off. Execute what you can to make progress."
                        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                        " You have access to the following tools: {tool_names}.\n{system_message}"
                        "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )
    
            prompt = prompt.partial(system_message=system_message)
            prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
            prompt = prompt.partial(current_date=current_date)
            prompt = prompt.partial(ticker=ticker)
            logger.info(f"Market Analyst Prompt: {prompt}")
    
            try:
                chain = prompt | llm.bind_tools(tools)
                result = chain.invoke(state["messages"])
                if len(result.tool_calls) == 0:
                    report = result.content
                tool_result_message = [result]
            except Exception as e_llm:
                logger.error(f"ERROR: Market Analyst LLM and Tool use failed: {e_llm}")
                report = f"Market Analysis failed due to LLM error. Regime Context: {regime_context}"
                tool_result_message = state["messages"] # No new message

        except Exception as e_fatal:
            logger.critical(f"CRITICAL ERROR in Market Analyst Node: {e_fatal}")
            # Only overwrite regime if we completely failed
            if "UNKNOWN" in str(regime_val) or regime_val is None:
                regime_val = f"UNKNOWN (Fatal Crash: {str(e_fatal)})"
            
            report = f"Market Analyst Node crashed completely: {e_fatal}"
            risk_multiplier = 0.5 # Default to conservative on crash

        # --- 6. RELATIVE STRENGTH LOGIC (The Alpha Calculator) ---
        # Logic: Compare Asset Regime (Boat) vs. Market Regime (Tide)
        if "risk_multiplier" not in locals():
            risk_multiplier = 1.0 # Default Neutral
        
        # Clean strings for comparison
        asset_r = str(regime_val).upper()
        spy_r = str(broad_market_regime).upper()
        
        if "TRENDING_UP" in asset_r:
            if "SIDEWAYS" in spy_r or "UNKNOWN" in spy_r:
                # Scenario: Asset is leading the market (Alpha)
                # Action: Press the advantage.
                risk_multiplier = 1.5 
            elif "TRENDING_DOWN" in spy_r:
                # Scenario: Asset fighting the tide (Divergence)
                # Action: Caution. Breakouts often fail in bear markets.
                risk_multiplier = 0.8
            elif "TRENDING_UP" in spy_r:
                # Scenario: A rising tide lifts all boats (Beta)
                # Action: Standard aggressive sizing.
                risk_multiplier = 1.2
                
        elif "VOLATILE" in asset_r:
            # Scenario: Choppy/Shakeout
            # Action: Reduce size to survive noise.
            risk_multiplier = 0.5
            
        elif "TRENDING_DOWN" in asset_r:
            # Scenario: Knife falling.
            # Action: Zero buying power.
            risk_multiplier = 0.0

        # --- 7. FINAL RETURN ---
        logger.info(f"DEBUG: Market Analyst Returning -> Regime: {regime_val}, Risk Multiplier: {risk_multiplier}x")
    
        return {
            "messages": tool_result_message,
            "market_report": report,
            "market_regime": regime_val,       # CRITICAL: Must not be UNKNOWN if successful
            "regime_metrics": metrics,
            "volatility_score": volatility_score,
            "broad_market_regime": broad_market_regime,
            "net_insider_flow": net_insider_flow,
            "risk_multiplier": risk_multiplier
        }
    
    return market_analyst_node
