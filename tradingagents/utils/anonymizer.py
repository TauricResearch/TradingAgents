"""
Ticker Anonymizer - Production Implementation

Handles:
- Ticker masking (AAPL → ASSET_042)
- Company name anonymization
- Product name anonymization
- Price normalization to base-100 index
- CRITICAL: Uses Adj Close to handle dividends/splits correctly
"""

import hashlib
import re
import json
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np


class TickerAnonymizer:
    """
    Anonymize tickers and normalize prices to prevent LLM identification.
    
    CRITICAL: Uses adjusted close prices to handle dividends and splits.
    """
    
    def __init__(self, seed: str = "blindfire_v1", auto_persist: bool = True):
        self.seed = seed
        self.ticker_map = {}
        self.reverse_map = {}
        self.company_names = {}
        self.baseline_prices = {}  # Store baseline for normalization
        self.auto_persist = auto_persist
        
        # Persistence path
        self.map_file = Path("ticker_map.json")
        if self.auto_persist:
            self._load_from_file()
        
        # Product name mappings
        self.product_map = {
            # Apple
            "iPhone": "Product A",
            "iPad": "Product B",
            "MacBook": "Product C",
            "Apple Watch": "Product D",
            "AirPods": "Product E",
            # Nvidia
            "GeForce": "Product X",
            "RTX": "Product Y",
            "H100": "Product Z",
            "A100": "Product W",
            # Microsoft
            "Windows": "Software Platform A",
            "Office": "Software Platform B",
            "Azure": "Cloud Platform A",
            # Meta
            "Facebook": "Social Platform A",
            "Instagram": "Social Platform B",
            "WhatsApp": "Messaging Platform A",
            # Google
            "Search": "Platform Service A",
            "YouTube": "Video Platform A",
            "Android": "Mobile OS A",
        }
        
    def _load_from_file(self):
        """Load mapping from disk if exists"""
        if self.map_file.exists():
            try:
                with open(self.map_file, 'r') as f:
                    data = json.load(f)
                    # Merge loaded data
                    self.ticker_map.update(data.get("ticker_map", {}))
                    self.reverse_map.update(data.get("reverse_map", {}))
                    self.company_names.update(data.get("company_names", {}))
            except Exception as e:
                print(f"Warning: Failed to load ticker map: {e}")

    def _save_to_file(self):
        """Save mapping to disk"""
        if not self.auto_persist:
            return
        
        data = {
            "ticker_map": self.ticker_map,
            "reverse_map": self.reverse_map,
            "company_names": self.company_names,
            "seed": self.seed
        }
        try:
            with open(self.map_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save ticker map: {e}")
    
    def anonymize_ticker(self, ticker: str) -> str:
        """
        Map ticker to anonymous label using deterministic hash.
        
        Args:
            ticker: Original ticker symbol (e.g., "AAPL")
        
        Returns:
            Anonymous label (e.g., "ASSET_042")
        """
        if ticker not in self.ticker_map:
            hash_input = f"{self.seed}_{ticker}"
            hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            anon_label = f"ASSET_{hash_val % 1000:03d}"
            self.ticker_map[ticker] = anon_label
            self.reverse_map[anon_label] = ticker
            self._save_to_file()  # Save on new mapping
            
        return self.ticker_map[ticker]
    
    def set_company_name(self, ticker: str, company_name: str):
        """Store company name for anonymization."""
        if ticker not in self.company_names or self.company_names[ticker] != company_name:
            self.company_names[ticker] = company_name
            self._save_to_file()
    
    def anonymize_text(self, text: str, ticker: str) -> str:
        """
        Replace all company-specific information in text.
        
        Args:
            text: Text to anonymize
            ticker: Ticker symbol for context
        
        Returns:
            Anonymized text
        """
        if not text:
            return text
        
        anon_ticker = self.anonymize_ticker(ticker)
        
        # Replace company name FIRST (before ticker, to avoid partial replacements)
        if ticker in self.company_names:
            company_name = self.company_names[ticker]
            # Escape special regex characters including periods
            escaped_name = re.escape(company_name)
            text = re.sub(
                rf'\b{escaped_name}\b',
                f"Company {anon_ticker}",
                text,
                flags=re.IGNORECASE
            )
        
        # Replace ticker symbol
        text = re.sub(rf'\b{ticker}\b', anon_ticker, text, flags=re.IGNORECASE)
        
        # Replace product names
        for product, anon_product in self.product_map.items():
            text = re.sub(
                rf'\b{re.escape(product)}\b',
                anon_product,
                text,
                flags=re.IGNORECASE
            )
        
        return text
    
    def normalize_price_series(
        self,
        df: pd.DataFrame,
        base_value: float = 100.0,
        use_adjusted: bool = True
    ) -> pd.DataFrame:
        """
        Normalize price series to base-100 index.
        
        CRITICAL: Uses Adj Close by default to handle dividends/splits correctly.
        
        Args:
            df: DataFrame with OHLCV columns
            base_value: Starting index value (default 100.0)
            use_adjusted: Use 'Adj Close' if available (default True)
        
        Returns:
            DataFrame with normalized prices
        
        Raises:
            ValueError: If required columns are missing
        """
        df_normalized = df.copy()
        
        # Determine which close column to use
        if use_adjusted and 'Adj Close' in df.columns:
            close_col = 'Adj Close'
        elif 'Close' in df.columns:
            close_col = 'Close'
        else:
            raise ValueError("DataFrame must have 'Close' or 'Adj Close' column")
        
        # Get baseline (first row)
        if len(df) == 0:
            raise ValueError("DataFrame is empty")
        
        baseline = df[close_col].iloc[0]
        if baseline <= 0 or np.isnan(baseline):
            raise ValueError(f"Invalid baseline price: {baseline}")
        
        # Normalize all price columns
        price_columns = ['Open', 'High', 'Low', 'Close']
        if 'Adj Close' in df.columns:
            price_columns.append('Adj Close')
        
        for col in price_columns:
            if col in df.columns:
                # Use the same baseline for all columns
                df_normalized[col] = (df[col] / baseline) * base_value
        
        # Volume stays absolute (less identifying than price)
        # Could normalize if needed, but keeping raw for now
        
        return df_normalized
    
    def normalize_price_value(
        self,
        value: float,
        baseline: float,
        base_value: float = 100.0
    ) -> float:
        """
        Normalize a single price value.
        
        Args:
            value: Current price
            baseline: Reference price
            base_value: Target baseline (default 100.0)
        
        Returns:
            Normalized price
        """
        if baseline <= 0:
            raise ValueError(f"Invalid baseline: {baseline}")
        return (value / baseline) * base_value
    
    def anonymize_csv(
        self,
        input_path: Path,
        output_path: Path,
        ticker: str,
        normalize_prices: bool = True
    ):
        """
        Anonymize a CSV file containing market data.
        
        Args:
            input_path: Path to input CSV
            output_path: Path to output CSV
            ticker: Ticker symbol
            normalize_prices: Whether to normalize prices to base-100
        """
        df = pd.read_csv(input_path)
        
        # Anonymize ticker in column names
        anon_ticker = self.anonymize_ticker(ticker)
        df.columns = [col.replace(ticker, anon_ticker) for col in df.columns]
        
        # Normalize prices if requested
        if normalize_prices:
            df = self.normalize_price_series(df, base_value=100.0)
        
        # Anonymize text columns
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(
                    lambda x: self.anonymize_text(str(x), ticker) if pd.notna(x) else x
                )
        
        df.to_csv(output_path, index=False)
        print(f"✅ Anonymized {input_path.name} → {output_path.name}")
    
    def save_mapping(self, output_path: Path):
        """Save ticker mapping for de-anonymization."""
        mapping = {
            "ticker_map": self.ticker_map,
            "reverse_map": self.reverse_map,
            "company_names": self.company_names,
            "seed": self.seed
        }
        with open(output_path, 'w') as f:
            json.dump(mapping, f, indent=2)
        print(f"✅ Saved mapping to {output_path}")
    
    def load_mapping(self, input_path: Path):
        """Load ticker mapping from file."""
        with open(input_path, 'r') as f:
            mapping = json.load(f)
        
        self.ticker_map = mapping["ticker_map"]
        self.reverse_map = mapping["reverse_map"]
        self.company_names = mapping["company_names"]
        self.seed = mapping.get("seed", self.seed)
        print(f"✅ Loaded mapping from {input_path}")
    
    def deanonymize_ticker(self, anon_ticker: str) -> Optional[str]:
        """Reverse mapping: ASSET_042 → AAPL."""
        return self.reverse_map.get(anon_ticker)


# Example usage
if __name__ == "__main__":
    anonymizer = TickerAnonymizer()
    
    # Test anonymization
    ticker = "AAPL"
    anonymizer.set_company_name(ticker, "Apple Inc.")
    
    anon_ticker = anonymizer.anonymize_ticker(ticker)
    print(f"Ticker: {ticker} → {anon_ticker}")
    
    # Test text anonymization
    text = "Apple Inc. (AAPL) reported strong iPhone sales"
    anon_text = anonymizer.anonymize_text(text, ticker)
    print(f"Text: {text}")
    print(f"Anonymized: {anon_text}")
    
    # Test price normalization with Adj Close
    df = pd.DataFrame({
        'Date': pd.date_range('2024-01-01', periods=5),
        'Open': [150.0, 152.0, 151.0, 153.0, 155.0],
        'High': [152.0, 154.0, 153.0, 155.0, 157.0],
        'Low': [149.0, 151.0, 150.0, 152.0, 154.0],
        'Close': [151.0, 153.0, 152.0, 154.0, 156.0],
        'Adj Close': [150.5, 152.5, 151.5, 153.5, 155.5],  # Adjusted for dividends
        'Volume': [1000000] * 5
    })
    
    print("\nOriginal prices:")
    print(df[['Date', 'Close', 'Adj Close']].head())
    
    df_normalized = anonymizer.normalize_price_series(df)
    print("\nNormalized prices (using Adj Close):")
    print(df_normalized[['Date', 'Close', 'Adj Close']].head())
