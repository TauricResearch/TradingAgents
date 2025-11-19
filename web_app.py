#!/usr/bin/env python3
"""
TradingAgents Web Interface

A beautiful web UI for running TradingAgents analysis and managing trades.

Usage:
    chainlit run web_app.py -w

Then open http://localhost:8000 in your browser!
"""

import chainlit as cl
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
import json
from typing import Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.brokers import AlpacaBroker
from tradingagents.brokers.base import OrderSide, OrderType
from tradingagents.security import validate_ticker

logger = logging.getLogger(__name__)


@cl.on_chat_start
async def start() -> None:
    """
    Initialize the chat session and welcome the user.

    Sets up session state, initializes configuration, and displays
    a welcome message with available commands.

    Session Variables:
        - ta_graph: TradingAgentsGraph instance (lazily initialized)
        - broker: AlpacaBroker instance (lazily initialized)
        - config: Configuration dictionary
        - broker_connected: Boolean connection status

    Note:
        All state is stored in Chainlit's user_session to avoid
        global variables and enable multi-user support.
    """
    logger.info("Chat session started - initializing session state")
    # Initialize session state - NO GLOBAL VARIABLES
    cl.user_session.set("ta_graph", None)
    cl.user_session.set("broker", None)
    cl.user_session.set("config", DEFAULT_CONFIG.copy())
    cl.user_session.set("broker_connected", False)

    logger.debug("Session state initialized")

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


@cl.on_message
async def main(message: cl.Message) -> None:
    """
    Handle incoming chat messages and dispatch to appropriate handlers.

    Parses user input, validates commands, and routes to the corresponding
    async handler function.

    Args:
        message: Chainlit Message object containing user input

    Supported Commands:
        - help: Display available commands
        - analyze TICKER: Analyze stock
        - portfolio: View positions
        - account: View account status
        - connect: Connect to paper trading
        - buy TICKER QTY: Buy shares
        - sell TICKER QTY: Sell shares
        - settings: View settings
        - provider NAME: Change LLM provider

    Note:
        All input is validated to prevent command injection and
        other security issues.
    """
    msg_content = message.content.strip().lower()
    parts = msg_content.split()

    logger.debug("Received message: %s", msg_content)

    if not parts:
        await cl.Message(content="Please enter a command. Type `help` for options.").send()
        return

    command = parts[0]
    logger.info("Processing command: %s", command)

    # Help command
    if command == "help":
        await show_help()

    # Analyze command
    elif command == "analyze":
        if len(parts) < 2:
            await cl.Message(content="Usage: `analyze TICKER`\n\nExample: `analyze AAPL`").send()
            return

        # SECURITY: Validate ticker to prevent command injection
        try:
            ticker = validate_ticker(parts[1])
            logger.info("User requested analysis for ticker: %s", ticker)
            await analyze_stock(ticker)
        except ValueError as e:
            logger.warning("Invalid ticker input: %s", str(e))
            await cl.Message(content=f"❌ Invalid ticker: {e}").send()
            return

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

        # SECURITY: Validate ticker to prevent command injection
        try:
            ticker = validate_ticker(parts[1])
        except ValueError as e:
            await cl.Message(content=f"❌ Invalid ticker: {e}").send()
            return

        # SECURITY: Validate quantity
        try:
            quantity = Decimal(parts[2])
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if quantity > Decimal('100000'):
                raise ValueError("Quantity too large (max 100,000 shares)")
            await execute_buy(ticker, quantity)
        except (ValueError, InvalidOperation) as e:
            await cl.Message(content=f"❌ Invalid quantity: {e}").send()

    # Sell command
    elif command == "sell":
        if len(parts) < 3:
            await cl.Message(content="Usage: `sell TICKER QUANTITY`\n\nExample: `sell AAPL 10`").send()
            return

        # SECURITY: Validate ticker to prevent command injection
        try:
            ticker = validate_ticker(parts[1])
        except ValueError as e:
            await cl.Message(content=f"❌ Invalid ticker: {e}").send()
            return

        # SECURITY: Validate quantity
        try:
            quantity = Decimal(parts[2])
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if quantity > Decimal('100000'):
                raise ValueError("Quantity too large (max 100,000 shares)")
            await execute_sell(ticker, quantity)
        except (ValueError, InvalidOperation) as e:
            await cl.Message(content=f"❌ Invalid quantity: {e}").send()

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


async def show_help() -> None:
    """
    Display help message with all available commands and examples.

    Shows user all supported commands, their syntax, and usage examples.
    """
    logger.debug("Displaying help message")
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


async def analyze_stock(ticker: str) -> None:
    """
    Analyze a stock using TradingAgents multi-agent system.

    Runs market, fundamentals, and news analysis on the specified ticker.
    Uses multiple expert agents to provide comprehensive analysis and
    trading signals.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "NVDA")

    Analysis Includes:
        - Market analysis: Technical indicators and price action
        - Fundamentals analysis: P/E, earnings, growth metrics
        - News sentiment: Recent news sentiment analysis
        - Investment decision: Combined recommendation

    Performance:
        Typical analysis time: 1-2 minutes (network and LLM dependent)

    Note:
        Analysis results are stored in session for reference during
        subsequent trading operations.
    """
    # Get from session instead of global
    ta_graph = cl.user_session.get("ta_graph")

    logger.info("Starting analysis for ticker: %s", ticker)

    # Show loading message
    msg = cl.Message(content=f"🔍 Analyzing **{ticker}** with TradingAgents...\n\nThis may take 1-2 minutes...")
    await msg.send()

    try:
        # Initialize TradingAgents if needed
        if ta_graph is None:
            logger.debug("Initializing TradingAgentsGraph for first time")
            config = cl.user_session.get("config")
            ta_graph = TradingAgentsGraph(
                selected_analysts=["market", "fundamentals", "news"],
                config=config
            )
            # Store in session
            cl.user_session.set("ta_graph", ta_graph)

        # Run analysis
        trade_date = datetime.now().strftime("%Y-%m-%d")
        logger.debug("Running analysis for %s on %s", ticker, trade_date)
        final_state, signal = ta_graph.propagate(ticker, trade_date)
        logger.info("Analysis completed for %s: signal=%s", ticker, signal)

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
        logger.error("Analysis failed for %s: %s", ticker, str(e), exc_info=True)
        await cl.Message(
            content=f"❌ Analysis failed: {str(e)}\n\nThis might be due to:\n- API quota limits\n- Network issues\n- Invalid ticker\n\nPlease try again or check your configuration."
        ).send()


async def connect_broker() -> None:
    """
    Connect to Alpaca paper trading broker.

    Establishes connection to Alpaca paper trading account and verifies
    credentials. Displays account information upon successful connection.

    The broker instance and connection state are stored in the Chainlit
    session for use by subsequent trading operations.

    Requires Environment Variables:
        - ALPACA_API_KEY: Alpaca API key
        - ALPACA_SECRET_KEY: Alpaca secret key

    Example Output:
        Shows account number, cash balance, buying power, and portfolio value.

    Note:
        Paper trading is a simulated trading environment for testing
        without real capital.
    """
    logger.info("User requested broker connection")

    if cl.user_session.get("broker_connected"):
        logger.debug("Broker already connected, skipping connection attempt")
        await cl.Message(content="✓ Already connected to Alpaca paper trading!").send()
        return

    msg = cl.Message(content="🔌 Connecting to Alpaca paper trading...")
    await msg.send()

    try:
        logger.debug("Creating AlpacaBroker instance")
        broker = AlpacaBroker(paper_trading=True)
        broker.connect()

        logger.debug("Fetching account information")
        account = broker.get_account()

        # Store in session
        cl.user_session.set("broker", broker)
        cl.user_session.set("broker_connected", True)

        logger.info("Successfully connected to Alpaca (Account: %s)", account.account_number)

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
        logger.error("Broker connection failed: %s", str(e), exc_info=True)
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


async def show_account() -> None:
    """
    Display current account status and financial metrics.

    Shows cash balance, buying power, portfolio value, and P&L information.
    Requires active broker connection.

    Displayed Information:
        - Account number
        - Available cash
        - Buying power (margin available)
        - Current portfolio value
        - Total equity
        - Session P&L (profit/loss)

    Requires:
        - Broker connection via `connect` command first
    """
    logger.debug("User requested account status")
    broker = cl.user_session.get("broker")

    if not broker or not cl.user_session.get("broker_connected"):
        logger.warning("Account requested but broker not connected")
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    try:
        logger.debug("Fetching account information")
        account = broker.get_account()

        session_pnl = account.equity - account.last_equity
        logger.debug("Account data retrieved: cash=%.2f, bp=%.2f, pnl=%.2f",
                    account.cash, account.buying_power, session_pnl)

        await cl.Message(
            content=f"""# 💰 Account Status

**Account Number:** {account.account_number}
**Cash Available:** ${account.cash:,.2f}
**Buying Power:** ${account.buying_power:,.2f}
**Portfolio Value:** ${account.portfolio_value:,.2f}
**Total Equity:** ${account.equity:,.2f}

**Session P&L:** ${session_pnl:,.2f}

Type `portfolio` to see your positions.
"""
        ).send()

    except Exception as e:
        logger.error("Failed to fetch account: %s", str(e), exc_info=True)
        await cl.Message(content=f"❌ Error: {str(e)}").send()


async def show_portfolio() -> None:
    """
    Display all current positions and portfolio metrics.

    Shows all open positions with quantity, entry price, current price,
    market value, and unrealized P&L for each position.

    Displayed Information per Position:
        - Ticker symbol
        - Quantity held
        - Average entry price
        - Current market price
        - Current market value
        - Unrealized profit/loss (dollars and percentage)

    Summary Totals:
        - Total position value across all holdings
        - Total unrealized P&L across portfolio

    Requires:
        - Broker connection via `connect` command first
    """
    logger.debug("User requested portfolio view")
    broker = cl.user_session.get("broker")

    if not broker or not cl.user_session.get("broker_connected"):
        logger.warning("Portfolio requested but broker not connected")
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    try:
        logger.debug("Fetching positions")
        positions = broker.get_positions()

        if not positions:
            logger.debug("No positions found")
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

        logger.debug("Portfolio retrieved: %d positions, total_value=%.2f, total_pnl=%.2f",
                    len(positions), total_value, total_pnl)

        await cl.Message(content=result).send()

    except Exception as e:
        logger.error("Failed to fetch portfolio: %s", str(e), exc_info=True)
        await cl.Message(content=f"❌ Error: {str(e)}").send()


async def execute_buy(ticker: str, quantity: Decimal) -> None:
    """
    Execute a market buy order for the specified ticker and quantity.

    Places a market buy order at the current market price. Requires
    sufficient buying power in the account.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        quantity: Number of shares to buy (Decimal)

    Error Handling:
        - Validates sufficient buying power
        - Handles connection errors
        - Returns detailed error messages

    Note:
        - Uses market order (executes at current market price)
        - Order status can be checked via `portfolio` command
        - Actual fill price may differ from market price

    Requires:
        - Broker connection via `connect` command first
    """
    logger.info("User requested buy order: %s qty=%s", ticker, quantity)
    broker = cl.user_session.get("broker")

    if not broker or not cl.user_session.get("broker_connected"):
        logger.warning("Buy requested but broker not connected")
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    msg = cl.Message(content=f"🔄 Placing buy order for {quantity} shares of {ticker}...")
    await msg.send()

    try:
        logger.debug("Executing buy order: %s qty=%s", ticker, quantity)
        order = broker.buy_market(ticker, quantity)

        logger.info("Buy order placed successfully: %s qty=%s order_id=%s",
                   ticker, quantity, order.order_id)

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
        logger.error("Buy order failed for %s: %s", ticker, str(e), exc_info=True)
        await cl.Message(content=f"❌ Order failed: {str(e)}").send()


async def execute_sell(ticker: str, quantity: Decimal) -> None:
    """
    Execute a market sell order for the specified ticker and quantity.

    Places a market sell order at the current market price. The account
    must hold at least the specified quantity of the stock.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        quantity: Number of shares to sell (Decimal)

    Error Handling:
        - Validates position exists and has sufficient quantity
        - Handles connection errors
        - Returns detailed error messages

    Note:
        - Uses market order (executes at current market price)
        - Position is closed or reduced based on quantity sold
        - Actual fill price may differ from market price
        - Proceeds are added to cash balance

    Requires:
        - Broker connection via `connect` command first
    """
    logger.info("User requested sell order: %s qty=%s", ticker, quantity)
    broker = cl.user_session.get("broker")

    if not broker or not cl.user_session.get("broker_connected"):
        logger.warning("Sell requested but broker not connected")
        await cl.Message(content="⚠️ Not connected. Use `connect` first!").send()
        return

    msg = cl.Message(content=f"🔄 Placing sell order for {quantity} shares of {ticker}...")
    await msg.send()

    try:
        logger.debug("Executing sell order: %s qty=%s", ticker, quantity)
        order = broker.sell_market(ticker, quantity)

        logger.info("Sell order placed successfully: %s qty=%s order_id=%s",
                   ticker, quantity, order.order_id)

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
        logger.error("Sell order failed for %s: %s", ticker, str(e), exc_info=True)
        await cl.Message(content=f"❌ Order failed: {str(e)}").send()


async def show_settings() -> None:
    """
    Display current application settings and configuration.

    Shows the configured LLM provider, models, and connection status.
    Provides information about how to change settings.

    Displayed Settings:
        - LLM Provider (openai, anthropic, google)
        - Deep thinking model for analysis
        - Quick thinking model for simple tasks
        - Broker connection status
    """
    logger.debug("User requested settings view")
    config = cl.user_session.get("config")
    broker_connected = cl.user_session.get('broker_connected', False)

    logger.debug("Settings: provider=%s, broker_connected=%s",
                config.get('llm_provider', 'openai'), broker_connected)

    await cl.Message(
        content=f"""# ⚙️ Current Settings

**LLM Provider:** {config.get('llm_provider', 'openai')}
**Deep Think Model:** {config.get('deep_think_llm', 'gpt-4o')}
**Quick Think Model:** {config.get('quick_think_llm', 'gpt-4o-mini')}
**Broker Connected:** {broker_connected}

To change LLM provider, use: `provider NAME`

Available providers: openai, anthropic, google
"""
    ).send()


async def set_provider(provider: str) -> None:
    """
    Change the LLM provider for analysis operations.

    Updates the session configuration to use the specified LLM provider.
    Resets the TradingAgents graph to use the new provider for subsequent
    analysis requests.

    Args:
        provider: LLM provider name (openai, anthropic, or google)

    Supported Providers:
        - openai: GPT-4, GPT-4O
        - anthropic: Claude models
        - google: Gemini models

    Note:
        The provider change takes effect on the next analysis command.
    """
    logger.info("User requested provider change: %s", provider)

    if provider not in ["openai", "anthropic", "google"]:
        logger.warning("Invalid provider requested: %s", provider)
        await cl.Message(content="❌ Invalid provider. Choose: openai, anthropic, or google").send()
        return

    config = cl.user_session.get("config")
    config["llm_provider"] = provider

    # Reset TradingAgents to use new provider
    cl.user_session.set("ta_graph", None)

    logger.debug("Provider set to: %s, TradingAgentsGraph reset", provider)

    await cl.Message(content=f"✓ LLM provider set to **{provider}**\n\nNext analysis will use this provider.").send()


if __name__ == "__main__":
    print("Run with: chainlit run web_app.py -w")
