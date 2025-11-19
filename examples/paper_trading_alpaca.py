#!/usr/bin/env python3
"""
Example: Paper Trading with Alpaca

This example shows how to use Alpaca's FREE paper trading to practice
trading strategies without risking real money.

Setup:
1. Sign up for free at https://alpaca.markets
2. Get your API keys from the dashboard
3. Add to .env:
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_PAPER_TRADING=true

4. Run this script!
"""

from decimal import Decimal
import time
from tradingagents.brokers import AlpacaBroker
from tradingagents.brokers.base import BrokerOrder, OrderSide, OrderType

def main():
    print("="*70)
    print("ALPACA PAPER TRADING EXAMPLE")
    print("="*70)

    # Initialize broker in paper trading mode (FREE!)
    print("\n1. Connecting to Alpaca paper trading...")
    broker = AlpacaBroker(paper_trading=True)

    try:
        broker.connect()
        print("   ✓ Connected successfully!")
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        print("\nMake sure you have:")
        print("  - Signed up at https://alpaca.markets")
        print("  - Set ALPACA_API_KEY in .env")
        print("  - Set ALPACA_SECRET_KEY in .env")
        return

    # Get account information
    print("\n2. Checking account status...")
    account = broker.get_account()
    print(f"   Account: {account.account_number}")
    print(f"   Cash: ${account.cash:,.2f}")
    print(f"   Buying Power: ${account.buying_power:,.2f}")
    print(f"   Portfolio Value: ${account.portfolio_value:,.2f}")

    # Get current positions
    print("\n3. Current positions...")
    positions = broker.get_positions()
    if positions:
        for pos in positions:
            print(f"   {pos.symbol}: {pos.quantity} shares @ ${pos.avg_entry_price}")
            print(f"      Current: ${pos.current_price} | P&L: ${pos.unrealized_pnl:,.2f}")
    else:
        print("   No positions (starting fresh!)")

    # Example 1: Market buy order
    print("\n4. Placing market buy order for AAPL...")
    try:
        buy_order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            order_type=OrderType.MARKET,
            time_in_force="day"
        )

        submitted = broker.submit_order(buy_order)
        print(f"   ✓ Order submitted!")
        print(f"   Order ID: {submitted.order_id}")
        print(f"   Status: {submitted.status.value}")

        # Wait a moment for order to fill
        time.sleep(2)

        # Check order status
        updated_order = broker.get_order(submitted.order_id)
        if updated_order:
            print(f"   Updated Status: {updated_order.status.value}")
            if updated_order.filled_qty > 0:
                print(f"   Filled: {updated_order.filled_qty} @ ${updated_order.filled_price}")

    except Exception as e:
        print(f"   ✗ Order failed: {e}")

    # Example 2: Limit sell order
    print("\n5. Placing limit sell order for AAPL...")
    try:
        # Get current price
        current_price = broker.get_current_price("AAPL")
        print(f"   Current AAPL price: ${current_price}")

        # Place limit order 5% above current price
        limit_price = current_price * Decimal("1.05")

        sell_order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=Decimal("2"),
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force="day"
        )

        submitted = broker.submit_order(sell_order)
        print(f"   ✓ Limit order placed at ${limit_price:.2f}")
        print(f"   Order ID: {submitted.order_id}")

    except Exception as e:
        print(f"   ✗ Order failed: {e}")

    # Example 3: Get all open orders
    print("\n6. Checking open orders...")
    from tradingagents.brokers.base import OrderStatus

    open_orders = broker.get_orders(status=OrderStatus.SUBMITTED)
    if open_orders:
        for order in open_orders:
            print(f"   {order.symbol}: {order.side.value} {order.quantity}")
            print(f"      Type: {order.order_type.value}")
            if order.limit_price:
                print(f"      Limit: ${order.limit_price}")
    else:
        print("   No open orders")

    # Example 4: Check specific position
    print("\n7. Checking AAPL position...")
    aapl_position = broker.get_position("AAPL")
    if aapl_position:
        print(f"   Shares: {aapl_position.quantity}")
        print(f"   Avg Cost: ${aapl_position.avg_entry_price:.2f}")
        print(f"   Current: ${aapl_position.current_price:.2f}")
        print(f"   Market Value: ${aapl_position.market_value:,.2f}")
        print(f"   P&L: ${aapl_position.unrealized_pnl:,.2f} ({aapl_position.unrealized_pnl_percent:.2%})")
    else:
        print("   No AAPL position")

    # Final account status
    print("\n8. Final account status...")
    account = broker.get_account()
    print(f"   Cash: ${account.cash:,.2f}")
    print(f"   Portfolio Value: ${account.portfolio_value:,.2f}")
    print(f"   Equity: ${account.equity:,.2f}")

    # Disconnect
    broker.disconnect()
    print("\n✓ Disconnected from Alpaca")

    print("\n" + "="*70)
    print("TIPS FOR PAPER TRADING")
    print("="*70)
    print("✓ Paper trading uses REAL market data")
    print("✓ Orders execute at REAL prices")
    print("✓ You can practice risk-free!")
    print("✓ Use this to test strategies before going live")
    print("\nNext steps:")
    print("  1. Try different order types (stop-loss, take-profit)")
    print("  2. Integrate with TradingAgents signals")
    print("  3. Build a complete trading bot!")
    print("="*70)


if __name__ == "__main__":
    main()
