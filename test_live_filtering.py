"""
Live integration test for scanner context filtering.
Tests with realistic scanner context to measure actual token reduction.
"""
from tradingagents.agents.utils.context_filtering import filter_scanner_context_for_ticker


def build_realistic_scanner_context(ticker: str) -> str:
    """Build a realistic scanner context packet (production-sized)."""
    
    # Build a realistic scanner context (simplified version)
    context = f"""# SCANNER CONTEXT PACKET: {ticker}
Date: 2026-03-31

## I. TICKER-SPECIFIC SCANNER THESIS
Rationale: Energy sector recovery play
Thesis Angle: Offshore drilling rebound
Conviction: Medium
Key Catalyst: Oil price stability above $70/bbl

## II. STRUCTURED LIVE DATA (GROUND TRUTH)

### Commodity Prices
- WTI Crude: $72.50 (+2.3%)
- Brent: $76.20 (+1.8%)
- Natural Gas: $2.85 (-0.5%)

### FX Rates
- EUR/USD: 1.0850
- GBP/USD: 1.2640
- USD/JPY: 151.20

### Earnings Calendar (7d lookback, 14d lookahead)
- {ticker}: Q4 earnings (Market Cap: 6.2B, Sector: Energy)
"""
    
    # Add 50+ companies for realistic volume
    companies = [
        ("XOM", "Exxon Mobil", "500B", "Energy"),
        ("CVX", "Chevron", "280B", "Energy"),
        ("COP", "ConocoPhillips", "140B", "Energy"),
        ("SLB", "Schlumberger", "65B", "Energy"),
        ("EOG", "EOG Resources", "70B", "Energy"),
        ("MPC", "Marathon Petroleum", "55B", "Energy"),
        ("PSX", "Phillips 66", "50B", "Energy"),
        ("VLO", "Valero Energy", "45B", "Energy"),
        ("OXY", "Occidental Petroleum", "48B", "Energy"),
        ("HAL", "Halliburton", "28B", "Energy"),
        ("BKR", "Baker Hughes", "32B", "Energy"),
        ("MRO", "Marathon Oil", "18B", "Energy"),
        ("DVN", "Devon Energy", "30B", "Energy"),
        ("FANG", "Diamondback Energy", "35B", "Energy"),
        ("HES", "Hess Corporation", "42B", "Energy"),
        # Add non-energy companies
        ("AAPL", "Apple Inc", "3000B", "Technology"),
        ("MSFT", "Microsoft Corp", "2800B", "Technology"),
        ("GOOGL", "Alphabet Inc", "1800B", "Technology"),
        ("AMZN", "Amazon.com Inc", "1600B", "Consumer Cyclical"),
        ("NVDA", "NVIDIA Corp", "2200B", "Technology"),
        ("META", "Meta Platforms", "1200B", "Communication Services"),
        ("TSLA", "Tesla Inc", "800B", "Consumer Cyclical"),
        ("BRK.B", "Berkshire Hathaway", "900B", "Financial Services"),
        ("JPM", "JPMorgan Chase", "550B", "Financial Services"),
        ("V", "Visa Inc", "520B", "Financial Services"),
        ("JNJ", "Johnson & Johnson", "480B", "Healthcare"),
        ("WMT", "Walmart Inc", "450B", "Consumer Defensive"),
        ("PG", "Procter & Gamble", "380B", "Consumer Defensive"),
        ("MA", "Mastercard Inc", "420B", "Financial Services"),
        ("UNH", "UnitedHealth Group", "500B", "Healthcare"),
    ]
    
    for sym, name, mcap, sect in companies:
        context += f"- {sym}: {name} ({mcap} cap, {sect})\n"
    
    context += """
### Economic Calendar (7d lookback, 14d lookahead)
- FOMC Meeting Minutes (Mar 20, High Impact)
- Core CPI m/m (Mar 22, High Impact)  
- Retail Sales m/m (Mar 23, High Impact)
- GDP Growth Rate (Mar 28, High Impact)
- Unemployment Rate (Mar 29, High Impact)
- ISM Manufacturing PMI (Apr 1, High Impact)
- Nonfarm Payrolls (Apr 5, High Impact)
- Core PCE Price Index (Apr 6, High Impact)
- Fed Chair Powell Speech (Apr 10, High Impact)
- Producer Price Index (Apr 12, High Impact)
- Building Permits (Mar 18, Medium Impact)
- Housing Starts (Mar 18, Medium Impact)
- Industrial Production (Mar 19, Medium Impact)
- Consumer Confidence (Mar 25, Medium Impact)
- Durable Goods Orders (Mar 26, Medium Impact)

## III. SMART MONEY & FLOW SIGNALS

### Dark Pool & Block Activity
"""
    
    # Add realistic smart money data
    context += f"""- {ticker}: Unusual dark pool volume (2.5M shares at $45.20)
- {ticker}: Block trade detected - 500K shares institutional buy
- Sector flow: Energy seeing +$450M inflows (weekly)

### Options Flow Analysis  
- XOM: Bullish call sweep 1500 @ $120 strike (Jun expiry)
- CVX: Put/call ratio declining (0.6 → 0.45)
- {ticker}: Unusual put activity 800 contracts @ $40 strike
- Sector options: Net bullish positioning across energy names

## IV. FACTOR ALIGNMENT & DRIFT

### {ticker} Factor Scores
- Momentum: +0.35 (improving)
- Value: +0.62 (attractive)  
- Quality: +0.28 (stable)
- Growth: -0.15 (challenged)
- Low Volatility: +0.45

### Sector Factor Rotation
- Energy momentum turning positive (+0.25 this week)
- Technology momentum fading (-0.18 from +0.45)
- Financials quality improving (+0.32)
- Healthcare defensive positioning strengthening

## V. MACRO & GEOPOLITICAL CONTEXT

### Central Bank Policy
- Fed holding rates at 5.25-5.50% (5th consecutive hold)
- Market pricing 60% chance of June cut
- ECB signaling potential May cut  
- BoJ maintaining ultra-loose policy

### Geopolitical Risks
- Middle East tensions elevated (Strait of Hormuz concerns)
- China economic stimulus measures announced ($200B package)
- EU energy diversification accelerating
- US-China tech restrictions expanding

## VI. SECTOR ROTATION & MARKET REGIME

### Current Market Regime: Risk-On Rotation
- S&P 500: +1.2% (week), testing 5200 resistance
- Volatility (VIX): 14.5 (declining from 18)
- Credit spreads: Tightening (HY: 350bps)

### Sector Performance (5D)
Energy: +3.2% (outperforming)
Materials: +2.1% (strength)
Industrials: +1.8% (rotation into)
Financials: +1.5% (steady)
Technology: -0.5% (taking profits)
Communication Services: -0.8% (weakness)
Consumer Discretionary: +0.3% (mixed)
Healthcare: +0.5% (defensive bid)
Utilities: -0.2% (rotation out)
Real Estate: -0.4% (rate concerns)

### Sector Rotation Signals
FROM: Technology, Communication Services  
TO: Energy, Materials, Industrials (cyclical rotation)

## VII. KEY GLOBAL THEMES

### Energy Transition & Commodity Supercycle
- Oil demand forecasts revised higher (IEA: +1.8M bpd 2026)
- Natural gas storage below 5-year average (supply concerns)
- Offshore drilling contracts increasing (dayrate recovery)

### Inflation & Rate Path
- Core inflation sticky at 3.2% (above Fed 2% target)
- Services inflation elevated (wage pressures)
- Goods deflation moderating

### China Growth & Commodity Demand
- China stimulus supporting commodity demand
- Manufacturing PMI expanding (51.2)
- Infrastructure spending accelerating

## VIII. MACRO RISK FACTORS
- Inflation persistence (sticky services inflation)
- Credit tightening (regional bank stress)
- Geopolitical escalation (energy supply risk premium)
- Policy uncertainty (election year dynamics)
- Commercial real estate stress (refinancing wall)
"""
    
    return context


def main():
    ticker = "RIG"
    
    print("=" * 80)
    print(f"LIVE INTEGRATION TEST: Scanner Context Filtering for {ticker}")
    print("=" * 80)
    
    # Build realistic scanner context
    print("\n1. Building realistic production-sized scanner context...")
    original_context = build_realistic_scanner_context(ticker)
    
    original_size = len(original_context)
    original_tokens = original_size // 4  # Rough token estimate (4 chars/token)
    
    print(f"\n2. Original context:")
    print(f"   - Size: {original_size:,} chars")
    print(f"   - Tokens (est): {original_tokens:,}")
    
    # Apply filtering
    print(f"\n3. Applying ticker-specific filtering for {ticker}...")
    filtered_context = filter_scanner_context_for_ticker(original_context, ticker)
    
    filtered_size = len(filtered_context)
    filtered_tokens = filtered_size // 4
    
    print(f"\n4. Filtered context:")
    print(f"   - Size: {filtered_size:,} chars")
    print(f"   - Tokens (est): {filtered_tokens:,}")
    
    # Calculate reduction
    size_reduction = ((original_size - filtered_size) / original_size) * 100
    token_reduction = ((original_tokens - filtered_tokens) / original_tokens) * 100
    
    print(f"\n5. RESULTS:")
    print(f"   - Size reduction: {size_reduction:.1f}%")
    print(f"   - Token reduction: {token_reduction:.1f}%")
    print(f"   - Saved tokens: {original_tokens - filtered_tokens:,}")
    
    # Cost savings (assuming $0.15 per 1M input tokens for Qwen)
    cost_per_token = 0.15 / 1_000_000
    cost_saved = (original_tokens - filtered_tokens) * cost_per_token
    
    print(f"\n6. COST IMPACT (per analysis):")
    print(f"   - Original cost: ${original_tokens * cost_per_token:.6f}")
    print(f"   - Filtered cost: ${filtered_tokens * cost_per_token:.6f}")
    print(f"   - Savings: ${cost_saved:.6f} ({size_reduction:.1f}% reduction)")
    
    # Show sample of filtered output
    print(f"\n7. Filtered context preview (first 1000 chars):")
    print("-" * 80)
    print(filtered_context[:1000])
    print("-" * 80)
    
    # Verify key sections preserved
    print(f"\n8. Validation:")
    checks = {
        "Ticker thesis preserved": "TICKER-SPECIFIC" in filtered_context,
        "Structured data present": "STRUCTURED LIVE DATA" in filtered_context,
        "Smart money filtered": "SMART MONEY" in filtered_context,
        "Macro context kept": "MACRO & GEOPOLITICAL" in filtered_context,
        "Themes preserved": "KEY GLOBAL THEMES" in filtered_context,
    }
    
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"   {status} {check}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
