# TradingAgents: Medium-Term Enhancements (1-5 Days)

**Strategic Features for Competitive Advantage**

---

## 🎯 MEDIUM-TERM ENHANCEMENTS

### 1. Real-Time Alert System
**Value:** Proactive trading opportunities
**Effort:** 2-3 days
**Impact:** Game-changer for active traders

**Use Cases:**
- Price alerts (when NVDA hits $900)
- Signal alerts (when TradingAgents recommends BUY)
- Risk alerts (portfolio drops 5%)
- News alerts (breaking news about held positions)

**Implementation:**

```python
# tradingagents/alerts/alert_system.py
from enum import Enum
from typing import Callable, List, Dict
from dataclasses import dataclass
from datetime import datetime
import smtplib
from twilio.rest import Client
import asyncio

class AlertType(Enum):
    PRICE = "price"
    SIGNAL = "signal"
    RISK = "risk"
    NEWS = "news"
    PORTFOLIO = "portfolio"

class AlertChannel(Enum):
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    PUSH = "push"
    TELEGRAM = "telegram"

@dataclass
class Alert:
    """Alert configuration."""
    id: str
    type: AlertType
    condition: Callable
    channels: List[AlertChannel]
    message_template: str
    enabled: bool = True
    cooldown: int = 300  # seconds between alerts

class AlertManager:
    """Manage trading alerts."""

    def __init__(self, config: Dict):
        self.config = config
        self.alerts: Dict[str, Alert] = {}
        self.last_triggered: Dict[str, datetime] = {}

    def add_alert(self, alert: Alert):
        """Add new alert."""
        self.alerts[alert.id] = alert

    async def check_alerts(self, context: Dict):
        """Check all alerts against current context."""
        for alert_id, alert in self.alerts.items():
            if not alert.enabled:
                continue

            # Check cooldown
            if self._is_in_cooldown(alert_id, alert.cooldown):
                continue

            # Evaluate condition
            try:
                if alert.condition(context):
                    await self._trigger_alert(alert, context)
                    self.last_triggered[alert_id] = datetime.now()
            except Exception as e:
                print(f"Error checking alert {alert_id}: {e}")

    def _is_in_cooldown(self, alert_id: str, cooldown: int) -> bool:
        """Check if alert is in cooldown period."""
        if alert_id not in self.last_triggered:
            return False

        elapsed = (datetime.now() - self.last_triggered[alert_id]).total_seconds()
        return elapsed < cooldown

    async def _trigger_alert(self, alert: Alert, context: Dict):
        """Send alert through configured channels."""
        message = alert.message_template.format(**context)

        tasks = []
        for channel in alert.channels:
            if channel == AlertChannel.EMAIL:
                tasks.append(self._send_email(message))
            elif channel == AlertChannel.SMS:
                tasks.append(self._send_sms(message))
            elif channel == AlertChannel.WEBHOOK:
                tasks.append(self._send_webhook(message, context))
            elif channel == AlertChannel.TELEGRAM:
                tasks.append(self._send_telegram(message))

        await asyncio.gather(*tasks)

    async def _send_email(self, message: str):
        """Send email alert."""
        smtp_server = self.config.get("smtp_server")
        from_email = self.config.get("from_email")
        to_email = self.config.get("alert_email")

        msg = f"Subject: TradingAgents Alert\n\n{message}"

        with smtplib.SMTP(smtp_server, 587) as server:
            server.starttls()
            server.login(from_email, self.config.get("email_password"))
            server.sendmail(from_email, to_email, msg)

    async def _send_sms(self, message: str):
        """Send SMS via Twilio."""
        client = Client(
            self.config.get("twilio_account_sid"),
            self.config.get("twilio_auth_token")
        )

        client.messages.create(
            body=message,
            from_=self.config.get("twilio_from_number"),
            to=self.config.get("alert_phone_number")
        )

    async def _send_webhook(self, message: str, context: Dict):
        """Send webhook notification."""
        import aiohttp
        webhook_url = self.config.get("webhook_url")

        async with aiohttp.ClientSession() as session:
            await session.post(
                webhook_url,
                json={
                    "message": message,
                    "context": context,
                    "timestamp": datetime.now().isoformat()
                }
            )

    async def _send_telegram(self, message: str):
        """Send Telegram message."""
        import aiohttp
        bot_token = self.config.get("telegram_bot_token")
        chat_id = self.config.get("telegram_chat_id")

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        async with aiohttp.ClientSession() as session:
            await session.post(
                url,
                json={"chat_id": chat_id, "text": message}
            )

# Example usage
alert_manager = AlertManager(config)

# Price alert
price_alert = Alert(
    id="nvda_price_900",
    type=AlertType.PRICE,
    condition=lambda ctx: ctx["price"] >= 900,
    channels=[AlertChannel.EMAIL, AlertChannel.SMS],
    message_template="🚨 NVDA hit ${price}! Time to consider your position."
)

# Signal alert
signal_alert = Alert(
    id="buy_signal",
    type=AlertType.SIGNAL,
    condition=lambda ctx: ctx["signal"] == "BUY" and ctx["confidence"] > 0.8,
    channels=[AlertChannel.EMAIL, AlertChannel.TELEGRAM],
    message_template="💰 Strong BUY signal for {ticker}: {confidence:.0%} confidence"
)

# Risk alert
risk_alert = Alert(
    id="portfolio_drawdown",
    type=AlertType.RISK,
    condition=lambda ctx: ctx["drawdown"] > 0.05,
    channels=[AlertChannel.EMAIL, AlertChannel.SMS, AlertChannel.WEBHOOK],
    message_template="⚠️ Portfolio drawdown: {drawdown:.1%}. Review your positions!"
)

alert_manager.add_alert(price_alert)
alert_manager.add_alert(signal_alert)
alert_manager.add_alert(risk_alert)

# Check alerts continuously
async def monitor_loop():
    while True:
        context = {
            "price": get_current_price("NVDA"),
            "signal": get_latest_signal("NVDA"),
            "confidence": get_signal_confidence("NVDA"),
            "drawdown": get_portfolio_drawdown(),
            "ticker": "NVDA"
        }

        await alert_manager.check_alerts(context)
        await asyncio.sleep(60)  # Check every minute
```

**Web UI Integration:**
```python
# Add to web_app.py
@cl.on_message
async def main(message: cl.Message):
    # ...
    elif command == "alert":
        await setup_alert(parts)

async def setup_alert(parts):
    """Setup a new alert."""
    if len(parts) < 4:
        await cl.Message(
            content="Usage: `alert TICKER CONDITION VALUE`\n\n"
            "Examples:\n"
            "- `alert NVDA price 900` - Alert when NVDA hits $900\n"
            "- `alert AAPL buy 0.8` - Alert on BUY signal with 80%+ confidence\n"
            "- `alert portfolio drop 5` - Alert on 5% drawdown"
        ).send()
        return

    ticker = parts[1].upper()
    condition_type = parts[2].lower()
    threshold = float(parts[3])

    # Create alert
    alert = create_alert(ticker, condition_type, threshold)
    alert_manager.add_alert(alert)

    await cl.Message(
        content=f"✅ Alert created!\n\n"
        f"**Ticker:** {ticker}\n"
        f"**Condition:** {condition_type} {threshold}\n"
        f"**Channels:** Email, Telegram\n\n"
        f"You'll be notified when this condition is met."
    ).send()
```

---

### 2. Interactive Broker Integration
**Value:** Access to professional trading
**Effort:** 3-4 days
**Impact:** Opens door to serious traders

**Implementation:**

```python
# tradingagents/brokers/ib_broker.py
from ib_insync import IB, Stock, MarketOrder, LimitOrder
from decimal import Decimal
from .base import BaseBroker, BrokerOrder, BrokerPosition, BrokerAccount

class InteractiveBrokersBroker(BaseBroker):
    """Interactive Brokers integration."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,  # 7497 for paper, 7496 for live
        client_id: int = 1,
        paper_trading: bool = True
    ):
        super().__init__(paper_trading)
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

    def connect(self) -> bool:
        """Connect to IB Gateway or TWS."""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to IB: {e}")

    def disconnect(self) -> None:
        """Disconnect from IB."""
        self.ib.disconnect()
        self.connected = False

    def get_account(self) -> BrokerAccount:
        """Get account information."""
        account_values = self.ib.accountValues()

        cash = Decimal(0)
        equity = Decimal(0)
        buying_power = Decimal(0)

        for value in account_values:
            if value.tag == "CashBalance":
                cash = Decimal(value.value)
            elif value.tag == "NetLiquidation":
                equity = Decimal(value.value)
            elif value.tag == "BuyingPower":
                buying_power = Decimal(value.value)

        return BrokerAccount(
            account_number=self.ib.wrapper.accounts[0],
            cash=cash,
            buying_power=buying_power,
            portfolio_value=equity,
            equity=equity,
            last_equity=equity,
            multiplier=Decimal("1"),
        )

    def get_positions(self) -> List[BrokerPosition]:
        """Get all positions."""
        positions = []

        for position in self.ib.positions():
            current_price = self._get_last_price(position.contract)

            positions.append(BrokerPosition(
                symbol=position.contract.symbol,
                quantity=Decimal(str(position.position)),
                avg_entry_price=Decimal(str(position.avgCost)),
                current_price=current_price,
                market_value=current_price * Decimal(str(position.position)),
                unrealized_pnl=Decimal(str(position.unrealizedPNL)),
                unrealized_pnl_percent=(
                    Decimal(str(position.unrealizedPNL)) /
                    Decimal(str(position.avgCost * position.position))
                ),
                cost_basis=Decimal(str(position.avgCost * position.position)),
            ))

        return positions

    def submit_order(self, order: BrokerOrder) -> BrokerOrder:
        """Submit order to IB."""
        contract = Stock(order.symbol, "SMART", "USD")

        if order.order_type == OrderType.MARKET:
            ib_order = MarketOrder(
                "BUY" if order.side == OrderSide.BUY else "SELL",
                float(order.quantity)
            )
        elif order.order_type == OrderType.LIMIT:
            ib_order = LimitOrder(
                "BUY" if order.side == OrderSide.BUY else "SELL",
                float(order.quantity),
                float(order.limit_price)
            )

        trade = self.ib.placeOrder(contract, ib_order)

        order.order_id = str(trade.order.orderId)
        order.status = self._convert_ib_status(trade.orderStatus.status)

        return order

    def _get_last_price(self, contract) -> Decimal:
        """Get last traded price."""
        ticker = self.ib.reqTickers(contract)[0]
        return Decimal(str(ticker.last))

# Example usage
ib_broker = InteractiveBrokersBroker(
    host="127.0.0.1",
    port=7497,  # Paper trading
    paper_trading=True
)

ib_broker.connect()
account = ib_broker.get_account()
print(f"IB Account: ${account.equity:,.2f}")
```

**Configuration:**
```python
# .env.example
# Interactive Brokers
IB_HOST=127.0.0.1
IB_PORT=7497  # 7497 for paper, 7496 for live
IB_CLIENT_ID=1
```

---

### 3. Advanced Charting System
**Value:** Professional-grade visualization
**Effort:** 3-4 days
**Impact:** Traders love charts

**Implementation using Plotly:**

```python
# tradingagents/visualization/charts.py
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

class TradingCharts:
    """Advanced charting for TradingAgents."""

    @staticmethod
    def create_candlestick_with_signals(
        df: pd.DataFrame,
        signals: pd.DataFrame,
        indicators: Dict = None
    ):
        """Create interactive candlestick chart with trading signals."""

        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=[0.6, 0.2, 0.2],
            subplot_titles=('Price & Signals', 'Volume', 'Indicators')
        )

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )

        # Buy signals
        buy_signals = signals[signals['action'] == 'buy']
        fig.add_trace(
            go.Scatter(
                x=buy_signals.index,
                y=buy_signals['price'],
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=15,
                    color='green'
                ),
                name='Buy Signal'
            ),
            row=1, col=1
        )

        # Sell signals
        sell_signals = signals[signals['action'] == 'sell']
        fig.add_trace(
            go.Scatter(
                x=sell_signals.index,
                y=sell_signals['price'],
                mode='markers',
                marker=dict(
                    symbol='triangle-down',
                    size=15,
                    color='red'
                ),
                name='Sell Signal'
            ),
            row=1, col=1
        )

        # Moving averages
        if indicators and 'sma_20' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=indicators['sma_20'],
                    name='SMA 20',
                    line=dict(color='orange', width=1)
                ),
                row=1, col=1
            )

        if indicators and 'sma_50' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=indicators['sma_50'],
                    name='SMA 50',
                    line=dict(color='blue', width=1)
                ),
                row=1, col=1
            )

        # Volume
        colors = ['red' if close < open else 'green'
                  for close, open in zip(df['close'], df['open'])]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['volume'],
                marker_color=colors,
                name='Volume',
                showlegend=False
            ),
            row=2, col=1
        )

        # RSI
        if indicators and 'rsi' in indicators:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=indicators['rsi'],
                    name='RSI',
                    line=dict(color='purple')
                ),
                row=3, col=1
            )

            # RSI zones
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

        # Layout
        fig.update_layout(
            title='TradingAgents Analysis',
            xaxis_rangeslider_visible=False,
            height=800,
            hovermode='x unified',
            template='plotly_dark'
        )

        fig.update_xaxes(title_text="Date", row=3, col=1)
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Volume", row=2, col=1)
        fig.update_yaxes(title_text="RSI", row=3, col=1)

        return fig

    @staticmethod
    def create_portfolio_dashboard(portfolio_data: Dict):
        """Create comprehensive portfolio dashboard."""

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Portfolio Value Over Time',
                'Position Allocation',
                'P&L by Position',
                'Win Rate Analysis'
            ),
            specs=[
                [{"type": "scatter"}, {"type": "pie"}],
                [{"type": "bar"}, {"type": "bar"}]
            ]
        )

        # Portfolio equity curve
        fig.add_trace(
            go.Scatter(
                x=portfolio_data['dates'],
                y=portfolio_data['equity'],
                mode='lines',
                name='Portfolio Value',
                fill='tozeroy'
            ),
            row=1, col=1
        )

        # Position allocation pie
        fig.add_trace(
            go.Pie(
                labels=portfolio_data['positions']['symbols'],
                values=portfolio_data['positions']['values'],
                name='Allocation'
            ),
            row=1, col=2
        )

        # P&L by position
        colors = ['green' if pnl > 0 else 'red'
                  for pnl in portfolio_data['positions']['pnl']]
        fig.add_trace(
            go.Bar(
                x=portfolio_data['positions']['symbols'],
                y=portfolio_data['positions']['pnl'],
                marker_color=colors,
                name='P&L'
            ),
            row=2, col=1
        )

        # Win rate
        fig.add_trace(
            go.Bar(
                x=['Wins', 'Losses'],
                y=[
                    portfolio_data['wins'],
                    portfolio_data['losses']
                ],
                marker_color=['green', 'red'],
                name='Trades'
            ),
            row=2, col=2
        )

        fig.update_layout(
            height=800,
            showlegend=True,
            template='plotly_dark'
        )

        return fig

# Integration with web UI
@cl.on_message
async def main(message: cl.Message):
    # ...
    elif command == "chart":
        await show_chart(parts)

async def show_chart(parts):
    """Show interactive chart."""
    if len(parts) < 2:
        await cl.Message(content="Usage: `chart TICKER`").send()
        return

    ticker = parts[1].upper()

    # Fetch data
    df = get_stock_data(ticker, days=90)
    signals = get_trading_signals(ticker)
    indicators = calculate_indicators(df)

    # Create chart
    fig = TradingCharts.create_candlestick_with_signals(
        df, signals, indicators
    )

    # Send to user
    await cl.Message(
        content=f"📊 Chart for {ticker}",
        elements=[cl.Plotly(name="chart", figure=fig)]
    ).send()
```

---

### 4. Strategy Backtesting UI
**Value:** Visual strategy optimization
**Effort:** 2-3 days
**Impact:** Makes backtesting accessible

**Implementation:**

```python
# Add to web_app.py
@cl.on_message
async def main(message: cl.Message):
    # ...
    elif command == "backtest":
        await run_backtest_ui(parts)

async def run_backtest_ui(parts):
    """Interactive backtesting interface."""

    if len(parts) < 4:
        await cl.Message(
            content="""# 📊 Backtest Your Strategy

Usage: `backtest TICKER START_DATE END_DATE`

Example:
`backtest NVDA 2023-01-01 2024-01-01`

This will:
1. Run TradingAgents on historical data
2. Show performance metrics
3. Generate interactive charts
4. Compare to buy-and-hold
"""
        ).send()
        return

    ticker = parts[1].upper()
    start_date = parts[2]
    end_date = parts[3]

    # Show progress
    progress_msg = await cl.Message(
        content=f"🔄 Running backtest for {ticker}...\n\n"
        "This may take a few minutes."
    ).send()

    try:
        # Run backtest
        from tradingagents.backtest import backtest_trading_agents

        results = await asyncio.to_thread(
            backtest_trading_agents,
            trading_graph=ta_graph,
            tickers=[ticker],
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0
        )

        # Create visualizations
        equity_fig = create_equity_curve(results)
        metrics_fig = create_metrics_dashboard(results)

        # Send results
        await cl.Message(
            content=f"""# 📊 Backtest Results: {ticker}

## Performance Summary

**Period:** {start_date} to {end_date}

### Returns
- **Total Return:** {results.total_return:.2%}
- **Annualized:** {results.annualized_return:.2%}
- **Benchmark (Buy & Hold):** {results.benchmark_return:.2%}
- **Alpha:** {results.alpha:.2%}

### Risk Metrics
- **Sharpe Ratio:** {results.sharpe_ratio:.2f}
- **Max Drawdown:** {results.max_drawdown:.2%}
- **Volatility:** {results.volatility:.2%}

### Trading Stats
- **Total Trades:** {results.total_trades}
- **Win Rate:** {results.win_rate:.1%}
- **Profit Factor:** {results.profit_factor:.2f}
- **Average Win:** ${results.avg_win:,.2f}
- **Average Loss:** ${results.avg_loss:,.2f}

## Charts
""",
            elements=[
                cl.Plotly(name="equity", figure=equity_fig),
                cl.Plotly(name="metrics", figure=metrics_fig)
            ]
        ).send()

        # Offer to save
        await cl.Message(
            content="💾 Save this report? Type `save report {ticker}_backtest`"
        ).send()

    except Exception as e:
        await cl.Message(
            content=f"❌ Backtest failed: {str(e)}\n\n"
            "Check your date range and ticker symbol."
        ).send()
```

---

### 5. Multi-Ticker Portfolio Mode
**Value:** Diversification support
**Effort:** 2-3 days
**Impact:** Professional portfolio management

**Implementation:**

```python
# tradingagents/portfolio/multi_ticker.py
from typing import List, Dict
import asyncio
from decimal import Decimal

class MultiTickerPortfolio:
    """Manage multiple tickers simultaneously."""

    def __init__(
        self,
        tickers: List[str],
        allocation: Dict[str, float] = None,
        rebalance_frequency: str = "monthly"
    ):
        self.tickers = tickers
        self.allocation = allocation or self._equal_weight()
        self.rebalance_frequency = rebalance_frequency

    def _equal_weight(self) -> Dict[str, float]:
        """Equal weight allocation."""
        weight = 1.0 / len(self.tickers)
        return {ticker: weight for ticker in self.tickers}

    async def analyze_all(self, date: str) -> Dict[str, any]:
        """Analyze all tickers in parallel."""

        tasks = [
            self._analyze_ticker(ticker, date)
            for ticker in self.tickers
        ]

        results = await asyncio.gather(*tasks)

        return {
            ticker: result
            for ticker, result in zip(self.tickers, results)
        }

    async def _analyze_ticker(self, ticker: str, date: str):
        """Analyze single ticker."""
        _, signal = await ta_graph.propagate_async(ticker, date)
        return signal

    def calculate_portfolio_signals(
        self,
        signals: Dict[str, str]
    ) -> Dict[str, Decimal]:
        """
        Calculate position sizes based on signals and allocation.

        Returns:
            Dict mapping ticker to target quantity
        """
        positions = {}

        for ticker, signal in signals.items():
            target_allocation = self.allocation[ticker]

            if signal == "BUY":
                # Increase position to target allocation
                positions[ticker] = self._calculate_target_shares(
                    ticker, target_allocation
                )
            elif signal == "SELL":
                # Reduce position
                positions[ticker] = Decimal(0)
            elif signal == "HOLD":
                # Maintain current position
                positions[ticker] = self._get_current_position(ticker)

        return positions

    def rebalance(self, portfolio_value: Decimal):
        """Rebalance portfolio to target allocations."""
        for ticker, target_pct in self.allocation.items():
            target_value = portfolio_value * Decimal(str(target_pct))
            current_value = self._get_position_value(ticker)

            difference = target_value - current_value

            if abs(difference) > portfolio_value * Decimal("0.05"):  # 5% threshold
                # Need to rebalance
                shares_to_trade = difference / self._get_current_price(ticker)
                yield ticker, shares_to_trade

# Usage in web UI
@cl.on_message
async def main(message: cl.Message):
    # ...
    elif command == "portfolio-analyze":
        await analyze_portfolio(parts)

async def analyze_portfolio(parts):
    """Analyze entire portfolio."""

    # Get user's portfolio
    tickers = ["NVDA", "AAPL", "MSFT", "GOOGL", "TSLA"]  # From config

    await cl.Message(
        content=f"🔍 Analyzing portfolio: {', '.join(tickers)}\n\n"
        "This will take 2-3 minutes..."
    ).send()

    # Analyze all in parallel
    portfolio = MultiTickerPortfolio(tickers)
    signals = await portfolio.analyze_all(date="2024-05-10")

    # Format results
    result = "# 📊 Portfolio Analysis Results\n\n"

    for ticker, signal in signals.items():
        emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "🟡"
        result += f"{emoji} **{ticker}**: {signal}\n"

    result += "\n## Recommendations\n\n"

    # Calculate suggested trades
    positions = portfolio.calculate_portfolio_signals(signals)

    for ticker, target_qty in positions.items():
        current_qty = get_current_position(ticker)
        difference = target_qty - current_qty

        if difference > 0:
            result += f"- Buy {difference} shares of {ticker}\n"
        elif difference < 0:
            result += f"- Sell {abs(difference)} shares of {ticker}\n"

    await cl.Message(content=result).send()
```

---

### 6. Decision History Database
**Value:** Learn from past decisions
**Effort:** 2-3 days
**Impact:** Enables analysis and improvement

**Implementation:**

```python
# tradingagents/history/decision_db.py
import sqlite3
from datetime import datetime
from typing import Dict, List
import json

class DecisionDatabase:
    """Store and analyze trading decisions."""

    def __init__(self, db_path: str = "tradingagents_decisions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL,
                market_price REAL,
                decision_data TEXT,
                analyst_reports TEXT,
                execution_price REAL,
                execution_time TEXT,
                outcome TEXT,
                pnl REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticker_date
            ON decisions(ticker, date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal
            ON decisions(signal)
        """)

        conn.commit()
        conn.close()

    def record_decision(
        self,
        ticker: str,
        date: str,
        signal: str,
        confidence: float,
        market_price: float,
        decision_data: Dict,
        analyst_reports: Dict
    ) -> int:
        """Record a trading decision."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO decisions (
                timestamp, ticker, date, signal, confidence,
                market_price, decision_data, analyst_reports
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            ticker,
            date,
            signal,
            confidence,
            market_price,
            json.dumps(decision_data),
            json.dumps(analyst_reports)
        ))

        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return decision_id

    def update_outcome(
        self,
        decision_id: int,
        execution_price: float,
        execution_time: str,
        outcome: str,
        pnl: float
    ):
        """Update decision outcome."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE decisions
            SET execution_price = ?,
                execution_time = ?,
                outcome = ?,
                pnl = ?
            WHERE id = ?
        """, (execution_price, execution_time, outcome, pnl, decision_id))

        conn.commit()
        conn.close()

    def get_decision_history(
        self,
        ticker: str = None,
        signal: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query decision history."""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM decisions WHERE 1=1"
        params = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)

        if signal:
            query += " AND signal = ?"
            params.append(signal)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        return [dict(row) for row in rows]

    def analyze_performance(self, ticker: str = None) -> Dict:
        """Analyze decision performance."""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                signal,
                COUNT(*) as total,
                AVG(confidence) as avg_confidence,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                AVG(pnl) as avg_pnl,
                SUM(pnl) as total_pnl
            FROM decisions
            WHERE outcome IS NOT NULL
        """

        if ticker:
            query += " AND ticker = ?"
            cursor.execute(query + " GROUP BY signal", (ticker,))
        else:
            cursor.execute(query + " GROUP BY signal")

        results = cursor.fetchall()
        conn.close()

        analysis = {}
        for row in results:
            signal = row[0]
            analysis[signal] = {
                "total": row[1],
                "avg_confidence": row[2],
                "wins": row[3],
                "losses": row[4],
                "win_rate": row[3] / row[1] if row[1] > 0 else 0,
                "avg_pnl": row[5],
                "total_pnl": row[6]
            }

        return analysis

# Integration
decision_db = DecisionDatabase()

# After analysis
decision_id = decision_db.record_decision(
    ticker="NVDA",
    date="2024-05-10",
    signal="BUY",
    confidence=0.85,
    market_price=880.50,
    decision_data=final_state,
    analyst_reports={
        "fundamentals": fundamentals_report,
        "news": news_report,
        "technical": technical_report
    }
)

# After trade execution
decision_db.update_outcome(
    decision_id=decision_id,
    execution_price=881.25,
    execution_time="2024-05-10T10:30:00",
    outcome="win",  # or "loss"
    pnl=245.00
)

# Analyze performance
performance = decision_db.analyze_performance(ticker="NVDA")
print(f"NVDA BUY signals win rate: {performance['BUY']['win_rate']:.1%}")
```

---

*Continued in STRATEGIC_INITIATIVES.md →*
