"""
Scheduler
=========

Orchestrates periodic tasks for the autonomous trading system.
Uses APScheduler for task scheduling and asyncio for async execution.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, time, timedelta
import os
import sys

# Add parent directory to path for imports
sys.path.append('..')

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .ibkr_connector import IBKRConnector
from .data_aggregator import DataAggregator
from .signal_processor import SignalProcessor
from .alert_engine import AlertEngine, AlertType, AlertPriority

logger = logging.getLogger(__name__)


class AutonomousScheduler:
    """
    Main scheduler for the autonomous trading system
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the scheduler

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.scheduler = AsyncIOScheduler()

        # Initialize components
        self.ibkr = IBKRConnector(
            host=self.config.get('ibkr_host', '127.0.0.1'),
            port=self.config.get('ibkr_port', 7497),
            client_id=self.config.get('ibkr_client_id', 1)
        )

        self.data_agg = DataAggregator(config)
        self.signal_processor = SignalProcessor(self.ibkr, self.data_agg, config)
        self.alert_engine = AlertEngine(config)

        # Track system state
        self.is_running = False
        self.last_portfolio_check = None
        self.last_market_scan = None
        self.trading_enabled = self.config.get('trading_enabled', False)

        # Your portfolio tickers
        self.portfolio_tickers = ["AVGO", "MSFT", "MU", "NVDA", "TSM"]
        self.watchlist = self.config.get('watchlist', ["AAPL", "TSLA", "META", "GOOGL"])

    async def initialize(self) -> bool:
        """
        Initialize connections and verify system readiness

        Returns:
            True if initialization successful
        """
        try:
            # Connect to IBKR
            logger.info("Connecting to IBKR...")
            connected = await self.ibkr.connect()

            if not connected:
                logger.error("Failed to connect to IBKR. Make sure TWS/Gateway is running.")
                await self.alert_engine.send_alert(
                    title="System Initialization Failed",
                    message="Could not connect to IBKR. Check TWS/Gateway.",
                    alert_type=AlertType.SYSTEM,
                    priority=AlertPriority.CRITICAL
                )
                return False

            # Initial portfolio sync
            logger.info("Syncing portfolio...")
            await self.ibkr.sync_portfolio()

            # Send startup notification
            await self.alert_engine.send_alert(
                title="🚀 Autonomous Trading System Started",
                message=f"System initialized successfully.\nMonitoring {len(self.portfolio_tickers)} positions.",
                alert_type=AlertType.SYSTEM,
                priority=AlertPriority.INFO
            )

            self.is_running = True
            return True

        except Exception as e:
            logger.error(f"Initialization error: {e}")
            return False

    def setup_schedules(self):
        """Configure all scheduled tasks"""

        # Portfolio monitoring - every 5 minutes
        self.scheduler.add_job(
            self.monitor_portfolio,
            IntervalTrigger(minutes=5),
            id='portfolio_monitor',
            name='Portfolio Monitor',
            misfire_grace_time=60
        )

        # Market scanning - every 15 minutes during market hours
        self.scheduler.add_job(
            self.scan_markets,
            IntervalTrigger(minutes=15),
            id='market_scanner',
            name='Market Scanner',
            misfire_grace_time=120
        )

        # Congressional trades check - every hour
        self.scheduler.add_job(
            self.check_congressional_trades,
            IntervalTrigger(hours=1),
            id='congressional_monitor',
            name='Congressional Trade Monitor',
            misfire_grace_time=300
        )

        # News monitoring - every 30 minutes
        self.scheduler.add_job(
            self.monitor_news,
            IntervalTrigger(minutes=30),
            id='news_monitor',
            name='News Monitor',
            misfire_grace_time=120
        )

        # Daily portfolio summary - at 4:30 PM ET (after market close)
        self.scheduler.add_job(
            self.daily_summary,
            CronTrigger(hour=16, minute=30),
            id='daily_summary',
            name='Daily Summary',
            misfire_grace_time=300
        )

        # Risk check - every 30 minutes during market hours
        self.scheduler.add_job(
            self.check_risk,
            IntervalTrigger(minutes=30),
            id='risk_monitor',
            name='Risk Monitor',
            misfire_grace_time=120
        )

        # Pre-market check - at 8:30 AM ET
        self.scheduler.add_job(
            self.premarket_check,
            CronTrigger(hour=8, minute=30),
            id='premarket_check',
            name='Pre-Market Check',
            misfire_grace_time=300
        )

        logger.info(f"Scheduled {len(self.scheduler.get_jobs())} jobs")

    async def monitor_portfolio(self):
        """Monitor portfolio positions and P&L"""
        if not self.is_running:
            return

        try:
            logger.info("Running portfolio monitor...")

            # Sync positions
            positions = await self.ibkr.sync_portfolio()

            if not positions:
                logger.warning("No positions found")
                return

            # Check for significant changes
            for ticker, position in positions.items():
                # Alert on large losses
                if position.percent_change < -5:
                    await self.alert_engine.send_alert(
                        title=f"⚠️ Risk Alert: {ticker}",
                        message=f"{ticker} is down {abs(position.percent_change):.1f}%\n"
                               f"Current: ${position.current_price:.2f}\n"
                               f"P&L: ${position.unrealized_pnl:,.2f}",
                        alert_type=AlertType.RISK_WARNING,
                        priority=AlertPriority.HIGH,
                        data={'ticker': ticker, 'loss_percent': position.percent_change}
                    )

                # Alert on large gains
                elif position.percent_change > 10:
                    await self.alert_engine.send_alert(
                        title=f"📈 Profit Alert: {ticker}",
                        message=f"{ticker} is up {position.percent_change:.1f}%\n"
                               f"Consider taking profits.\n"
                               f"P&L: ${position.unrealized_pnl:,.2f}",
                        alert_type=AlertType.PORTFOLIO_UPDATE,
                        priority=AlertPriority.MEDIUM,
                        data={'ticker': ticker, 'gain_percent': position.percent_change}
                    )

            self.last_portfolio_check = datetime.now()

        except Exception as e:
            logger.error(f"Portfolio monitor error: {e}")

    async def scan_markets(self):
        """Scan markets for trading opportunities"""
        if not self.is_running:
            return

        try:
            logger.info("Running market scanner...")

            # Get all tickers to scan
            all_tickers = list(set(self.portfolio_tickers + self.watchlist))

            # Aggregate signals
            await self.data_agg.aggregate_signals(all_tickers)

            # Process signals
            recommendations = []
            for ticker in all_tickers:
                rec = await self.signal_processor.process_signals(ticker)
                if rec and rec.action != 'HOLD' and rec.confidence > 70:
                    recommendations.append(rec)

            # Send top recommendations
            recommendations.sort(key=lambda x: x.confidence, reverse=True)

            for rec in recommendations[:3]:  # Top 3 opportunities
                await self.alert_engine.send_trading_signal(rec)
                await asyncio.sleep(1)  # Avoid flooding

            self.last_market_scan = datetime.now()
            logger.info(f"Found {len(recommendations)} opportunities")

        except Exception as e:
            logger.error(f"Market scanner error: {e}")

    async def check_congressional_trades(self):
        """Check for new congressional trades"""
        if not self.is_running:
            return

        try:
            logger.info("Checking congressional trades...")

            # Get recent trades
            trades = await self.data_agg.fetch_congressional_trades(
                self.portfolio_tickers,
                days_back=2
            )

            # Alert on trades matching portfolio
            for trade in trades:
                if trade.ticker in self.portfolio_tickers:
                    emoji = "🟢" if 'purchase' in trade.action else "🔴"
                    await self.alert_engine.send_alert(
                        title=f"🏛️ Congressional Trade: {trade.ticker}",
                        message=f"{emoji} {trade.politician} ({trade.party}-{trade.state}) "
                               f"{trade.action} {trade.ticker}\n"
                               f"Amount: {trade.amount_range}\n"
                               f"Filed: {trade.filing_date.strftime('%Y-%m-%d')}",
                        alert_type=AlertType.CONGRESSIONAL_TRADE,
                        priority=AlertPriority.HIGH,
                        data={
                            'ticker': trade.ticker,
                            'politician': trade.politician,
                            'action': trade.action
                        }
                    )

        except Exception as e:
            logger.error(f"Congressional trade check error: {e}")

    async def monitor_news(self):
        """Monitor news for portfolio companies"""
        if not self.is_running:
            return

        try:
            logger.info("Monitoring news...")

            for ticker in self.portfolio_tickers[:3]:  # Limit to avoid rate limits
                sentiment = await self.data_agg.fetch_market_sentiment(ticker)

                # Alert on strong sentiment
                if sentiment['sentiment_score'] > 0.5:
                    await self.alert_engine.send_alert(
                        title=f"📰 Positive News: {ticker}",
                        message=f"Strong positive sentiment detected for {ticker}\n"
                               f"Sentiment Score: {sentiment['sentiment_score']:.2f}",
                        alert_type=AlertType.MARKET_MOVE,
                        priority=AlertPriority.MEDIUM,
                        data=sentiment
                    )

                await asyncio.sleep(2)  # Rate limiting

        except Exception as e:
            logger.error(f"News monitor error: {e}")

    async def check_risk(self):
        """Monitor portfolio risk levels"""
        if not self.is_running:
            return

        try:
            logger.info("Checking portfolio risk...")

            # Get account info
            account_info = await self.ibkr.get_account_info()

            if not account_info:
                return

            portfolio_summary = self.ibkr.get_portfolio_summary()

            # Check daily P&L
            if account_info.day_pnl < -1000:  # Lost more than $1000 today
                await self.alert_engine.send_alert(
                    title="⚠️ Daily Loss Alert",
                    message=f"Today's P&L: ${account_info.day_pnl:,.2f}\n"
                           f"Consider reducing risk or stopping for the day.",
                    alert_type=AlertType.RISK_WARNING,
                    priority=AlertPriority.HIGH
                )

            # Check concentration risk
            if portfolio_summary['positions']:
                max_position = max(portfolio_summary['positions'],
                                 key=lambda x: x['value'])
                concentration = max_position['value'] / portfolio_summary['total_value']

                if concentration > 0.30:  # More than 30% in one position
                    await self.alert_engine.send_alert(
                        title=f"⚠️ Concentration Risk: {max_position['ticker']}",
                        message=f"{max_position['ticker']} is {concentration:.1%} of portfolio\n"
                               f"Consider rebalancing to reduce risk.",
                        alert_type=AlertType.RISK_WARNING,
                        priority=AlertPriority.MEDIUM
                    )

        except Exception as e:
            logger.error(f"Risk check error: {e}")

    async def premarket_check(self):
        """Pre-market preparation and alerts"""
        if not self.is_running:
            return

        try:
            logger.info("Running pre-market check...")

            # Check earnings today
            earnings = await self.data_agg.fetch_earnings_calendar(
                self.portfolio_tickers,
                days_ahead=1
            )

            for event in earnings:
                await self.alert_engine.send_alert(
                    title=f"📊 Earnings Today: {event.ticker}",
                    message=f"{event.ticker} reports earnings today\n"
                           f"EPS Estimate: ${event.eps_estimate:.2f}",
                    alert_type=AlertType.EARNINGS,
                    priority=AlertPriority.HIGH
                )

            # Run full market scan
            await self.scan_markets()

        except Exception as e:
            logger.error(f"Pre-market check error: {e}")

    async def daily_summary(self):
        """Generate and send daily portfolio summary"""
        if not self.is_running:
            return

        try:
            logger.info("Generating daily summary...")

            # Get portfolio summary
            portfolio_summary = self.ibkr.get_portfolio_summary()
            account_info = await self.ibkr.get_account_info()

            if portfolio_summary and account_info:
                await self.alert_engine.send_portfolio_summary(portfolio_summary)

                # Additional daily stats
                message = f"""
📊 **Daily Trading Summary**

Account Value: ${account_info.net_liquidation:,.2f}
Today's P&L: ${account_info.day_pnl:+,.2f}
Buying Power: ${account_info.buying_power:,.2f}

Top Opportunities Found: {len(self.signal_processor.recommendations)}
Alerts Sent Today: {len(self.alert_engine.sent_alerts)}

System Status: ✅ All systems operational
"""
                await self.alert_engine.send_alert(
                    title="📈 End of Day Report",
                    message=message,
                    alert_type=AlertType.PORTFOLIO_UPDATE,
                    priority=AlertPriority.INFO
                )

        except Exception as e:
            logger.error(f"Daily summary error: {e}")

    async def start(self):
        """Start the autonomous trading system"""
        logger.info("Starting Autonomous Trading System...")

        # Initialize
        if not await self.initialize():
            logger.error("Failed to initialize system")
            return

        # Setup schedules
        self.setup_schedules()

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")

        # Run initial scans
        await self.monitor_portfolio()
        await self.scan_markets()

        logger.info("Autonomous Trading System is running")

        # Keep running
        try:
            while self.is_running:
                await asyncio.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            await self.stop()

    async def stop(self):
        """Stop the autonomous trading system"""
        logger.info("Stopping Autonomous Trading System...")

        self.is_running = False

        # Shutdown scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # Disconnect from IBKR
        await self.ibkr.disconnect()

        # Send shutdown notification
        await self.alert_engine.send_alert(
            title="🛑 System Shutdown",
            message="Autonomous Trading System stopped",
            alert_type=AlertType.SYSTEM,
            priority=AlertPriority.INFO
        )

        logger.info("System stopped")


# Main entry point
async def main():
    """Main entry point for the autonomous system"""

    # Load configuration
    config = {
        # IBKR settings
        'ibkr_host': os.getenv('IBKR_HOST', '127.0.0.1'),
        'ibkr_port': int(os.getenv('IBKR_PORT', 7497)),  # 7497 for paper, 7496 for live
        'ibkr_client_id': int(os.getenv('IBKR_CLIENT_ID', 1)),

        # API keys
        'quiver_api_key': os.getenv('QUIVER_API_KEY'),
        'alpha_vantage_api_key': os.getenv('ALPHA_VANTAGE_API_KEY'),
        'openai_api_key': os.getenv('OPENAI_API_KEY'),

        # Notification settings
        'discord_webhook_url': os.getenv('DISCORD_WEBHOOK_URL'),
        'telegram_bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID'),

        # Trading settings
        'trading_enabled': os.getenv('TRADING_ENABLED', 'false').lower() == 'true',
        'watchlist': ['AAPL', 'TSLA', 'META', 'GOOGL', 'AMZN']
    }

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and start scheduler
    scheduler = AutonomousScheduler(config)
    await scheduler.start()


if __name__ == "__main__":
    asyncio.run(main())