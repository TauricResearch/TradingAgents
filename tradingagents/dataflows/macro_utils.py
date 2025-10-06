import requests
import json
from datetime import datetime, timedelta
from typing import Annotated, Dict, List, Optional
from .config import get_api_key, DATA_DIR
import os
import pandas as pd


def get_fred_api_key():
    """Get FRED API key from config or environment"""
    try:
        api_key = get_api_key("fred_api_key", "FRED_API_KEY")
    except:
        api_key = None
    if not api_key:
        api_key = os.getenv("FRED_API_KEY")
    return api_key


def get_fred_data(series_id: str, start_date: str, end_date: str) -> Dict:
    """
    Get economic data from FRED API
    
    Args:
        series_id: FRED series ID (e.g., 'FEDFUNDS', 'CPIAUCSL')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        Dictionary with FRED data
    """
    api_key = get_fred_api_key()
    if not api_key:
        return {"error": "FRED API key not found. Please set FRED_API_KEY environment variable."}
    
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'observation_start': start_date,
        'observation_end': end_date,
        'sort_order': 'desc',
        'limit': 100
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch FRED data for {series_id}: {str(e)}"}


def get_treasury_yield_curve(curr_date: str) -> str:
    """
    Get current Treasury yield curve data
    
    Args:
        curr_date: Current date in YYYY-MM-DD format
        
    Returns:
        Formatted string with yield curve data
    """
    # Treasury yield series IDs
    yield_series = {
        "1 Month": "DGS1MO",
        "3 Month": "DGS3MO", 
        "6 Month": "DGS6MO",
        "1 Year": "DGS1",
        "2 Year": "DGS2",
        "3 Year": "DGS3",
        "5 Year": "DGS5",
        "7 Year": "DGS7",
        "10 Year": "DGS10",
        "20 Year": "DGS20",
        "30 Year": "DGS30"
    }
    
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    
    result = f"## Treasury Yield Curve as of {curr_date}\n\n"
    
    yield_data = []
    for maturity, series_id in yield_series.items():
        data = get_fred_data(series_id, start_date, curr_date)
        
        if "error" in data:
            continue
            
        observations = data.get("observations", [])
        if observations:
            latest = observations[0]
            if latest.get("value") != ".":
                yield_data.append({
                    "maturity": maturity,
                    "yield": float(latest["value"]),
                    "date": latest["date"]
                })
    
    if yield_data:
        result += "| Maturity | Yield (%) | Date |\n"
        result += "|----------|-----------|------|\n"
        
        for item in yield_data:
            result += f"| {item['maturity']} | {item['yield']:.2f}% | {item['date']} |\n"
        
        # Calculate yield curve analysis
        result += "\n### Yield Curve Analysis\n"
        
        # Find 2Y and 10Y for inversion check
        two_year = next((item for item in yield_data if item["maturity"] == "2 Year"), None)
        ten_year = next((item for item in yield_data if item["maturity"] == "10 Year"), None)
        
        if two_year and ten_year:
            spread = ten_year["yield"] - two_year["yield"]
            result += f"- **2Y-10Y Spread**: {spread:.2f} basis points\n"
            
            if spread < 0:
                result += "- **⚠️ INVERTED YIELD CURVE**: Potential recession signal\n"
            elif spread < 50:
                result += "- **📊 FLAT YIELD CURVE**: Economic uncertainty\n"
            else:
                result += "- **📈 NORMAL YIELD CURVE**: Healthy economic expectations\n"
    else:
        result += "No recent yield curve data available.\n"
    
    return result


def get_economic_indicators_report(curr_date: str, lookback_days: int = 90) -> str:
    """
    Get comprehensive economic indicators report
    
    Args:
        curr_date: Current date in YYYY-MM-DD format
        lookback_days: How many days to look back for data
        
    Returns:
        Formatted string with economic indicators
    """
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    # Key economic indicators
    indicators = {
        "Federal Funds Rate": {
            "series": "FEDFUNDS",
            "description": "Federal Reserve's target interest rate",
            "unit": "%"
        },
        "Consumer Price Index (CPI)": {
            "series": "CPIAUCSL",
            "description": "Inflation measure based on consumer goods",
            "unit": "Index",
            "yoy": True
        },
        "Producer Price Index (PPI)": {
            "series": "PPIACO",
            "description": "Inflation measure at producer level",
            "unit": "Index",
            "yoy": True
        },
        "Unemployment Rate": {
            "series": "UNRATE",
            "description": "Percentage of labor force unemployed",
            "unit": "%"
        },
        "Nonfarm Payrolls": {
            "series": "PAYEMS",
            "description": "Monthly change in employment",
            "unit": "Thousands",
            "mom": True
        },
        "GDP Growth Rate": {
            "series": "GDP",
            "description": "Gross Domestic Product growth",
            "unit": "Billions",
            "qoq": True
        },
        "ISM Manufacturing PMI": {
            "series": "NAPM",
            "description": "Manufacturing sector health indicator",
            "unit": "Index"
        },
        "Consumer Confidence": {
            "series": "CSCICP03USM665S",
            "description": "Consumer sentiment indicator",
            "unit": "Index"
        },
        "VIX": {
            "series": "VIXCLS",
            "description": "Market volatility index",
            "unit": "Index"
        }
    }
    
    result = f"## Economic Indicators Report ({start_date} to {curr_date})\n\n"
    
    for indicator_name, config in indicators.items():
        data = get_fred_data(config["series"], start_date, curr_date)
        
        if "error" in data:
            result += f"### {indicator_name}\n**Error**: {data['error']}\n\n"
            continue
        
        observations = data.get("observations", [])
        if not observations:
            result += f"### {indicator_name}\n**No data available**\n\n"
            continue
        
        # Filter out missing values
        valid_obs = [obs for obs in observations if obs.get("value") != "."]
        if not valid_obs:
            result += f"### {indicator_name}\n**No valid data available**\n\n"
            continue
        
        latest = valid_obs[0]
        latest_value = float(latest["value"])
        latest_date = latest["date"]
        
        result += f"### {indicator_name}\n"
        result += f"- **Latest Value**: {latest_value:.2f} {config['unit']} (as of {latest_date})\n"
        result += f"- **Description**: {config['description']}\n"
        
        # Calculate changes if we have enough data
        if len(valid_obs) >= 2:
            previous = valid_obs[1]
            previous_value = float(previous["value"])
            change = latest_value - previous_value
            change_pct = (change / previous_value) * 100 if previous_value != 0 else 0
            
            result += f"- **Change**: {change:+.2f} {config['unit']} ({change_pct:+.2f}%)\n"
            result += f"- **Previous**: {previous_value:.2f} {config['unit']} (as of {previous['date']})\n"
        
        # Calculate year-over-year change for inflation indicators
        if config.get("yoy") and len(valid_obs) >= 12:
            year_ago = valid_obs[11] if len(valid_obs) > 11 else valid_obs[-1]
            year_ago_value = float(year_ago["value"])
            yoy_change = ((latest_value - year_ago_value) / year_ago_value) * 100
            result += f"- **Year-over-Year**: {yoy_change:+.2f}%\n"
        
        # Add interpretation
        if indicator_name == "Federal Funds Rate":
            if latest_value > 4.0:
                result += "- **💡 Analysis**: Restrictive monetary policy stance\n"
            elif latest_value < 2.0:
                result += "- **💡 Analysis**: Accommodative monetary policy stance\n"
            else:
                result += "- **💡 Analysis**: Neutral monetary policy stance\n"
        
        elif "CPI" in indicator_name or "PPI" in indicator_name:
            if len(valid_obs) >= 12:
                if yoy_change > 3.0:
                    result += "- **💡 Analysis**: Above Fed's 2% inflation target\n"
                elif yoy_change < 1.0:
                    result += "- **💡 Analysis**: Below Fed's 2% inflation target\n"
                else:
                    result += "- **💡 Analysis**: Near Fed's 2% inflation target\n"
        
        elif indicator_name == "Unemployment Rate":
            if latest_value < 4.0:
                result += "- **💡 Analysis**: Very low unemployment, tight labor market\n"
            elif latest_value > 6.0:
                result += "- **💡 Analysis**: Elevated unemployment, loose labor market\n"
            else:
                result += "- **💡 Analysis**: Moderate unemployment levels\n"
        
        elif "PMI" in indicator_name:
            if latest_value > 50:
                result += "- **💡 Analysis**: Expanding manufacturing sector\n"
            else:
                result += "- **💡 Analysis**: Contracting manufacturing sector\n"
        
        elif indicator_name == "VIX":
            if latest_value > 30:
                result += "- **💡 Analysis**: High market volatility/fear\n"
            elif latest_value < 15:
                result += "- **💡 Analysis**: Low market volatility/complacency\n"
            else:
                result += "- **💡 Analysis**: Moderate market volatility\n"
        
        result += "\n"
    
    return result


def get_fed_calendar_and_minutes(curr_date: str) -> str:
    """
    Get Federal Reserve meeting calendar and recent minutes
    
    Args:
        curr_date: Current date in YYYY-MM-DD format
        
    Returns:
        Formatted string with Fed calendar information
    """
    result = f"## Federal Reserve Calendar & Policy Updates\n\n"
    
    # Get recent Fed Funds rate data to show policy trajectory
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    fed_data = get_fred_data("FEDFUNDS", start_date, curr_date)
    
    if "error" not in fed_data:
        observations = fed_data.get("observations", [])
        valid_obs = [obs for obs in observations if obs.get("value") != "."]
        
        if valid_obs and len(valid_obs) >= 2:
            result += "### Recent Federal Funds Rate History\n"
            result += "| Date | Rate (%) | Change |\n"
            result += "|------|----------|--------|\n"
            
            for i, obs in enumerate(valid_obs[:6]):  # Show last 6 observations
                rate = float(obs["value"])
                if i < len(valid_obs) - 1:
                    prev_rate = float(valid_obs[i + 1]["value"])
                    change = rate - prev_rate
                    change_str = f"{change:+.2f}%" if change != 0 else "No change"
                else:
                    change_str = "-"
                
                result += f"| {obs['date']} | {rate:.2f}% | {change_str} |\n"
            
            result += "\n"
    
    return result


def get_macro_economic_summary(curr_date: str, lookback_days: int = 90) -> str:
    """
    Get comprehensive macro economic summary combining economic indicators, yield curves, and Fed data
    
    Args:
        curr_date: Current date in YYYY-MM-DD format
        lookback_days: How many days to look back for data
        
    Returns:
        Complete macro economic analysis
    """
    result = f"# Macro Economic Analysis - {curr_date}\n\n"
    
    # Get all components
    indicators_report = get_economic_indicators_report(curr_date, lookback_days)
    yield_curve = get_treasury_yield_curve(curr_date)
    fed_calendar = get_fed_calendar_and_minutes(curr_date)
    
    # Combine all reports
    result += indicators_report + "\n"
    result += yield_curve + "\n"
    result += fed_calendar + "\n"
    
    return result
