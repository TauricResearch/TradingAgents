#!/usr/bin/env python3
"""
TradingAgents Web Interface

A beautiful web UI for running TradingAgents analysis and managing trades.

Usage:
    chainlit run web_app.py -w

Then open http://localhost:8000 in your browser!
"""

import chainlit as cl
from decimal import Decimal
from datetime import datetime
import json
from typing import Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.brokers import AlpacaBroker
from tradingagents.brokers.base import OrderSide, OrderType


# Global state
ta_graph: Optional[TradingAgentsGraph] = None
broker: Optional[AlpacaBroker] = None


@cl.on_chat_start
async def start():
    """Initialize the chat session."""
    await cl.Message(
        content="""# 🤖 Welcome to TradingAgents!

I'm your AI-powered trading assistant. I can help you:

📊 **Analyze Stocks** - Deep analysis using multiple expert agents
💼 **Manage Positions** - Track your portfolio and P&L
📈 **Execute Trades** - Paper trading integration with Alpaca
📉 **View Reports** - Detailed analysis and recommendations

**Quick Commands:**
- `analyze AAPL` - Analyze a stock
- `portfolio` - View current positions
- `account` - Check account status
- `help` - Show all commands

**Getting Started:**
1. Make sure your `.env` is configured
2. Try analyzing a stock: `analyze NVDA`
3. Review the detailed analysis
4. Execute trades based on signals!

What would you like to do?
"""
    ).send()

    # Store settings in session
    cl.user_session.set("config", DEFAULT_CONFIG.copy())
    cl.user_session.set("broker_connected", False)


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages."""
    global ta_graph, broker

    msg_content = message.content.strip().lower()
    parts = msg_content.split()

    if not parts:
        await cl.Message(content="Please enter a command. Type `help` for options.").send()
        return

    command = parts[0]

    # Help command
    if command == "help":
        await show_help()

    # Analyze command
    elif command == "analyze":
        if len(parts) < 2:
            await cl.Message(content="Usage: `analyze TICKER`\n\nExample: `analyze AAPL`").send()
            return

        ticker = parts[1].upper()
        await analyze_stock(ticker)

    # Portfolio command
    elif command == "portfolio":
        await show_portfolio()

    # Account command
    elif command == "account":
        await show_account()

    # Connect broker command
    elif command == "connect":
        await connect_broker()

    # Buy command
    elif command == "buy":
        if len(parts) < 3:
            await cl.Message(content="Usage: `buy TICKER QUANTITY`\n\nExample: `buy AAPL 10`").send()
            return

        ticker = parts[1].upper()
        try:
            quantity = Decimal(parts[2])
            await execute_buy(ticker, quantity)
        except ValueError:
            await cl.Message(content="Invalid quantity. Please use a number.").send()

    # Sell command
    elif command == "sell":
        if len(parts) < 3:
            await cl.Message(content="Usage: `sell TICKER QUANTITY`\n\nExample: `sell AAPL 10`").send()
            return

        ticker = parts[1].upper()
        try:
            quantity = Decimal(parts[2])
            await execute_sell(ticker, quantity)
        except ValueError:
            await cl.Message(content="Invalid quantity. Please use a number.").send()

    # Settings command
    elif command == "settings":
        await show_settings()

    # Set LLM provider
    elif command == "provider":
        if len(parts) < 2:
            await cl.Message(content="Usage: `provider PROVIDER`\n\nOptions: openai, anthropic, google").send()
            return

        provider = parts[1].lower()
        await set_provider(provider)

    else:
        await cl.Message(
            content=f"Unknown command: `{command}`\n\nType `help` to see available commands."
        ).send()


async def show_help():
    """Show help message."""
    await cl.Message(
        content="""# 📚 TradingAgents Commands

## Analysis
- `analyze TICKER` - Analyze a stock with all agents
- `settings` - View current settings
- `provider NAME` - Change LLM provider (openai/anthropic/google)

## Trading
- `connect` - Connect to paper trading broker
- `account` - View account balance and buying power
- `portfolio` - View all positions and P&L
- `buy TICKER QTY` - Buy shares (e.g., `buy AAPL 10`)
- `sell TICKER QTY` - Sell shares (e.g., `sell AAPL 10`)

## Examples
```
analyze NVDA
buy NVDA 5
portfolio
sell NVDA 5
```

**Tips:**
- Start with `analyze` to get AI insights
- Use `connect` to enable paper trading
- Check `portfolio` regularly to track P&L
- All trades are paper trading (no real money!)
"""
    ).send()


async def analyze_stock(ticker: str):
    """Analyze a stock using TradingAgents."""
    global ta_graph

    # Show loading message
    msg = cl.Message(content=f"🔍 Analyzing **{ticker}** with TradingAgents...\n\nThis may take 1-2 minutes...")
    await msg.send()

    try:
        # Initialize TradingAgents if needed
        if ta_graph is None:
            config = cl.user_session.get("config")
            ta_graph = TradingAgentsGraph(
                selected_analysts=["market", "fundamentals", "news"],
                config=config
            )

        # Run analysis
        trade_date = datetime.now().strftime("%Y-%m-%d")
        final_state, signal = ta_graph.propagate(ticker, trade_date)

        # Format results
        result = f"""# 📊 Analysis Complete: {ticker}

## 🎯 Trading Signal: **{signal}**

### Market Analysis
{final_state.get('market_report', 'No market data available')[:500]}...

### Fundamentals Analysis
{final_state.get('fundamentals_report', 'No fundamentals data available')[:500]}...

### News Sentiment
{final_state.get('news_report', 'No news data available')[:500]}...

### Investment Decision
{final_state.get('trader_investment_plan', 'No decision available')[:500]}...

---

**Recommendation:** {signal}

Would you like to execute this signal? Use:
- `buy {ticker} <quantity>` if signal is BUY
- `sell {ticker} <quantity>` if signal is SELL
"""

        await cl.Message(content=result).send()

        # Store analysis in session
        cl.user_session.set("last_analysis", {
            "ticker": ticker,
            "signal": signal,
            "state": final_state
        })

    except Exception as e:
        await cl.Message(
            content=f"❌ Analysis failed: {str(e)}\n\nThis might be due to:\n- API quota limits\n- Network issues\n- Invalid ticker\n\nPlease try again or check your configuration."
        ).send()


async def connect_broker():
    """Connect to paper trading broker."""
    global broker

    if cl.user_session.get("broker_connected"):
        await cl.Message(content="✓ Already connected to Alpaca paper trading!").send()
        return

    msg = cl.Message(content="🔌 Connecting to Alpaca paper trading...")
    await msg.send()

    try:
        broker = AlpacaBroker(paper_trading=True)
        broker.connect()

        account = broker.get_account()

        cl.user_session.set("broker_connected", True)

        await cl.Message(
            content=f"""✓ Connected to Alpaca Paper Trading!

**Account:** {account.account_number}
**Cash:** ${account.cash:,.2f}
**Buying Power:** ${account.buying_power:,.2f}
**Portfolio Value:** ${account.portfolio_value:,.2f}

You can now execute trades!
"""
        ).send()

    except Exception as e:
        await cl.Message(
            content=f"""❌ Connection failed: {str(e)}

**Setup Required:**
1. Sign up at https://alpaca.markets
2. Get your API keys
3. Add to `.env`:
   ```
   ALPACA_API_KEY=your_key
   ALPACA_SECRET_KEY=your_secret
   ALPACA_PAPER_TRADING=true
   ```
4. Restart the app
"""
        ).send()


async def show_account():
    """Show account information."""
    global broker

    if not broker or not cl.user_session.get("broker_connected"):
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    try:
        account = broker.get_account()

        await cl.Message(
            content=f"""# 💰 Account Status

**Account Number:** {account.account_number}
**Cash Available:** ${account.cash:,.2f}
**Buying Power:** ${account.buying_power:,.2f}
**Portfolio Value:** ${account.portfolio_value:,.2f}
**Total Equity:** ${account.equity:,.2f}

**Session P&L:** ${account.equity - account.last_equity:,.2f}

Type `portfolio` to see your positions.
"""
        ).send()

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()


async def show_portfolio():
    """Show current positions."""
    global broker

    if not broker or not cl.user_session.get("broker_connected"):
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    try:
        positions = broker.get_positions()

        if not positions:
            await cl.Message(content="📭 No positions currently held.").send()
            return

        result = "# 📈 Current Positions\n\n"
        total_value = Decimal("0")
        total_pnl = Decimal("0")

        for pos in positions:
            result += f"""## {pos.symbol}
- **Quantity:** {pos.quantity} shares
- **Avg Cost:** ${pos.avg_entry_price:.2f}
- **Current Price:** ${pos.current_price:.2f}
- **Market Value:** ${pos.market_value:,.2f}
- **P&L:** ${pos.unrealized_pnl:,.2f} ({pos.unrealized_pnl_percent:.2%})

"""
            total_value += pos.market_value
            total_pnl += pos.unrealized_pnl

        result += f"""---
**Total Position Value:** ${total_value:,.2f}
**Total Unrealized P&L:** ${total_pnl:,.2f}
"""

        await cl.Message(content=result).send()

    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()


async def execute_buy(ticker: str, quantity: Decimal):
    """Execute a buy order."""
    global broker

    if not broker or not cl.user_session.get("broker_connected"):
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    msg = cl.Message(content=f"🔄 Placing buy order for {quantity} shares of {ticker}...")
    await msg.send()

    try:
        order = broker.buy_market(ticker, quantity)

        await cl.Message(
            content=f"""✓ Buy order placed successfully!

**Order ID:** {order.order_id}
**Symbol:** {order.symbol}
**Quantity:** {order.quantity}
**Status:** {order.status.value}

Check your `portfolio` to see the position.
"""
        ).send()

    except Exception as e:
        await cl.Message(content=f"❌ Order failed: {str(e)}").send()


async def execute_sell(ticker: str, quantity: Decimal):
    """Execute a sell order."""
    global broker

    if not broker or not cl.user_session.get("broker_connected"):
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    msg = cl.Message(content=f"🔄 Placing sell order for {quantity} shares of {ticker}...")
    await msg.send()

    try:
        order = broker.sell_market(ticker, quantity)

        await cl.Message(
            content=f"""✓ Sell order placed successfully!

**Order ID:** {order.order_id}
**Symbol:** {order.symbol}
**Quantity:** {order.quantity}
**Status:** {order.status.value}

Check your `portfolio` to see updated positions.
"""
        ).send()

    except Exception as e:
        await cl.Message(content=f"❌ Order failed: {str(e)}").send()


async def show_settings():
    """Show current settings."""
    config = cl.user_session.get("config")

    await cl.Message(
        content=f"""# ⚙️ Current Settings

**LLM Provider:** {config.get('llm_provider', 'openai')}
**Deep Think Model:** {config.get('deep_think_llm', 'gpt-4o')}
**Quick Think Model:** {config.get('quick_think_llm', 'gpt-4o-mini')}
**Broker Connected:** {cl.user_session.get('broker_connected', False)}

To change LLM provider, use: `provider NAME`

Available providers: openai, anthropic, google
"""
    ).send()


async def set_provider(provider: str):
    """Set LLM provider."""
    global ta_graph

    if provider not in ["openai", "anthropic", "google"]:
        await cl.Message(content="❌ Invalid provider. Choose: openai, anthropic, or google").send()
        return

    config = cl.user_session.get("config")
    config["llm_provider"] = provider

    # Reset TradingAgents to use new provider
    ta_graph = None

    await cl.Message(content=f"✓ LLM provider set to **{provider}**\n\nNext analysis will use this provider.").send()


if __name__ == "__main__":
    print("Run with: chainlit run web_app.py -w")
