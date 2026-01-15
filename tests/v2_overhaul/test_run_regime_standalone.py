
import sys
import os
import yfinance as yf
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Import RegimeDetector & Utils
try:
    from tradingagents.engines.regime_detector import RegimeDetector, DynamicIndicatorSelector
    from tradingagents.dataflows.y_finance import get_robust_revenue_growth, get_insider_transactions
    from io import StringIO
except ImportError:
    print("❌ Error: Could not import required modules. Run from project root.")
    sys.exit(1)

def apply_trend_override_copy(trade_decision_str, hard_data, regime):
    """
    COPY OF logic from tradingagents/graph/trading_graph.py
    """
    # Robust Enum Extraction (Double Lock)
    if hasattr(regime, "value"):
        regime_val = regime.value
    else:
        regime_val = str(regime)
        
    regime_val = regime_val.upper().strip()
        
    price = hard_data["current_price"]
    sma_200 = hard_data["sma_200"]
    growth = hard_data["revenue_growth"]
    
    # 1. Technical Uptrend (Price > 200 SMA)
    is_technical_uptrend = price > sma_200
    
    # 2. Hyper-Growth (> 30% YoY)
    is_hyper_growth = growth > 0.30
    
    # 3. Supportive Regime (Protect leaders unless it's a clear TRENDING_DOWN regime)
    is_bear_regime = regime_val in ["TRENDING_DOWN", "BEAR", "BEARISH"]
    is_bull_regime = not is_bear_regime
    
    print(f"[LOGIC COPY] DEBUG OVERRIDE: Price={price}, SMA={sma_200}, Growth={growth}, Regime='{regime_val}'")
    print(f"[LOGIC COPY] DEBUG CHECK: Technical={is_technical_uptrend}, Growth={is_hyper_growth}, BullRegime={is_bull_regime}")

    # 4. Trigger Override if trying to SELL a leader in a bull market
    if is_technical_uptrend and is_hyper_growth and is_bull_regime:
        decision_upper = trade_decision_str.upper()
        if "SELL" in decision_upper:
            print("🛑 TREND OVERRIDE TRIGGERED!")
            print(f"   Reason: Stock (${price:.2f}) is > 200SMA (${sma_200:.2f}) and Growth is {growth:.1%}")
            return True
        else:
             print("[LOGIC COPY] Conditions met, but decision was NOT 'SELL'. No action.")
             return False
    else:
        print("[LOGIC COPY] Conditions NOT met. Passive.")
        return False

def _calculate_net_insider_flow(raw_data: str) -> float:
    """Calculate net insider transaction value from report string."""
    try:
        if not raw_data or "Error" in raw_data or "No insider" in raw_data:
            return 0.0
            
        df = pd.read_csv(StringIO(raw_data), comment='#')
        
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
        print(f"Failed to parse insider flow: {e}")
        return 0.0

def fetch_regime_data(ticker, days=450): # 450 days for SMA 200 buffer
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    df = yf.download(ticker, start=start_date, end=end_date, progress=False, multi_level_index=False)
    
    if df.empty:
        return None
        
    # Standardize Column Names
    if 'Close' in df.columns:
        return df['Close']
    elif 'close' in df.columns:
        return df['close']
        
    return None

def run_regime_standalone(ticker="PLTR"):
    print(f"🚀 STANDALONE REGIME DETECTOR RUN: {ticker}")
    print("="*60)
    
    # 1. Fetch Target Data
    print(f"📡 Fetching REAL data for {ticker}...")
    prices = fetch_regime_data(ticker)
    
    if prices is None or prices.empty:
        print("❌ Error: No data fetched.")
        return

    print(f"✅ Data Fetched. Length: {len(prices)}")
    
    print("-" * 40)
    print(f"[CONSOLE] DEBUG: Passing prices to detector. Type: {type(prices)}, Length: {len(prices)}")
    print("-" * 40)
    
    # 2. Run Regime Logic (Target)
    print(f"🧠 Running RegimeDetector for {ticker}...")
    regime, metrics = RegimeDetector.detect_regime(prices)
    regime_val = regime.value if hasattr(regime, "value") else str(regime)
    
    print(f"🔹 DETECTED REGIME: {regime_val}")

    print("\n🔹 METRICS:")
    for k, v in metrics.items():
        print(f"   - {k}: {v}")
        
    # 3. Fetch SPY Data (Broad Market)
    print(f"\n📡 Fetching REAL data for SPY (Broad Market)...")
    spy_prices = fetch_regime_data("SPY", days=365)
    broad_market_regime = "UNKNOWN"
    
    if spy_prices is not None and not spy_prices.empty:
        spy_reg, _ = RegimeDetector.detect_regime(spy_prices)
        broad_market_regime = spy_reg.value if hasattr(spy_reg, "value") else str(spy_reg)
        print(f"✅ SPY Regime: {broad_market_regime}")
    else:
        print("⚠️ SPY data fetch failed. Defaulting to UNKNOWN.")

    # 3.5 Check Insider Veto
    print(f"\n🕵️ Checking Insider Data for {ticker}...")
    try:
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        insider_data_raw = get_insider_transactions(ticker, curr_date=current_date_str)
        net_insider = _calculate_net_insider_flow(insider_data_raw)
        print(f"   Net Insider Flow (90d): ${net_insider:,.2f}")
        
        if net_insider < -50_000_000:
             print("   ⚠️ FAIL: Significant Insider Selling Detected (> $50M)")
        else:
             print("   ✅ PASS: Insider Flow within limits.")
             
    except Exception as e:
        print(f"   ❌ Insider fetch failed: {e}")

    # 4. Construct System Prompt (Mimic Market Analyst)
    print("\n� GENERATING SYSTEM PROMPT...")
    optimal_params = DynamicIndicatorSelector.get_optimal_parameters(regime)
    
    regime_context = f"MARKET REGIME DETECTED: {regime_val}\n"
    regime_context += f"BROAD MARKET CONTEXT (SPY): {broad_market_regime}\n"
    regime_context += f"METRICS: {json.dumps(metrics)}\n"
    regime_context += f"RECOMMENDED STRATEGY: {optimal_params.get('strategy', 'N/A')}\n"
    regime_context += f"RECOMMENDED INDICATORS: {json.dumps(optimal_params)}\n"
    regime_context += f"RATIONALE: {optimal_params.get('rationale', '')}"
    
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
    
    print("-" * 60)
    print(system_message)
    print("-" * 60)
    
        
    # 5. Calculate Hard Metrics & Override Logic
    print("\n🧮 CALCULATING HARD METRICS...")
    current_price = prices.iloc[-1]
    sma_200 = prices.rolling(200).mean().iloc[-1]
    
    print(f"   Fetching Revenue Growth for {ticker}...")
    try:
        growth = get_robust_revenue_growth(ticker)
    except Exception as e:
        print(f"   ⚠️ Growth fetch failed ({e}). Using PLTR Default (0.62).")
        growth = 0.627
        
    hard_data = {
        "current_price": current_price,
        "sma_200": sma_200,
        "revenue_growth": growth
    }
    
    print("\n⚖️ APPLYING OVERRIDE LOGIC (Copy):")
    decision_mock = "Final Decision: SELL 50% due to valuation."
    fires = apply_trend_override_copy(decision_mock, hard_data, regime)
    
    print("\n🏁 FINAL VERDICT:")
    if fires:
        print(f"✅ OVERRIDE WORKING correctly for {ticker}.")
    else:
        print(f"❌ OVERRIDE FAILED / PASSIVE for {ticker}.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_regime_standalone(sys.argv[1])
    else:
        run_regime_standalone("PLTR")
