"""
24/7 Bot Operation Manager
Production-ready framework for continuous paper trading
"""
import time
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Callable
from pathlib import Path
import json


class BotManager:
    """
    Manages 24/7 bot operation with monitoring and recovery.

    Features:
    - Automatic restart on errors
    - Health monitoring
    - Daily reports
    - Log rotation
    - Graceful shutdown
    """

    def __init__(
        self,
        engine,
        dashboard,
        max_retries: int = 5,
        retry_delay: int = 60,
        health_check_interval: int = 300,  # 5 minutes
        daily_report_time: str = "00:00",
        log_dir: str = "./logs"
    ):
        """
        Initialize bot manager.

        Args:
            engine: PaperTradingEngine instance
            dashboard: PaperTradingDashboard instance
            max_retries: Max restart attempts on error
            retry_delay: Seconds to wait before retry
            health_check_interval: Seconds between health checks
            daily_report_time: Time to generate daily report (HH:MM)
            log_dir: Directory for logs
        """
        self.engine = engine
        self.dashboard = dashboard
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval
        self.daily_report_time = daily_report_time
        self.log_dir = Path(log_dir)

        # State
        self.is_running = False
        self.retry_count = 0
        self.last_health_check = None
        self.last_daily_report = None
        self.start_time = None

        # Setup logging
        self._setup_logging()

        # Register signal handlers
        self._setup_signal_handlers()

    def _setup_logging(self):
        """Setup logging configuration."""
        self.log_dir.mkdir(exist_ok=True)

        log_file = self.log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

        self.logger = logging.getLogger('BotManager')

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {sig}, initiating graceful shutdown...")
        self.stop()
        sys.exit(0)

    def start(self, symbols: list):
        """
        Start bot operation.

        Args:
            symbols: List of trading symbols
        """
        if self.is_running:
            self.logger.warning("Bot already running!")
            return

        self.is_running = True
        self.start_time = datetime.now()
        self.logger.info("="*80)
        self.logger.info("BOT MANAGER STARTED")
        self.logger.info("="*80)
        self.logger.info(f"Symbols: {symbols}")
        self.logger.info(f"Start time: {self.start_time}")

        # Start engine
        self.engine.start(symbols)

        # Main monitoring loop
        self._monitoring_loop()

    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                # Health check
                if self._should_health_check():
                    self._perform_health_check()

                # Daily report
                if self._should_generate_daily_report():
                    self._generate_daily_report()

                # Check if engine is still running
                if not self.engine.is_running and self.is_running:
                    self.logger.error("Engine stopped unexpectedly! Attempting restart...")
                    self._handle_engine_failure()

                # Sleep
                time.sleep(10)

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                self.logger.exception(e)
                self._handle_error()

    def _should_health_check(self) -> bool:
        """Check if health check should be performed."""
        if self.last_health_check is None:
            return True

        elapsed = (datetime.now() - self.last_health_check).total_seconds()
        return elapsed >= self.health_check_interval

    def _perform_health_check(self):
        """Perform health check."""
        self.last_health_check = datetime.now()

        try:
            # Check engine status
            if not self.engine.is_running:
                self.logger.warning("⚠️  Health check: Engine not running!")
                return

            # Check portfolio value
            portfolio_value = self.engine.get_portfolio_value()
            if portfolio_value <= 0:
                self.logger.error("🚨 Health check: Portfolio value is zero!")
                self.stop()
                return

            # Check for excessive loss
            total_return = (portfolio_value - self.engine.initial_capital) / self.engine.initial_capital
            if total_return < -0.50:  # 50% loss
                self.logger.error(f"🚨 Health check: Excessive loss {total_return:.2%}! Stopping bot.")
                self.stop()
                return

            # Log status
            self.logger.info("✓ Health check passed")
            self.logger.info(f"  Portfolio: ${portfolio_value:,.2f} ({total_return:+.2%})")
            self.logger.info(f"  Orders: {len(self.engine.orders)}")
            self.logger.info(f"  Positions: {len(self.engine.positions)}")

            # Reset retry count on successful check
            self.retry_count = 0

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")

    def _should_generate_daily_report(self) -> bool:
        """Check if daily report should be generated."""
        if self.last_daily_report is None:
            # First report after 24 hours
            elapsed = (datetime.now() - self.start_time).total_seconds()
            return elapsed >= 86400  # 24 hours

        # Check if time matches
        now = datetime.now()
        report_hour, report_minute = map(int, self.daily_report_time.split(':'))

        if now.hour == report_hour and now.minute == report_minute:
            # Check if already generated today
            if self.last_daily_report.date() < now.date():
                return True

        return False

    def _generate_daily_report(self):
        """Generate daily performance report."""
        self.last_daily_report = datetime.now()

        self.logger.info("="*80)
        self.logger.info("DAILY REPORT")
        self.logger.info("="*80)

        # Performance report
        self.dashboard.print_performance_report()

        # Export data
        self.dashboard.export_to_csv(
            f"daily_orders_{self.last_daily_report.strftime('%Y%m%d')}.csv"
        )
        self.dashboard.export_portfolio_history(
            f"daily_portfolio_{self.last_daily_report.strftime('%Y%m%d')}.csv"
        )
        self.dashboard.generate_html_report(
            f"daily_dashboard_{self.last_daily_report.strftime('%Y%m%d')}.html"
        )

        self.logger.info("✓ Daily report generated and exported")

    def _handle_engine_failure(self):
        """Handle engine failure with retry logic."""
        if self.retry_count >= self.max_retries:
            self.logger.error(f"Max retries ({self.max_retries}) reached. Stopping bot.")
            self.stop()
            return

        self.retry_count += 1
        self.logger.info(f"Retry {self.retry_count}/{self.max_retries} in {self.retry_delay} seconds...")

        time.sleep(self.retry_delay)

        # Restart engine
        try:
            self.engine.start(self.engine.symbols)
            self.logger.info("✓ Engine restarted successfully")
        except Exception as e:
            self.logger.error(f"Failed to restart engine: {e}")

    def _handle_error(self):
        """Handle general errors."""
        if self.retry_count >= self.max_retries:
            self.logger.error("Too many errors. Stopping bot.")
            self.stop()
            return

        self.retry_count += 1
        self.logger.info(f"Waiting {self.retry_delay} seconds before continuing...")
        time.sleep(self.retry_delay)

    def stop(self):
        """Stop bot operation."""
        if not self.is_running:
            return

        self.logger.info("="*80)
        self.logger.info("STOPPING BOT MANAGER")
        self.logger.info("="*80)

        self.is_running = False

        # Stop engine
        if self.engine.is_running:
            self.engine.stop()

        # Final report
        self._generate_final_report()

        runtime = datetime.now() - self.start_time
        self.logger.info(f"Total runtime: {runtime}")
        self.logger.info("Bot stopped successfully")

    def _generate_final_report(self):
        """Generate final report on shutdown."""
        self.logger.info("\n" + "="*80)
        self.logger.info("FINAL REPORT")
        self.logger.info("="*80)

        self.dashboard.print_performance_report()

        # Export final data
        self.dashboard.export_to_csv("final_orders.csv")
        self.dashboard.export_portfolio_history("final_portfolio.csv")
        self.dashboard.generate_html_report("final_dashboard.html")

    def get_status(self) -> dict:
        """Get current bot status."""
        return {
            'is_running': self.is_running,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'runtime_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'retry_count': self.retry_count,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'last_daily_report': self.last_daily_report.isoformat() if self.last_daily_report else None,
            'engine_running': self.engine.is_running,
            'portfolio_value': self.engine.get_portfolio_value(),
            'total_orders': len(self.engine.orders),
            'open_positions': len(self.engine.positions),
        }
