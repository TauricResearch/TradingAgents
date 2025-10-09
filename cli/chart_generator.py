"""Chart generation utilities for PDF reports."""
import io
from pathlib import Path
from typing import Optional, Dict, Any
import datetime


def generate_stock_price_chart(ticker: str, analysis_date: str) -> Optional[io.BytesIO]:
    """
    Generate a stock price chart with moving averages.

    Args:
        ticker: Stock ticker symbol
        analysis_date: Analysis date string (YYYY-MM-DD)

    Returns:
        BytesIO buffer containing the chart image, or None if generation fails
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import yfinance as yf
        from datetime import datetime, timedelta
    except ImportError:
        print("Warning: matplotlib required for chart generation")
        return None

    try:
        # Parse the analysis date
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        # Get 90 days of data for context
        start_date = end_date - timedelta(days=90)

        # Fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'),
                          end=end_date.strftime('%Y-%m-%d'))

        if df.empty:
            print(f"Warning: No data available for {ticker}")
            return None

        # Calculate moving averages
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()

        # Create the figure
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot price and moving averages
        ax.plot(df.index, df['Close'], label='Close Price', linewidth=2, color='#2E86AB')
        ax.plot(df.index, df['SMA_20'], label='20-day SMA', linewidth=1.5,
                linestyle='--', color='#A23B72', alpha=0.8)
        ax.plot(df.index, df['SMA_50'], label='50-day SMA', linewidth=1.5,
                linestyle='--', color='#F18F01', alpha=0.8)

        # Formatting
        ax.set_title(f'{ticker} Stock Price - Last 90 Days', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Price ($)', fontsize=12)
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        plt.xticks(rotation=45)

        # Tight layout to prevent label cutoff
        plt.tight_layout()

        # Save to BytesIO buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        print(f"Error generating stock price chart: {e}")
        return None


def generate_volume_chart(ticker: str, analysis_date: str) -> Optional[io.BytesIO]:
    """
    Generate a trading volume chart.

    Args:
        ticker: Stock ticker symbol
        analysis_date: Analysis date string (YYYY-MM-DD)

    Returns:
        BytesIO buffer containing the chart image, or None if generation fails
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import yfinance as yf
        from datetime import datetime, timedelta
    except ImportError:
        return None

    try:
        # Parse the analysis date
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=90)

        # Fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'),
                          end=end_date.strftime('%Y-%m-%d'))

        if df.empty:
            return None

        # Create the figure
        fig, ax = plt.subplots(figsize=(10, 4))

        # Plot volume bars
        colors = ['green' if close >= open_ else 'red'
                 for close, open_ in zip(df['Close'], df['Open'])]
        ax.bar(df.index, df['Volume'], color=colors, alpha=0.6)

        # Add average volume line
        avg_volume = df['Volume'].mean()
        ax.axhline(y=avg_volume, color='blue', linestyle='--',
                  linewidth=1.5, label=f'Avg Volume: {avg_volume:,.0f}', alpha=0.7)

        # Formatting
        ax.set_title(f'{ticker} Trading Volume - Last 90 Days', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date', fontsize=12)
        ax.set_ylabel('Volume', fontsize=12)
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3, axis='y')

        # Format y-axis to show volume in millions
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e6:.1f}M'))

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        plt.xticks(rotation=45)

        plt.tight_layout()

        # Save to BytesIO buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        print(f"Error generating volume chart: {e}")
        return None


def generate_technical_indicators_chart(ticker: str, analysis_date: str) -> Optional[io.BytesIO]:
    """
    Generate a chart showing RSI and MACD technical indicators.

    Args:
        ticker: Stock ticker symbol
        analysis_date: Analysis date string (YYYY-MM-DD)

    Returns:
        BytesIO buffer containing the chart image, or None if generation fails
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import yfinance as yf
        import pandas as pd
        from datetime import datetime, timedelta
    except ImportError:
        return None

    try:
        # Parse the analysis date
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=90)

        # Fetch stock data
        stock = yf.Ticker(ticker)
        df = stock.history(start=start_date.strftime('%Y-%m-%d'),
                          end=end_date.strftime('%Y-%m-%d'))

        if df.empty:
            return None

        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Calculate MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Create subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

        # RSI plot
        ax1.plot(df.index, df['RSI'], label='RSI', linewidth=2, color='#2E86AB')
        ax1.axhline(y=70, color='red', linestyle='--', linewidth=1, alpha=0.7, label='Overbought (70)')
        ax1.axhline(y=30, color='green', linestyle='--', linewidth=1, alpha=0.7, label='Oversold (30)')
        ax1.fill_between(df.index, 30, 70, alpha=0.1, color='gray')
        ax1.set_ylabel('RSI', fontsize=12)
        ax1.set_title(f'{ticker} Technical Indicators', fontsize=14, fontweight='bold')
        ax1.legend(loc='best', fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0, 100)

        # MACD plot
        ax2.plot(df.index, df['MACD'], label='MACD', linewidth=2, color='#2E86AB')
        ax2.plot(df.index, df['Signal'], label='Signal', linewidth=2, color='#F18F01')
        ax2.bar(df.index, df['MACD'] - df['Signal'], label='Histogram',
                color='gray', alpha=0.3)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.set_xlabel('Date', fontsize=12)
        ax2.set_ylabel('MACD', fontsize=12)
        ax2.legend(loc='best', fontsize=10)
        ax2.grid(True, alpha=0.3)

        # Format x-axis dates
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax2.xaxis.set_major_locator(mdates.MonthLocator())
        plt.xticks(rotation=45)

        plt.tight_layout()

        # Save to BytesIO buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        print(f"Error generating technical indicators chart: {e}")
        return None
