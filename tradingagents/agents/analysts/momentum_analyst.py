"""Momentum Analyst Agent.

Specializes in multi-timeframe momentum analysis using:
- Rate of Change (ROC) across multiple periods
- Average Directional Index (ADX) for trend strength
- RSI momentum confirmation
- MACD momentum signals
- Multi-timeframe momentum divergence detection

Issue #13: [AGENT-12] Momentum Analyst - multi-TF momentum, ROC, ADX
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from typing import Annotated, Dict, Any, List, Optional
import pandas as pd

from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.interface import route_to_vendor


# ============================================================================
# Momentum-Specific Tools
# ============================================================================

@tool
def get_multi_timeframe_momentum(
    symbol: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    short_period: Annotated[int, "Short-term ROC period (default: 5)"] = 5,
    medium_period: Annotated[int, "Medium-term ROC period (default: 14)"] = 14,
    long_period: Annotated[int, "Long-term ROC period (default: 30)"] = 30,
) -> str:
    """
    Calculate multi-timeframe momentum using Rate of Change (ROC) across periods.

    ROC measures percentage change over a period:
    - Positive ROC = upward momentum
    - Negative ROC = downward momentum
    - Divergence across timeframes signals potential reversals

    Returns analysis of short, medium, and long-term momentum alignment.
    """
    try:
        # Get stock data for analysis
        stock_data = route_to_vendor("get_stock_data", symbol, curr_date, max(long_period * 2, 60))

        if isinstance(stock_data, str) and "error" in stock_data.lower():
            return f"Error retrieving stock data: {stock_data}"

        # Parse the data if it's a string (CSV format)
        if isinstance(stock_data, str):
            from io import StringIO
            df = pd.read_csv(StringIO(stock_data))
        else:
            df = stock_data

        if df.empty or len(df) < long_period:
            return f"Insufficient data for momentum analysis. Need at least {long_period} periods."

        # Calculate ROC for each timeframe
        close = df['close'] if 'close' in df.columns else df['Close']

        roc_short = ((close.iloc[-1] - close.iloc[-short_period]) / close.iloc[-short_period]) * 100
        roc_medium = ((close.iloc[-1] - close.iloc[-medium_period]) / close.iloc[-medium_period]) * 100
        roc_long = ((close.iloc[-1] - close.iloc[-long_period]) / close.iloc[-long_period]) * 100

        # Determine momentum alignment
        all_positive = roc_short > 0 and roc_medium > 0 and roc_long > 0
        all_negative = roc_short < 0 and roc_medium < 0 and roc_long < 0

        if all_positive:
            alignment = "BULLISH - All timeframes showing positive momentum"
            strength = "STRONG" if min(roc_short, roc_medium, roc_long) > 2 else "MODERATE"
        elif all_negative:
            alignment = "BEARISH - All timeframes showing negative momentum"
            strength = "STRONG" if max(roc_short, roc_medium, roc_long) < -2 else "MODERATE"
        else:
            alignment = "MIXED - Timeframes diverging, potential trend change"
            strength = "WEAK"

        # Detect acceleration/deceleration
        acceleration = ""
        if roc_short > roc_medium > roc_long:
            acceleration = "ACCELERATING - Short-term momentum exceeding longer-term"
        elif roc_short < roc_medium < roc_long:
            acceleration = "DECELERATING - Short-term momentum lagging longer-term"
        else:
            acceleration = "TRANSITIONING - Mixed momentum dynamics"

        report = f"""
## Multi-Timeframe Momentum Analysis for {symbol}
Analysis Date: {curr_date}

### Rate of Change (ROC) by Timeframe

| Timeframe | Period | ROC (%) | Signal |
|-----------|--------|---------|--------|
| Short-term | {short_period} days | {roc_short:.2f}% | {"🟢 Bullish" if roc_short > 0 else "🔴 Bearish"} |
| Medium-term | {medium_period} days | {roc_medium:.2f}% | {"🟢 Bullish" if roc_medium > 0 else "🔴 Bearish"} |
| Long-term | {long_period} days | {roc_long:.2f}% | {"🟢 Bullish" if roc_long > 0 else "🔴 Bearish"} |

### Momentum Summary

- **Alignment**: {alignment}
- **Strength**: {strength}
- **Trend Dynamics**: {acceleration}

### Interpretation

{"Strong bullish momentum confirmed across all timeframes. Consider long positions with confidence." if all_positive else ""}
{"Strong bearish momentum confirmed across all timeframes. Consider defensive or short positions." if all_negative else ""}
{"Mixed signals suggest caution. Wait for clearer alignment before taking significant positions." if not all_positive and not all_negative else ""}
"""
        return report

    except Exception as e:
        return f"Error in multi-timeframe momentum analysis: {str(e)}"


@tool
def get_adx_analysis(
    symbol: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    adx_period: Annotated[int, "ADX calculation period (default: 14)"] = 14,
    look_back_days: Annotated[int, "Days of history to analyze (default: 60)"] = 60,
) -> str:
    """
    Analyze trend strength using Average Directional Index (ADX).

    ADX measures trend strength regardless of direction:
    - 0-20: Weak or absent trend (ranging market)
    - 20-40: Moderate trend developing
    - 40-60: Strong trend
    - 60-80: Very strong trend
    - 80+: Extremely strong trend (rare)

    Also includes +DI and -DI for directional analysis.
    """
    try:
        # Get stock data
        stock_data = route_to_vendor("get_stock_data", symbol, curr_date, look_back_days)

        if isinstance(stock_data, str) and "error" in stock_data.lower():
            return f"Error retrieving stock data: {stock_data}"

        # Parse data
        if isinstance(stock_data, str):
            from io import StringIO
            df = pd.read_csv(StringIO(stock_data))
        else:
            df = stock_data

        if df.empty or len(df) < adx_period * 2:
            return f"Insufficient data for ADX analysis. Need at least {adx_period * 2} periods."

        # Get column names (handle different case conventions)
        high_col = 'high' if 'high' in df.columns else 'High'
        low_col = 'low' if 'low' in df.columns else 'Low'
        close_col = 'close' if 'close' in df.columns else 'Close'

        high = df[high_col]
        low = df[low_col]
        close = df[close_col]

        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

        # Smooth with EMA
        atr = tr.ewm(span=adx_period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=adx_period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=adx_period, adjust=False).mean() / atr)

        # Calculate ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=adx_period, adjust=False).mean()

        # Get current values
        current_adx = adx.iloc[-1]
        current_plus_di = plus_di.iloc[-1]
        current_minus_di = minus_di.iloc[-1]
        prev_adx = adx.iloc[-2]

        # Determine trend strength
        if current_adx < 20:
            trend_strength = "WEAK/ABSENT - Market is ranging"
            recommendation = "Avoid trend-following strategies. Consider range-bound approaches."
        elif current_adx < 40:
            trend_strength = "MODERATE - Trend developing"
            recommendation = "Trend is present but not dominant. Selective entries recommended."
        elif current_adx < 60:
            trend_strength = "STRONG - Clear trend in place"
            recommendation = "Good conditions for trend-following strategies."
        elif current_adx < 80:
            trend_strength = "VERY STRONG - Powerful trend"
            recommendation = "Excellent trend conditions. Watch for exhaustion signs."
        else:
            trend_strength = "EXTREME - Rare strength level"
            recommendation = "Trend may be overextended. Consider taking profits."

        # Trend direction
        if current_plus_di > current_minus_di:
            direction = "BULLISH (+DI > -DI)"
            direction_signal = "🟢 Uptrend"
        else:
            direction = "BEARISH (-DI > +DI)"
            direction_signal = "🔴 Downtrend"

        # ADX momentum
        adx_trend = "RISING" if current_adx > prev_adx else "FALLING"

        report = f"""
## ADX Trend Strength Analysis for {symbol}
Analysis Date: {curr_date}

### Current Readings

| Indicator | Value | Interpretation |
|-----------|-------|----------------|
| ADX | {current_adx:.2f} | {trend_strength.split(' - ')[0]} |
| +DI | {current_plus_di:.2f} | Bullish pressure |
| -DI | {current_minus_di:.2f} | Bearish pressure |
| ADX Trend | {adx_trend} | {"Trend strengthening" if adx_trend == "RISING" else "Trend weakening"} |

### Analysis Summary

- **Trend Strength**: {trend_strength}
- **Trend Direction**: {direction} {direction_signal}
- **ADX Momentum**: {adx_trend} (Previous: {prev_adx:.2f})

### Trading Recommendation

{recommendation}

### Key Signals

{"✅ +DI crossing above -DI recently suggests bullish momentum building." if current_plus_di > current_minus_di and abs(current_plus_di - current_minus_di) < 5 else ""}
{"⚠️ -DI crossing above +DI recently suggests bearish momentum building." if current_minus_di > current_plus_di and abs(current_plus_di - current_minus_di) < 5 else ""}
{"📈 Rising ADX with strong directional bias suggests continuation." if adx_trend == "RISING" and current_adx > 25 else ""}
{"📉 Falling ADX suggests trend is losing momentum." if adx_trend == "FALLING" and current_adx > 25 else ""}
{"⏸️ Low ADX indicates consolidation phase." if current_adx < 20 else ""}
"""
        return report

    except Exception as e:
        return f"Error in ADX analysis: {str(e)}"


@tool
def get_momentum_divergence(
    symbol: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Days to analyze for divergence (default: 30)"] = 30,
) -> str:
    """
    Detect momentum divergences between price and momentum indicators.

    Bullish Divergence: Price makes lower low, indicator makes higher low
    Bearish Divergence: Price makes higher high, indicator makes lower high

    Divergences often precede trend reversals.
    """
    try:
        # Get stock data
        stock_data = route_to_vendor("get_stock_data", symbol, curr_date, look_back_days * 2)

        if isinstance(stock_data, str) and "error" in stock_data.lower():
            return f"Error retrieving stock data: {stock_data}"

        # Parse data
        if isinstance(stock_data, str):
            from io import StringIO
            df = pd.read_csv(StringIO(stock_data))
        else:
            df = stock_data

        if df.empty or len(df) < look_back_days:
            return f"Insufficient data for divergence analysis."

        close_col = 'close' if 'close' in df.columns else 'Close'
        close = df[close_col].values[-look_back_days:]

        # Calculate RSI for divergence detection
        delta = pd.Series(close).diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.values

        # Find local extremes
        price_highs = []
        price_lows = []
        rsi_highs = []
        rsi_lows = []

        for i in range(2, len(close) - 2):
            # Price highs
            if close[i] > close[i-1] and close[i] > close[i-2] and close[i] > close[i+1] and close[i] > close[i+2]:
                price_highs.append((i, close[i]))
            # Price lows
            if close[i] < close[i-1] and close[i] < close[i-2] and close[i] < close[i+1] and close[i] < close[i+2]:
                price_lows.append((i, close[i]))

        # RSI extremes (after RSI is calculated, handling NaN)
        valid_rsi = rsi[~pd.isna(rsi)]
        rsi_start = len(rsi) - len(valid_rsi)

        for i in range(rsi_start + 2, len(rsi) - 2):
            if pd.notna(rsi[i]) and pd.notna(rsi[i-1]) and pd.notna(rsi[i+1]):
                if rsi[i] > rsi[i-1] and rsi[i] > rsi[i+1]:
                    rsi_highs.append((i, rsi[i]))
                if rsi[i] < rsi[i-1] and rsi[i] < rsi[i+1]:
                    rsi_lows.append((i, rsi[i]))

        # Detect divergences
        bullish_divergence = False
        bearish_divergence = False
        divergence_details = []

        # Check for bearish divergence (higher price high, lower RSI high)
        if len(price_highs) >= 2 and len(rsi_highs) >= 2:
            recent_price = price_highs[-1]
            prev_price = price_highs[-2]
            recent_rsi = rsi_highs[-1] if rsi_highs else None
            prev_rsi = rsi_highs[-2] if len(rsi_highs) >= 2 else None

            if recent_rsi and prev_rsi:
                if recent_price[1] > prev_price[1] and recent_rsi[1] < prev_rsi[1]:
                    bearish_divergence = True
                    divergence_details.append(
                        f"Bearish: Price high {recent_price[1]:.2f} > {prev_price[1]:.2f}, "
                        f"RSI high {recent_rsi[1]:.2f} < {prev_rsi[1]:.2f}"
                    )

        # Check for bullish divergence (lower price low, higher RSI low)
        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            recent_price = price_lows[-1]
            prev_price = price_lows[-2]
            recent_rsi = rsi_lows[-1] if rsi_lows else None
            prev_rsi = rsi_lows[-2] if len(rsi_lows) >= 2 else None

            if recent_rsi and prev_rsi:
                if recent_price[1] < prev_price[1] and recent_rsi[1] > prev_rsi[1]:
                    bullish_divergence = True
                    divergence_details.append(
                        f"Bullish: Price low {recent_price[1]:.2f} < {prev_price[1]:.2f}, "
                        f"RSI low {recent_rsi[1]:.2f} > {prev_rsi[1]:.2f}"
                    )

        # Generate report
        divergence_status = "NEUTRAL"
        if bullish_divergence and not bearish_divergence:
            divergence_status = "BULLISH DIVERGENCE DETECTED 🟢"
        elif bearish_divergence and not bullish_divergence:
            divergence_status = "BEARISH DIVERGENCE DETECTED 🔴"
        elif bullish_divergence and bearish_divergence:
            divergence_status = "MIXED SIGNALS - CONFLICTING DIVERGENCES ⚠️"

        report = f"""
## Momentum Divergence Analysis for {symbol}
Analysis Date: {curr_date}
Analysis Period: {look_back_days} days

### Divergence Status: {divergence_status}

### Detected Patterns

{"No significant divergences detected in the analysis period." if not divergence_details else ""}
{"".join([f"- {detail}" + chr(10) for detail in divergence_details])}

### Pattern Summary

- **Price Highs Found**: {len(price_highs)}
- **Price Lows Found**: {len(price_lows)}
- **RSI Highs Found**: {len(rsi_highs)}
- **RSI Lows Found**: {len(rsi_lows)}

### Interpretation

{"**Bullish Divergence**: Price is making lower lows while RSI is making higher lows. This suggests selling pressure is waning and a potential bottom is forming. Consider long entries with confirmation." if bullish_divergence else ""}
{"**Bearish Divergence**: Price is making higher highs while RSI is making lower highs. This suggests buying pressure is waning and a potential top is forming. Consider reducing exposure or short entries with confirmation." if bearish_divergence else ""}
{"**No Divergence**: Price and momentum are moving in sync. The current trend appears healthy." if not bullish_divergence and not bearish_divergence else ""}
"""
        return report

    except Exception as e:
        return f"Error in divergence analysis: {str(e)}"


# ============================================================================
# Momentum Analyst Agent Factory
# ============================================================================

def create_momentum_analyst(llm):
    """
    Create a Momentum Analyst agent that specializes in:
    - Multi-timeframe momentum analysis (ROC)
    - Trend strength measurement (ADX)
    - Momentum divergence detection
    - RSI/MACD momentum confirmation

    Args:
        llm: Language model for generating analysis

    Returns:
        Function that processes state and returns momentum analysis
    """

    def momentum_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_stock_data,
            get_indicators,
            get_multi_timeframe_momentum,
            get_adx_analysis,
            get_momentum_divergence,
        ]

        system_message = """You are a specialized Momentum Analyst with expertise in quantitative momentum analysis. Your role is to provide comprehensive momentum assessments using multiple techniques:

## Your Analytical Framework

### 1. Multi-Timeframe Momentum (ROC Analysis)
- Analyze Rate of Change across short (5-day), medium (14-day), and long-term (30-day) periods
- Identify momentum alignment or divergence across timeframes
- Detect acceleration/deceleration patterns

### 2. Trend Strength (ADX Analysis)
- Use ADX to measure trend strength (0-100 scale)
- Analyze +DI/-DI for directional bias
- Identify trending vs ranging market conditions

### 3. Momentum Divergence Detection
- Identify bullish divergences (price lower low, indicator higher low)
- Identify bearish divergences (price higher high, indicator lower high)
- Assess reversal probability based on divergence patterns

### 4. Traditional Momentum Indicators
- RSI for overbought/oversold conditions
- MACD for momentum confirmation
- Stochastic for entry timing

## Analysis Process

1. **Start with get_stock_data** to retrieve price history
2. **Use get_multi_timeframe_momentum** for ROC analysis across periods
3. **Apply get_adx_analysis** to measure trend strength
4. **Check get_momentum_divergence** for reversal signals
5. **Use get_indicators** for RSI and MACD confirmation

## Output Requirements

Provide a comprehensive Momentum Report including:
- Overall momentum score and direction
- Timeframe alignment assessment
- Trend strength classification
- Divergence alerts if detected
- Trading recommendations based on momentum state

**Always include a summary table with key momentum metrics.**

Focus on actionable insights. Quantify momentum states where possible (e.g., "RSI at 72 suggests overbought, but ADX at 45 confirms strong uptrend - momentum remains bullish but overextended")."""

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a specialized Momentum Analyst assistant, collaborating with other analysts."
                    " Use the provided momentum analysis tools to assess trend strength and direction."
                    " Execute comprehensive momentum analysis to support trading decisions."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}. The company we want to analyze is {ticker}.",
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
            "momentum_report": report,
        }

    return momentum_analyst_node
