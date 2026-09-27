"""Ticker lookup by symbol or company name for the browser UI's ticker fields.

Asks Yahoo Finance's search endpoint (through the data layer) so "reliance industries"
finds RELIANCE.NS and "tencent" finds 0700.HK. When Yahoo is unreachable or
rate-limited, a small built-in list of well-known symbols keeps the box useful.
"""

from __future__ import annotations

import threading
import time

from cli.prompts import is_valid_ticker_input

# Yahoo quote types worth analysing; mutual-fund share classes and options are noise here.
KINDS = {"EQUITY": "Stock", "ETF": "ETF", "INDEX": "Index", "CRYPTOCURRENCY": "Crypto",
         "FUTURE": "Future", "CURRENCY": "FX"}

# symbol, name, exchange, kind — the offline fallback.
POPULAR = [
    ("AAPL", "Apple Inc.", "NASDAQ", "Stock"), ("MSFT", "Microsoft Corporation", "NASDAQ", "Stock"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ", "Stock"), ("AMZN", "Amazon.com, Inc.", "NASDAQ", "Stock"),
    ("GOOGL", "Alphabet Inc. (Google) Class A", "NASDAQ", "Stock"),
    ("META", "Meta Platforms, Inc. (Facebook)", "NASDAQ", "Stock"),
    ("TSLA", "Tesla, Inc.", "NASDAQ", "Stock"), ("AVGO", "Broadcom Inc.", "NASDAQ", "Stock"),
    ("AMD", "Advanced Micro Devices, Inc.", "NASDAQ", "Stock"), ("INTC", "Intel Corporation", "NASDAQ", "Stock"),
    ("NFLX", "Netflix, Inc.", "NASDAQ", "Stock"), ("ADBE", "Adobe Inc.", "NASDAQ", "Stock"),
    ("CRM", "Salesforce, Inc.", "NYSE", "Stock"), ("ORCL", "Oracle Corporation", "NYSE", "Stock"),
    ("PLTR", "Palantir Technologies Inc.", "NASDAQ", "Stock"), ("TSM", "Taiwan Semiconductor Manufacturing", "NYSE", "Stock"),
    ("BRK-B", "Berkshire Hathaway Inc. Class B", "NYSE", "Stock"), ("JPM", "JPMorgan Chase & Co.", "NYSE", "Stock"),
    ("BAC", "Bank of America Corporation", "NYSE", "Stock"), ("GS", "The Goldman Sachs Group, Inc.", "NYSE", "Stock"),
    ("V", "Visa Inc.", "NYSE", "Stock"), ("MA", "Mastercard Incorporated", "NYSE", "Stock"),
    ("WMT", "Walmart Inc.", "NYSE", "Stock"), ("COST", "Costco Wholesale Corporation", "NASDAQ", "Stock"),
    ("KO", "The Coca-Cola Company", "NYSE", "Stock"), ("PEP", "PepsiCo, Inc.", "NASDAQ", "Stock"),
    ("DIS", "The Walt Disney Company", "NYSE", "Stock"), ("NKE", "NIKE, Inc.", "NYSE", "Stock"),
    ("JNJ", "Johnson & Johnson", "NYSE", "Stock"), ("LLY", "Eli Lilly and Company", "NYSE", "Stock"),
    ("PFE", "Pfizer Inc.", "NYSE", "Stock"), ("UNH", "UnitedHealth Group Incorporated", "NYSE", "Stock"),
    ("XOM", "Exxon Mobil Corporation", "NYSE", "Stock"), ("CVX", "Chevron Corporation", "NYSE", "Stock"),
    ("BA", "The Boeing Company", "NYSE", "Stock"), ("UBER", "Uber Technologies, Inc.", "NYSE", "Stock"),
    ("TM", "Toyota Motor Corporation", "NYSE", "Stock"), ("BABA", "Alibaba Group Holding Limited", "NYSE", "Stock"),
    ("SPY", "SPDR S&P 500 ETF Trust", "NYSEArca", "ETF"), ("QQQ", "Invesco QQQ Trust (Nasdaq 100)", "NASDAQ", "ETF"),
    ("DIA", "SPDR Dow Jones Industrial Average ETF", "NYSEArca", "ETF"), ("IWM", "iShares Russell 2000 ETF", "NYSEArca", "ETF"),
    ("GLD", "SPDR Gold Shares", "NYSEArca", "ETF"),
    ("^GSPC", "S&P 500", "SNP", "Index"), ("^IXIC", "NASDAQ Composite", "NASDAQ", "Index"),
    ("^NSEI", "NIFTY 50", "NSE", "Index"), ("^BSESN", "S&P BSE SENSEX", "BSE", "Index"),
    ("RELIANCE.NS", "Reliance Industries Ltd", "NSE", "Stock"), ("TCS.NS", "Tata Consultancy Services Ltd", "NSE", "Stock"),
    ("INFY.NS", "Infosys Ltd", "NSE", "Stock"), ("HDFCBANK.NS", "HDFC Bank Ltd", "NSE", "Stock"),
    ("ICICIBANK.NS", "ICICI Bank Ltd", "NSE", "Stock"), ("SBIN.NS", "State Bank of India", "NSE", "Stock"),
    ("BHARTIARTL.NS", "Bharti Airtel Ltd", "NSE", "Stock"), ("ITC.NS", "ITC Ltd", "NSE", "Stock"),
    ("HINDUNILVR.NS", "Hindustan Unilever Ltd", "NSE", "Stock"), ("LT.NS", "Larsen & Toubro Ltd", "NSE", "Stock"),
    ("WIPRO.NS", "Wipro Ltd", "NSE", "Stock"), ("TATAMOTORS.NS", "Tata Motors Ltd", "NSE", "Stock"),
    ("ADANIENT.NS", "Adani Enterprises Ltd", "NSE", "Stock"), ("MARUTI.NS", "Maruti Suzuki India Ltd", "NSE", "Stock"),
    ("0700.HK", "Tencent Holdings Ltd", "Hong Kong", "Stock"), ("9988.HK", "Alibaba Group Holding Ltd", "Hong Kong", "Stock"),
    ("7203.T", "Toyota Motor Corp", "Tokyo", "Stock"), ("005930.KS", "Samsung Electronics Co., Ltd.", "KRX", "Stock"),
    ("ASML", "ASML Holding N.V.", "NASDAQ", "Stock"), ("SAP", "SAP SE", "NYSE", "Stock"),
    ("BTC-USD", "Bitcoin USD", "CCC", "Crypto"), ("ETH-USD", "Ethereum USD", "CCC", "Crypto"),
    ("SOL-USD", "Solana USD", "CCC", "Crypto"), ("XRP-USD", "XRP USD", "CCC", "Crypto"),
    ("DOGE-USD", "Dogecoin USD", "CCC", "Crypto"),
    ("GC=F", "Gold Futures", "COMEX", "Future"), ("CL=F", "Crude Oil Futures", "NYMEX", "Future"),
    ("EURUSD=X", "EUR/USD", "CCY", "FX"),
]

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 15 * 60
_CACHE_MAX = 500


def _entry(symbol: str, name: str, exchange: str, kind: str) -> dict:
    return {"symbol": symbol, "name": name, "exchange": exchange, "kind": kind}


def search_local(query: str, limit: int = 8) -> list[dict]:
    """Rank the built-in list: exact symbol, symbol prefix, name word prefix, substring."""
    q = query.strip().lower()
    if not q:
        return []
    ranked = []
    for symbol, name, exchange, kind in POPULAR:
        s, n = symbol.lower(), name.lower()
        base = s.split(".")[0]
        if q in (s, base):
            rank = 0
        elif s.startswith(q):
            rank = 1
        elif n.startswith(q) or any(w.startswith(q) for w in n.replace("(", " ").split()):
            rank = 2
        elif q in n or q in s:
            rank = 3
        else:
            continue
        ranked.append((rank, len(symbol), _entry(symbol, name, exchange, kind)))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in ranked[:limit]]


def _search_yahoo(query: str, limit: int) -> list[dict]:
    from tradingagents.dataflows.vendors.yahoo.search import search_quotes

    quotes = search_quotes(query, max_results=limit + 6)
    out = []
    for q in quotes:
        symbol, kind = str(q.get("symbol") or ""), KINDS.get(str(q.get("quoteType") or ""))
        if not kind or not symbol or not is_valid_ticker_input(symbol):
            continue
        name = " ".join(str(q.get("longname") or q.get("shortname") or symbol).split())
        out.append(_entry(symbol, name, str(q.get("exchDisp") or q.get("exchange") or ""), kind))
    return out[:limit]


def search_tickers(query: str, limit: int = 8) -> dict:
    """Matches for a symbol or company name, best first.

    Returns ``{"results": [...], "source": "yahoo" | "offline"}``; each result
    has ``symbol``, ``name``, ``exchange`` and ``kind``.
    """
    query = " ".join(query.split())[:64]
    if not query:
        return {"results": [], "source": "offline"}
    key = f"{query.lower()}|{limit}"
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return {"results": hit[1], "source": "yahoo"}
    try:
        results = _search_yahoo(query, limit)
    except Exception:  # noqa: BLE001 — offline, rate-limited or a changed endpoint
        return {"results": search_local(query, limit), "source": "offline"}
    if not results:  # Yahoo found nothing tradable; the built-in list may still know it
        return {"results": search_local(query, limit), "source": "offline"}
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = (now, results)
    return {"results": results, "source": "yahoo"}
