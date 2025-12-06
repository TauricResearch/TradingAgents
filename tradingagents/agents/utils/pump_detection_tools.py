"""
Pump Detection Tools
Tools for identifying stocks that may experience sudden price increases.
Detects patterns like volume spikes, price acceleration, social sentiment surges, etc.
"""

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
import json


@tool
def detect_volume_spike(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back for comparison"] = 20,
    threshold_multiplier: Annotated[float, "volume spike threshold (e.g., 2.0 = 2x average)"] = 2.0,
) -> str:
    """
    Detect abnormal volume spikes that may indicate pump activity.
    Volume spikes are early indicators of increased market interest.
    
    Args:
        symbol: Ticker symbol
        curr_date: Current trading date
        look_back_days: Historical period to calculate average volume
        threshold_multiplier: How many times the average volume to flag as spike
    
    Returns:
        Analysis of volume spike patterns
    """
    try:
        # Get historical stock data
        stock_data = route_to_vendor("get_stock_data", symbol, curr_date, look_back_days)
        
        # Parse the CSV data
        lines = stock_data.strip().split('\n')
        if len(lines) < 2:
            return f"Insufficient data for {symbol} to analyze volume spikes"
        
        # Skip header and parse volumes
        volumes = []
        dates = []
        for line in lines[1:]:
            parts = line.split(',')
            if len(parts) >= 6:
                try:
                    volume = float(parts[5])
                    volumes.append(volume)
                    dates.append(parts[0])
                except:
                    continue
        
        if not volumes:
            return f"Could not extract volume data for {symbol}"
        
        # Calculate average volume (excluding today)
        if len(volumes) > 1:
            avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
            current_volume = volumes[-1]
        else:
            avg_volume = volumes[0]
            current_volume = volumes[0]
        
        spike_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        is_spike = spike_ratio >= threshold_multiplier
        
        result = f"""## Volume Spike Analysis for {symbol}

**Current Volume**: {current_volume:,.0f} shares
**Average Volume (last {look_back_days} days)**: {avg_volume:,.0f} shares
**Spike Ratio**: {spike_ratio:.2f}x
**Threshold**: {threshold_multiplier}x
**SPIKE DETECTED**: {'YES ⚠️' if is_spike else 'NO'}

### Interpretation:
"""
        if is_spike:
            result += f"🚨 **PUMP SIGNAL**: Volume is {spike_ratio:.1f}x the average. This suggests increased institutional or retail interest."
        else:
            result += f"Normal volume activity. Current volume is {spike_ratio:.1f}x average (threshold: {threshold_multiplier}x)."
        
        return result
        
    except Exception as e:
        return f"Error analyzing volume spike for {symbol}: {str(e)}"


@tool
def detect_price_acceleration(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 10,
) -> str:
    """
    Detect rapid price acceleration that may indicate a pump.
    Compares recent gains to longer-term performance.
    
    Args:
        symbol: Ticker symbol
        curr_date: Current trading date
        look_back_days: Historical period to analyze
    
    Returns:
        Analysis of price acceleration patterns
    """
    try:
        stock_data = route_to_vendor("get_stock_data", symbol, curr_date, look_back_days)
        
        lines = stock_data.strip().split('\n')
        if len(lines) < 3:
            return f"Insufficient data for {symbol} to analyze price acceleration"
        
        # Parse closing prices
        prices = []
        dates = []
        for line in lines[1:]:
            parts = line.split(',')
            if len(parts) >= 5:
                try:
                    close = float(parts[4])
                    prices.append(close)
                    dates.append(parts[0])
                except:
                    continue
        
        if len(prices) < 3:
            return f"Could not extract sufficient price data for {symbol}"
        
        prices.reverse()  # Make chronological order
        
        # Calculate gains
        overall_gain = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
        
        # Calculate recent acceleration (last 3 days vs before)
        if len(prices) >= 4:
            recent_gain = ((prices[-1] - prices[-3]) / prices[-3]) * 100 if prices[-3] > 0 else 0
            older_gain = ((prices[-3] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
        else:
            recent_gain = overall_gain
            older_gain = 0
        
        is_accelerating = recent_gain > 5 and recent_gain > (older_gain * 1.5) if older_gain != 0 else recent_gain > 5
        
        result = f"""## Price Acceleration Analysis for {symbol}

**Overall Gain ({look_back_days} days)**: {overall_gain:+.2f}%
**Recent Gain (last 3 days)**: {recent_gain:+.2f}%
**Older Gain (before that)**: {older_gain:+.2f}%
**ACCELERATION DETECTED**: {'YES ⚠️' if is_accelerating else 'NO'}

### Interpretation:
"""
        if is_accelerating:
            result += f"🚨 **PUMP SIGNAL**: Price accelerating rapidly with {recent_gain:.1f}% gain in last 3 days. Potential pump momentum building."
        else:
            result += f"Price movement steady or decelerating. Recent: {recent_gain:.1f}%, Overall: {overall_gain:.1f}%"
        
        return result
        
    except Exception as e:
        return f"Error analyzing price acceleration for {symbol}: {str(e)}"


@tool
def detect_social_sentiment_surge(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
) -> str:
    """
    Detect surges in social media sentiment that often precede pump moves.
    Monitors Reddit, Twitter, StockTwits for unusual activity.
    
    Args:
        symbol: Ticker symbol
        curr_date: Current trading date
    
    Returns:
        Analysis of social sentiment patterns
    """
    try:
        # Try to get trending social data
        social_data = route_to_vendor("get_trending_social", curr_date, 3, 50)
        
        # Check if our symbol is in trending data
        is_trending = symbol.upper() in social_data.upper()
        
        result = f"""## Social Sentiment Surge Analysis for {symbol}

**Trending Status**: {'YES 🔥' if is_trending else 'NO'}

### Current Market Buzz:
{social_data[:500]}...

### Interpretation:
"""
        if is_trending:
            result += f"🚨 **PUMP SIGNAL**: {symbol} is actively buzzing on social platforms. High retail interest detected."
        else:
            result += f"{symbol} is not currently in top trending stocks. Limited social momentum at this time."
        
        return result
        
    except Exception as e:
        return f"Error analyzing social sentiment for {symbol}: {str(e)}"


@tool
def detect_oversold_bounce(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    rsi_threshold: Annotated[int, "RSI threshold for oversold (default 30)"] = 30,
) -> str:
    """
    Detect oversold conditions that often precede pump bounces.
    Uses RSI and other momentum indicators.
    
    Args:
        symbol: Ticker symbol
        curr_date: Current trading date
        rsi_threshold: RSI value threshold (below = oversold)
    
    Returns:
        Analysis of oversold bounce potential
    """
    try:
        # Get RSI indicator
        rsi_data = route_to_vendor("get_indicators", symbol, "rsi", curr_date, 5)
        
        # Parse RSI values to find current
        lines = rsi_data.split('\n')
        current_rsi = None
        
        for line in lines:
            if curr_date in line:
                # Extract the RSI value
                parts = line.split(':')
                if len(parts) >= 2:
                    try:
                        current_rsi = float(parts[-1].strip())
                        break
                    except:
                        continue
        
        if current_rsi is None:
            # Try to get any RSI value
            for line in lines:
                if 'N/A' not in line and ':' in line and len(line.split(':')) >= 2:
                    try:
                        val = float(line.split(':')[-1].strip())
                        if 0 <= val <= 100:
                            current_rsi = val
                            break
                    except:
                        continue
        
        is_oversold = current_rsi is not None and current_rsi < rsi_threshold
        
        result = f"""## Oversold Bounce Analysis for {symbol}

**Current RSI**: {current_rsi:.1f if current_rsi else 'N/A'}
**Oversold Threshold**: {rsi_threshold}
**OVERSOLD**: {'YES ⚠️' if is_oversold else 'NO'}

### Interpretation:
"""
        if is_oversold:
            result += f"🚨 **PUMP SIGNAL**: RSI at {current_rsi:.1f} indicates oversold conditions. High probability of bounce/recovery pump."
        else:
            result += f"RSI at {current_rsi:.1f if current_rsi else 'N/A'} - not in oversold territory. Lower bounce probability."
        
        return result
        
    except Exception as e:
        return f"Error analyzing oversold bounce for {symbol}: {str(e)}"


@tool
def detect_catalyst_event(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
) -> str:
    """
    Detect upcoming or recent catalyst events that could trigger pumps.
    Looks for earnings, FDA approvals, partnerships, etc.
    
    Args:
        symbol: Ticker symbol
        curr_date: Current trading date
    
    Returns:
        Analysis of potential catalyst events
    """
    try:
        # Check earnings calendar
        earnings_data = route_to_vendor("get_earnings_calendar", "3month", symbol)
        
        has_catalyst = "earnings" in earnings_data.lower() or "scheduled" in earnings_data.lower()
        
        result = f"""## Catalyst Event Analysis for {symbol}

**Upcoming Catalysts**: {'YES 📅' if has_catalyst else 'NO'}

### Catalyst Information:
{earnings_data[:400]}...

### Interpretation:
"""
        if has_catalyst:
            result += f"🚨 **PUMP SIGNAL**: Upcoming catalyst event detected. Catalysts drive pump volume and speculation."
        else:
            result += f"No major catalysts identified in the next 3 months."
        
        return result
        
    except Exception as e:
        return f"Error analyzing catalyst events for {symbol}: {str(e)}"


@tool
def calculate_pump_score(
    symbol: Annotated[str, "ticker symbol"],
    volume_spike_detected: Annotated[bool, "whether volume spike was detected"],
    price_acceleration_detected: Annotated[bool, "whether price acceleration was detected"],
    social_sentiment_surge: Annotated[bool, "whether social sentiment surge was detected"],
    oversold_bounce: Annotated[bool, "whether oversold bounce signal was detected"],
    catalyst_event: Annotated[bool, "whether catalyst event exists"],
) -> str:
    """
    Calculate a composite pump probability score (0-100) based on detected signals.
    
    Args:
        symbol: Ticker symbol
        volume_spike_detected: Boolean
        price_acceleration_detected: Boolean
        social_sentiment_surge: Boolean
        oversold_bounce: Boolean
        catalyst_event: Boolean
    
    Returns:
        Pump score and risk assessment
    """
    # Score calculation
    score = 0
    signals_detected = 0
    
    weights = {
        "volume_spike": 25,
        "price_acceleration": 20,
        "social_sentiment": 15,
        "oversold_bounce": 20,
        "catalyst": 20,
    }
    
    if volume_spike_detected:
        score += weights["volume_spike"]
        signals_detected += 1
    
    if price_acceleration_detected:
        score += weights["price_acceleration"]
        signals_detected += 1
    
    if social_sentiment_surge:
        score += weights["social_sentiment"]
        signals_detected += 1
    
    if oversold_bounce:
        score += weights["oversold_bounce"]
        signals_detected += 1
    
    if catalyst_event:
        score += weights["catalyst"]
        signals_detected += 1
    
    # Risk assessment
    if score >= 70:
        risk_level = "🔴 VERY HIGH RISK - HIGH PUMP PROBABILITY"
        recommendation = "Strong indicators of potential pump. Exercise caution and use tight stop-losses."
    elif score >= 50:
        risk_level = "🟠 HIGH RISK - MODERATE PUMP PROBABILITY"
        recommendation = "Multiple signals detected. Consider entry with risk management."
    elif score >= 30:
        risk_level = "🟡 MODERATE RISK - LOW PUMP PROBABILITY"
        recommendation = "Some signals present. Requires additional confirmation before entry."
    else:
        risk_level = "🟢 LOW RISK - LOW PUMP PROBABILITY"
        recommendation = "Limited pump signals. Better to wait for stronger setup."
    
    result = f"""## Pump Detection Score for {symbol}

**Pump Probability Score**: {score}/100
**Signals Detected**: {signals_detected}/5
**Risk Level**: {risk_level}

### Signal Breakdown:
- Volume Spike: {'✅' if volume_spike_detected else '❌'}
- Price Acceleration: {'✅' if price_acceleration_detected else '❌'}
- Social Sentiment Surge: {'✅' if social_sentiment_surge else '❌'}
- Oversold Bounce Setup: {'✅' if oversold_bounce else '❌'}
- Catalyst Event: {'✅' if catalyst_event else '❌'}

### Recommendation:
{recommendation}

### Risk Management:
- Enter with small position size (1-2% of portfolio)
- Use tight stop-loss (2-3% below entry)
- Set profit targets at resistance levels
- Monitor volume and momentum continuously
- Exit on volume decline or reversal signals
"""
    
    return result
