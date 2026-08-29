"""
Full Environment Test - End-to-End with Real APIs
===================================================
Tests the complete system with real API keys:
1. FRED API for US interest rates
2. ExchangeRate-API for FX rates
3. Frankfurter for additional FX rates
4. Alpaca for execution readiness

Usage:
    python examples/test_full_environment.py
"""

import os
import sys
import httpx
import json
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    print(f"\n--- {title} ---")


def test_interest_rates():
    """Test interest rates from FRED + fallback"""
    print_section("INTEREST RATES (FRED + Fallback)")
    
    from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
    
    provider = GlobalInterestRatesProvider()
    
    try:
        rates = provider.get_all_rates()
        
        print(f"\nLoaded {len(rates)} central bank rates:\n")
        
        # Sort by rate
        sorted_rates = sorted(rates.items(), key=lambda x: x[1].rate, reverse=True)
        
        for country, rate_data in sorted_rates:
            source = "FRED" if rate_data.source == "FRED" else "fallback"
            print(f"  {country:4s} ({rate_data.currency}): {rate_data.rate:6.2f}%  [{source}]")
        
        # Find opportunities
        print_section("CARRY TRADE OPPORTUNITIES (Spread > 2%)")
        
        opportunities = provider.get_carry_opportunities(min_spread=2.0)
        
        print(f"\nFound {len(opportunities)} opportunities:\n")
        
        for i, opp in enumerate(opportunities[:10], 1):
            print(f"  {i:2d}. {opp['funding_currency']} -> {opp['investing_currency']}")
            print(f"      Funding: {opp['funding_rate']:.2f}% | Investing: {opp['investing_rate']:.2f}% | Spread: {opp['spread']:.2f}%")
        
        provider.close()
        return True, rates, opportunities
        
    except Exception as e:
        print(f"  Error: {e}")
        provider.close()
        return False, {}, []


def test_fx_rates():
    """Test FX rates from multiple sources"""
    print_section("FX RATES (ExchangeRate-API + Frankfurter)")
    
    from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
    
    provider = MultiCurrencyFXProvider()
    
    try:
        # Get key rates
        key_pairs = [
            ("USD", "EUR"), ("USD", "GBP"), ("USD", "JPY"),
            ("USD", "BRL"), ("USD", "MXN"), ("USD", "ARS"),
            ("USD", "INR"), ("USD", "CLP"), ("USD", "ZAR"),
            ("USD", "TRY"),
        ]
        
        fx_rates = {}
        
        print("\nKey FX Rates:\n")
        
        for base, quote in key_pairs:
            rate = provider.get_rate(base, quote)
            if rate:
                fx_rates[f"{base}_{quote}"] = rate.rate
                print(f"  {base}/{quote}: {rate.rate:8.4f}  [{rate.source}]")
        
        # Get volatility
        print_section("FX VOLATILITY (30-day)")
        
        volatility_pairs = [("USD", "BRL"), ("USD", "MXN"), ("USD", "JPY")]
        
        for base, quote in volatility_pairs:
            vol = provider.get_fx_volatility(base, quote, days=30)
            if vol:
                print(f"  {base}/{quote}: {vol:.2%} annualized")
        
        provider.close()
        return True, fx_rates
        
    except Exception as e:
        print(f"  Error: {e}")
        provider.close()
        return False, {}


def test_alpaca_connection():
    """Test Alpaca paper trading connection"""
    print_section("ALPACA PAPER TRADING")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    
    if not api_key or not secret_key:
        print("  [SKIP] Alpaca keys not configured")
        return False
    
    try:
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        
        # Get account info
        response = httpx.get(f"{base_url}/v2/account", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"\n  Account Status: {data.get('status', 'N/A')}")
            print(f"  Portfolio Value: ${float(data.get('portfolio_value', 0)):,.2f}")
            print(f"  Buying Power: ${float(data.get('buying_power', 0)):,.2f}")
            print(f"  Cash: ${float(data.get('cash', 0)):,.2f}")
            
            # Get positions
            pos_response = httpx.get(f"{base_url}/v2/positions", headers=headers, timeout=10)
            
            if pos_response.status_code == 200:
                positions = pos_response.json()
                print(f"\n  Open Positions: {len(positions)}")
                
                for pos in positions[:5]:
                    print(f"    {pos.get('symbol', 'N/A')}: {pos.get('qty', 0)} shares @ ${float(pos.get('avg_entry_price', 0)):,.2f}")
            
            # Get buying power
            print(f"\n  Day Trades Remaining: {data.get('daytrade_count', 'N/A')}")
            print(f"  Pattern Day Trader: {data.get('pattern_day_trader', 'N/A')}")
            
            return True
        else:
            print(f"  Error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"  Error: {e}")
        return False


def test_carry_trade_analysis():
    """Test carry trade analysis with real data"""
    print_section("CARRY TRADE ANALYSIS")
    
    from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
    from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
    
    rates_provider = GlobalInterestRatesProvider()
    fx_provider = MultiCurrencyFXProvider()
    
    try:
        # Get rates
        rates = rates_provider.get_all_rates()
        
        # Get FX rates
        fx_pairs = ["USD_BRL", "USD_MXN", "USD_INR", "USD_ZAR"]
        fx_rates = {}
        
        for pair in fx_pairs:
            base, quote = pair.split("_")
            rate = fx_provider.get_rate(base, quote)
            if rate:
                fx_rates[pair] = rate.rate
        
        # Analyze USD/BRL specifically
        print("\n  USD/BRL Carry Trade Analysis:")
        print("  " + "-" * 40)
        
        us_rate = rates.get("US")
        br_rate = rates.get("BR")
        
        if us_rate and br_rate:
            print(f"  Funding: USD at {us_rate.rate:.2f}%")
            print(f"  Investment: BRL at {br_rate.rate:.2f}%")
            print(f"  Interest Differential: {br_rate.rate - us_rate.rate:.2f}%")
            
            # Get FX volatility
            vol = fx_provider.get_fx_volatility("USD", "BRL", days=30)
            if vol:
                print(f"  30-day FX Volatility: {vol:.2%}")
                
                # Risk-adjusted return
                interest_diff = br_rate.rate - us_rate.rate
                risk_adjusted = interest_diff - (vol * 100)
                print(f"  Risk-Adjusted Return: {risk_adjusted:.2f}%")
        
        # Show all opportunities
        print("\n  Top 5 Carry Trade Opportunities:")
        print("  " + "-" * 40)
        
        opportunities = rates_provider.get_carry_opportunities(min_spread=3.0)
        
        for i, opp in enumerate(opportunities[:5], 1):
            print(f"  {i}. {opp['funding_currency']}/{opp['investing_currency']}: {opp['spread']:.2f}% spread")
        
        rates_provider.close()
        fx_provider.close()
        return True
        
    except Exception as e:
        print(f"  Error: {e}")
        rates_provider.close()
        fx_provider.close()
        return False


def main():
    print_header("FULL ENVIRONMENT TEST")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Testing complete system with real APIs...\n")
    
    results = {}
    
    # Test 1: Interest Rates
    success, rates, opportunities = test_interest_rates()
    results["Interest Rates"] = success
    
    # Test 2: FX Rates
    success, fx_rates = test_fx_rates()
    results["FX Rates"] = success
    
    # Test 3: Alpaca Connection
    success = test_alpaca_connection()
    results["Alpaca"] = success
    
    # Test 4: Carry Trade Analysis
    success = test_carry_trade_analysis()
    results["Carry Trade Analysis"] = success
    
    # Summary
    print_header("TEST RESULTS")
    
    all_passed = True
    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("ALL TESTS PASSED!")
        print("\nSystem ready for:")
        print("  1. Live carry trade analysis")
        print("  2. Paper trading execution")
        print("  3. Strategy development")
    else:
        print("Some tests failed. Check configuration.")
    
    print()
    
    # Show next steps
    print_header("NEXT STEPS")
    print("""
1. Run carry trade demo:
   python examples/global_carry_demo.py

2. Test with Alpaca paper trading:
   - Execute a carry trade strategy in dry run
   - Monitor positions
   - Analyze performance

3. Develop new strategies:
   - Add more currency pairs
   - Implement risk management
   - Create automated rebalancing
    """)


if __name__ == "__main__":
    main()
