#!/usr/bin/env python3
"""
Test script to verify TradingAgents backend API endpoints
"""

import requests
import json
import sys
import os

def test_backend():
    """Test all backend endpoints"""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing TradingAgents Backend API")
    print("=" * 50)
    
    # Test 1: Health check
    print("\n1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Backend not running. Please start the backend server first:")
        print("   cd web_app/backend && python main.py")
        return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False
    
    # Test 2: Companies endpoint
    print("\n2. Testing companies endpoint...")
    try:
        response = requests.get(f"{base_url}/results/companies", timeout=10)
        if response.status_code == 200:
            data = response.json()
            companies = data.get('companies', [])
            print(f"✅ Companies endpoint working - Found {len(companies)} companies")
            for company in companies:
                print(f"   - {company['symbol']}: {company['total_analyses']} analyses, {company.get('transformed_analyses', 0)} transformed")
        else:
            print(f"❌ Companies endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Companies endpoint error: {e}")
    
    # Test 3: Transformed data endpoints
    print("\n3. Testing transformed data endpoints...")
    try:
        # Get companies first
        response = requests.get(f"{base_url}/results/companies", timeout=10)
        if response.status_code == 200:
            companies = response.json().get('companies', [])
            
            for company in companies:
                if company.get('transformed_analyses', 0) > 0:
                    symbol = company['symbol']
                    print(f"\n   Testing {symbol} transformed data...")
                    
                    # Test company transformed results
                    response = requests.get(f"{base_url}/transformed-results/{symbol}", timeout=10)
                    if response.status_code == 200:
                        results = response.json().get('results', [])
                        print(f"   ✅ {symbol} has {len(results)} transformed analyses")
                        
                        # Test specific transformed result
                        if results:
                            first_result = results[0]
                            date = first_result['date']
                            response = requests.get(f"{base_url}/transformed-results/{symbol}/{date}", timeout=10)
                            if response.status_code == 200:
                                data = response.json()
                                print(f"   ✅ Specific analysis loaded for {symbol} on {date}")
                                
                                # Check data structure
                                if 'metadata' in data and 'financial_data' in data:
                                    print(f"   ✅ Data structure is correct")
                                    metadata = data['metadata']
                                    print(f"      - Company: {metadata.get('company_ticker', 'N/A')}")
                                    print(f"      - Recommendation: {metadata.get('final_recommendation', 'N/A')}")
                                    print(f"      - Confidence: {metadata.get('confidence_level', 'N/A')}")
                                    print(f"      - Current Price: ${metadata.get('current_price', 0)}")
                                else:
                                    print(f"   ⚠️  Data structure may be incomplete")
                            else:
                                print(f"   ❌ Failed to load specific analysis: {response.status_code}")
                    else:
                        print(f"   ❌ Failed to load {symbol} transformed data: {response.status_code}")
                        print(f"      Response: {response.text}")
                    
                    break  # Test only first company with transformed data
        
    except Exception as e:
        print(f"❌ Transformed data endpoints error: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Backend API test completed")
    return True

if __name__ == "__main__":
    test_backend()
