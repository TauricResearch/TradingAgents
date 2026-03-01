import os
import pytz
from typing import Dict, List, Any
from tradingagents.default_config import DEFAULT_CONFIG

# Indian market configuration
INDIAN_CONFIG = DEFAULT_CONFIG.copy()

# Update with Indian market specific settings
INDIAN_CONFIG.update({
    # Market identification
    "market_region": "india",
    "currency": "INR",
    "timezone": "Asia/Kolkata",
    
    # Trading hours (IST)
    "trading_hours": {
        "pre_open": "09:00",
        "open": "09:15", 
        "close": "15:30",
        "post_close": "16:00",
        "timezone": "Asia/Kolkata"
    },
    
    # Indian exchanges
    "exchanges": {
        "primary": "NSE",
        "secondary": "BSE",
        "supported": ["NSE", "BSE"]
    },
    
    # Data sources configuration
    "data_sources": {
        "market_data": {
            "primary": "alpha_vantage",
            "secondary": "yahoo_finance", 
            "fallback": "manual_nse_api"
        },
        "fundamental_data": {
            "primary": "alpha_vantage",
            "secondary": "yahoo_finance",
            "indian_specific": "moneycontrol_scraper"
        },
        "news_data": {
            "primary": "google_news",
            "indian_sources": ["economic_times", "moneycontrol", "business_standard"],
            "government": ["rbi_announcements", "sebi_updates"]
        },
        "sentiment_data": {
            "social_media": ["twitter_india", "reddit_india"],
            "forums": ["indian_stock_forums", "valuepickr"]
        }
    },
    
    # API keys (to be set via environment variables)
    "api_keys": {
        "alpha_vantage": os.getenv("ALPHA_VANTAGE_API_KEY"),
        "financial_modeling_prep": os.getenv("FMP_API_KEY"),
        "polygon": os.getenv("POLYGON_API_KEY"),
        "twitter": os.getenv("TWITTER_API_KEY"),
        "news_api": os.getenv("NEWS_API_KEY")
    },
    
    # Indian market specific parameters
    "market_parameters": {
        "circuit_breakers": {
            "individual_stock": {"upper": 0.20, "lower": 0.20},  # 20% circuit breakers
            "index": {"upper": 0.10, "lower": 0.10}  # 10% for indices
        },
        "lot_sizes": {
            # Will be populated dynamically or from file
            "default": 1
        },
        "tick_sizes": {
            "below_100": 0.05,
            "100_to_1000": 0.05, 
            "above_1000": 0.05
        },
        "settlement": "T+1"  # Indian market settlement cycle
    },
    
    # Indian indices for correlation analysis
    "benchmark_indices": {
        "broad_market": ["^NSEI", "^BSESN"],  # Nifty 50, Sensex
        "sectoral": {
            "banking": "^CNXBANK",
            "it": "^CNXIT", 
            "auto": "^CNXAUTO",
            "pharma": "^CNXPHARMA",
            "fmcg": "^CNXFMCG",
            "metal": "^CNXMETAL",
            "realty": "^CNXREALTY"
        }
    },
    
    # Regulatory and compliance
    "regulatory": {
        "sebi_regulations": True,
        "insider_trading_rules": True,
        "disclosure_requirements": True,
        "algorithmic_trading_approval": False  # Set to True if approved
    },
    
    # Indian market holidays (major ones - should be updated annually)
    "market_holidays_2024": [
        "2024-01-26",  # Republic Day
        "2024-03-08",  # Holi
        "2024-03-29",  # Good Friday
        "2024-04-11",  # Eid ul Fitr
        "2024-04-17",  # Ram Navami
        "2024-05-01",  # Maharashtra Day
        "2024-08-15",  # Independence Day
        "2024-08-26",  # Janmashtami
        "2024-10-02",  # Gandhi Jayanti
        "2024-10-31",  # Diwali Laxmi Puja
        "2024-11-01",  # Diwali Balipratipada
        "2024-11-15",  # Guru Nanak Jayanti
    ],
    
    # Risk management parameters for Indian market
    "risk_parameters": {
        "max_position_size": 0.05,  # 5% of portfolio
        "stop_loss_default": 0.08,  # 8% stop loss
        "volatility_adjustment": 1.2,  # Indian markets are more volatile
        "liquidity_threshold": 1000000,  # Minimum daily volume in INR
        "market_cap_preference": "large_cap"  # Prefer large cap for stability
    },
    
    # Currency and conversion
    "currency_settings": {
        "base_currency": "INR",
        "usd_inr_tracking": True,
        "currency_hedging": False
    }
})

# Major Indian stocks for testing and validation
MAJOR_INDIAN_STOCKS = {
    # Large Cap - Nifty 50 constituents
    "RELIANCE": {"name": "Reliance Industries Ltd", "sector": "Energy", "exchange": "NSE"},
    "TCS": {"name": "Tata Consultancy Services", "sector": "IT", "exchange": "NSE"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "sector": "Banking", "exchange": "NSE"},
    "INFY": {"name": "Infosys Ltd", "sector": "IT", "exchange": "NSE"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "sector": "Banking", "exchange": "NSE"},
    "HINDUNILVR": {"name": "Hindustan Unilever Ltd", "sector": "FMCG", "exchange": "NSE"},
    "ITC": {"name": "ITC Ltd", "sector": "FMCG", "exchange": "NSE"},
    "SBIN": {"name": "State Bank of India", "sector": "Banking", "exchange": "NSE"},
    "BHARTIARTL": {"name": "Bharti Airtel Ltd", "sector": "Telecom", "exchange": "NSE"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank", "sector": "Banking", "exchange": "NSE"},
    "LT": {"name": "Larsen & Toubro Ltd", "sector": "Infrastructure", "exchange": "NSE"},
    "HCLTECH": {"name": "HCL Technologies Ltd", "sector": "IT", "exchange": "NSE"},
    "ASIANPAINT": {"name": "Asian Paints Ltd", "sector": "Paints", "exchange": "NSE"},
    "MARUTI": {"name": "Maruti Suzuki India Ltd", "sector": "Auto", "exchange": "NSE"},
    "BAJFINANCE": {"name": "Bajaj Finance Ltd", "sector": "NBFC", "exchange": "NSE"},
    "WIPRO": {"name": "Wipro Ltd", "sector": "IT", "exchange": "NSE"},
    "NESTLEIND": {"name": "Nestle India Ltd", "sector": "FMCG", "exchange": "NSE"},
    "ULTRACEMCO": {"name": "UltraTech Cement Ltd", "sector": "Cement", "exchange": "NSE"},
    "TITAN": {"name": "Titan Company Ltd", "sector": "Jewellery", "exchange": "NSE"},
    "POWERGRID": {"name": "Power Grid Corporation", "sector": "Power", "exchange": "NSE"}
}

# Sectoral classifications for Indian market
INDIAN_SECTORS = {
    "banking": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK"],
    "it": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM"],
    "fmcg": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA"],
    "auto": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO"],
    "pharma": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "energy": ["RELIANCE", "ONGC", "IOC", "BPCL"],
    "telecom": ["BHARTIARTL", "JIOFINANCE"],
    "metals": ["TATASTEEL", "HINDALCO", "VEDL", "JSW"],
    "cement": ["ULTRACEMCO", "SHREECEM", "ACC"],
    "nbfc": ["BAJFINANCE", "SBICARD", "CHOLAFIN"]
}

def get_indian_config() -> Dict[str, Any]:
    """Get the Indian market configuration"""
    return INDIAN_CONFIG.copy()

def get_major_stocks() -> Dict[str, Dict[str, str]]:
    """Get major Indian stocks dictionary"""
    return MAJOR_INDIAN_STOCKS.copy()

def get_sector_stocks(sector: str) -> List[str]:
    """Get stocks for a specific sector"""
    return INDIAN_SECTORS.get(sector.lower(), [])

def is_market_open() -> bool:
    """Check if Indian market is currently open"""
    import datetime
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Check trading hours
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_open <= now <= market_close

def get_market_status() -> str:
    """Get current market status"""
    import datetime
    
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    
    if now.weekday() >= 5:
        return "closed_weekend"
    
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    pre_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    
    if now < pre_open:
        return "pre_market"
    elif pre_open <= now < market_open:
        return "pre_open"
    elif market_open <= now <= market_close:
        return "open"
    else:
        return "closed" 