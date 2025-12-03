#!/usr/bin/env python3
"""
Script to build historical memories for TradingAgents

This script:
1. Fetches historical stock data for specified tickers
2. Analyzes outcomes to create agent-specific memories
3. Saves memories to disk for later use

Usage:
    python scripts/build_historical_memories.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.historical_memory_builder import HistoricalMemoryBuilder
import pickle
from datetime import datetime, timedelta


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║      TradingAgents - Historical Memory Builder               ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # Configuration
    tickers = [
        "AAPL", "GOOGL", "MSFT", "NVDA", "TSLA",  # Tech
        "JPM", "BAC", "GS",                        # Finance
        "XOM", "CVX",                              # Energy
        "JNJ", "PFE",                              # Healthcare
        "WMT", "AMZN"                              # Retail
    ]

    # Date range - last 2 years
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years

    print(f"Tickers: {', '.join(tickers)}")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Lookforward: 7 days (1 week returns)")
    print(f"Sample interval: 30 days (monthly)\n")

    proceed = input("Proceed with memory building? (y/n): ")
    if proceed.lower() != 'y':
        print("Aborted.")
        return

    # Build memories
    builder = HistoricalMemoryBuilder(DEFAULT_CONFIG)

    memories = builder.populate_agent_memories(
        tickers=tickers,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        lookforward_days=7,
        interval_days=30
    )

    # Save to disk
    memory_dir = os.path.join(DEFAULT_CONFIG["data_dir"], "memories")
    os.makedirs(memory_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for agent_type, memory in memories.items():
        filename = os.path.join(memory_dir, f"{agent_type}_memory_{timestamp}.pkl")

        # Save the ChromaDB collection data
        # Note: ChromaDB doesn't serialize well, so we extract the data
        collection = memory.situation_collection
        data = {
            "documents": [],
            "metadatas": [],
            "embeddings": [],
            "ids": []
        }

        # Get all items from collection
        results = collection.get(include=["documents", "metadatas", "embeddings"])

        with open(filename, 'wb') as f:
            pickle.dump({
                "documents": results["documents"],
                "metadatas": results["metadatas"],
                "embeddings": results["embeddings"],
                "ids": results["ids"],
                "created_at": timestamp,
                "tickers": tickers,
                "config": {
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "lookforward_days": 7,
                    "interval_days": 30
                }
            }, f)

        print(f"✅ Saved {agent_type} memory to {filename}")

    print(f"\n🎉 Memory building complete!")
    print(f"   Memories saved to: {memory_dir}")
    print(f"\n📝 To use these memories, update DEFAULT_CONFIG with:")
    print(f'   "memory_dir": "{memory_dir}"')
    print(f'   "load_historical_memories": True')


if __name__ == "__main__":
    main()
