#!/usr/bin/env python3
"""
Build strategy-specific historical memories for different trading styles

This script creates memory sets optimized for:
- Day trading (1-day horizon, daily samples)
- Swing trading (7-day horizon, weekly samples)
- Position trading (30-day horizon, monthly samples)
- Long-term investing (90-day horizon, quarterly samples)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.historical_memory_builder import HistoricalMemoryBuilder
import pickle
from datetime import datetime, timedelta


# Strategy configurations
STRATEGIES = {
    "day_trading": {
        "lookforward_days": 1,      # Next day returns
        "interval_days": 1,         # Sample daily
        "description": "Day Trading - Capture intraday momentum and next-day moves",
        "tickers": ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD", "AMZN"],  # High volume
    },
    "swing_trading": {
        "lookforward_days": 7,      # Weekly returns
        "interval_days": 7,         # Sample weekly
        "description": "Swing Trading - Capture week-long trends and momentum",
        "tickers": ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "AMD", "NFLX"],
    },
    "position_trading": {
        "lookforward_days": 30,     # Monthly returns
        "interval_days": 30,        # Sample monthly
        "description": "Position Trading - Capture monthly trends and fundamentals",
        "tickers": ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA", "JPM", "BAC", "XOM", "JNJ", "WMT"],
    },
    "long_term_investing": {
        "lookforward_days": 90,     # Quarterly returns
        "interval_days": 90,        # Sample quarterly
        "description": "Long-term Investing - Capture fundamental value and trends",
        "tickers": ["AAPL", "GOOGL", "MSFT", "BRK.B", "JPM", "JNJ", "PG", "KO", "DIS", "V"],
    },
}


def build_strategy_memories(strategy_name: str, config: dict):
    """Build memories for a specific trading strategy."""

    strategy = STRATEGIES[strategy_name]

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Building Memories: {strategy_name.upper().replace('_', ' ')}
╚══════════════════════════════════════════════════════════════╝

Strategy: {strategy['description']}
Lookforward: {strategy['lookforward_days']} days
Sampling: Every {strategy['interval_days']} days
Tickers: {', '.join(strategy['tickers'])}
    """)

    # Date range - last 2 years
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)

    # Build memories
    builder = HistoricalMemoryBuilder(DEFAULT_CONFIG)

    memories = builder.populate_agent_memories(
        tickers=strategy['tickers'],
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        lookforward_days=strategy['lookforward_days'],
        interval_days=strategy['interval_days']
    )

    # Save to disk
    memory_dir = os.path.join(DEFAULT_CONFIG["data_dir"], "memories", strategy_name)
    os.makedirs(memory_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for agent_type, memory in memories.items():
        filename = os.path.join(memory_dir, f"{agent_type}_memory_{timestamp}.pkl")

        # Extract collection data
        collection = memory.situation_collection
        results = collection.get(include=["documents", "metadatas", "embeddings"])

        with open(filename, 'wb') as f:
            pickle.dump({
                "documents": results["documents"],
                "metadatas": results["metadatas"],
                "embeddings": results["embeddings"],
                "ids": results["ids"],
                "created_at": timestamp,
                "strategy": strategy_name,
                "tickers": strategy['tickers'],
                "config": {
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "lookforward_days": strategy['lookforward_days'],
                    "interval_days": strategy['interval_days']
                }
            }, f)

        print(f"✅ Saved {agent_type} memory to {filename}")

    print(f"\n🎉 {strategy_name.replace('_', ' ').title()} memories complete!")
    print(f"   Saved to: {memory_dir}\n")

    return memory_dir


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║   TradingAgents - Strategy-Specific Memory Builder          ║
╚══════════════════════════════════════════════════════════════╝

This script builds optimized memories for different trading styles:

1. Day Trading      - 1-day returns, daily samples
2. Swing Trading    - 7-day returns, weekly samples
3. Position Trading - 30-day returns, monthly samples
4. Long-term        - 90-day returns, quarterly samples
    """)

    print("Available strategies:")
    for i, (name, config) in enumerate(STRATEGIES.items(), 1):
        print(f"  {i}. {name.replace('_', ' ').title()}")
        print(f"     {config['description']}")
        print(f"     Horizon: {config['lookforward_days']} days, Interval: {config['interval_days']} days\n")

    choice = input("Choose strategy (1-4, or 'all' for all strategies): ").strip()

    if choice.lower() == 'all':
        strategies_to_build = list(STRATEGIES.keys())
    else:
        try:
            idx = int(choice) - 1
            strategies_to_build = [list(STRATEGIES.keys())[idx]]
        except (ValueError, IndexError):
            print("Invalid choice. Exiting.")
            return

    print(f"\nWill build memories for: {', '.join(strategies_to_build)}")
    proceed = input("Proceed? (y/n): ")

    if proceed.lower() != 'y':
        print("Aborted.")
        return

    # Build memories for each selected strategy
    results = {}
    for strategy_name in strategies_to_build:
        memory_dir = build_strategy_memories(strategy_name, DEFAULT_CONFIG)
        results[strategy_name] = memory_dir

    # Print summary
    print("\n" + "="*70)
    print("📊 MEMORY BUILDING COMPLETE")
    print("="*70)
    for strategy_name, memory_dir in results.items():
        print(f"\n{strategy_name.replace('_', ' ').title()}:")
        print(f"  Location: {memory_dir}")
        print(f"  Config to use:")
        print(f'    "memory_dir": "{memory_dir}"')
        print(f'    "load_historical_memories": True')

    print("\n" + "="*70)
    print("\n💡 TIP: To use a specific strategy's memories, update your config:")
    print("""
    config = DEFAULT_CONFIG.copy()
    config["memory_dir"] = "data/memories/swing_trading"  # or your strategy
    config["load_historical_memories"] = True
    """)


if __name__ == "__main__":
    main()
