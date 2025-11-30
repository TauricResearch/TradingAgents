import requests
import json

def test_stocktwits():
    print("Testing StockTwits Trending...")
    url = "https://api.stocktwits.com/api/2/trending/symbols.json"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            data = response.json()
            symbols = [s['symbol'] for s in data['symbols']]
            print(f"StockTwits Trending: {symbols[:5]}")
            return True
        else:
            print(f"StockTwits Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"StockTwits Error: {e}")
        return False

def test_apewisdom():
    print("\nTesting Ape Wisdom (Reddit)...")
    url = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            data = response.json()
            # Ape Wisdom returns a list of objects
            symbols = [s['ticker'] for s in data['results']]
            print(f"Ape Wisdom Trending: {symbols[:5]}")
            return True
        else:
            print(f"Ape Wisdom Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"Ape Wisdom Error: {e}")
        return False

if __name__ == "__main__":
    st_success = test_stocktwits()
    aw_success = test_apewisdom()
