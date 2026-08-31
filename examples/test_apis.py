"""
Live API Test - Verifies all API keys work correctly
=====================================================
Tests:
1. FRED API (interest rates)
2. ExchangeRate-API (FX rates)
3. Alpaca Paper Trading (connection)

Usage:
    python examples/test_apis.py
"""

import os
import httpx
from dotenv import load_dotenv

# Load .env file
load_dotenv()


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_fred_api():
    """Test FRED API with real key"""
    print_header("TESTING FRED API")
    
    api_key = os.getenv("FRED_API_KEY")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}" if api_key else "NOT SET")
    
    if not api_key:
        print("[FAIL] FRED_API_KEY not set")
        return False
    
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "FEDFUNDS",
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        
        response = httpx.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "observations" in data and data["observations"]:
                obs = data["observations"][0]
                print("[PASS] FRED API working!")
                print(f"   Fed Funds Rate: {obs['value']}%")
                print(f"   Date: {obs['date']}")
                return True
        else:
            print(f"[FAIL] FRED API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[FAIL] FRED API error: {e}")
        return False


def test_exchangerate_api():
    """Test ExchangeRate-API with real key"""
    print_header("TESTING EXCHANGERATE-API")
    
    api_key = os.getenv("EXCHANGERATE_API_KEY")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}" if api_key else "NOT SET")
    
    if not api_key:
        print("[FAIL] EXCHANGERATE_API_KEY not set")
        return False
    
    try:
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD"
        
        response = httpx.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("result") == "success":
                print("[PASS] ExchangeRate-API working!")
                print(f"   USD/EUR: {data['conversion_rates'].get('EUR', 'N/A')}")
                print(f"   USD/GBP: {data['conversion_rates'].get('GBP', 'N/A')}")
                print(f"   USD/JPY: {data['conversion_rates'].get('JPY', 'N/A')}")
                print(f"   USD/BRL: {data['conversion_rates'].get('BRL', 'N/A')}")
                return True
        else:
            print(f"[FAIL] ExchangeRate-API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[FAIL] ExchangeRate-API error: {e}")
        return False


def test_alpaca_api():
    """Test Alpaca Paper Trading API"""
    print_header("TESTING ALPACA PAPER TRADING")
    
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}" if api_key else "NOT SET")
    print(f"Secret Key: {secret_key[:8]}...{secret_key[-4:]}" if secret_key else "NOT SET")
    print(f"Base URL: {base_url}")
    
    if not api_key or not secret_key:
        print("[FAIL] ALPACA_API_KEY or ALPACA_SECRET_KEY not set")
        return False
    
    try:
        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }
        
        # Test account endpoint
        response = httpx.get(f"{base_url}/v2/account", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("[PASS] Alpaca Paper Trading working!")
            print(f"   Account Status: {data.get('status', 'N/A')}")
            print(f"   Portfolio Value: ${float(data.get('portfolio_value', 0)):,.2f}")
            print(f"   Buying Power: ${float(data.get('buying_power', 0)):,.2f}")
            return True
        else:
            print(f"[FAIL] Alpaca API error: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"[FAIL] Alpaca API error: {e}")
        return False


def main():
    print_header("LIVE API TEST")
    print("Testing all configured API keys...\n")
    
    results = {
        "FRED": test_fred_api(),
        "ExchangeRate": test_exchangerate_api(),
        "Alpaca": test_alpaca_api(),
    }
    
    print_header("RESULTS")
    
    all_passed = True
    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("All APIs working! System ready for live trading.")
    else:
        print("Some APIs failed. Check configuration.")
    
    print()


if __name__ == "__main__":
    main()
