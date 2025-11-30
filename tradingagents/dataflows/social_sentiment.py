import requests
from langchain_core.tools import tool
from typing import Annotated

def get_stocktwits_trending() -> list[str]:
    """Fetch trending symbols from StockTwits."""
    url = "https://api.stocktwits.com/api/2/trending/symbols.json"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            data = response.json()
            return [s['symbol'] for s in data['symbols']]
        return []
    except Exception as e:
        print(f"Error fetching StockTwits trending: {e}")
        return []

def get_apewisdom_trending() -> list[str]:
    """Fetch trending tickers from Reddit via Ape Wisdom."""
    url = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/1"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code == 200:
            data = response.json()
            return [s['ticker'] for s in data['results']]
        return []
    except Exception as e:
        print(f"Error fetching Ape Wisdom trending: {e}")
        return []

@tool
def get_trending_social(
    platform: Annotated[str, "Platform to check: 'stocktwits', 'reddit', or 'all'"] = "all"
) -> str:
    """
    Retrieve a list of trending stocks from social media platforms (StockTwits, Reddit).
    Useful for finding 'hyped' stocks or retail sentiment plays.
    """
    results = []
    
    if platform in ["stocktwits", "all"]:
        st_symbols = get_stocktwits_trending()
        if st_symbols:
            results.append(f"StockTwits Trending: {', '.join(st_symbols[:10])}")
    
    if platform in ["reddit", "all"]:
        aw_symbols = get_apewisdom_trending()
        if aw_symbols:
            results.append(f"Reddit Trending (Ape Wisdom): {', '.join(aw_symbols[:10])}")
            
    if not results:
        return "No trending data available."
        
    return "\n\n".join(results)
