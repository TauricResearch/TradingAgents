"""
Unit Tests for Ticker Anonymizer

Tests:
- Ticker anonymization (deterministic hashing)
- Text anonymization (company names, products)
- Price normalization with Adj Close
- Dividend/split handling
- Edge cases (empty data, invalid prices)
"""

import unittest
import pandas as pd
import numpy as np
from pathlib import Path
import tempfile
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.utils.anonymizer import TickerAnonymizer


class TestTickerAnonymizer(unittest.TestCase):
    """Test suite for TickerAnonymizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.anonymizer = TickerAnonymizer(seed="test_seed")
    
    def test_ticker_anonymization_deterministic(self):
        """Test that ticker anonymization is deterministic."""
        ticker = "AAPL"
        anon1 = self.anonymizer.anonymize_ticker(ticker)
        anon2 = self.anonymizer.anonymize_ticker(ticker)
        
        self.assertEqual(anon1, anon2, "Anonymization should be deterministic")
        self.assertTrue(anon1.startswith("ASSET_"), "Should start with ASSET_")
        self.assertNotEqual(anon1, ticker, "Should be different from original")
    
    def test_different_tickers_different_labels(self):
        """Test that different tickers get different labels."""
        anon_aapl = self.anonymizer.anonymize_ticker("AAPL")
        anon_msft = self.anonymizer.anonymize_ticker("MSFT")
        
        self.assertNotEqual(anon_aapl, anon_msft, "Different tickers should have different labels")
    
    def test_text_anonymization_ticker(self):
        """Test ticker replacement in text."""
        ticker = "AAPL"
        text = "AAPL stock rose 5% today"
        anon_text = self.anonymizer.anonymize_text(text, ticker)
        
        self.assertNotIn("AAPL", anon_text, "Original ticker should be removed")
        self.assertIn("ASSET_", anon_text, "Should contain anonymous label")
    
    def test_text_anonymization_company_name(self):
        """Test company name replacement."""
        ticker = "AAPL"
        self.anonymizer.set_company_name(ticker, "Apple Inc.")
        
        text = "Apple Inc. reported strong earnings"
        anon_text = self.anonymizer.anonymize_text(text, ticker)
        
        self.assertNotIn("Apple Inc.", anon_text, "Company name should be removed")
        self.assertIn("Company ASSET_", anon_text, "Should contain anonymous company label")
    
    def test_text_anonymization_products(self):
        """Test product name replacement."""
        ticker = "AAPL"
        text = "iPhone sales exceeded expectations"
        anon_text = self.anonymizer.anonymize_text(text, ticker)
        
        self.assertNotIn("iPhone", anon_text, "Product name should be removed")
        self.assertIn("Product A", anon_text, "Should contain anonymous product label")
    
    def test_price_normalization_basic(self):
        """Test basic price normalization to base-100."""
        df = pd.DataFrame({
            'Date': pd.date_range('2024-01-01', periods=5),
            'Open': [150.0, 152.0, 151.0, 153.0, 155.0],
            'High': [152.0, 154.0, 153.0, 155.0, 157.0],
            'Low': [149.0, 151.0, 150.0, 152.0, 154.0],
            'Close': [151.0, 153.0, 152.0, 154.0, 156.0],
            'Volume': [1000000] * 5
        })
        
        df_normalized = self.anonymizer.normalize_price_series(df, base_value=100.0, use_adjusted=False)
        
        # First close should be 100.0
        self.assertAlmostEqual(df_normalized['Close'].iloc[0], 100.0, places=2)
        
        # Relative changes should be preserved
        original_pct_change = (df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1
        normalized_pct_change = (df_normalized['Close'].iloc[-1] / df_normalized['Close'].iloc[0]) - 1
        
        self.assertAlmostEqual(original_pct_change, normalized_pct_change, places=6,
                              msg="Percentage changes should be preserved")
    
    def test_price_normalization_with_adj_close(self):
        """Test price normalization using Adj Close (handles dividends/splits)."""
        df = pd.DataFrame({
            'Date': pd.date_range('2024-01-01', periods=5),
            'Open': [150.0, 152.0, 151.0, 153.0, 155.0],
            'High': [152.0, 154.0, 153.0, 155.0, 157.0],
            'Low': [149.0, 151.0, 150.0, 152.0, 154.0],
            'Close': [151.0, 153.0, 152.0, 154.0, 156.0],
            'Adj Close': [150.5, 152.5, 151.5, 153.5, 155.5],  # Adjusted for dividends
            'Volume': [1000000] * 5
        })
        
        df_normalized = self.anonymizer.normalize_price_series(df, base_value=100.0, use_adjusted=True)
        
        # Should use Adj Close as baseline
        baseline = df['Adj Close'].iloc[0]
        expected_first_close = (df['Close'].iloc[0] / baseline) * 100.0
        
        self.assertAlmostEqual(df_normalized['Close'].iloc[0], expected_first_close, places=2)
    
    def test_price_normalization_preserves_volume(self):
        """Test that volume is not normalized."""
        df = pd.DataFrame({
            'Date': pd.date_range('2024-01-01', periods=3),
            'Close': [150.0, 153.0, 156.0],
            'Volume': [1000000, 1500000, 2000000]
        })
        
        df_normalized = self.anonymizer.normalize_price_series(df, use_adjusted=False)
        
        # Volume should remain unchanged
        pd.testing.assert_series_equal(df['Volume'], df_normalized['Volume'])
    
    def test_price_normalization_empty_dataframe(self):
        """Test that empty DataFrame raises error."""
        df = pd.DataFrame()
        
        with self.assertRaises(ValueError):
            self.anonymizer.normalize_price_series(df)
    
    def test_price_normalization_invalid_baseline(self):
        """Test that invalid baseline (zero or negative) raises error."""
        df = pd.DataFrame({
            'Close': [0.0, 10.0, 20.0]  # First value is zero
        })
        
        with self.assertRaises(ValueError):
            self.anonymizer.normalize_price_series(df, use_adjusted=False)
    
    def test_price_normalization_missing_close_column(self):
        """Test that missing Close column raises error."""
        df = pd.DataFrame({
            'Open': [150.0, 152.0],
            'Volume': [1000000, 1500000]
        })
        
        with self.assertRaises(ValueError):
            self.anonymizer.normalize_price_series(df, use_adjusted=False)
    
    def test_normalize_single_value(self):
        """Test normalizing a single price value."""
        value = 153.0
        baseline = 150.0
        normalized = self.anonymizer.normalize_price_value(value, baseline, base_value=100.0)
        
        expected = (153.0 / 150.0) * 100.0
        self.assertAlmostEqual(normalized, expected, places=2)
    
    def test_normalize_single_value_invalid_baseline(self):
        """Test that invalid baseline raises error."""
        with self.assertRaises(ValueError):
            self.anonymizer.normalize_price_value(100.0, 0.0)
    
    def test_save_and_load_mapping(self):
        """Test saving and loading ticker mappings."""
        # Create some mappings
        self.anonymizer.anonymize_ticker("AAPL")
        self.anonymizer.anonymize_ticker("MSFT")
        self.anonymizer.set_company_name("AAPL", "Apple Inc.")
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = Path(f.name)
        
        try:
            self.anonymizer.save_mapping(temp_path)
            
            # Load into new anonymizer
            new_anonymizer = TickerAnonymizer()
            new_anonymizer.load_mapping(temp_path)
            
            # Check mappings are preserved
            self.assertEqual(
                self.anonymizer.ticker_map,
                new_anonymizer.ticker_map,
                "Ticker mappings should be preserved"
            )
            self.assertEqual(
                self.anonymizer.company_names,
                new_anonymizer.company_names,
                "Company names should be preserved"
            )
        finally:
            temp_path.unlink()
    
    def test_deanonymize_ticker(self):
        """Test reverse mapping from anonymous to original ticker."""
        ticker = "AAPL"
        anon_ticker = self.anonymizer.anonymize_ticker(ticker)
        
        original = self.anonymizer.deanonymize_ticker(anon_ticker)
        self.assertEqual(original, ticker, "Should reverse map correctly")
    
    def test_anonymize_csv(self):
        """Test anonymizing a CSV file."""
        # Create test CSV
        df = pd.DataFrame({
            'Date': pd.date_range('2024-01-01', periods=3),
            'Close': [150.0, 153.0, 156.0],
            'Adj Close': [150.0, 153.0, 156.0],
            'Volume': [1000000, 1500000, 2000000]
        })
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            input_path = Path(f.name)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            output_path = Path(f.name)
        
        try:
            df.to_csv(input_path, index=False)
            
            self.anonymizer.anonymize_csv(input_path, output_path, "AAPL", normalize_prices=True)
            
            # Read output
            df_output = pd.read_csv(output_path)
            
            # Check normalization
            self.assertAlmostEqual(df_output['Close'].iloc[0], 100.0, places=1)
            
        finally:
            input_path.unlink()
            output_path.unlink()


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
