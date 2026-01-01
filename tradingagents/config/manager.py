"""
Centralized configuration management for TradingAgents.

This module provides a Settings class that loads environment variables
once and makes them available as attributes throughout the application.
"""
import os
from typing import Dict, Any, List
from dotenv import load_dotenv


class Settings:
    """Application settings loaded from environment variables and defaults."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._load_environment()
            self._load_settings()
            Settings._initialized = True
    
    def _load_environment(self):
        """Load environment variables from .env file if it exists."""
        # Try to find .env file starting from current directory and going up
        env_file = None
        current_dir = os.getcwd()
        
        # Check common locations
        possible_locations = [
            current_dir,
            os.path.dirname(__file__),
            os.path.dirname(os.path.dirname(__file__)),  # tradingagents dir
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # project root
        ]
        
        for location in possible_locations:
            env_path = os.path.join(location, '.env')
            if os.path.exists(env_path):
                env_file = env_path
                break
        
        if env_file:
            print(f"INFO: Loading environment from {env_file}")
            load_dotenv(env_file)
        else:
            print("INFO: No .env file found, using system environment variables")
    
    def _load_settings(self):
        """Load all settings from environment variables with defaults."""
        
        # App settings
        self.APP_HOST = os.getenv("APP_HOST", "localhost")
        self.APP_PORT = int(os.getenv("APP_PORT", 8000))
        
        # Directory settings
        self.PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.RESULTS_DIR = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
        self.DATA_DIR = os.getenv("TRADINGAGENTS_DATA_DIR", "/Users/yluo/Documents/Code/ScAI/FR1-data")
        self.DATA_CACHE_DIR = os.path.join(self.PROJECT_DIR, "dataflows/data_cache")
        
        # LLM settings
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
        self.DEEP_THINK_LLM = os.getenv("DEEP_THINK_LLM", "gpt-4o-mini")
        self.QUICK_THINK_LLM = os.getenv("QUICK_THINK_LLM", "gpt-4o-mini")
        self.BACKEND_URL = os.getenv("BACKEND_URL", "https://api.openai.com/v1")
        
        # Debate and discussion settings
        self.MAX_DEBATE_ROUNDS = int(os.getenv("MAX_DEBATE_ROUNDS", 1))
        self.MAX_RISK_DISCUSS_ROUNDS = int(os.getenv("MAX_RISK_DISCUSS_ROUNDS", 1))
        self.MAX_RECUR_LIMIT = int(os.getenv("MAX_RECUR_LIMIT", 100))
        
        # Data vendor settings
        self.CORE_CRYPTO_APIS = os.getenv("CORE_CRYPTO_APIS", "bybit")
        self.CORE_STOCK_APIS = os.getenv("CORE_STOCK_APIS", "yfinance")
        self.TECHNICAL_INDICATORS = os.getenv("TECHNICAL_INDICATORS", "bybit")
        self.FUNDAMENTAL_DATA = os.getenv("FUNDAMENTAL_DATA", "alpha_vantage")
        self.NEWS_DATA = os.getenv("NEWS_DATA", "openai")
        self.PROFILE_DATA = os.getenv("PROFILE_DATA", "bybit")
        
        # Tool overrides
        self.TOOL_GET_GLOBAL_NEWS = os.getenv("TOOL_GET_GLOBAL_NEWS", "telegram")
        
        # External API settings
        self.BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
        self.TAAPI_BASE_URL = os.getenv("TAAPI_BASE_URL", "https://api.taapi.io")
        self.TAAPI_API_KEY = os.getenv("TAAPI_API_KEY", "")
        self.BYBIT_BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api-demo.bybit.com")
        self.BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
        self.BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")
        self.COIN_GECKO_API_BASE_URL = os.getenv("COIN_GECKO_API_BASE_URL", "https://api.coingecko.com/api/v3")
        self.TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
        self.TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
        self.TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "")
        
        # Redis settings
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        self.REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "defaultpassword")
        self.REDIS_DB = int(os.getenv("REDIS_DB", 0))
        
        # RQ settings
        self.RQ_RETRIES = int(os.getenv("RQ_RETRIES", 3))
        self.RQ_INTERVALS = [
            int(x.strip()) for x in os.getenv("RQ_INTERVALS", "30,60,120").split(",")
        ]
    
    @property
    def data_vendors(self) -> Dict[str, str]:
        """Get data vendors configuration as dictionary for backwards compatibility."""
        return {
            "core_crypto_apis": self.CORE_CRYPTO_APIS,
            "core_stock_apis": self.CORE_STOCK_APIS,
            "technical_indicators": self.TECHNICAL_INDICATORS,
            "fundamental_data": self.FUNDAMENTAL_DATA,
            "news_data": self.NEWS_DATA,
            "profile_data": self.PROFILE_DATA,
        }
    
    @property
    def tool_vendors(self) -> Dict[str, str]:
        """Get tool vendors configuration as dictionary for backwards compatibility."""
        return {
            "get_global_news": self.TOOL_GET_GLOBAL_NEWS
        }
    
    @property
    def tool_providers(self) -> Dict[str, str]:
        """Get tool providers configuration as dictionary for backwards compatibility."""
        return {
            "TAAPI_BASE_URL": self.TAAPI_BASE_URL,
        }
    
    @property
    def external(self) -> Dict[str, str]:
        """Get external APIs configuration as dictionary for backwards compatibility."""
        return {
            "BINANCE_API_KEY": self.BINANCE_API_KEY,
            "TAAPI_BASE_URL": self.TAAPI_BASE_URL,
            "TAAPI_API_KEY": self.TAAPI_API_KEY,
            "BYBIT_BASE_URL": self.BYBIT_BASE_URL,
            "BYBIT_API_KEY": self.BYBIT_API_KEY,
            "BYBIT_API_SECRET": self.BYBIT_API_SECRET,
            "COIN_GECKO_API_BASE_URL": self.COIN_GECKO_API_BASE_URL,
            "TELEGRAM_API_ID": self.TELEGRAM_API_ID,
            "TELEGRAM_API_HASH": self.TELEGRAM_API_HASH,
            "TELEGRAM_SESSION_NAME": self.TELEGRAM_SESSION_NAME,
        }
    
    @property
    def redis(self) -> Dict[str, Any]:
        """Get Redis configuration as dictionary for backwards compatibility."""
        return {
            "REDIS_HOST": self.REDIS_HOST,
            "REDIS_PORT": self.REDIS_PORT,
            "REDIS_PASSWORD": self.REDIS_PASSWORD,
            "REDIS_DB": self.REDIS_DB,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary for backwards compatibility."""
        return {
            # App config
            "APP_HOST": self.APP_HOST,
            "APP_PORT": self.APP_PORT,
            
            # Directory settings
            "project_dir": self.PROJECT_DIR,
            "results_dir": self.RESULTS_DIR,
            "data_dir": self.DATA_DIR,
            "data_cache_dir": self.DATA_CACHE_DIR,
            
            # LLM settings
            "llm_provider": self.LLM_PROVIDER,
            "deep_think_llm": self.DEEP_THINK_LLM,
            "quick_think_llm": self.QUICK_THINK_LLM,
            "backend_url": self.BACKEND_URL,
            
            # Debate settings
            "max_debate_rounds": self.MAX_DEBATE_ROUNDS,
            "max_risk_discuss_rounds": self.MAX_RISK_DISCUSS_ROUNDS,
            "max_recur_limit": self.MAX_RECUR_LIMIT,
            
            # Data vendors
            "data_vendors": self.data_vendors,
            "tool_vendors": self.tool_vendors,
            "tool_providers": self.tool_providers,
            "external": self.external,
            "redis": self.redis,
        }


# Global singleton instance
settings = Settings()


# Backwards compatibility functions
def get_config() -> Dict[str, Any]:
    """Get configuration as dictionary for backwards compatibility."""
    return settings.to_dict()


def update_config(updates: Dict[str, Any]) -> None:
    """Update configuration for backwards compatibility."""
    # Update settings attributes based on dictionary updates
    for key, value in updates.items():
        if key == "llm_provider":
            settings.LLM_PROVIDER = value
        elif key == "deep_think_llm":
            settings.DEEP_THINK_LLM = value
        elif key == "quick_think_llm":
            settings.QUICK_THINK_LLM = value
        elif key == "backend_url":
            settings.BACKEND_URL = value
        elif key == "max_debate_rounds":
            settings.MAX_DEBATE_ROUNDS = value
        elif key == "max_risk_discuss_rounds":
            settings.MAX_RISK_DISCUSS_ROUNDS = value
        elif key == "data_vendors" and isinstance(value, dict):
            for vendor_key, vendor_value in value.items():
                if vendor_key == "core_crypto_apis":
                    settings.CORE_CRYPTO_APIS = vendor_value
                elif vendor_key == "core_stock_apis":
                    settings.CORE_STOCK_APIS = vendor_value
                elif vendor_key == "technical_indicators":
                    settings.TECHNICAL_INDICATORS = vendor_value
                elif vendor_key == "fundamental_data":
                    settings.FUNDAMENTAL_DATA = vendor_value
                elif vendor_key == "news_data":
                    settings.NEWS_DATA = vendor_value
                elif vendor_key == "profile_data":
                    settings.PROFILE_DATA = vendor_value


def set_config(config: Dict[str, Any]) -> None:
    """Set/update configuration. For backwards compatibility."""
    update_config(config)


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a specific configuration value."""
    return getattr(settings, key.upper(), default)


def get_nested_config(*keys: str, default: Any = None) -> Any:
    """Get a nested configuration value."""
    if len(keys) == 1:
        return getattr(settings, keys[0].upper(), default)
    
    # Handle nested keys for backwards compatibility
    if len(keys) == 2:
        if keys[0] == "redis":
            return getattr(settings, f"REDIS_{keys[1]}", default)
        elif keys[0] == "external":
            return getattr(settings, keys[1], default)
    
    return default


def initialize_config() -> None:
    """Force initialization of configuration."""
    settings._load_settings()


# Convenience functions
def get_redis_config() -> Dict[str, Any]:
    """Get Redis configuration."""
    return settings.redis


def get_external_config() -> Dict[str, Any]:
    """Get external APIs configuration."""
    return settings.external


def get_rq_config() -> Dict[str, Any]:
    """Get RQ configuration."""
    return {
        "RQ_RETRIES": settings.RQ_RETRIES,
        "RQ_INTERVALS": settings.RQ_INTERVALS,
    }
