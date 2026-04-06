#!/usr/bin/env python3
"""
Position Updater Script

This script:
1. Fetches current prices for all open positions
2. Updates positions with latest price data
3. Calculates return % for each position
4. Can be run manually or via cron for continuous monitoring

Usage:
    python scripts/update_positions.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime

import yfinance as yf

from tradingagents.dataflows.discovery.performance.position_tracker import PositionTracker
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_current_prices(tickers):
    """
    Fetch current prices for given tickers using yfinance.

    Handles both single and multiple tickers with appropriate error handling.

    Args:
        tickers: List of ticker symbols

    Returns:
        Dictionary mapping ticker to current price (or None if fetch failed)
    """
    prices = {}

    if not tickers:
        return prices

    # Try to download all tickers at once for efficiency
    try:
        if len(tickers) == 1:
            # Single ticker - yfinance returns Series instead of DataFrame
            ticker = tickers[0]
            data = yf.download(
                ticker,
                period="1d",
                progress=False,
                auto_adjust=True,
            )

            if not data.empty:
                # For single ticker with period='1d', get the latest close
                prices[ticker] = float(data["Close"].iloc[-1])
            else:
                logger.warning(f"Could not fetch data for {ticker}")
                prices[ticker] = None

        else:
            # Multiple tickers - yfinance returns DataFrame with MultiIndex
            data = yf.download(
                tickers,
                period="1d",
                progress=False,
                auto_adjust=True,
            )

            if not data.empty:
                # Get the latest close for each ticker
                if len(tickers) > 1:
                    for ticker in tickers:
                        if ticker in data.columns:
                            close_price = data[ticker]["Close"]
                            if not close_price.empty:
                                prices[ticker] = float(close_price.iloc[-1])
                            else:
                                prices[ticker] = None
                        else:
                            prices[ticker] = None
                else:
                    # Edge case: single ticker in batch download
                    if "Close" in data.columns:
                        prices[tickers[0]] = float(data["Close"].iloc[-1])
                    else:
                        prices[tickers[0]] = None
            else:
                for ticker in tickers:
                    prices[ticker] = None

    except Exception as e:
        logger.warning(f"Batch download failed: {e}")
        # Fall back to per-ticker download
        for ticker in tickers:
            try:
                data = yf.download(
                    ticker,
                    period="1d",
                    progress=False,
                    auto_adjust=True,
                )
                if not data.empty:
                    prices[ticker] = float(data["Close"].iloc[-1])
                else:
                    prices[ticker] = None
            except Exception as e:
                logger.error(f"Failed to fetch price for {ticker}: {e}")
                prices[ticker] = None

    return prices


def main():
    """
    Main function to update all open positions with current prices.

    Process:
    1. Initialize PositionTracker
    2. Load all open positions
    3. Get unique tickers
    4. Fetch current prices via yfinance
    5. Update each position with new price
    6. Save updated positions
    7. Print progress messages
    """
    logger.info("""
╔══════════════════════════════════════════════════════════════╗
║         TradingAgents - Position Updater                    ║
╚══════════════════════════════════════════════════════════════╝""".strip())

    # Initialize position tracker
    tracker = PositionTracker(data_dir="data")

    # Load all open positions
    logger.info("📂 Loading open positions...")
    positions = tracker.load_all_open_positions()

    if not positions:
        logger.info("✅ No open positions to update.")
        return

    logger.info(f"✅ Found {len(positions)} open position(s)")

    # Get unique tickers
    tickers = list({pos["ticker"] for pos in positions})
    logger.info(f"📊 Fetching current prices for {len(tickers)} unique ticker(s)...")
    logger.info(f"Tickers: {', '.join(sorted(tickers))}")

    # Fetch current prices
    prices = fetch_current_prices(tickers)

    # Update positions and track results
    updated_count = 0
    failed_count = 0

    for position in positions:
        ticker = position["ticker"]
        current_price = prices.get(ticker)

        if current_price is None:
            logger.error(f"{ticker}: Failed to fetch price - position not updated")
            failed_count += 1
            continue

        # Update position with new price
        entry_price = position["entry_price"]
        return_pct = ((current_price - entry_price) / entry_price) * 100

        # Update the position
        position = tracker.update_position_price(position, current_price)

        # Save the updated position
        tracker.save_position(position)

        # Log progress
        return_symbol = "📈" if return_pct >= 0 else "📉"
        logger.info(
            f"{return_symbol} {ticker:6} | Price: ${current_price:8.2f} | Return: {return_pct:+7.2f}%"
        )
        updated_count += 1

    # Summary
    logger.info("=" * 60)
    logger.info("✅ Update Summary:")
    logger.info(f"Updated: {updated_count}/{len(positions)} positions")
    logger.info(f"Failed:  {failed_count}/{len(positions)} positions")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 60)

    if updated_count > 0:
        logger.info("🎉 Position update complete!")
    else:
        logger.warning("No positions were successfully updated.")


if __name__ == "__main__":
    main()
