import hashlib
import hmac
import json
import time
from typing import Dict, Optional, List
from urllib.parse import urlencode

import requests
from tradingagents.config import settings

import json
from datetime import datetime, timedelta, timezone
import pandas as pd
from stockstats import StockDataFrame


def bybit_v5_request(method: str, path: str, params: Optional[Dict] = None, body: Optional[Dict] = None) -> Dict:
    """Generic signed HTTP request helper for Bybit V5 API."""
    base_url = settings.BYBIT_BASE_URL.rstrip("/")
    api_key = settings.BYBIT_API_KEY
    api_secret = settings.BYBIT_API_SECRET

    if not api_key or not api_secret:
        raise ValueError("Missing BYBIT_API_KEY or BYBIT_API_SECRET")

    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"

    # Build query string for GET or body for POST
    if method.upper() == "GET" and params:
        query_string = urlencode(sorted(params.items()))
        url = f"{base_url}{path}?{query_string}"
        payload = query_string
    else:
        url = f"{base_url}{path}"
        payload = json.dumps(body, separators=(',', ':')) if body else ""

    # Create signature
    sign_payload = f"{timestamp}{api_key}{recv_window}{payload}"
    signature = hmac.new(
        api_secret.encode('utf-8'),
        sign_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Headers
    headers = {
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json"
    }

    # Make request
    if method.upper() == "GET":
        response = requests.get(url, headers=headers)
    else:
        response = requests.post(url, headers=headers, data=payload)

    response.raise_for_status()
    data = response.json()

    if data.get("retCode") != 0:
        raise ValueError(f"Bybit API error: {data.get('retMsg')}")

    return data

def get_account_balance(symbol: str) -> dict:
    """
    To determine total equity, available free margin for new trades, and locked capital.
    
    Args:
        symbol: Format "BASE/QUOTE" (e.g., "BTC/USDT")
        quote_coin: The currency used for buying (e.g., "USDT")
    """
    if "/" not in symbol:
        return f"Error: Symbol '{symbol}' is not in the correct format. Please use 'BASE/QUOTE' format, e.g., 'BTC/USDT'."
    base_coin, quote_coin = symbol.split("/")
    # 1. Fetch all assets from Bybit (omitting 'coin' gets everything)
    data = bybit_v5_request("GET", "/v5/account/wallet-balance", {
        "accountType": "UNIFIED"
    })

    
    # 2. Parse the raw response
    try:
        raw_list = data["result"]["list"][0]["coin"]
        # Convert list to a dictionary for easy lookup: {'BTC': {...}, 'USDT': {...}}
        result = {
            item["coin"]: {k: float(v) if v else 0.0 for k, v in item.items() if k != "coin"}
            for item in raw_list
        }
    except (IndexError, KeyError, TypeError):
        result = {"error": "Could not retrieve wallet balance"}
    
    total_equity = sum(asset.get("usdValue", 0.0) for asset in result.values())

    report = f"# Account Balance Report for {base_coin}/{quote_coin}\n"
    report += f"** Total Equity: ${total_equity} **\n"
    report += f"## {quote_coin} (Quote) Details:\n"
    report += json.dumps(result.get(quote_coin, {}), indent=2) + "\n"
    report += f"## {base_coin} (Base) Details:\n"
    report += json.dumps(result.get(base_coin, {}), indent=2) + "\n"
    return report

def get_symbol(base_coin: str, quote_coin: str) -> str:
    """
    Safely retrieves the correct Bybit symbol (e.g., "BTCUSDT") for a given base/quote pair.
    
    Args:
        base_coin: The asset (e.g., "BTC")
        quote_coin: The currency (e.g., "USDT")
        category: "linear", "spot", or "inverse"
        
    Returns:
        The valid symbol string (e.g., "BTCUSDT") or None if not found.
    """
    # 1. Query the API specifically for this Base Coin
    # This filters the search on the server side, which is much faster.
    params = {
        "category": "spot",
        "baseCoin": base_coin.upper(),
        "limit": 20 # We only expect a few matches (e.g., BTCUSDT, BTC-PERP)
    }
    
    data = bybit_v5_request("GET", "/v5/market/instruments-info", params)

    result = data.get("result", {})
    instruments = result.get("list", [])

    # 2. Find the exact match for the Quote Coin
    # This handles cases where BTC might pair with USDT, USDC, or DAI
    for item in instruments:
        if item.get("quoteCoin") == quote_coin.upper() and item.get("baseCoin") == base_coin.upper():
            return item.get("symbol")

    # 3. Fallback/Error handling
    return None

def get_open_orders(symbol: str) -> str:
    """
    Fetches active orders and returns a text report analyzing capital lock-up and order age.
    """
    if "/" not in symbol:
        return f"Error: Symbol '{symbol}' is not in the correct format. Please use 'BASE/QUOTE' format, e.g., 'BTC/USDT'."
    base_coin, quote_coin = symbol.split("/")
    symbol = get_symbol(base_coin, quote_coin)
    if not symbol:
        return f"Error: No valid spot symbol found for {base_coin}/{quote_coin}"
    # 1. Fetch Open Orders
    data = bybit_v5_request("GET", "/v5/order/realtime", {
        "category": "spot",
        "symbol": symbol.upper(),
        "openOnly": 0  # 0=Active orders (Pending)
    })

    result = data.get("result", {})
    orders = result.get("list", [])

    for i in range(len(orders)):
        # try to change to float if can
        for k, v in orders[i].items():
            if k in ["orderLinkId", "orderId"]:
                continue
            try:
                orders[i][k] = float(v)
            except:
                pass
        # change createdTime and updatedTime to yyyy-mm-dd hh:mm:ss format (utc)
        orders[i]["createdTime"] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(orders[i]["createdTime"]/1000))
        orders[i]["updatedTime"] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(orders[i]["updatedTime"]/1000))

    report = f"# Open Orders for {symbol.upper()}\n"
    report += json.dumps(orders, indent=2)

    return report


def get_market_data(symbol:str, start_date: str, end_date: str) -> str:
    """
    Fetches historical Daily (1D) OHLCV data for a specific date range.
    
    Args:
        symbol: Format "BASE/QUOTE" (e.g., "BTC/USDT").
        start_date: Format "YYYY-MM-DD" (Inclusive).
        end_date: Format "YYYY-MM-DD" (Inclusive).
        
    Returns:
        A formatted CSV-style string report.
    """
    if "/" not in symbol:
        return f"Error: Symbol '{symbol}' is not in the correct format. Please use 'BASE/QUOTE' format, e.g., 'BTC/USDT'."
    # 1. Convert Date Strings to Timestamps (ms)
    try:
        # Start of the start_date (00:00:00)
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
        ts_start = int(dt_start.timestamp() * 1000)
        
        # End of the end_date (23:59:59) - Bybit 'end' parameter is inclusive if valid candle exists
        dt_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        ts_end = int(dt_end.timestamp() * 1000)
    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."

    # 2. Request Data from Bybit
    # We use interval "D" for Daily. Limit 1000 covers ~2.7 years of daily data in one call.
    base_coin, quote_coin = symbol.split("/")
    symbol2 = get_symbol(base_coin, quote_coin)
    if not symbol2:
        return f"# Error: No valid spot symbol found for {base_coin}/{quote_coin}."
    params = {
        "category": "spot",
        "symbol": symbol2.upper(),
        "interval": "D",
        "start": ts_start,
        "end": ts_end,
        "limit": 1000 
    }
    
    data = bybit_v5_request("GET", "/v5/market/kline", params)

    result = data.get("result", {})
    raw_candles = result.get("list", []) # Returns [timestamp, open, high, low, close, volume, turnover]
    
    if not raw_candles:
        return f"# No market data found for {symbol.upper()} from {start_date} to {end_date}."

    # 3. Format Data
    # Bybit returns Newest -> Oldest. We reverse it to get chronological order (Oldest -> Newest).
    raw_candles.reverse()
    
    csv_lines = []
    
    for candle in raw_candles:
        # Parse Timestamp
        ts_ms = int(candle[0])
        date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
        
        # Parse Values
        open_p = candle[1]
        high_p = candle[2]
        low_p = candle[3]
        close_p = candle[4]
        volume = float(candle[5]) # Volume in Base Currency (e.g. BTC)
        
        # Format Line: Date,Open,High,Low,Close,Volume
        # Note: We omit Dividends/Stock Splits as requested
        line = f"{date_str},{open_p},{high_p},{low_p},{close_p},{int(volume)}"
        csv_lines.append(line)

    # 4. Construct Final Report Header
    current_time = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    header = [
        f"# Crypto data for {symbol.upper()} from {start_date} to {end_date}",
        f"# Total records: {len(csv_lines)}",
        f"# Data retrieved on: {current_time}",
        "",
        "Date,Open,High,Low,Close,Volume"
    ]
    
    return "\n".join(header + csv_lines)

def get_crypto_indicator_window(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int
) -> str:
    """
    Calculates technical indicators for a crypto pair using Bybit data.
    Fix: Uses index lookup for dates since stockstats sets 'date' as the index.
    """
    if "/" not in symbol:
        return f"Error: Symbol '{symbol}' is not in the correct format. Please use 'BASE/QUOTE' format, e.g., 'BTC/USDT'."
    base_coin, quote_coin = symbol.split("/")
    symbol2 = get_symbol(base_coin, quote_coin)
    
    # 1. Define Supported Indicators (Same as before)
    best_ind_params = {
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    # 2. Calculate Date Range
    target_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_window_dt = target_date_dt - timedelta(days=look_back_days)
    
    # Buffer: Fetch 250 extra days before start_window for lagging indicators (like 200 SMA)
    buffer_days = 250 
    fetch_start_dt = start_window_dt - timedelta(days=buffer_days)
    
    # Convert to timestamps for Bybit (ms)
    ts_start = int(fetch_start_dt.timestamp() * 1000)
    ts_end = int((target_date_dt + timedelta(days=1)).timestamp() * 1000)

    # 3. Fetch Data from Bybit
    params = {
        "category": "linear",
        "symbol": symbol2.upper(),
        "interval": "D",
        "start": ts_start,
        "end": ts_end,
        "limit": 1000
    }
    
    # Ensure 'bybit_v5_request' is defined in your scope
    data = bybit_v5_request("GET", "/v5/market/kline", params)
    raw_list = data.get("result", {}).get("list", [])
    
    if not raw_list:
        return f"Error: No data found for {symbol2}."

    # 4. Prepare DataFrame
    parsed_data = []
    for row in raw_list:
        parsed_data.append({
            # Standardize date format for the Index
            "date": datetime.fromtimestamp(int(row[0])/1000).strftime('%Y-%m-%d'),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5])
        })
    
    df = pd.DataFrame(parsed_data)
    # Sort Ascending (Oldest -> Newest) is CRITICAL for stockstats
    df = df.sort_values("date").reset_index(drop=True)
    
    # 5. Calculate Indicator
    # retype(df) sets 'date' column as the Index!
    stock = StockDataFrame.retype(df) 
    
    try:
        # Trigger calculation
        _ = stock[indicator] 
    except KeyError:
        return f"Error: Could not calculate {indicator}. Check if supported."

    # 6. Build Report
    report_lines = []
    current_check_date = target_date_dt
    
    while current_check_date >= start_window_dt:
        date_str = current_check_date.strftime('%Y-%m-%d')
        
        # --- FIX: Use .loc to find the row by Index (Date) ---
        try:
            # Locate the row using the date string index
            val = stock.loc[date_str][indicator]
            
            # Format value
            if isinstance(val, (float, int)):
                val_str = f"{val:.4f}"
            else:
                val_str = str(val)
                
            report_lines.append(f"{date_str}: {val_str}")
            
        except KeyError:
            # Date not found in index
            report_lines.append(f"{date_str}: N/A (No Data)")
        except Exception as e:
            report_lines.append(f"{date_str}: Error ({str(e)})")
            
        current_check_date -= timedelta(days=1)

    # 7. Final Output
    description = best_ind_params.get(indicator, "No description available.")
    
    result_str = (
        f"## {indicator} values for {symbol2} from {start_window_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(report_lines)
        + "\n\n"
        + description
    )

    return result_str

def get_crypto_indicators_bulk(
    symbol: str,
    indicators: List[str],
    curr_date: str,
    look_back_days: int
) -> str:
    """
    Calculates multiple technical indicators for a crypto pair in one go.
    
    Args:
        symbol: e.g., "BTC/USDT"
        indicators: List of keys, e.g. ["rsi", "close_200_sma", "macd"]
        curr_date: "YYYY-MM-DD"
        look_back_days: Days of history to show in the report.
    """
    if "/" not in symbol:
        return f"Error: Symbol '{symbol}' is not in the correct format. Please use 'BASE/QUOTE' format, e.g., 'BTC/USDT'."
    base_coin, quote_coin = symbol.split("/")
    symbol2 = get_symbol(base_coin, quote_coin)
    
    # 1. Define Descriptions
    best_ind_params = {
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    # 2. Fetch Data (ONLY ONCE)
    # ---------------------------------------------------------
    target_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_window_dt = target_date_dt - timedelta(days=look_back_days)
    
    # Buffer for lagging indicators
    buffer_days = 250 
    fetch_start_dt = start_window_dt - timedelta(days=buffer_days)
    
    ts_start = int(fetch_start_dt.timestamp() * 1000)
    ts_end = int((target_date_dt + timedelta(days=1)).timestamp() * 1000)

    params = {
        "category": "linear",
        "symbol": symbol2.upper(),
        "interval": "D",
        "start": ts_start,
        "end": ts_end,
        "limit": 1000
    }
    
    data = bybit_v5_request("GET", "/v5/market/kline", params)
    raw_list = data.get("result", {}).get("list", [])
    
    if not raw_list:
        return f"Error: No data found for {symbol2}."

    parsed_data = []
    for row in raw_list:
        parsed_data.append({
            "date": datetime.fromtimestamp(int(row[0])/1000).strftime('%Y-%m-%d'),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5])
        })
    
    df = pd.DataFrame(parsed_data)
    df = df.sort_values("date").reset_index(drop=True)
    stock = StockDataFrame.retype(df) 
    # ---------------------------------------------------------

    # 3. Process Each Indicator
    final_report = [f"# Technical Indicators Report for {symbol2}\n" + '-' * 40]

    for ind in indicators:
        # Pre-calculation check
        try:
            # Trigger calculation of the specific column
            _ = stock[ind]
        except (KeyError, ValueError):
            final_report.append(f"## Error: Indicator '{ind}' is not supported or failed to calculate.\n")
            continue

        # Generate Block Report
        report_lines = []
        current_check_date = target_date_dt
        
        while current_check_date >= start_window_dt:
            date_str = current_check_date.strftime('%Y-%m-%d')
            try:
                # Use .loc because 'date' is the index
                val = stock.loc[date_str][ind]
                
                if isinstance(val, (float, int)):
                    val_str = f"{val:.4f}"
                else:
                    val_str = str(val)
                report_lines.append(f"{date_str}: {val_str}")
            except KeyError:
                report_lines.append(f"{date_str}: N/A")
            
            current_check_date -= timedelta(days=1)

        description = best_ind_params.get(ind, "No description available.")
        
        block = (
            f"## {ind} values for {symbol2} from {start_window_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + "\n".join(report_lines)
            + "\n\n"
            + f"Description: {description}\n"
            + "-" * 40  # Separator line
        )
        final_report.append(block)

    return "\n\n".join(final_report)

def get_order_status(order_id: str, category: str = "spot") -> Dict:
    """
    Get order status by order ID.
    
    Args:
        order_id: Order ID to query
        category: Trading category ("spot", "linear", "inverse")
        
    Returns:
        Dict containing order information
    """
    params = {
        "category": category.lower(),
        "orderId": order_id
    }
    
    data = bybit_v5_request("GET", "/v5/order/realtime", params=params)
    result = data.get("result", {})
    orders = result.get("list", [])
    
    return orders[0] if orders else {}


def cancel_order(order_id: str, symbol: str, category: str = "spot") -> Dict:
    """
    Cancel an existing order.
    
    Args:
        order_id: Order ID to cancel
        symbol: Trading pair symbol
        category: Trading category ("spot", "linear", "inverse")
        
    Returns:
        Dict containing cancellation result
    """
    body = {
        "category": category.lower(),
        "symbol": symbol.upper(),
        "orderId": order_id
    }
    
    data = bybit_v5_request("POST", "/v5/order/cancel", body=body)
    return data.get("result", {})


def get_order_history(
    symbol: Optional[str] = None, 
    category: str = "spot",
    limit: int = 20
) -> Dict:
    """
    Get order history.
    
    Args:
        symbol: Optional trading pair to filter by
        category: Trading category ("spot", "linear", "inverse")
        limit: Number of records to return (max 50)
        
    Returns:
        Dict containing order history
    """
    params = {
        "category": category.lower(),
        "limit": min(limit, 50)
    }
    
    if symbol:
        params["symbol"] = symbol.upper()
    
    data = bybit_v5_request("GET", "/v5/order/history", params=params)
    return data.get("result", {})


def get_account_info(account_type: str = "UNIFIED") -> Dict:
    """
    Get account information.
    
    Args:
        account_type: Account type ("UNIFIED")
        
    Returns:
        Dict containing account information
    """
    params = {
        "accountType": account_type
    }
    
    data = bybit_v5_request("GET", "/v5/account/info", params=params)
    return data.get("result", {})

def place_order(
    symbol: str,
    side: str,
    order_type: str,
    qty: float,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    sl_limit_price: Optional[float] = None,
    tp_limit_price: Optional[float] = None,
    sl_order_type: str = "Market",
    tp_order_type: str = "Market",
    time_in_force: str = "GTC",
    account_type: str = "UNIFIED",
    category: str = "spot",
    order_link_id: Optional[str] = None,
    reduce_only: bool = False,
    close_on_trigger: bool = False
) -> Dict:
    """
    Place an order on Bybit with comprehensive support for spot trading.
    
    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Order side ("Buy" or "Sell")
        order_type: Order type ("Market", "Limit")
        qty: Order quantity
        price: Order price (required for Limit orders)
        stop_loss: Stop loss trigger price
        take_profit: Take profit trigger price
        sl_limit_price: Stop loss limit price (for limit SL orders)
        tp_limit_price: Take profit limit price (for limit TP orders)
        sl_order_type: Stop loss order type ("Market" or "Limit")
        tp_order_type: Take profit order type ("Market" or "Limit")
        time_in_force: Time in force ("GTC", "IOC", "FOK", "PostOnly")
        account_type: Account type ("UNIFIED")
        category: Trading category ("spot", "linear", "inverse")
        order_link_id: Custom order ID
        reduce_only: Reduce only flag
        close_on_trigger: Close on trigger flag
        
    Returns:
        Dict containing order result
        
    Raises:
        ValueError: If required parameters are missing or invalid
    """
    # Validate required parameters
    if not symbol or not side or not order_type:
        raise ValueError("symbol, side, and order_type are required")
    
    if qty <= 0:
        raise ValueError("qty must be greater than 0")
    
    # Validate order type and price requirement
    if order_type.upper() == "LIMIT" and price is None:
        raise ValueError("price is required for Limit orders")
    
    # Validate side
    if side.upper() not in ["BUY", "SELL"]:
        raise ValueError("side must be 'Buy' or 'Sell'")
    
    # Validate order type
    valid_order_types = ["MARKET", "LIMIT"]
    if order_type.upper() not in valid_order_types:
        raise ValueError(f"order_type must be one of {valid_order_types}")
    
    # Build order body
    body = {
        "category": category.lower(),
        "symbol": symbol.upper(),
        "side": side.capitalize(),
        "orderType": order_type.capitalize(),
        "qty": str(qty),
        "timeInForce": time_in_force,
    }
    
    # Add price for limit orders
    if price is not None:
        body["price"] = str(price)
    
    # Add stop loss with proper formatting
    if stop_loss is not None:
        body["stopLoss"] = str(stop_loss)
        body["slOrderType"] = sl_order_type.capitalize()
        
        # Add limit price for stop loss if specified
        if sl_order_type.upper() == "LIMIT" and sl_limit_price is not None:
            body["slLimitPrice"] = str(sl_limit_price)
    
    # Add take profit with proper formatting
    if take_profit is not None:
        body["takeProfit"] = str(take_profit)
        body["tpOrderType"] = tp_order_type.capitalize()
        
        # Add limit price for take profit if specified
        if tp_order_type.upper() == "LIMIT" and tp_limit_price is not None:
            body["tpLimitPrice"] = str(tp_limit_price)
    
    # Add optional parameters
    if order_link_id:
        body["orderLinkId"] = order_link_id
    
    if reduce_only:
        body["reduceOnly"] = True
    
    if close_on_trigger:
        body["closeOnTrigger"] = True
    
    try:
        data = bybit_v5_request("POST", "/v5/order/create", body=body)
        return data.get("result", {})
    except Exception as e:
        raise ValueError(f"Failed to place order: {str(e)}")

def place_spot_order_with_sl_tp(
    symbol: str,
    side: str,
    qty: float,
    price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    sl_limit_price: Optional[float] = None,
    tp_limit_price: Optional[float] = None,
    sl_order_type: str = "Market",
    tp_order_type: str = "Market",
    order_type: str = "Limit",
    time_in_force: str = "PostOnly"
) -> Dict:
    """
    Convenience function to place a spot order with stop loss and take profit.
    
    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        side: Order side ("Buy" or "Sell")
        qty: Order quantity
        price: Limit price (None for market orders)
        stop_loss_price: Stop loss trigger price
        take_profit_price: Take profit trigger price
        sl_limit_price: Stop loss limit price (for limit SL orders)
        tp_limit_price: Take profit limit price (for limit TP orders)
        sl_order_type: Stop loss order type ("Market" or "Limit")
        tp_order_type: Take profit order type ("Market" or "Limit")
        order_type: "Limit" or "Market"
        time_in_force: Time in force ("GTC", "IOC", "FOK", "PostOnly")
        
    Returns:
        Dict containing order result
    """
    return place_order(
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        price=price,
        stop_loss=stop_loss_price,
        take_profit=take_profit_price,
        sl_limit_price=sl_limit_price,
        tp_limit_price=tp_limit_price,
        sl_order_type=sl_order_type,
        tp_order_type=tp_order_type,
        time_in_force=time_in_force,
        category="spot"
    )
