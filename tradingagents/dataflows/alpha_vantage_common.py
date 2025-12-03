import logging
import os
import requests
import pandas as pd
import json
from datetime import datetime
from io import StringIO

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.alphavantage.co/query"

def get_api_key() -> str:
    try:
        from tradingagents.config import get_settings
        return get_settings().require_api_key("alpha_vantage")
    except ImportError:
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")
        return api_key

def format_datetime_for_api(date_input) -> str:
    if isinstance(date_input, str):
        if len(date_input) == 13 and 'T' in date_input:
            return date_input
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}")
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

class AlphaVantageRateLimitError(Exception):
    pass

def _make_api_request(function_name: str, params: dict) -> dict | str:
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "trading_agents",
    })

    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement

    if entitlement:
        api_params["entitlement"] = entitlement
    elif "entitlement" in api_params:
        api_params.pop("entitlement", None)

    response = requests.get(API_BASE_URL, params=api_params, timeout=30)
    response.raise_for_status()

    response_text = response.text

    try:
        response_json = json.loads(response_text)
        if "Information" in response_json:
            info_message = response_json["Information"]
            if "rate limit" in info_message.lower() or "api key" in info_message.lower():
                raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {info_message}")
    except json.JSONDecodeError:
        pass

    return response_text



def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    if not csv_data or csv_data.strip() == "":
        return csv_data

    try:
        df = pd.read_csv(StringIO(csv_data))

        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])

        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]

        return filtered_df.to_csv(index=False)

    except (pd.errors.ParserError, KeyError, ValueError) as e:
        logger.warning("Failed to filter CSV data by date range: %s", e)
        return csv_data
