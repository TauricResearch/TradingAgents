#!/usr/bin/env python3
"""
Ticker Anonymization Script - The "Blindfire Protocol"

This script anonymizes historical trading data by replacing:
- Ticker symbols (AAPL → ASSET_042)
- Company names (Apple Inc. → Company ASSET_042)
- Product names (iPhone → Product A, MacBook → Product B)

This prevents LLMs from using memorized knowledge about specific companies.
"""

import hashlib
import re
import json
from pathlib import Path
from typing import Dict, List
import pandas as pd


class TickerAnonymizer:
    """Anonymize tickers and company-specific information."""
    
    def __init__(self, seed: str = "blindfire_v1"):
        self.seed = seed
        self.ticker_map = {}
        self.reverse_map = {}
        self.company_names = {}
        self.product_map = {
            # Apple products
            "iPhone": "Product A",
            "iPad": "Product B",
            "MacBook": "Product C",
            "Apple Watch": "Product D",
            "AirPods": "Product E",
            # Nvidia products
            "GeForce": "Product X",
            "RTX": "Product Y",
            "H100": "Product Z",
            "A100": "Product W",
            # Microsoft products
            "Windows": "Software Platform A",
            "Office": "Software Platform B",
            "Azure": "Cloud Platform A",
            # Meta products
            "Facebook": "Social Platform A",
            "Instagram": "Social Platform B",
            "WhatsApp": "Messaging Platform A",
            # Google products
            "Search": "Platform Service A",
            "YouTube": "Video Platform A",
            "Android": "Mobile OS A",
        }
    
    def anonymize_ticker(self, ticker: str) -> str:
        """
        Map ticker to anonymous label.
        
        Example: AAPL → ASSET_042
        """
        if ticker not in self.ticker_map:
            hash_input = f"{self.seed}_{ticker}"
            hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            anon_label = f"ASSET_{hash_val % 1000:03d}"
            self.ticker_map[ticker] = anon_label
            self.reverse_map[anon_label] = ticker
        return self.ticker_map[ticker]
    
    def set_company_name(self, ticker: str, company_name: str):
        """Store company name for anonymization."""
        self.company_names[ticker] = company_name
    
    def anonymize_text(self, text: str, ticker: str) -> str:
        """
        Replace all company-specific information in text.
        
        Args:
            text: Text to anonymize (news article, earnings report, etc.)
            ticker: Ticker symbol for context
        
        Returns:
            Anonymized text with ASSET_XXX labels
        """
        if not text:
            return text
        
        anon_ticker = self.anonymize_ticker(ticker)
        
        # Replace ticker symbol (case-insensitive)
        text = re.sub(rf'\b{ticker}\b', anon_ticker, text, flags=re.IGNORECASE)
        
        # Replace company name if known
        if ticker in self.company_names:
            company_name = self.company_names[ticker]
            text = re.sub(
                rf'\b{re.escape(company_name)}\b',
                f"Company {anon_ticker}",
                text,
                flags=re.IGNORECASE
            )
        
        # Replace product names
        for product, anon_product in self.product_map.items():
            text = re.sub(
                rf'\b{re.escape(product)}\b',
                anon_product,
                text,
                flags=re.IGNORECASE
            )
        
        return text
    
    def normalize_price_series(self, df: pd.DataFrame, base_value: float = 100.0) -> pd.DataFrame:
        """
        Normalize price series to base-100 index to prevent LLM from identifying stocks by price level.
        
        This prevents the "Price Scale Leak" where an LLM can identify NVDA by seeing $480 prices.
        
        Args:
            df: DataFrame with OHLCV columns
            base_value: Starting index value (default 100.0)
        
        Returns:
            DataFrame with normalized prices (all rebased to start at 100.0)
        
        Example:
            Original: Close = [150, 153, 149, 155]
            Normalized: Close = [100.0, 102.0, 99.33, 103.33]
        """
        df_normalized = df.copy()
        
        # Get first row as baseline
        first_row = df.iloc[0]
        
        # Normalize OHLC columns
        price_columns = ['Open', 'High', 'Low', 'Close']
        for col in price_columns:
            if col in df.columns:
                baseline = first_row[col]
                if baseline > 0:
                    # Rebase to 100.0
                    df_normalized[col] = (df[col] / baseline) * base_value
        
        # Volume stays absolute (but could be normalized too if desired)
        # Keeping volume absolute for now as it's less identifying
        
        return df_normalized
    
    def normalize_price_value(self, value: float, baseline: float, base_value: float = 100.0) -> float:
        """
        Normalize a single price value.
        
        Args:
            value: Current price
            baseline: Reference price (e.g., first price in series)
            base_value: Target baseline (default 100.0)
        
        Returns:
            Normalized price
        """
        if baseline <= 0:
            return value
        return (value / baseline) * base_value
    
    def anonymize_csv(self, input_path: Path, output_path: Path, ticker: str):
        """
        Anonymize a CSV file containing market data.
        
        Preserves numerical data but removes ticker references.
        """
        df = pd.read_csv(input_path)
        
        # Replace ticker in column names if present
        anon_ticker = self.anonymize_ticker(ticker)
        df.columns = [col.replace(ticker, anon_ticker) for col in df.columns]
        
        # Anonymize any text columns
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(lambda x: self.anonymize_text(str(x), ticker) if pd.notna(x) else x)
        
        df.to_csv(output_path, index=False)
        print(f"✅ Anonymized {input_path.name} → {output_path.name}")
    
    def save_mapping(self, output_path: Path):
        """Save ticker mapping for later de-anonymization."""
        mapping = {
            "ticker_map": self.ticker_map,
            "reverse_map": self.reverse_map,
            "company_names": self.company_names,
        }
        with open(output_path, 'w') as f:
            json.dump(mapping, f, indent=2)
        print(f"✅ Saved mapping to {output_path}")


def main():
    """
    Anonymize dataset for TradingAgents testing.
    
    Usage:
        python scripts/anonymize_dataset.py
    """
    # Configuration
    tickers = ["AAPL", "NVDA", "MSFT", "META", "GOOGL"]
    company_names = {
        "AAPL": "Apple Inc.",
        "NVDA": "NVIDIA Corporation",
        "MSFT": "Microsoft Corporation",
        "META": "Meta Platforms Inc.",
        "GOOGL": "Alphabet Inc.",
    }
    
    # Paths
    data_dir = Path("data/raw")
    output_dir = Path("data/anonymized")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize anonymizer
    anonymizer = TickerAnonymizer(seed="blindfire_v1")
    
    # Set company names
    for ticker, name in company_names.items():
        anonymizer.set_company_name(ticker, name)
    
    print("🔒 BLINDFIRE PROTOCOL - Anonymizing Dataset")
    print("=" * 60)
    
    # Anonymize each ticker's data
    for ticker in tickers:
        anon_ticker = anonymizer.anonymize_ticker(ticker)
        print(f"\n📊 Processing {ticker} → {anon_ticker}")
        
        # Anonymize price data
        price_file = data_dir / f"{ticker}_prices.csv"
        if price_file.exists():
            anonymizer.anonymize_csv(
                price_file,
                output_dir / f"{anon_ticker}_prices.csv",
                ticker
            )
        
        # Anonymize news data
        news_file = data_dir / f"{ticker}_news.csv"
        if news_file.exists():
            anonymizer.anonymize_csv(
                news_file,
                output_dir / f"{anon_ticker}_news.csv",
                ticker
            )
        
        # Anonymize fundamentals
        fundamentals_file = data_dir / f"{ticker}_fundamentals.csv"
        if fundamentals_file.exists():
            anonymizer.anonymize_csv(
                fundamentals_file,
                output_dir / f"{anon_ticker}_fundamentals.csv",
                ticker
            )
    
    # Save mapping for de-anonymization
    anonymizer.save_mapping(output_dir / "ticker_mapping.json")
    
    print("\n" + "=" * 60)
    print("✅ ANONYMIZATION COMPLETE")
    print(f"📁 Anonymized data saved to: {output_dir}")
    print("\n🎯 Next Steps:")
    print("1. Update TradingAgents config to use anonymized data")
    print("2. Modify analyst prompts to remove {ticker} references")
    print("3. Run backtests on anonymized dataset")
    print("4. Compare results to original (should be similar if no contamination)")


if __name__ == "__main__":
    main()
