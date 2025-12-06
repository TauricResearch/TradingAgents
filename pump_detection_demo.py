#!/usr/bin/env python3
"""
Pump Detection Demo
Demonstrates pump detection with sample data and cached stocks.
"""

from datetime import datetime


def demo_pump_detection():
    """
    Run a demonstration of pump detection on available cached data.
    """
    import os
    from pathlib import Path
    
    print("\n" + "="*80)
    print("🚀 PUMP DETECTION SYSTEM - DEMO")
    print("="*80 + "\n")
    
    # Check for cached stock data
    cache_dir = Path("/home/gnara/TradingAgents/tradingagents/dataflows/data_cache")
    
    if not cache_dir.exists():
        print("❌ Cache directory not found. Please run main_screening.py first to cache data.")
        return
    
    cached_files = list(cache_dir.glob("*-YFin-data-*.csv"))
    
    if not cached_files:
        print("❌ No cached stock data found. Please run main_screening.py first.")
        return
    
    print(f"📊 Found {len(cached_files)} cached stock files:")
    
    available_tickers = []
    for f in cached_files:
        # Extract ticker from filename
        ticker = f.name.split('-')[0]
        available_tickers.append(ticker)
        print(f"  • {ticker}")
    
    print("\n" + "-"*80)
    print("📈 PUMP DETECTION ANALYSIS")
    print("-"*80 + "\n")
    
    # Analyze each available stock
    for ticker in available_tickers[:3]:  # Demo: analyze first 3
        print(f"\n🔍 Analyzing {ticker}...\n")
        analyze_ticker_cached(ticker, cache_dir)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80 + "\n")
    
    print("💡 To run pump detection with live data:")
    print("  1. Set up your data sources (yfinance, Alpha Vantage API)")
    print("  2. Run: python pump_screening.py --ticker NVDA")
    print("  3. Or screen full market: python pump_screening.py\n")


def analyze_ticker_cached(ticker, cache_dir):
    """
    Analyze a ticker using cached CSV data.
    """
    from pathlib import Path
    import csv
    
    # Find the cached file for this ticker
    cache_files = list(cache_dir.glob(f"{ticker}-YFin-data-*.csv"))
    
    if not cache_files:
        print(f"  ❌ No cached data for {ticker}")
        return
    
    cache_file = cache_files[0]
    
    try:
        # Parse the CSV
        volumes = []
        prices = []
        dates = []
        
        with open(cache_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            
            for row in reader:
                try:
                    date = row[0]
                    close = float(row[4])
                    volume = float(row[5])
                    
                    dates.append(date)
                    prices.append(close)
                    volumes.append(volume)
                except:
                    continue
        
        if not volumes or len(volumes) < 5:
            print(f"  ⚠️  Insufficient data for {ticker}")
            return
        
        # Reverse to chronological order
        dates.reverse()
        prices.reverse()
        volumes.reverse()
        
        # --- VOLUME SPIKE ANALYSIS ---
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else volumes[0]
        current_volume = volumes[-1]
        spike_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        volume_spike = spike_ratio >= 2.0
        
        print(f"  Volume Spike: {current_volume:,.0f} shares ({spike_ratio:.2f}x avg)")
        print(f"    {'✅ DETECTED' if volume_spike else '❌ Not detected'}")
        
        # --- PRICE ACCELERATION ---
        if len(prices) >= 4:
            recent_gain = ((prices[-1] - prices[-3]) / prices[-3]) * 100 if prices[-3] > 0 else 0
            older_gain = ((prices[-3] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
        else:
            recent_gain = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] > 0 else 0
            older_gain = 0
        
        price_acceleration = recent_gain > 5 and (older_gain == 0 or recent_gain > older_gain * 1.5)
        
        print(f"  Price Acceleration: Recent {recent_gain:+.2f}% vs Older {older_gain:+.2f}%")
        print(f"    {'✅ DETECTED' if price_acceleration else '❌ Not detected'}")
        
        # --- SCORE CALCULATION ---
        score = 0
        signals = 0
        
        if volume_spike:
            score += 40
            signals += 1
        
        if price_acceleration:
            score += 40
            signals += 1
        
        # Add some baseline for being "active"
        if current_volume > avg_volume * 1.2:
            score += 20
            signals += 0.5
        
        print(f"\n  🎯 Pump Detection Score: {score:.0f}/100")
        print(f"  🔔 Signals Detected: {signals:.1f}/5")
        
        if score >= 60:
            print(f"  🚀 RECOMMENDATION: HIGH PUMP PROBABILITY - Consider entry with risk management")
        elif score >= 40:
            print(f"  📊 RECOMMENDATION: MODERATE - Watch for confirmation")
        else:
            print(f"  ⏳ RECOMMENDATION: WAIT - Insufficient pump signals")
        
        print()
        
    except Exception as e:
        print(f"  ❌ Error analyzing {ticker}: {e}")


if __name__ == "__main__":
    demo_pump_detection()
