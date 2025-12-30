import hashlib
import hmac
import json
import time
from typing import Dict, Optional
from urllib.parse import urlencode

import requests
from .config import get_config

import json


def bybit_v5_request(method: str, path: str, params: Optional[Dict] = None, body: Optional[Dict] = None) -> Dict:
    """Generic signed HTTP request helper for Bybit V5 API."""
    config = get_config()["external"]
    base_url = config["BYBIT_BASE_URL"].rstrip("/")
    api_key = config["BYBIT_API_KEY"]
    api_secret = config["BYBIT_API_SECRET"]

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

def get_account_balance(base_coin: str, quote_coin: str = "USDT") -> dict:
    """
    To determine total equity, available free margin for new trades, and locked capital.
    
    Args:
        base_coin: The asset being analyzed (e.g., "BTC")
        quote_coin: The currency used for buying (e.g., "USDT")
    """
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

def get_open_orders(base_coin: str, quote_coin: str) -> str:
    """
    Fetches active orders and returns a text report analyzing capital lock-up and order age.
    """
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


# def get_open_orders(symbol: Optional[str] = None, category: str = "spot") -> Dict:
#     """
#     Get all open orders.
    
#     Args:
#         symbol: Optional trading pair to filter by
#         category: Trading category ("spot", "linear", "inverse")
        
#     Returns:
#         Dict containing list of open orders
#     """
#     params = {
#         "category": category.lower()
#     }
    
#     if symbol:
#         params["symbol"] = symbol.upper()
    
#     data = bybit_v5_request("GET", "/v5/order/realtime", params=params)
#     return data.get("result", {})


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
