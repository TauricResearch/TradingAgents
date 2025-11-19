#!/usr/bin/env python3
"""
Example: TradingAgents + Alpaca Paper Trading Integration

This example shows how to:
1. Use TradingAgents to analyze stocks and generate signals
2. Execute those signals with real paper trading on Alpaca
3. Track performance over time

Setup:
1. Configure .env with both TradingAgents and Alpaca credentials
2. Run this script to see the full integration in action!
"""

from decimal import Decimal
from datetime import datetime
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.brokers import AlpacaBroker
from tradingagents.brokers.base import BrokerOrder, OrderSide, OrderType
from tradingagents.default_config import DEFAULT_CONFIG


def execute_trading_signal(broker, signal, symbol, position_size=Decimal("10")):
    """
    Execute a trading signal from TradingAgents.

    Args:
        broker: AlpacaBroker instance
        signal: Signal from TradingAgents (BUY, SELL, HOLD)
        symbol: Stock ticker
        position_size: Number of shares to trade

    Returns:
        Executed order or None
    """
    signal_upper = signal.upper()

    if signal_upper == "BUY":
        print(f"   📈 BUY signal for {symbol}")

        # Check if we already have a position
        current_position = broker.get_position(symbol)
        if current_position and current_position.quantity > 0:
            print(f"   ⚠ Already holding {current_position.quantity} shares, skipping")
            return None

        # Place market buy order
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=position_size,
            order_type=OrderType.MARKET,
            time_in_force="day"
        )

        try:
            executed = broker.submit_order(order)
            print(f"   ✓ Buy order placed: {executed.order_id}")
            return executed
        except Exception as e:
            print(f"   ✗ Order failed: {e}")
            return None

    elif signal_upper == "SELL":
        print(f"   📉 SELL signal for {symbol}")

        # Check if we have a position to sell
        current_position = broker.get_position(symbol)
        if not current_position or current_position.quantity == 0:
            print(f"   ⚠ No position to sell, skipping")
            return None

        # Sell entire position
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=current_position.quantity,
            order_type=OrderType.MARKET,
            time_in_force="day"
        )

        try:
            executed = broker.submit_order(order)
            print(f"   ✓ Sell order placed: {executed.order_id}")
            return executed
        except Exception as e:
            print(f"   ✗ Order failed: {e}")
            return None

    elif signal_upper == "HOLD":
        print(f"   ⏸️  HOLD signal for {symbol}")
        return None

    else:
        print(f"   ❓ Unknown signal: {signal}")
        return None


def main():
    print("="*70)
    print("TRADINGAGENTS + ALPACA INTEGRATION")
    print("AI-Powered Trading with Real Paper Trading")
    print("="*70)

    # Initialize TradingAgents
    print("\n1. Initializing TradingAgents...")
    config = DEFAULT_CONFIG.copy()

    # You can use Claude for better analysis!
    # config["llm_provider"] = "anthropic"
    # config["deep_think_llm"] = "claude-3-5-sonnet-20241022"

    ta = TradingAgentsGraph(
        selected_analysts=["market", "fundamentals", "news"],
        config=config
    )
    print("   ✓ TradingAgents ready")

    # Initialize Alpaca broker
    print("\n2. Connecting to Alpaca paper trading...")
    broker = AlpacaBroker(paper_trading=True)

    try:
        broker.connect()
        print("   ✓ Connected to Alpaca")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        print("\nSetup required:")
        print("  1. Sign up at https://alpaca.markets")
        print("  2. Add ALPACA_API_KEY to .env")
        print("  3. Add ALPACA_SECRET_KEY to .env")
        return

    # Show initial account status
    print("\n3. Initial Account Status...")
    account = broker.get_account()
    print(f"   Cash: ${account.cash:,.2f}")
    print(f"   Buying Power: ${account.buying_power:,.2f}")
    print(f"   Portfolio Value: ${account.portfolio_value:,.2f}")

    # Analyze a stock with TradingAgents
    ticker = "NVDA"
    trade_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n4. Analyzing {ticker} with TradingAgents...")
    print(f"   Trade Date: {trade_date}")
    print("   (This may take 1-2 minutes...)")

    try:
        final_state, processed_signal = ta.propagate(ticker, trade_date)

        print(f"\n   📊 Analysis Complete!")
        print(f"   Signal: {processed_signal}")

        # Show some insights from the analysis
        if final_state.get("market_report"):
            print(f"\n   Market Analysis:")
            print(f"   {final_state['market_report'][:200]}...")

        if final_state.get("fundamentals_report"):
            print(f"\n   Fundamentals:")
            print(f"   {final_state['fundamentals_report'][:200]}...")

    except Exception as e:
        print(f"   ✗ Analysis failed: {e}")
        print("   (This might be due to API quota limits)")
        # Use a dummy signal for demo
        processed_signal = "HOLD"
        print(f"   Using dummy signal: {processed_signal}")

    # Execute the signal
    print(f"\n5. Executing Trading Signal...")
    order = execute_trading_signal(
        broker=broker,
        signal=processed_signal,
        symbol=ticker,
        position_size=Decimal("5")
    )

    # Show final positions
    print(f"\n6. Final Positions...")
    positions = broker.get_positions()
    if positions:
        total_value = Decimal("0")
        for pos in positions:
            print(f"   {pos.symbol}:")
            print(f"      Quantity: {pos.quantity}")
            print(f"      Avg Cost: ${pos.avg_entry_price:.2f}")
            print(f"      Current: ${pos.current_price:.2f}")
            print(f"      P&L: ${pos.unrealized_pnl:,.2f} ({pos.unrealized_pnl_percent:.2%})")
            total_value += pos.market_value
        print(f"\n   Total Position Value: ${total_value:,.2f}")
    else:
        print("   No open positions")

    # Final account status
    print(f"\n7. Final Account Status...")
    account = broker.get_account()
    print(f"   Cash: ${account.cash:,.2f}")
    print(f"   Portfolio Value: ${account.portfolio_value:,.2f}")
    print(f"   Total Equity: ${account.equity:,.2f}")

    # Calculate session P&L
    session_pnl = account.equity - account.last_equity
    print(f"   Session P&L: ${session_pnl:,.2f}")

    broker.disconnect()
    print("\n✓ Disconnected from Alpaca")

    print("\n" + "="*70)
    print("INTEGRATION SUMMARY")
    print("="*70)
    print("✓ TradingAgents analyzed the stock")
    print("✓ Signal was executed via Alpaca paper trading")
    print("✓ Portfolio updated with real market prices")
    print("\nThis is how you build a REAL trading bot:")
    print("  1. TradingAgents provides intelligent analysis")
    print("  2. Alpaca executes trades with real market data")
    print("  3. You practice risk-free with paper trading")
    print("  4. When ready, switch to live trading!")
    print("="*70)


if __name__ == "__main__":
    main()
