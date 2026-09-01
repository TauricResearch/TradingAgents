"""
Entry Points Strategy Module: Identifies and manages CALL and PUT option entry points.
Based on technical analysis, support/resistance levels, and market conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from langchain_core.tools import tool


class OptionType(str, Enum):
    """Types of options."""
    CALL = "call"
    PUT = "put"


@dataclass
class EntryPoint:
    """Represents a trading entry point for options."""
    symbol: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: float
    reason: str
    technical_setup: dict
    option_type: OptionType = OptionType.CALL


@dataclass
class CallEntryPoint(EntryPoint):
    """CALL option entry point (bullish strategy)."""
    option_type: OptionType = OptionType.CALL
    
    def __post_init__(self):
        self.option_type = OptionType.CALL
        assert self.entry_price < self.take_profit, "Call: entry must be below take profit"
        assert self.entry_price > self.stop_loss, "Call: entry must be above stop loss"


@dataclass
class PutEntryPoint(EntryPoint):
    """PUT option entry point (bearish strategy)."""
    option_type: OptionType = OptionType.PUT
    
    def __post_init__(self):
        self.option_type = OptionType.PUT
        assert self.entry_price > self.take_profit, "Put: entry must be above take profit"
        assert self.entry_price < self.stop_loss, "Put: entry must be below stop loss"


def identify_support_resistance(
    current_price: float,
    high_52w: float,
    low_52w: float,
    recent_highs: list[float],
    recent_lows: list[float],
) -> dict:
    """
    Identify support and resistance levels from technical data.
    
    Args:
        current_price: Current trading price
        high_52w: 52-week high
        low_52w: 52-week low
        recent_highs: List of recent swing highs
        recent_lows: List of recent swing lows
        
    Returns:
        Dictionary with support and resistance levels
    """
    pivot = (high_52w + low_52w) / 2
    resistance_1 = pivot + (pivot - low_52w) * 0.382
    resistance_2 = high_52w
    support_1 = pivot - (high_52w - pivot) * 0.382
    support_2 = low_52w

    return {
        "pivot": pivot,
        "resistance_1": resistance_1,
        "resistance_2": resistance_2,
        "support_1": support_1,
        "support_2": support_2,
        "recent_highs": sorted(recent_highs, reverse=True)[:3],
        "recent_lows": sorted(recent_lows)[:3],
    }


def find_call_entry_points(
    symbol: str,
    current_price: float,
    rsi: float,
    support_level: float,
    resistance_level: float,
    atr: float,
    volume_trend: str,
) -> str:
    """
    Identify CALL option entry points (bullish strategy).
    
    CALL signals when:
    - Price breaks above support (bullish reversal)
    - RSI oversold (<30) but recovering
    - Volume increasing on upside
    - Price near support levels
    
    Args:
        symbol: Stock ticker symbol
        current_price: Current trading price
        rsi: Relative Strength Index (0-100)
        support_level: Key support price level
        resistance_level: Key resistance price level
        atr: Average True Range for position sizing
        volume_trend: Direction of volume trend ('increasing', 'decreasing', 'neutral')
        
    Returns:
        Entry point recommendation with confidence score
    """
    signals = []
    confidence = 0.0
    
    # Signal 1: Price testing support (reversal setup)
    if abs(current_price - support_level) / support_level < 0.02:  # Within 2% of support
        signals.append("Price testing key support level")
        confidence += 0.3
    
    # Signal 2: RSI oversold but recovering
    if rsi < 35:
        signals.append("RSI oversold (potential bounce)")
        confidence += 0.25
    elif rsi < 50:
        signals.append("RSI in neutral zone (upside potential)")
        confidence += 0.15
    
    # Signal 3: Volume increasing on upside
    if volume_trend == "increasing":
        signals.append("Volume increasing (institutional accumulation)")
        confidence += 0.25
    
    # Signal 4: Price structure
    if current_price < resistance_level * 0.95:
        signals.append("Significant upside to resistance")
        confidence += 0.2
    
    entry_price = support_level + (atr * 0.5)  # Enter above support by half ATR
    stop_loss = support_level - (atr * 1.0)
    take_profit = resistance_level
    
    entry_point = CallEntryPoint(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence_score=min(confidence, 1.0),
        reason="; ".join(signals) if signals else "No strong signals",
        technical_setup={
            "current_price": current_price,
            "rsi": rsi,
            "atr": atr,
            "support": support_level,
            "resistance": resistance_level,
            "volume_trend": volume_trend,
        }
    )
    
    return format_entry_point_report(entry_point)


def find_put_entry_points(
    symbol: str,
    current_price: float,
    rsi: float,
    support_level: float,
    resistance_level: float,
    atr: float,
    volume_trend: str,
) -> str:
    """
    Identify PUT option entry points (bearish strategy).
    
    PUT signals when:
    - Price breaks below resistance (bearish reversal)
    - RSI overbought (>70)
    - Volume decreasing on rallies (distribution)
    - Price near resistance levels
    
    Args:
        symbol: Stock ticker symbol
        current_price: Current trading price
        rsi: Relative Strength Index (0-100)
        support_level: Key support price level
        resistance_level: Key resistance price level
        atr: Average True Range for position sizing
        volume_trend: Direction of volume trend ('increasing', 'decreasing', 'neutral')
        
    Returns:
        Entry point recommendation with confidence score
    """
    signals = []
    confidence = 0.0
    
    # Signal 1: Price testing resistance (breakdown setup)
    if abs(current_price - resistance_level) / resistance_level < 0.02:  # Within 2% of resistance
        signals.append("Price testing key resistance level")
        confidence += 0.3
    
    # Signal 2: RSI overbought
    if rsi > 65:
        signals.append("RSI overbought (potential pullback)")
        confidence += 0.25
    elif rsi > 50:
        signals.append("RSI in upper zone (vulnerable to correction)")
        confidence += 0.15
    
    # Signal 3: Volume decreasing on rallies (distribution)
    if volume_trend == "decreasing":
        signals.append("Volume decreasing (institutional distribution)")
        confidence += 0.25
    
    # Signal 4: Price structure
    if current_price > support_level * 1.05:
        signals.append("Significant downside to support")
        confidence += 0.2
    
    entry_price = resistance_level - (atr * 0.5)  # Enter below resistance by half ATR
    stop_loss = resistance_level + (atr * 1.0)
    take_profit = support_level
    
    entry_point = PutEntryPoint(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence_score=min(confidence, 1.0),
        reason="; ".join(signals) if signals else "No strong signals",
        technical_setup={
            "current_price": current_price,
            "rsi": rsi,
            "atr": atr,
            "support": support_level,
            "resistance": resistance_level,
            "volume_trend": volume_trend,
        }
    )
    
    return format_entry_point_report(entry_point)


def format_entry_point_report(entry_point: EntryPoint) -> str:
    """Format entry point data for display."""
    return f"""
Entry Point Report: {entry_point.option_type.upper()} on {entry_point.symbol}
{"=" * 60}
Confidence Score: {entry_point.confidence_score:.1%}
Reason: {entry_point.reason}

Price Levels:
  Entry Price: ${entry_point.entry_price:.2f}
  Stop Loss:  ${entry_point.stop_loss:.2f}
  Take Profit: ${entry_point.take_profit:.2f}
  Risk/Reward Ratio: 1:{abs((entry_point.take_profit - entry_point.entry_price) / (entry_point.entry_price - entry_point.stop_loss)):.2f}

Technical Setup:
{_format_dict_indent(entry_point.technical_setup)}
"""


def _format_dict_indent(d: dict, indent: int = 2) -> str:
    """Helper to format dictionary with indentation."""
    lines = []
    for key, value in d.items():
        if isinstance(value, float):
            lines.append(f"{' ' * indent}{key}: {value:.2f}")
        else:
            lines.append(f"{' ' * indent}{key}: {value}")
    return "\n".join(lines)


def make_call_entry_points_tool():
    """Factory function to create CALL entry points tool for agents."""
    @tool
    def call_entry_points(
        symbol: Annotated[str, "Ticker symbol"],
        current_price: Annotated[float, "Current price of the stock"],
        rsi: Annotated[float, "RSI indicator (0-100)"],
        support_level: Annotated[float, "Key support level from technical analysis"],
        resistance_level: Annotated[float, "Key resistance level from technical analysis"],
        atr: Annotated[float, "Average True Range for volatility measurement"],
        volume_trend: Annotated[str, "Volume trend: 'increasing', 'decreasing', or 'neutral'"],
    ) -> str:
        """Identify CALL option entry points for bullish strategies."""
        return find_call_entry_points(
            symbol=symbol,
            current_price=current_price,
            rsi=rsi,
            support_level=support_level,
            resistance_level=resistance_level,
            atr=atr,
            volume_trend=volume_trend,
        )
    return call_entry_points


def make_put_entry_points_tool():
    """Factory function to create PUT entry points tool for agents."""
    @tool
    def put_entry_points(
        symbol: Annotated[str, "Ticker symbol"],
        current_price: Annotated[float, "Current price of the stock"],
        rsi: Annotated[float, "RSI indicator (0-100)"],
        support_level: Annotated[float, "Key support level from technical analysis"],
        resistance_level: Annotated[float, "Key resistance level from technical analysis"],
        atr: Annotated[float, "Average True Range for volatility measurement"],
        volume_trend: Annotated[str, "Volume trend: 'increasing', 'decreasing', or 'neutral'"],
    ) -> str:
        """Identify PUT option entry points for bearish strategies."""
        return find_put_entry_points(
            symbol=symbol,
            current_price=current_price,
            rsi=rsi,
            support_level=support_level,
            resistance_level=resistance_level,
            atr=atr,
            volume_trend=volume_trend,
        )
    return put_entry_points
