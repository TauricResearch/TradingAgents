import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
print(f"API Key: {api_key}")

# Test API connection
url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&apikey={api_key}'

try:
    response = requests.get(url, timeout=10)
    print(f"\nStatus Code: {response.status_code}")
    print(f"\nResponse:\n{response.json()}")
except Exception as e:
    print(f"Error: {e}")
