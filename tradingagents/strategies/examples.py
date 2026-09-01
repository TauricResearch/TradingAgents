"""
Example: Using Entry Points for NIFTY 50 Trading based on the TradingView Chart.
Shows how to identify CALL and PUT entry points for options trading.
"""

from tradingagents.strategies.entry_points import (
    find_call_entry_points,
    find_put_entry_points,
)


def example_nifty50_entry_points():
    """
    Example using NIFTY 50 chart data from TradingView.
    
    Chart Analysis (Sep 01, 2026, 05:25 UTC):
    - Current Price: 24,087.65
    - Key Support: 24,000-24,087.65
    - Key Resistance: 24,250-24,500
    - Volume: 94.99M (recent increase)
    - Trend: Recovering from downtrend with bullish volume divergence
    """
    
    print("\n" + "=" * 70)
    print("NIFTY 50 ENTRY POINTS ANALYSIS - TradingView Chart")
    print("=" * 70 + "\n")
    
    # Market Parameters from Chart Analysis
    symbol = "NIFTY50"
    current_price = 24087.65
    support_level = 24000.00
    resistance_level = 24500.00
    atr = 150.00  # Estimated from chart volatility
    rsi = 42.0  # Neutral zone - slightly oversold recovery
    volume_trend = "increasing"  # Volume bars show accumulation
    
    # Find CALL Entry Points
    print("1. CALL ENTRY POINTS (Bullish Strategy)")
    print("-" * 70)
    call_signal = find_call_entry_points(
        symbol=symbol,
        current_price=current_price,
        rsi=rsi,
        support_level=support_level,
        resistance_level=resistance_level,
        atr=atr,
        volume_trend=volume_trend,
    )
    print(call_signal)
    
    # Find PUT Entry Points
    print("\n2. PUT ENTRY POINTS (Bearish Strategy)")
    print("-" * 70)
    put_signal = find_put_entry_points(
        symbol=symbol,
        current_price=current_price,
        rsi=rsi,
        support_level=support_level,
        resistance_level=resistance_level,
        atr=atr,
        volume_trend=volume_trend,
    )
    print(put_signal)
    
    # Trading Recommendation
    print("\n3. TRADING RECOMMENDATION")
    print("-" * 70)
    print(f"""
Strategy: Bullish Bias with Risk Management

Primary Trade: CALL Options
  >> Price near support with bullish divergence
  >> Volume increasing (accumulation signal)
  >> RSI recovering from oversold (42)
  >> Upside target: {resistance_level:,.2f}

Entry Setup:
  * Entry Zone: {support_level:,.2f} to {support_level + (atr * 0.5):,.2f}
  * Stop Loss: {support_level - (atr * 1.0):,.2f}
  * Take Profit: {resistance_level:,.2f}
  * Risk: {atr * 1.0:,.2f} points (~{(atr * 1.0 / current_price * 100):.2f}%)
  * Reward: {resistance_level - (support_level + atr * 0.5):,.2f} points

Alternatively:
  - PUT options at resistance ({resistance_level:,.2f}) if price breaks above resistance
  - Watch for volume confirmation before entering

Expiry Suggestion: 
  * CALL: 1-2 weeks out (collect theta while bullish)
  * PUT: For protection only, sell for premium
""")


def example_real_world_parameters():
    """
    Example with typical real-world market parameters.
    """
    print("\n" + "=" * 70)
    print("EXAMPLE: GENERIC STOCK ENTRY POINT ANALYSIS")
    print("=" * 70 + "\n")
    
    # Hypothetical stock parameters
    examples = [
        {
            "name": "Strong Bullish Setup",
            "symbol": "AAPL",
            "current_price": 150.50,
            "support_level": 148.00,
            "resistance_level": 155.00,
            "atr": 2.50,
            "rsi": 28.0,  # Oversold
            "volume_trend": "increasing",
            "description": "Oversold bounce at support with increasing volume",
        },
        {
            "name": "Bearish Breakdown Setup",
            "symbol": "MSFT",
            "current_price": 320.00,
            "support_level": 310.00,
            "resistance_level": 325.00,
            "atr": 4.00,
            "rsi": 72.0,  # Overbought
            "volume_trend": "decreasing",
            "description": "Overbought at resistance with decreasing volume (distribution)",
        },
    ]
    
    for example in examples:
        print(f"\nSetup: {example['name']}")
        print(f"Reason: {example['description']}")
        print("-" * 70)
        
        if example["rsi"] < 40:
            signal = find_call_entry_points(
                symbol=example["symbol"],
                current_price=example["current_price"],
                rsi=example["rsi"],
                support_level=example["support_level"],
                resistance_level=example["resistance_level"],
                atr=example["atr"],
                volume_trend=example["volume_trend"],
            )
            print("CALL Signal:")
        else:
            signal = find_put_entry_points(
                symbol=example["symbol"],
                current_price=example["current_price"],
                rsi=example["rsi"],
                support_level=example["support_level"],
                resistance_level=example["resistance_level"],
                atr=example["atr"],
                volume_trend=example["volume_trend"],
            )
            print("PUT Signal:")
        
        print(signal)


if __name__ == "__main__":
    example_nifty50_entry_points()
    example_real_world_parameters()
