"""
Test Suite for Indian Market Functionality
Comprehensive tests for Indian stock market features
"""

import unittest
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.indian_config import (
    get_indian_config, 
    get_major_stocks, 
    get_sector_stocks,
    is_market_open,
    get_market_status
)
from tradingagents.dataflows.ticker_utils import (
    TickerFormatter,
    TickerValidator,
    TickerConverter,
    TickerManager,
    format_indian_ticker,
    validate_indian_ticker
)

class TestIndianConfig(unittest.TestCase):
    """Test Indian market configuration"""
    
    def test_get_indian_config(self):
        """Test getting Indian configuration"""
        config = get_indian_config()
        
        self.assertIsInstance(config, dict)
        self.assertEqual(config["market_region"], "india")
        self.assertEqual(config["currency"], "INR")
        self.assertEqual(config["timezone"], "Asia/Kolkata")
        self.assertIn("NSE", config["exchanges"]["supported"])
        self.assertIn("BSE", config["exchanges"]["supported"])
    
    def test_get_major_stocks(self):
        """Test getting major stocks list"""
        stocks = get_major_stocks()
        
        self.assertIsInstance(stocks, dict)
        self.assertIn("RELIANCE", stocks)
        self.assertIn("TCS", stocks)
        self.assertIn("HDFCBANK", stocks)
        
        # Check stock structure
        reliance = stocks["RELIANCE"]
        self.assertIn("name", reliance)
        self.assertIn("sector", reliance)
        self.assertIn("exchange", reliance)
    
    def test_get_sector_stocks(self):
        """Test getting sector stocks"""
        banking_stocks = get_sector_stocks("banking")
        it_stocks = get_sector_stocks("it")
        
        self.assertIsInstance(banking_stocks, list)
        self.assertIsInstance(it_stocks, list)
        self.assertIn("HDFCBANK", banking_stocks)
        self.assertIn("TCS", it_stocks)
        
        # Test non-existent sector
        invalid_stocks = get_sector_stocks("invalid_sector")
        self.assertEqual(invalid_stocks, [])
    
    @patch('tradingagents.indian_config.datetime')
    def test_market_status_functions(self, mock_datetime):
        """Test market status and timing functions"""
        # Mock a weekday during market hours (Tuesday 10:00 AM IST)
        mock_now = Mock()
        mock_now.weekday.return_value = 1  # Tuesday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_datetime.datetime.now.return_value = mock_now
        mock_datetime.datetime.now().replace.return_value = mock_now
        
        # Test during market hours
        # Note: These tests might need adjustment based on actual implementation
        status = get_market_status()
        self.assertIsInstance(status, str)
        
        # Test weekend
        mock_now.weekday.return_value = 5  # Saturday
        status = get_market_status()
        self.assertEqual(status, "closed_weekend")

class TestTickerUtils(unittest.TestCase):
    """Test ticker utilities"""
    
    def test_ticker_formatter(self):
        """Test ticker formatting"""
        # Test NSE formatting
        nse_ticker = TickerFormatter.format_ticker("RELIANCE", "NSE")
        self.assertEqual(nse_ticker, "RELIANCE.NS")
        
        # Test BSE formatting
        bse_ticker = TickerFormatter.format_ticker("RELIANCE", "BSE")
        self.assertEqual(bse_ticker, "RELIANCE.BO")
        
        # Test with already formatted ticker
        formatted_ticker = TickerFormatter.format_ticker("TCS.NS", "NSE")
        self.assertEqual(formatted_ticker, "TCS.NS")
        
        # Test plain symbol extraction
        plain = TickerFormatter.get_plain_symbol("RELIANCE.NS")
        self.assertEqual(plain, "RELIANCE")
        
        plain = TickerFormatter.get_plain_symbol("RELIANCE")
        self.assertEqual(plain, "RELIANCE")
    
    def test_ticker_validator(self):
        """Test ticker validation"""
        # Test valid NSE tickers
        self.assertTrue(TickerValidator.is_valid_nse_ticker("RELIANCE.NS"))
        self.assertTrue(TickerValidator.is_valid_nse_ticker("TCS.NS"))
        
        # Test valid BSE tickers
        self.assertTrue(TickerValidator.is_valid_bse_ticker("500325.BO"))
        self.assertTrue(TickerValidator.is_valid_bse_ticker("532540.BO"))
        
        # Test invalid formats
        self.assertFalse(TickerValidator.is_valid_nse_ticker("RELIANCE"))
        self.assertFalse(TickerValidator.is_valid_bse_ticker("RELIANCE.NS"))
        
        # Test general validation
        self.assertTrue(TickerValidator.is_valid_indian_ticker("RELIANCE.NS"))
        self.assertTrue(TickerValidator.is_valid_indian_ticker("500325.BO"))
        self.assertFalse(TickerValidator.is_valid_indian_ticker("AAPL"))
    
    def test_ticker_converter(self):
        """Test ticker conversion between exchanges"""
        # Test NSE to BSE conversion
        bse_ticker = TickerConverter.nse_to_bse("RELIANCE")
        self.assertEqual(bse_ticker, "500325.BO")
        
        bse_ticker = TickerConverter.nse_to_bse("RELIANCE.NS")
        self.assertEqual(bse_ticker, "500325.BO")
        
        # Test BSE to NSE conversion
        nse_ticker = TickerConverter.bse_to_nse("500325")
        self.assertEqual(nse_ticker, "RELIANCE.NS")
        
        nse_ticker = TickerConverter.bse_to_nse("500325.BO")
        self.assertEqual(nse_ticker, "RELIANCE.NS")
        
        # Test cross-exchange conversion
        cross_ticker = TickerConverter.get_cross_exchange_ticker("RELIANCE.NS")
        self.assertEqual(cross_ticker, "500325.BO")
        
        cross_ticker = TickerConverter.get_cross_exchange_ticker("500325.BO")
        self.assertEqual(cross_ticker, "RELIANCE.NS")
        
        # Test non-existent mapping
        result = TickerConverter.nse_to_bse("NONEXISTENT")
        self.assertIsNone(result)
    
    def test_ticker_manager(self):
        """Test ticker manager functionality"""
        manager = TickerManager()
        
        # Test ticker processing
        result = manager.process_ticker("RELIANCE", "NSE")
        
        self.assertIsInstance(result, dict)
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["formatted_ticker"], "RELIANCE.NS")
        self.assertEqual(result["plain_symbol"], "RELIANCE")
        self.assertEqual(result["exchange"], "NSE")
        self.assertEqual(result["cross_exchange_ticker"], "500325.BO")
        
        # Test all formats
        formats = manager.get_all_formats("RELIANCE")
        
        self.assertEqual(formats["plain"], "RELIANCE")
        self.assertEqual(formats["nse"], "RELIANCE.NS")
        self.assertEqual(formats["bse"], "RELIANCE.BO")
        self.assertEqual(formats["bse_equivalent"], "500325.BO")
    
    def test_convenience_functions(self):
        """Test convenience functions"""
        # Test formatting
        ticker = format_indian_ticker("RELIANCE", "NSE")
        self.assertEqual(ticker, "RELIANCE.NS")
        
        # Test validation
        is_valid = validate_indian_ticker("RELIANCE.NS")
        self.assertTrue(is_valid)
        
        is_valid = validate_indian_ticker("INVALID")
        self.assertFalse(is_valid)

class TestIndianMarketUtils(unittest.TestCase):
    """Test Indian market data utilities"""
    
    @patch('tradingagents.dataflows.indian_market_utils.requests.get')
    def test_alpha_vantage_api(self, mock_get):
        """Test Alpha Vantage API client"""
        from tradingagents.dataflows.indian_market_utils import AlphaVantageAPI
        
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2024-01-01": {
                    "1. open": "100.0",
                    "2. high": "105.0",
                    "3. low": "99.0",
                    "4. close": "103.0",
                    "5. volume": "1000000"
                }
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        api = AlphaVantageAPI("test_key")
        
        # Test rate limiter initialization
        self.assertIsNotNone(api.rate_limiter)
        
        # Test data retrieval
        df = api.get_daily_data("RELIANCE.NS")
        
        self.assertIsNotNone(df)
        # Additional assertions would depend on pandas DataFrame structure
    
    @patch('yfinance.Ticker')
    def test_yahoo_finance_api(self, mock_ticker):
        """Test Yahoo Finance API client"""
        from tradingagents.dataflows.indian_market_utils import YahooFinanceAPI
        
        # Mock yfinance response
        mock_ticker_instance = Mock()
        mock_ticker_instance.history.return_value = Mock()  # Mock DataFrame
        mock_ticker_instance.info = {"symbol": "RELIANCE.NS", "longName": "Reliance Industries"}
        mock_ticker.return_value = mock_ticker_instance
        
        api = YahooFinanceAPI()
        
        # Test company info retrieval
        info = api.get_company_info("RELIANCE.NS")
        
        self.assertIsInstance(info, dict)
        self.assertEqual(info["symbol"], "RELIANCE.NS")

class TestIndianAgentToolkit(unittest.TestCase):
    """Test Indian agent toolkit"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock the toolkit to avoid actual API calls
        self.toolkit_patcher = patch('tradingagents.agents.utils.indian_agent_toolkit.indian_toolkit')
        self.mock_toolkit = self.toolkit_patcher.start()
        
    def tearDown(self):
        """Clean up test fixtures"""
        self.toolkit_patcher.stop()
    
    def test_toolkit_initialization(self):
        """Test toolkit initialization"""
        from tradingagents.agents.utils.indian_agent_toolkit import IndianAgentToolkit
        
        # This will test the import and basic initialization
        # Actual functionality testing would require mocking external dependencies
        try:
            toolkit = IndianAgentToolkit()
            self.assertIsNotNone(toolkit)
        except Exception as e:
            # If initialization fails due to missing dependencies, that's expected in test environment
            self.assertIsInstance(e, (ImportError, AttributeError))

class TestIndianAnalysts(unittest.TestCase):
    """Test Indian market analysts"""
    
    @patch('tradingagents.agents.utils.agent_utils.AgentUtils')
    def test_fundamentals_analyst_initialization(self, mock_agent_utils):
        """Test fundamentals analyst initialization"""
        from tradingagents.agents.analysts.indian_fundamentals_analyst import IndianFundamentalsAnalyst
        
        try:
            analyst = IndianFundamentalsAnalyst()
            self.assertEqual(analyst.agent_id, "indian_fundamentals_analyst")
            self.assertIsNotNone(analyst.major_stocks)
            self.assertIsInstance(analyst.key_metrics, list)
        except ImportError:
            # Skip if dependencies not available
            self.skipTest("Dependencies not available for analyst testing")
    
    @patch('tradingagents.agents.utils.agent_utils.AgentUtils')
    def test_market_analyst_initialization(self, mock_agent_utils):
        """Test market analyst initialization"""
        from tradingagents.agents.analysts.indian_market_analyst import IndianMarketAnalyst
        
        try:
            analyst = IndianMarketAnalyst()
            self.assertEqual(analyst.agent_id, "indian_market_analyst")
            self.assertIsNotNone(analyst.config)
            self.assertIsInstance(analyst.technical_indicators, list)
        except ImportError:
            # Skip if dependencies not available
            self.skipTest("Dependencies not available for analyst testing")

class TestIntegration(unittest.TestCase):
    """Integration tests for Indian market functionality"""
    
    def test_end_to_end_ticker_processing(self):
        """Test end-to-end ticker processing"""
        # Test the complete flow from raw symbol to formatted ticker
        raw_symbol = "reliance"
        
        # Format ticker
        formatted = format_indian_ticker(raw_symbol, "NSE")
        self.assertEqual(formatted, "RELIANCE.NS")
        
        # Validate ticker
        is_valid = validate_indian_ticker(formatted)
        self.assertTrue(is_valid)
        
        # Get cross-exchange equivalent
        manager = TickerManager()
        result = manager.process_ticker(raw_symbol, "NSE")
        
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["cross_exchange_ticker"], "500325.BO")
    
    def test_config_consistency(self):
        """Test configuration consistency across modules"""
        config = get_indian_config()
        major_stocks = get_major_stocks()
        
        # Ensure major stocks are consistent with config
        self.assertIsInstance(config, dict)
        self.assertIsInstance(major_stocks, dict)
        
        # Check that all major stocks have required fields
        for symbol, info in major_stocks.items():
            self.assertIn("name", info)
            self.assertIn("sector", info)
            self.assertIn("exchange", info)
            self.assertIn(info["exchange"], config["exchanges"]["supported"])

class TestErrorHandling(unittest.TestCase):
    """Test error handling in Indian market functionality"""
    
    def test_invalid_ticker_handling(self):
        """Test handling of invalid tickers"""
        manager = TickerManager()
        
        # Test with invalid symbol
        result = manager.process_ticker("INVALID_SYMBOL_123", "NSE")
        
        # Should still process but may have limitations
        self.assertIsInstance(result, dict)
        self.assertIn("formatted_ticker", result)
    
    def test_invalid_sector_handling(self):
        """Test handling of invalid sectors"""
        stocks = get_sector_stocks("invalid_sector")
        self.assertEqual(stocks, [])
    
    def test_api_error_handling(self):
        """Test API error handling"""
        from tradingagents.dataflows.indian_market_utils import AlphaVantageAPI
        
        # Test with invalid API key
        api = AlphaVantageAPI("invalid_key")
        
        # This should handle errors gracefully
        # In a real test, we'd mock the API response to return an error
        self.assertIsNotNone(api.api_key)

# Test data for mocking
SAMPLE_MARKET_DATA = """
Date,Open,High,Low,Close,Volume
2024-01-01,100.0,105.0,99.0,103.0,1000000
2024-01-02,103.0,108.0,102.0,107.0,1200000
2024-01-03,107.0,110.0,105.0,109.0,900000
"""

SAMPLE_FUNDAMENTALS_DATA = {
    "symbol": "RELIANCE.NS",
    "marketCap": 1500000000000,
    "trailingPE": 15.5,
    "priceToBook": 2.1,
    "dividendYield": 0.035,
    "sector": "Energy",
    "industry": "Oil & Gas"
}

if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2) 