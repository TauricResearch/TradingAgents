#!/usr/bin/env python3
"""
Autonomous Trading System Main Entry Point
==========================================

Run this to start the 24/7 autonomous trading system.
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from autonomous.scheduler import AutonomousScheduler
from autonomous.config.settings import Config


# Global scheduler instance for signal handling
scheduler = None


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    print("\n🛑 Shutdown signal received...")
    if scheduler:
        asyncio.create_task(scheduler.stop())
    sys.exit(0)


async def main():
    """Main entry point"""
    global scheduler

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('autonomous_trader.log'),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)

    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║            🤖 AUTONOMOUS TRADING SYSTEM 🤖                  ║
    ║                                                              ║
    ║    24/7 Market Monitoring | AI-Powered | Multi-Source       ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    # Validate configuration
    if not Config.validate():
        logger.error("Configuration validation failed. Please check your settings.")
        return

    # Display configuration
    print(f"📊 Portfolio: {', '.join(Config.PORTFOLIO_TICKERS)}")
    print(f"👀 Watchlist: {', '.join(Config.WATCHLIST)}")
    print(f"🎯 Mode: {'PAPER TRADING' if Config.PAPER_TRADING else '⚠️ LIVE TRADING'}")
    print(f"💼 Trading: {'ENABLED' if Config.TRADING_ENABLED else 'DISABLED (Monitoring Only)'}")
    print()

    # Confirm before starting
    if not Config.PAPER_TRADING and Config.TRADING_ENABLED:
        response = input("⚠️ WARNING: Live trading is enabled! Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    # Create scheduler
    scheduler = AutonomousScheduler(Config.to_dict())

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start the system
        await scheduler.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        if scheduler:
            await scheduler.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)