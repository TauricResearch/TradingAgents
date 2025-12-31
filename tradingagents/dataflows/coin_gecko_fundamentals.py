import requests
from .alpha_vantage_common import API_BASE_URL
from tradingagents.dataflows.config import get_config

def get_market_cap() -> str:
    """
    Retrieve the market capitalization percentage data for various cryptocurrencies using CoinGecko.

    Returns:
        str: Market capitalization percentage data for cryptocurrencies
    """
    config = get_config()
    api_base_url = config["external"].get("COIN_GECKO_API_BASE_URL", "https://api.coingecko.com/api/v3")
    endpoint = f"{api_base_url}/global"
    response = requests.get(endpoint)
    print(f"DEBUG: CoinGecko API response status code: {response.status_code}")
    response.raise_for_status()
    data = response.json()
    market_cap_pct = data.get("data", {}).get("market_cap_percentage", {})
    # return json.dumps(result, indent=2)
    result = "# Market Capitalization Percentage Data\n\n"
    for coin, percentage in market_cap_pct.items():
        # Format each line as "Coin: XX.XX%"
        result += f"- {coin.upper()}: {percentage:.2f}%\n"
    return result
