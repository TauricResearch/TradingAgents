"""
Data Aggregator
===============

Aggregates data from multiple sources including:
- Congressional trades (QuiverQuant)
- Market data (yfinance, Alpha Vantage)
- News sentiment
- Insider trading
- Earnings calendars
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import os
import json
import aiohttp

# Import existing TradingAgents data tools
import sys
sys.path.append('..')
from tradingagents.dataflows.y_finance import YfinanceInterface
from tradingagents.dataflows.alpha_vantage_news import AlphaVantageNewsInterface

# Optional imports
try:
    import quiverquant
    QUIVER_AVAILABLE = True
except ImportError:
    QUIVER_AVAILABLE = False
    print("QuiverQuant not installed. Install with: pip install quiverquant")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CongressionalTrade:
    """Represents a congressional trade"""
    politician: str
    ticker: str
    action: str  # 'purchase' or 'sale'
    amount_range: str
    transaction_date: datetime
    filing_date: datetime
    party: str
    state: str
    chamber: str  # 'house' or 'senate'


@dataclass
class InsiderTrade:
    """Represents an insider trade"""
    insider_name: str
    ticker: str
    action: str  # 'Buy' or 'Sell'
    shares: int
    value: float
    transaction_date: datetime
    position: str  # CEO, CFO, Director, etc.


@dataclass
class EarningsEvent:
    """Represents an earnings event"""
    ticker: str
    earnings_date: datetime
    eps_estimate: float
    eps_actual: Optional[float]
    revenue_estimate: float
    revenue_actual: Optional[float]
    surprise_percent: Optional[float]


@dataclass
class MarketSignal:
    """Aggregated market signal"""
    ticker: str
    signal_type: str  # 'congressional', 'insider', 'earnings', 'technical'
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0-100
    data: Dict[str, Any]
    timestamp: datetime


class DataAggregator:
    """
    Aggregates data from multiple sources for trading decisions
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize data aggregator

        Args:
            config: Configuration dictionary with API keys
        """
        self.config = config or {}
        self.quiver_client = None
        self.congressional_trades: List[CongressionalTrade] = []
        self.insider_trades: List[InsiderTrade] = []
        self.earnings_calendar: List[EarningsEvent] = []
        self.market_signals: List[MarketSignal] = []

        # Initialize QuiverQuant if available
        if QUIVER_AVAILABLE and self.config.get('quiver_api_key'):
            self.quiver_client = quiverquant.quiver(self.config['quiver_api_key'])

    async def fetch_congressional_trades(self,
                                       tickers: Optional[List[str]] = None,
                                       days_back: int = 30) -> List[CongressionalTrade]:
        """
        Fetch recent congressional trades

        Args:
            tickers: List of tickers to filter (None for all)
            days_back: Number of days to look back

        Returns:
            List of congressional trades
        """
        trades = []

        if not self.quiver_client:
            logger.warning("QuiverQuant not configured, using mock data")
            # Return mock data for demonstration
            return self._get_mock_congressional_trades(tickers)

        try:
            # Fetch congressional trading data
            df = self.quiver_client.congress_trading()

            if df is not None and not df.empty:
                # Filter by date
                cutoff_date = datetime.now() - timedelta(days=days_back)
                df['TransactionDate'] = pd.to_datetime(df['TransactionDate'])
                df = df[df['TransactionDate'] >= cutoff_date]

                # Filter by tickers if provided
                if tickers:
                    df = df[df['Ticker'].isin(tickers)]

                # Convert to CongressionalTrade objects
                for _, row in df.iterrows():
                    trade = CongressionalTrade(
                        politician=row.get('Representative', 'Unknown'),
                        ticker=row.get('Ticker', ''),
                        action=row.get('Transaction', 'Unknown').lower(),
                        amount_range=row.get('Range', 'Unknown'),
                        transaction_date=row.get('TransactionDate'),
                        filing_date=row.get('FilingDate', row.get('TransactionDate')),
                        party=row.get('Party', 'Unknown'),
                        state=row.get('State', 'Unknown'),
                        chamber=row.get('Chamber', 'house')
                    )
                    trades.append(trade)

            self.congressional_trades = trades
            logger.info(f"Fetched {len(trades)} congressional trades")

        except Exception as e:
            logger.error(f"Error fetching congressional trades: {e}")
            trades = self._get_mock_congressional_trades(tickers)

        return trades

    def _get_mock_congressional_trades(self, tickers: Optional[List[str]] = None) -> List[CongressionalTrade]:
        """Get mock congressional trades for testing"""
        mock_trades = [
            CongressionalTrade(
                politician="Nancy Pelosi",
                ticker="NVDA",
                action="purchase",
                amount_range="$1,000,001 - $5,000,000",
                transaction_date=datetime.now() - timedelta(days=5),
                filing_date=datetime.now() - timedelta(days=2),
                party="D",
                state="CA",
                chamber="house"
            ),
            CongressionalTrade(
                politician="Dan Crenshaw",
                ticker="MSFT",
                action="purchase",
                amount_range="$15,001 - $50,000",
                transaction_date=datetime.now() - timedelta(days=10),
                filing_date=datetime.now() - timedelta(days=7),
                party="R",
                state="TX",
                chamber="house"
            ),
            CongressionalTrade(
                politician="Josh Gottheimer",
                ticker="AVGO",
                action="purchase",
                amount_range="$50,001 - $100,000",
                transaction_date=datetime.now() - timedelta(days=3),
                filing_date=datetime.now() - timedelta(days=1),
                party="D",
                state="NJ",
                chamber="house"
            )
        ]

        if tickers:
            mock_trades = [t for t in mock_trades if t.ticker in tickers]

        return mock_trades

    async def fetch_insider_trades(self,
                                  ticker: str,
                                  days_back: int = 90) -> List[InsiderTrade]:
        """
        Fetch insider trading data

        Args:
            ticker: Stock ticker
            days_back: Number of days to look back

        Returns:
            List of insider trades
        """
        trades = []

        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance not available for insider data")
            return trades

        try:
            stock = yf.Ticker(ticker)
            insider_df = stock.insider_transactions

            if insider_df is not None and not insider_df.empty:
                cutoff_date = datetime.now() - timedelta(days=days_back)

                for _, row in insider_df.iterrows():
                    # Parse date
                    date_str = row.get('Date', '')
                    try:
                        trade_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    except:
                        continue

                    if trade_date >= cutoff_date:
                        trade = InsiderTrade(
                            insider_name=row.get('Insider', 'Unknown'),
                            ticker=ticker,
                            action='Buy' if row.get('Transaction', '').lower() in ['buy', 'purchase'] else 'Sell',
                            shares=int(row.get('Shares', 0)),
                            value=float(row.get('Value', 0)),
                            transaction_date=trade_date,
                            position=row.get('Position', 'Unknown')
                        )
                        trades.append(trade)

            logger.info(f"Fetched {len(trades)} insider trades for {ticker}")

        except Exception as e:
            logger.error(f"Error fetching insider trades: {e}")

        return trades

    async def fetch_earnings_calendar(self,
                                     tickers: List[str],
                                     days_ahead: int = 30) -> List[EarningsEvent]:
        """
        Fetch upcoming earnings events

        Args:
            tickers: List of tickers to check
            days_ahead: Number of days to look ahead

        Returns:
            List of earnings events
        """
        events = []

        if not YFINANCE_AVAILABLE:
            return events

        try:
            for ticker in tickers:
                stock = yf.Ticker(ticker)
                calendar = stock.calendar

                if calendar is not None and not calendar.empty:
                    # Get earnings date
                    earnings_date = calendar.get('Earnings Date')
                    if earnings_date and len(earnings_date) > 0:
                        event = EarningsEvent(
                            ticker=ticker,
                            earnings_date=earnings_date[0] if isinstance(earnings_date, list) else earnings_date,
                            eps_estimate=calendar.get('EPS Estimate', 0),
                            eps_actual=None,  # Will be filled after earnings
                            revenue_estimate=calendar.get('Revenue Estimate', 0),
                            revenue_actual=None,
                            surprise_percent=None
                        )
                        events.append(event)

            self.earnings_calendar = events
            logger.info(f"Fetched {len(events)} upcoming earnings events")

        except Exception as e:
            logger.error(f"Error fetching earnings calendar: {e}")

        return events

    async def fetch_market_sentiment(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch market sentiment from various sources

        Returns:
            Dictionary with sentiment data
        """
        sentiment = {
            'ticker': ticker,
            'overall_sentiment': 'neutral',
            'sentiment_score': 0.0,
            'sources': {}
        }

        try:
            # Fetch news sentiment using existing TradingAgents tools
            news_interface = AlphaVantageNewsInterface()
            news_data = news_interface.get_news(ticker, datetime.now().strftime('%Y-%m-%d'))

            if news_data:
                # Simple sentiment analysis based on news
                positive_keywords = ['beat', 'surge', 'jump', 'gain', 'profit', 'upgrade']
                negative_keywords = ['miss', 'fall', 'drop', 'loss', 'downgrade', 'concern']

                positive_count = 0
                negative_count = 0

                for article in news_data[:10]:  # Check first 10 articles
                    title = article.get('title', '').lower()
                    for keyword in positive_keywords:
                        if keyword in title:
                            positive_count += 1
                    for keyword in negative_keywords:
                        if keyword in title:
                            negative_count += 1

                # Calculate sentiment score
                total = positive_count + negative_count
                if total > 0:
                    sentiment['sentiment_score'] = (positive_count - negative_count) / total

                if sentiment['sentiment_score'] > 0.2:
                    sentiment['overall_sentiment'] = 'positive'
                elif sentiment['sentiment_score'] < -0.2:
                    sentiment['overall_sentiment'] = 'negative'

                sentiment['sources']['news'] = {
                    'positive_articles': positive_count,
                    'negative_articles': negative_count,
                    'total_articles': len(news_data)
                }

        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")

        return sentiment

    async def aggregate_signals(self, tickers: List[str]) -> List[MarketSignal]:
        """
        Aggregate all data sources into trading signals

        Args:
            tickers: List of tickers to analyze

        Returns:
            List of market signals
        """
        signals = []

        # Fetch all data
        congress_trades = await self.fetch_congressional_trades(tickers, days_back=7)

        for ticker in tickers:
            # Congressional signal
            ticker_congress = [t for t in congress_trades if t.ticker == ticker]
            if ticker_congress:
                recent_purchases = [t for t in ticker_congress if 'purchase' in t.action.lower()]
                recent_sales = [t for t in ticker_congress if 'sale' in t.action.lower()]

                if len(recent_purchases) > len(recent_sales):
                    signal = MarketSignal(
                        ticker=ticker,
                        signal_type='congressional',
                        action='BUY',
                        confidence=min(80 + len(recent_purchases) * 5, 95),
                        data={
                            'trades': [
                                {
                                    'politician': t.politician,
                                    'amount': t.amount_range,
                                    'date': t.transaction_date.isoformat()
                                }
                                for t in recent_purchases[:3]
                            ]
                        },
                        timestamp=datetime.now()
                    )
                    signals.append(signal)

            # Insider signal
            insider_trades = await self.fetch_insider_trades(ticker, days_back=30)
            if insider_trades:
                recent_buys = [t for t in insider_trades if t.action == 'Buy']
                recent_sells = [t for t in insider_trades if t.action == 'Sell']

                if len(recent_buys) > len(recent_sells) * 2:  # Strong buy signal
                    signal = MarketSignal(
                        ticker=ticker,
                        signal_type='insider',
                        action='BUY',
                        confidence=min(70 + len(recent_buys) * 3, 90),
                        data={
                            'insider_buys': len(recent_buys),
                            'insider_sells': len(recent_sells),
                            'net_buying': sum(t.value for t in recent_buys)
                        },
                        timestamp=datetime.now()
                    )
                    signals.append(signal)

            # Sentiment signal
            sentiment = await self.fetch_market_sentiment(ticker)
            if sentiment['overall_sentiment'] == 'positive' and sentiment['sentiment_score'] > 0.3:
                signal = MarketSignal(
                    ticker=ticker,
                    signal_type='sentiment',
                    action='BUY',
                    confidence=min(60 + sentiment['sentiment_score'] * 100, 85),
                    data=sentiment,
                    timestamp=datetime.now()
                )
                signals.append(signal)

        self.market_signals = signals
        logger.info(f"Generated {len(signals)} market signals")
        return signals

    def get_top_opportunities(self, n: int = 5) -> List[MarketSignal]:
        """
        Get top trading opportunities based on confidence

        Args:
            n: Number of opportunities to return

        Returns:
            Top n signals by confidence
        """
        sorted_signals = sorted(self.market_signals, key=lambda x: x.confidence, reverse=True)
        return sorted_signals[:n]


# Example usage
async def main():
    """Example of using the data aggregator"""
    config = {
        'quiver_api_key': os.getenv('QUIVER_API_KEY'),
        'alpha_vantage_api_key': os.getenv('ALPHA_VANTAGE_API_KEY')
    }

    aggregator = DataAggregator(config)

    # Your portfolio tickers
    portfolio_tickers = ["AVGO", "MSFT", "MU", "NVDA", "TSM"]

    # Fetch congressional trades
    congress_trades = await aggregator.fetch_congressional_trades(portfolio_tickers)
    print(f"\nCongressional Trades:")
    for trade in congress_trades:
        print(f"  {trade.politician} - {trade.action} {trade.ticker} ({trade.amount_range})")

    # Aggregate all signals
    signals = await aggregator.aggregate_signals(portfolio_tickers)
    print(f"\nTop Trading Signals:")
    for signal in aggregator.get_top_opportunities(3):
        print(f"  {signal.ticker}: {signal.action} (Confidence: {signal.confidence}%) - {signal.signal_type}")


if __name__ == "__main__":
    asyncio.run(main())