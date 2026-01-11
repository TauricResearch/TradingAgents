from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config



from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector
from tradingagents.utils.anonymizer import TickerAnonymizer
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta

# Initialize anonymizer (shared instance appropriate here or inside)
def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        # Re-initialize or reload anonymizer state
        anonymizer = TickerAnonymizer()
        real_ticker = state["company_of_interest"]
        ticker = anonymizer.anonymize_ticker(real_ticker)
        
        # NOTE: We continue to use 'ticker' variable name but it now holds 'ASSET_XXX'

        # REGIME DETECTION LOGIC
        regime_val = "UNKNOWN"
        metrics = {}
        optimal_params = {}
        regime_context = "REGIME DETECTION FAILED or DATA UNAVAILABLE"
        volatility_score = 0.0

        try:
            # Calculate start date (1 year lookback for robust regime detection)
            dt_obj = datetime.strptime(current_date, "%Y-%m-%d")
            start_date = (dt_obj - timedelta(days=365)).strftime("%Y-%m-%d")

            # Fetch data for regime detection using the anonymized ticker
            raw_data = get_stock_data.invoke({
                "symbol": real_ticker, 
                "start_date": start_date,
                "end_date": current_date,
                "format": "csv"
            })
            
            # Parse data
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

                print(f"DEBUG: Regime Detection - Ticker: {real_ticker}, Rows: {len(price_data)}")
                
                if not price_data.empty and len(price_data) >= 10:
                    # Detect Regime
                    regime, metrics = RegimeDetector.detect_regime(price_data)
                    optimal_params = DynamicIndicatorSelector.get_optimal_parameters(regime)
                    regime_val = regime.value
                    volatility_score = metrics.get("volatility", 0.0)
                    
                    # Construct Context String
                    regime_context = f"MARKET REGIME DETECTED: {regime_val}\n"
                    regime_context += f"METRICS: {json.dumps(metrics)}\n"
                    regime_context += f"RECOMMENDED STRATEGY: {optimal_params.get('strategy', 'N/A')}\n"
                    regime_context += f"RECOMMENDED INDICATORS: {json.dumps(optimal_params)}\n"
                    regime_context += f"RATIONALE: {optimal_params.get('rationale', '')}"
                else:
                    print(f"WARNING: Insufficient price data for {ticker}. Columns: {list(df.columns)}, Len: {len(df)}")
            else:
                print(f"WARNING: Market data retrieval failed for regime detection for {ticker}. Data snippet: {str(raw_data)[:100]}")
        except Exception as e:
            print(f"WARNING: Regime detection failed for {ticker}: {e}")

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """ROLE: Quantitative Technical Analyst.
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

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content
       
        return {
            "messages": [result],
            "market_report": report,
            "market_regime": regime_val,
            "regime_metrics": metrics,
            "volatility_score": volatility_score
        }

    return market_analyst_node
