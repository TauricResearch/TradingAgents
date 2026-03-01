"""
Ticker utilities for Indian stock exchanges (NSE/BSE)
Handles ticker formatting, validation, and exchange-specific operations
"""

import re
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class IndianExchange(Enum):
    """Indian stock exchanges"""
    NSE = "NSE"
    BSE = "BSE"

# NSE and BSE ticker patterns
NSE_PATTERN = re.compile(r'^[A-Z0-9&\-]+\.NS$')
BSE_PATTERN = re.compile(r'^[A-Z0-9&\-]+\.BO$')
PLAIN_PATTERN = re.compile(r'^[A-Z0-9&\-]+$')

# Exchange suffixes
EXCHANGE_SUFFIXES = {
    IndianExchange.NSE: ".NS",
    IndianExchange.BSE: ".BO"
}

# Common ticker mappings between exchanges
NSE_TO_BSE_MAPPING = {
    "RELIANCE": "500325",
    "TCS": "532540", 
    "HDFCBANK": "500180",
    "INFY": "500209",
    "ICICIBANK": "532174",
    "HINDUNILVR": "500696",
    "ITC": "500875",
    "SBIN": "500112",
    "BHARTIARTL": "532454",
    "KOTAKBANK": "500247",
    "LT": "500510",
    "HCLTECH": "532281",
    "ASIANPAINT": "500820",
    "MARUTI": "532500",
    "BAJFINANCE": "500034",
    "WIPRO": "507685",
    "NESTLEIND": "500790",
    "ULTRACEMCO": "532538",
    "TITAN": "500114",
    "POWERGRID": "532898"
}

# Reverse mapping
BSE_TO_NSE_MAPPING = {v: k for k, v in NSE_TO_BSE_MAPPING.items()}

class TickerFormatter:
    """Handles ticker formatting for Indian exchanges"""
    
    @staticmethod
    def format_ticker(symbol: str, exchange: Union[str, IndianExchange] = IndianExchange.NSE) -> str:
        """
        Format ticker symbol for specified exchange
        
        Args:
            symbol: Raw ticker symbol (e.g., 'RELIANCE', 'TCS')
            exchange: Target exchange (NSE or BSE)
            
        Returns:
            Formatted ticker (e.g., 'RELIANCE.NS', 'TCS.NS')
        """
        if isinstance(exchange, str):
            exchange = IndianExchange(exchange.upper())
            
        # Clean the symbol
        clean_symbol = symbol.upper().strip()
        
        # Remove existing suffixes if present
        if clean_symbol.endswith(('.NS', '.BO')):
            clean_symbol = clean_symbol[:-3]
        
        # Add appropriate suffix
        suffix = EXCHANGE_SUFFIXES[exchange]
        return f"{clean_symbol}{suffix}"
    
    @staticmethod
    def format_nse_ticker(symbol: str) -> str:
        """Format ticker for NSE"""
        return TickerFormatter.format_ticker(symbol, IndianExchange.NSE)
    
    @staticmethod
    def format_bse_ticker(symbol: str) -> str:
        """Format ticker for BSE"""
        return TickerFormatter.format_ticker(symbol, IndianExchange.BSE)
    
    @staticmethod
    def get_plain_symbol(ticker: str) -> str:
        """
        Extract plain symbol from formatted ticker
        
        Args:
            ticker: Formatted ticker (e.g., 'RELIANCE.NS')
            
        Returns:
            Plain symbol (e.g., 'RELIANCE')
        """
        if ticker.endswith(('.NS', '.BO')):
            return ticker[:-3]
        return ticker.upper()

class TickerValidator:
    """Validates ticker symbols and formats"""
    
    @staticmethod
    def is_valid_nse_ticker(ticker: str) -> bool:
        """Check if ticker is valid NSE format"""
        return bool(NSE_PATTERN.match(ticker))
    
    @staticmethod
    def is_valid_bse_ticker(ticker: str) -> bool:
        """Check if ticker is valid BSE format"""
        return bool(BSE_PATTERN.match(ticker))
    
    @staticmethod
    def is_valid_indian_ticker(ticker: str) -> bool:
        """Check if ticker is valid for any Indian exchange"""
        return (TickerValidator.is_valid_nse_ticker(ticker) or 
                TickerValidator.is_valid_bse_ticker(ticker))
    
    @staticmethod
    def get_exchange_from_ticker(ticker: str) -> Optional[IndianExchange]:
        """
        Determine exchange from ticker format
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            Exchange enum or None if not recognized
        """
        if TickerValidator.is_valid_nse_ticker(ticker):
            return IndianExchange.NSE
        elif TickerValidator.is_valid_bse_ticker(ticker):
            return IndianExchange.BSE
        return None
    
    @staticmethod
    def validate_and_format(symbol: str, preferred_exchange: str = "NSE") -> Tuple[bool, str, str]:
        """
        Validate symbol and return formatted ticker
        
        Args:
            symbol: Input symbol
            preferred_exchange: Preferred exchange if not specified
            
        Returns:
            Tuple of (is_valid, formatted_ticker, exchange)
        """
        try:
            # Check if already formatted
            exchange = TickerValidator.get_exchange_from_ticker(symbol)
            if exchange:
                return True, symbol, exchange.value
            
            # Try to format for preferred exchange
            formatted = TickerFormatter.format_ticker(symbol, preferred_exchange)
            return True, formatted, preferred_exchange.upper()
            
        except Exception as e:
            logger.error(f"Error validating ticker {symbol}: {e}")
            return False, symbol, ""

class TickerConverter:
    """Converts tickers between exchanges"""
    
    @staticmethod
    def nse_to_bse(nse_symbol: str) -> Optional[str]:
        """
        Convert NSE symbol to BSE equivalent
        
        Args:
            nse_symbol: NSE symbol (with or without .NS suffix)
            
        Returns:
            BSE ticker with .BO suffix or None if not found
        """
        plain_symbol = TickerFormatter.get_plain_symbol(nse_symbol)
        bse_code = NSE_TO_BSE_MAPPING.get(plain_symbol)
        
        if bse_code:
            return f"{bse_code}.BO"
        return None
    
    @staticmethod
    def bse_to_nse(bse_symbol: str) -> Optional[str]:
        """
        Convert BSE symbol to NSE equivalent
        
        Args:
            bse_symbol: BSE symbol (with or without .BO suffix)
            
        Returns:
            NSE ticker with .NS suffix or None if not found
        """
        plain_symbol = TickerFormatter.get_plain_symbol(bse_symbol)
        nse_symbol = BSE_TO_NSE_MAPPING.get(plain_symbol)
        
        if nse_symbol:
            return f"{nse_symbol}.NS"
        return None
    
    @staticmethod
    def get_cross_exchange_ticker(ticker: str) -> Optional[str]:
        """
        Get equivalent ticker on the other exchange
        
        Args:
            ticker: Input ticker
            
        Returns:
            Cross-exchange ticker or None if not found
        """
        exchange = TickerValidator.get_exchange_from_ticker(ticker)
        
        if exchange == IndianExchange.NSE:
            return TickerConverter.nse_to_bse(ticker)
        elif exchange == IndianExchange.BSE:
            return TickerConverter.bse_to_nse(ticker)
        
        return None

class TickerManager:
    """Main interface for ticker operations"""
    
    def __init__(self):
        self.formatter = TickerFormatter()
        self.validator = TickerValidator()
        self.converter = TickerConverter()
    
    def process_ticker(self, symbol: str, exchange: str = "NSE") -> Dict[str, Union[str, bool]]:
        """
        Process ticker symbol and return comprehensive information
        
        Args:
            symbol: Input ticker symbol
            exchange: Preferred exchange
            
        Returns:
            Dictionary with ticker information
        """
        result = {
            "original": symbol,
            "is_valid": False,
            "formatted_ticker": "",
            "plain_symbol": "",
            "exchange": "",
            "cross_exchange_ticker": None,
            "error": None
        }
        
        try:
            # Validate and format
            is_valid, formatted, detected_exchange = self.validator.validate_and_format(
                symbol, exchange
            )
            
            if is_valid:
                result.update({
                    "is_valid": True,
                    "formatted_ticker": formatted,
                    "plain_symbol": self.formatter.get_plain_symbol(formatted),
                    "exchange": detected_exchange,
                    "cross_exchange_ticker": self.converter.get_cross_exchange_ticker(formatted)
                })
            else:
                result["error"] = f"Invalid ticker format: {symbol}"
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error processing ticker {symbol}: {e}")
        
        return result
    
    def get_all_formats(self, symbol: str) -> Dict[str, Optional[str]]:
        """
        Get ticker in all available formats
        
        Args:
            symbol: Input symbol
            
        Returns:
            Dictionary with all ticker formats
        """
        plain = self.formatter.get_plain_symbol(symbol)
        
        return {
            "plain": plain,
            "nse": self.formatter.format_nse_ticker(plain),
            "bse": self.formatter.format_bse_ticker(plain),
            "bse_equivalent": self.converter.nse_to_bse(plain),
            "nse_equivalent": self.converter.bse_to_nse(plain)
        }

# Convenience functions for common operations
def format_indian_ticker(symbol: str, exchange: str = "NSE") -> str:
    """Format ticker for Indian exchange"""
    return TickerFormatter.format_ticker(symbol, exchange)

def validate_indian_ticker(ticker: str) -> bool:
    """Validate Indian ticker format"""
    return TickerValidator.is_valid_indian_ticker(ticker)

def get_plain_symbol(ticker: str) -> str:
    """Get plain symbol from formatted ticker"""
    return TickerFormatter.get_plain_symbol(ticker)

def process_ticker_list(symbols: List[str], exchange: str = "NSE") -> List[Dict[str, Union[str, bool]]]:
    """Process multiple ticker symbols"""
    manager = TickerManager()
    return [manager.process_ticker(symbol, exchange) for symbol in symbols]

# Predefined lists for validation
VALID_NSE_SYMBOLS = list(NSE_TO_BSE_MAPPING.keys())
VALID_BSE_SYMBOLS = list(BSE_TO_NSE_MAPPING.keys())

def get_supported_symbols(exchange: str = "NSE") -> List[str]:
    """Get list of supported symbols for exchange"""
    if exchange.upper() == "NSE":
        return VALID_NSE_SYMBOLS.copy()
    elif exchange.upper() == "BSE":
        return VALID_BSE_SYMBOLS.copy()
    else:
        return VALID_NSE_SYMBOLS + VALID_BSE_SYMBOLS

# Example usage and testing
if __name__ == "__main__":
    # Test the ticker utilities
    manager = TickerManager()
    
    test_symbols = ["RELIANCE", "TCS.NS", "500325.BO", "INVALID"]
    
    for symbol in test_symbols:
        result = manager.process_ticker(symbol)
        print(f"Symbol: {symbol}")
        print(f"Result: {result}")
        print("-" * 50) 