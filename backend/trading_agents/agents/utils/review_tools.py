import os
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import yfinance as yf
from langchain_core.tools import tool
from tradingagents.default_config import DEFAULT_CONFIG

@tool
def get_past_performance_data(ticker: str, curr_date: str | None = None) -> str:
    """
    Search the local results directory for the most recent past analysis report of this ticker.
    Extract the date of that report, the system's past decision, and calculate the actual price performance since then.
    
    Args:
        ticker (str): The stock ticker symbol.
        curr_date (str | None): Optional current simulated trading date in YYYY-MM-DD format.
    
    Returns:
        str: A summary of the past prediction, past price, current price, and return percentage.
    """
    try:
        results_dir = Path(DEFAULT_CONFIG["results_dir"]) / ticker
        if not results_dir.exists():
            return "No past analysis data found for this ticker."

        # Find all date directories (e.g. 2026-05-08)
        date_dirs = [d for d in results_dir.iterdir() if d.is_dir()]
        if not date_dirs:
            return "No past analysis data found for this ticker."

        # Sort by date
        date_dirs.sort(key=lambda x: x.name, reverse=True)
        
        # Look for the most recent report that is NOT today (or just take the most recent available if we only have past ones)
        # To be safe, we just find the first one that has a trader_investment_plan.md
        past_report = None
        past_date = None
        for d in date_dirs:
            report_file = d / "reports" / "trader_investment_plan.md"
            if report_file.exists():
                with open(report_file, "r") as f:
                    past_report = f.read()
                past_date = d.name
                break
                
        if not past_report:
            return "No past trader investment plans found for this ticker."

        # Fetch historical data
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # If the report is from today, it's not "past" performance, but we can still evaluate it if requested
        if past_date == today_str and len(date_dirs) > 1:
            # Try to get an older one
            for d in date_dirs[1:]:
                report_file = d / "reports" / "trader_investment_plan.md"
                if report_file.exists():
                    with open(report_file, "r") as f:
                        past_report = f.read()
                    past_date = d.name
                    break

        # Fetch prices
        try:
            from tradingagents.dataflows.stockstats_utils import load_ohlcv
            if not curr_date:
                curr_date = datetime.now().strftime("%Y-%m-%d")
                
            hist = load_ohlcv(ticker, curr_date)
            # Filter hist to rows >= past_date
            hist_filtered = hist[hist['Date'] >= pd.to_datetime(past_date)]
            
            if hist_filtered.empty:
                return f"Found past report from {past_date}, but could not fetch price history from local cache."
                
            past_price = hist_filtered.iloc[0]['Close']
            current_price = hist_filtered.iloc[-1]['Close']
            
            return_pct = ((current_price - past_price) / past_price) * 100
            
            # Extract a brief summary of the past report (first 1000 chars to avoid token limits)
            brief_report = past_report[:1000] + "..." if len(past_report) > 1000 else past_report
            
            result = (
                f"--- PAST PERFORMANCE DATA FOR {ticker} ---\n"
                f"Past Analysis Date: {past_date}\n"
                f"Price on that date: ${past_price:.2f}\n"
                f"Current Price (as of {curr_date}): ${current_price:.2f}\n"
                f"Actual Return Since Then: {return_pct:.2f}%\n"
                f"\n--- EXCERPT OF PAST TRADER PLAN ---\n"
                f"{brief_report}\n"
            )
            return result
            
        except Exception as e:
            return f"Error fetching price data for {ticker}: {e}"

    except Exception as e:
        return f"Error retrieving past performance data: {e}"
