"""Sample data fixtures for testing TradingAgents."""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any


class SampleDataFactory:
    """Factory class for creating sample test data."""

    @staticmethod
    def create_market_data(ticker: str = "AAPL", days: int = 30) -> Dict[str, Any]:
        """Create sample market data for testing."""
        base_date = datetime(2024, 5, 1)
        data = {}

        for i in range(days):
            date = base_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")

            # Create realistic stock data with some volatility
            base_price = 150.0
            daily_change = (i % 10 - 5) * 2.0  # Random-ish daily changes
            price = base_price + daily_change + (i * 0.5)  # Slight upward trend

            data[date_str] = {
                "open": round(price - 1.0, 2),
                "high": round(price + 2.0, 2),
                "low": round(price - 2.0, 2),
                "close": round(price, 2),
                "volume": 1000000 + (i * 50000),
                "adj_close": round(price, 2),
            }

        return data

    @staticmethod
    def create_finnhub_news_data(
        ticker: str = "AAPL", count: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Create sample FinnHub news data for testing."""
        base_date = datetime(2024, 5, 10)
        data = {}

        news_templates = [
            {
                "headline": "{} reports strong Q1 earnings",
                "summary": "Company beats expectations with revenue growth",
            },
            {
                "headline": "{} announces new product launch",
                "summary": "Revolutionary product expected to boost market share",
            },
            {
                "headline": "Analysts upgrade {} price target",
                "summary": "Multiple firms raise target price on strong fundamentals",
            },
            {
                "headline": "{} faces regulatory challenges",
                "summary": "Government scrutiny may impact future operations",
            },
            {
                "headline": "{} stock shows technical breakout",
                "summary": "Chart patterns suggest continued upward momentum",
            },
        ]

        for i in range(count):
            date = base_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")

            # Create 1-3 news items per day
            news_items = []
            for j in range((i % 3) + 1):
                template = news_templates[j % len(news_templates)]
                news_item = {
                    "headline": template["headline"].format(ticker),
                    "summary": template["summary"],
                    "url": f"https://example.com/news/{ticker.lower()}-{i}-{j}",
                    "source": "Reuters" if j % 2 else "Bloomberg",
                    "datetime": int(date.timestamp()),
                    "related": ticker,
                    "image": f"https://example.com/images/{ticker.lower()}.jpg",
                    "lang": "en",
                }
                news_items.append(news_item)

            if news_items:  # Only add non-empty days
                data[date_str] = news_items

        return data

    @staticmethod
    def create_insider_transactions_data(
        ticker: str = "AAPL",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Create sample insider transactions data for testing."""
        base_date = datetime(2024, 5, 5)
        data = {}

        # Create some insider transaction events
        transactions = [
            {"type": "buy", "shares": 1000, "price": 148.50, "person": "CEO John Doe"},
            {
                "type": "sell",
                "shares": 5000,
                "price": 152.30,
                "person": "CFO Jane Smith",
            },
            {
                "type": "buy",
                "shares": 2500,
                "price": 145.80,
                "person": "CTO Bob Wilson",
            },
        ]

        for i, transaction in enumerate(transactions):
            date = base_date + timedelta(days=i * 3)
            date_str = date.strftime("%Y-%m-%d")

            data[date_str] = [
                {
                    "symbol": ticker,
                    "transactionDate": date_str,
                    "transactionCode": "P" if transaction["type"] == "buy" else "S",
                    "transactionShares": transaction["shares"],
                    "transactionPrice": transaction["price"],
                    "transactionValue": transaction["shares"] * transaction["price"],
                    "reportingName": transaction["person"],
                    "typeOfOwner": "officer",
                }
            ]

        return data

    @staticmethod
    def create_financial_statements_data(
        ticker: str = "AAPL", period: str = "annual"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Create sample financial statements data for testing."""
        if period == "annual":
            dates = ["2023-12-31", "2022-12-31", "2021-12-31"]
        else:  # quarterly
            dates = ["2024-03-31", "2023-12-31", "2023-09-30"]

        data = {}

        for i, date in enumerate(dates):
            # Create realistic financial data with growth trends
            base_multiplier = 1 + (i * 0.1)  # 10% growth each period

            financial_data = {
                "symbol": ticker,
                "date": date,
                "period": period,
                "revenue": int(100000000000 * base_multiplier),  # $100B base
                "costOfRevenue": int(60000000000 * base_multiplier),
                "grossProfit": int(40000000000 * base_multiplier),
                "operatingIncome": int(25000000000 * base_multiplier),
                "netIncome": int(20000000000 * base_multiplier),
                "totalAssets": int(350000000000 * base_multiplier),
                "totalLiabilities": int(120000000000 * base_multiplier),
                "totalStockholdersEquity": int(230000000000 * base_multiplier),
                "cashAndCashEquivalents": int(50000000000 * base_multiplier),
                "operatingCashFlow": int(30000000000 * base_multiplier),
                "freeCashFlow": int(25000000000 * base_multiplier),
            }

            data[date] = [financial_data]

        return data

    @staticmethod
    def create_social_sentiment_data(
        ticker: str = "AAPL",
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Create sample social media sentiment data for testing."""
        base_date = datetime(2024, 5, 8)
        data = {}

        sentiment_posts = [
            {
                "text": f"Bullish on ${ticker}! Great fundamentals and strong growth",
                "sentiment": "positive",
                "score": 0.8,
            },
            {
                "text": f"${ticker} looking weak, might sell my position",
                "sentiment": "negative",
                "score": -0.6,
            },
            {
                "text": f"Holding ${ticker} for the long term, solid company",
                "sentiment": "positive",
                "score": 0.7,
            },
            {
                "text": f"${ticker} earnings coming up, could be volatile",
                "sentiment": "neutral",
                "score": 0.1,
            },
            {
                "text": f"Just bought more ${ticker} on the dip!",
                "sentiment": "positive",
                "score": 0.9,
            },
        ]

        for i in range(7):  # One week of data
            date = base_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")

            # Select 2-3 posts per day
            daily_posts = []
            for j in range((i % 3) + 2):
                post = sentiment_posts[j % len(sentiment_posts)]
                daily_posts.append(
                    {
                        "id": f"post_{i}_{j}",
                        "text": post["text"],
                        "sentiment": post["sentiment"],
                        "sentiment_score": post["score"],
                        "author": f"user_{i}_{j}",
                        "timestamp": int(date.timestamp()),
                        "subreddit": "stocks" if j % 2 else "investing",
                        "upvotes": 10 + (j * 5),
                        "comments": 3 + j,
                    }
                )

            data[date_str] = daily_posts

        return data

    @staticmethod
    def create_technical_indicators_data(ticker: str = "AAPL") -> Dict[str, Any]:
        """Create sample technical indicators data for testing."""
        return {
            "symbol": ticker,
            "date": "2024-05-10",
            "indicators": {
                "rsi": 65.5,
                "macd": 0.45,
                "macds": 0.38,
                "macdh": 0.07,
                "close_50_sma": 148.75,
                "close_200_sma": 142.30,
                "close_10_ema": 149.82,
                "boll": 149.50,
                "boll_ub": 155.20,
                "boll_lb": 143.80,
                "atr": 3.25,
                "vwma": 149.15,
            },
            "signals": {
                "rsi_signal": "neutral",  # Between 30-70
                "macd_signal": "bullish",  # MACD above signal
                "sma_signal": "bullish",  # Above both SMAs
                "bollinger_signal": "neutral",  # Within bands
            },
        }

    @staticmethod
    def create_complete_test_dataset(ticker: str = "AAPL") -> Dict[str, Dict[str, Any]]:
        """Create a complete dataset for comprehensive testing."""
        return {
            "market_data": SampleDataFactory.create_market_data(ticker),
            "news_data": SampleDataFactory.create_finnhub_news_data(ticker),
            "insider_transactions": SampleDataFactory.create_insider_transactions_data(
                ticker
            ),
            "financial_annual": SampleDataFactory.create_financial_statements_data(
                ticker, "annual"
            ),
            "financial_quarterly": SampleDataFactory.create_financial_statements_data(
                ticker, "quarterly"
            ),
            "social_sentiment": SampleDataFactory.create_social_sentiment_data(ticker),
            "technical_indicators": SampleDataFactory.create_technical_indicators_data(
                ticker
            ),
        }


# Predefined sample data constants
SAMPLE_TICKERS = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "META"]

SAMPLE_TRADING_DECISIONS = [
    {
        "ticker": "AAPL",
        "date": "2024-05-10",
        "decision": "BUY",
        "confidence": 0.75,
        "rationale": "Strong fundamentals and positive technical indicators",
    },
    {
        "ticker": "TSLA",
        "date": "2024-05-11",
        "decision": "HOLD",
        "confidence": 0.60,
        "rationale": "Mixed signals from different analysts",
    },
    {
        "ticker": "NVDA",
        "date": "2024-05-12",
        "decision": "SELL",
        "confidence": 0.80,
        "rationale": "Overbought conditions and profit-taking opportunity",
    },
]

SAMPLE_ANALYST_REPORTS = {
    "market": "Technical analysis shows bullish momentum with RSI at 65.5 and MACD bullish crossover.",
    "social": "Social sentiment is predominantly positive with 70% bullish posts on Reddit and Twitter.",
    "news": "Recent earnings beat expectations and product launch announcements are driving positive coverage.",
    "fundamentals": "Strong balance sheet with growing revenue and margins, P/E ratio attractive at current levels.",
}


def save_sample_data_to_files(base_path: str, ticker: str = "AAPL") -> None:
    """Save sample data to JSON files for testing file-based operations."""
    import os

    dataset = SampleDataFactory.create_complete_test_dataset(ticker)

    # Create directory structure
    finnhub_path = os.path.join(base_path, "finnhub_data")

    data_types = {
        "news_data": dataset["news_data"],
        "insider_trans": dataset["insider_transactions"],
        "fin_as_reported": dataset["financial_annual"],
    }

    for data_type, data in data_types.items():
        dir_path = os.path.join(finnhub_path, data_type)
        os.makedirs(dir_path, exist_ok=True)

        file_path = os.path.join(dir_path, f"{ticker}_data_formatted.json")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

    # Save quarterly data separately
    quarterly_path = os.path.join(
        finnhub_path, "fin_as_reported", f"{ticker}_quarterly_data_formatted.json"
    )
    with open(quarterly_path, "w") as f:
        json.dump(dataset["financial_quarterly"], f, indent=2)
