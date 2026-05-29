"""Benchmark tracking and performance comparison."""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import yfinance as yf

logger = logging.getLogger(__name__)


class BenchmarkTracker:
    """Track benchmark performance for comparison."""
    
    def __init__(self, benchmark_ticker: str = "SPY"):
        """Initialize benchmark tracker.
        
        Args:
            benchmark_ticker: Benchmark ticker (default SPY)
        """
        self.benchmark_ticker = benchmark_ticker
        self.daily_prices = {}  # date -> {"open": float, "close": float, "return": float}
        self.cache = {}
    
    def fetch_benchmark_data(self, start_date: str, end_date: str) -> Dict[str, float]:
        """Fetch benchmark daily returns for period.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary of date -> daily return %
        """
        if start_date == end_date:
            try:
                # Add 1 day to make the end date inclusive in yfinance
                dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                try:
                    dt = datetime.fromisoformat(start_date)
                    end_date = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
                except Exception:
                    pass

        try:
            ticker = yf.Ticker(self.benchmark_ticker)
            hist = ticker.history(start=start_date, end=end_date)
            
            daily_returns = {}
            prev_close = None
            
            for date, row in hist.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                current_close = row["Close"]
                
                if prev_close is not None:
                    daily_return = ((current_close - prev_close) / prev_close) * 100
                    daily_returns[date_str] = daily_return
                    
                    self.daily_prices[date_str] = {
                        "open": float(row["Open"]),
                        "close": float(current_close),
                        "return": daily_return,
                    }
                else:
                    self.daily_prices[date_str] = {
                        "open": float(row["Open"]),
                        "close": float(current_close),
                        "return": 0.0,
                    }
                
                prev_close = current_close
            
            logger.info(f"Fetched {self.benchmark_ticker} data for {len(daily_returns)} days")
            return daily_returns
        
        except Exception as e:
            logger.error(f"Failed to fetch benchmark data: {e}")
            return {}
    
    def get_period_return(self, start_date: str, end_date: str) -> float:
        """Get cumulative return for period.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Cumulative return %
        """
        try:
            ticker = yf.Ticker(self.benchmark_ticker)
            hist = ticker.history(start=start_date, end=end_date)
            
            if len(hist) < 2:
                return 0.0
            
            start_price = hist.iloc[0]["Close"]
            if start_price <= 0:
                return 0.0
                
            end_price = hist.iloc[-1]["Close"]
            
            return ((end_price - start_price) / start_price) * 100
        
        except Exception as e:
            logger.error(f"Failed to calculate period return: {e}")
            return 0.0
    
    def calculate_alpha(self, portfolio_return: float, benchmark_return: float) -> float:
        """Calculate alpha (excess return).
        
        Args:
            portfolio_return: Portfolio return %
            benchmark_return: Benchmark return %
            
        Returns:
            Alpha in basis points (100 bp = 1%)
        """
        return (portfolio_return - benchmark_return) * 100
    
    def get_daily_benchmark_return(self, date: str) -> float:
        """Get daily benchmark return for date.
        
        Args:
            date: Date (YYYY-MM-DD)
            
        Returns:
            Daily return % or 0.0 if not found
        """
        if date not in self.daily_prices:
            self.fetch_benchmark_data(date, date)
        
        return self.daily_prices.get(date, {}).get("return", 0.0)
    
    def get_benchmark_price(self, date: str, price_type: str = "close") -> Optional[float]:
        """Get benchmark price for date.
        
        Args:
            date: Date (YYYY-MM-DD)
            price_type: 'open' or 'close'
            
        Returns:
            Price or None
        """
        if date not in self.daily_prices:
            self.fetch_benchmark_data(date, date)
        
        return self.daily_prices.get(date, {}).get(price_type)
    
    def outperformance_ratio(self, portfolio_return: float, benchmark_return: float) -> float:
        """Calculate outperformance ratio.
        
        Args:
            portfolio_return: Portfolio return %
            benchmark_return: Benchmark return %
            
        Returns:
            Ratio (>1 means outperformance)
        """
        if benchmark_return == 0:
            return 1.0 if portfolio_return >= 0 else 0.0
        
        return portfolio_return / benchmark_return
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "benchmark_ticker": self.benchmark_ticker,
            "data_points": len(self.daily_prices),
            "latest_data": self.daily_prices.get(max(self.daily_prices.keys())) 
                          if self.daily_prices else None,
        }


class PerformanceComparison:
    """Compare portfolio performance against benchmark."""
    
    def __init__(self, benchmark_tracker: BenchmarkTracker):
        """Initialize performance comparison.
        
        Args:
            benchmark_tracker: BenchmarkTracker instance
        """
        self.benchmark = benchmark_tracker
        self.portfolio_returns = []  # List of daily returns
        self.benchmark_returns = []  # List of daily benchmark returns
    
    def add_daily_performance(self, portfolio_return: float, date: str):
        """Record daily portfolio performance.
        
        Args:
            portfolio_return: Daily portfolio return %
            date: Date (YYYY-MM-DD)
        """
        self.portfolio_returns.append(portfolio_return)
        
        benchmark_return = self.benchmark.get_daily_benchmark_return(date)
        self.benchmark_returns.append(benchmark_return)
    
    def get_cumulative_alpha(self) -> float:
        """Get cumulative alpha over all recorded days.
        
        Returns:
            Cumulative alpha in percentage points
        """
        if len(self.portfolio_returns) != len(self.benchmark_returns):
            return 0.0
        
        total_alpha = sum(
            p - b for p, b in zip(self.portfolio_returns, self.benchmark_returns)
        )
        return total_alpha
    
    def get_outperformance_days(self) -> int:
        """Get number of days portfolio outperformed benchmark.
        
        Returns:
            Count of outperformance days
        """
        if len(self.portfolio_returns) != len(self.benchmark_returns):
            return 0
        
        return sum(
            1 for p, b in zip(self.portfolio_returns, self.benchmark_returns) if p > b
        )
    
    def get_win_rate(self) -> float:
        """Get percentage of days outperforming.
        
        Returns:
            Win rate as percentage
        """
        if not self.portfolio_returns:
            return 0.0
        
        outperformance_days = self.get_outperformance_days()
        return (outperformance_days / len(self.portfolio_returns)) * 100
    
    def get_tracking_error(self) -> float:
        """Get tracking error (std dev of daily alpha).
        
        Returns:
            Tracking error %
        """
        import math
        
        if len(self.portfolio_returns) < 2 or len(self.benchmark_returns) < 2:
            return 0.0
        
        daily_alphas = [p - b for p, b in zip(self.portfolio_returns, self.benchmark_returns)]
        mean_alpha = sum(daily_alphas) / len(daily_alphas)
        
        variance = sum((a - mean_alpha) ** 2 for a in daily_alphas) / len(daily_alphas)
        tracking_error = math.sqrt(variance)
        
        # Annualize (252 trading days)
        return tracking_error * math.sqrt(252)
    
    def get_information_ratio(self) -> float:
        """Get information ratio (alpha / tracking_error).
        
        Returns:
            Information ratio
        """
        tracking_error = self.get_tracking_error()
        if tracking_error == 0:
            return 0.0
        
        cumulative_alpha = self.get_cumulative_alpha()
        daily_alpha = cumulative_alpha / len(self.portfolio_returns) if self.portfolio_returns else 0
        
        # Annualize
        annual_alpha = daily_alpha * 252
        
        return annual_alpha / tracking_error
    
    def get_comparison_summary(self) -> Dict:
        """Get comprehensive performance comparison.
        
        Returns:
            Summary dictionary
        """
        portfolio_total = sum(self.portfolio_returns) if self.portfolio_returns else 0
        benchmark_total = sum(self.benchmark_returns) if self.benchmark_returns else 0
        
        return {
            "portfolio_total_return_pct": portfolio_total,
            "benchmark_total_return_pct": benchmark_total,
            "cumulative_alpha_pct": self.get_cumulative_alpha(),
            "alpha_basis_points": self.get_cumulative_alpha() * 100,
            "outperformance_days": self.get_outperformance_days(),
            "total_days": len(self.portfolio_returns),
            "win_rate_pct": self.get_win_rate(),
            "tracking_error_pct": self.get_tracking_error(),
            "information_ratio": self.get_information_ratio(),
            "benchmark_ticker": self.benchmark.benchmark_ticker,
        }
