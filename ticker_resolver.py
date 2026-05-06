"""Resolve a free-form company-name query (Chinese, English, ticker) to a
Yahoo-Finance-style ticker symbol.

Pure-Python — no Streamlit dependency. Used by both ``webui.py`` (for the live
sidebar input) and ``scheduler.py`` (for the daily-batch tickers list).

Resolution order (cheapest → most expensive):
  1. Built-in alias dict (Chinese names of popular stocks → US/HK ticker)
  2. Plain ticker pattern (``NVDA``, ``BRK-B``, ``600519.SS``)
  3. yfinance.Search (handles English company names: "Apple Inc." → AAPL)
  4. Gemini LLM (handles A-shares, less-common names, typos)
  5. Fallback: upper-cased input

Both callers should have ``HTTPS_PROXY`` set in the environment if their host
can't reach Google APIs / yfinance directly.
"""
from __future__ import annotations

import functools
import re
from typing import Optional

TICKER_ALIASES: dict[str, str] = {
    # ─── US tech ───
    "苹果": "AAPL", "蘋果": "AAPL",
    "微软": "MSFT", "微軟": "MSFT",
    "谷歌": "GOOGL", "Google": "GOOGL", "alphabet": "GOOGL", "Alphabet": "GOOGL",
    "亚马逊": "AMZN", "亞馬遜": "AMZN",
    "脸书": "META", "臉書": "META", "facebook": "META", "Facebook": "META", "meta": "META",
    "英伟达": "NVDA", "英偉達": "NVDA", "辉达": "NVDA",
    "特斯拉": "TSLA",
    "奈飞": "NFLX", "网飞": "NFLX",
    "甲骨文": "ORCL",
    "超微": "AMD", "超威": "AMD",
    "英特尔": "INTC", "英特爾": "INTC",
    "台积电": "TSM", "台積電": "TSM",
    "博通": "AVGO",
    "高通": "QCOM",
    "美光": "MU",
    "应用材料": "AMAT", "應用材料": "AMAT",
    "阿斯麦": "ASML", "阿斯麥": "ASML",
    "赛富时": "CRM", "salesforce": "CRM", "Salesforce": "CRM",
    "奥多比": "ADBE", "Adobe": "ADBE",
    "迪士尼": "DIS",
    # ─── Finance ───
    "摩根大通": "JPM", "高盛": "GS", "摩根士丹利": "MS",
    "美国银行": "BAC", "花旗": "C",
    "伯克希尔": "BRK-B", "巴菲特": "BRK-B",
    "贝莱德": "BLK",
    "维萨": "V", "Visa": "V", "万事达": "MA", "Mastercard": "MA",
    # ─── Other US ───
    "可口可乐": "KO", "百事": "PEP", "麦当劳": "MCD", "星巴克": "SBUX",
    "耐克": "NKE", "沃尔玛": "WMT", "好市多": "COST",
    "辉瑞": "PFE", "强生": "JNJ", "礼来": "LLY", "默克": "MRK",
    "波音": "BA", "卡特彼勒": "CAT", "通用电气": "GE",
    "埃克森美孚": "XOM", "雪佛龙": "CVX",
    "宝洁": "PG", "联合健康": "UNH",
    # ─── Chinese ADRs / HK ───
    "阿里巴巴": "BABA", "阿里": "BABA",
    "京东": "JD", "拼多多": "PDD",
    "百度": "BIDU", "网易": "NTES",
    "蔚来": "NIO", "小鹏": "XPEV",
    "理想汽车": "LI", "理想": "LI",
    "腾讯": "TCEHY", "騰訊": "TCEHY",
    "美团": "MPNGY",
    # ─── Crypto-adjacent ───
    "比特币": "BTC-USD", "以太坊": "ETH-USD", "以太币": "ETH-USD",
    "微策略": "MSTR", "MicroStrategy": "MSTR",
    "coinbase": "COIN", "Coinbase": "COIN",
    # ─── ETFs ───
    "标普": "SPY", "标普500": "SPY", "spy": "SPY",
    "纳指": "QQQ", "纳斯达克": "QQQ",
    "道指": "DIA", "道琼斯": "DIA",
    "罗素": "IWM",
}


@functools.lru_cache(maxsize=500)
def _llm_resolve(query: str) -> Optional[str]:
    """Ask Gemini to map a free-form query to a Yahoo Finance ticker.

    Cached at module level — repeated lookups for the same query are free.
    Caller must have proxy env set so the API is reachable.
    """
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
        prompt = (
            "You are a stock ticker resolver. Given a company name or query in any "
            "language, return the most-likely Yahoo Finance ticker symbol.\n\n"
            "Rules:\n"
            "- Output only the ticker symbol — no explanation, no markdown, no period.\n"
            "- US stocks: just the symbol (AAPL, NVDA, TSLA).\n"
            "- Hong Kong stocks: NNNN.HK (e.g., 0700.HK for Tencent).\n"
            "- Mainland China A-shares: NNNNNN.SS for Shanghai, NNNNNN.SZ for Shenzhen.\n"
            "- Tokyo: NNNN.T. London: TICK.L. Other exchanges: standard Yahoo suffix.\n"
            "- If the company is dual-listed and has a US ADR, prefer the US ADR.\n"
            "- If you cannot determine a ticker confidently, output exactly: UNKNOWN\n\n"
            f"Query: {query}\n\n"
            "Ticker:"
        )
        result = llm.invoke(prompt)
        ticker = (result.content if hasattr(result, "content") else str(result)).strip()
        ticker = ticker.split()[0].rstrip(".,;:!?").upper() if ticker else ""
        if not ticker or ticker == "UNKNOWN":
            return None
        if not re.fullmatch(r"[A-Z0-9]{1,8}([.\-][A-Z0-9]{1,4})?", ticker):
            return None
        return ticker
    except Exception:
        return None


def resolve_ticker(query: str) -> tuple[str, str]:
    """Resolve user input to ``(ticker, display_message)``.

    ``display_message`` is empty when the input was already a clean ticker;
    otherwise it explains how the resolution happened (helpful for logs/UI).
    """
    q = query.strip()
    if not q:
        return "", ""

    # 1. Alias dict (case-insensitive on ASCII keys)
    if q in TICKER_ALIASES:
        t = TICKER_ALIASES[q]
        return t, f"{q} → {t}"
    for k, v in TICKER_ALIASES.items():
        if k.lower() == q.lower():
            return v, f"{k} → {v}"

    # 2. Looks like a ticker already
    if re.fullmatch(r"[A-Z]{1,6}([.\-][A-Z0-9]{1,4})?", q) or \
       re.fullmatch(r"[A-Za-z]{1,6}[.\-][A-Za-z0-9]{1,4}", q) or \
       re.fullmatch(r"[A-Za-z0-9]+[.\-][A-Za-z0-9]+", q):
        return q.upper(), q.upper()

    # 3. yfinance Search (English-only — useless for Chinese)
    if not re.search(r"[一-鿿]", q):
        try:
            from yfinance import Search
            quotes = Search(q, max_results=5).quotes or []
            for quote in quotes:
                if quote.get("quoteType") == "EQUITY" and quote.get("symbol"):
                    sym = quote["symbol"]
                    name = quote.get("shortname") or quote.get("longname") or sym
                    return sym, f"{q} → {sym} ({name})"
            if quotes and quotes[0].get("symbol"):
                sym = quotes[0]["symbol"]
                name = quotes[0].get("shortname") or sym
                return sym, f"{q} → {sym} ({name})"
        except Exception:
            pass

    # 4. LLM fallback
    llm_ticker = _llm_resolve(q)
    if llm_ticker:
        return llm_ticker, f"{q} → {llm_ticker} 🤖"

    # 5. Final fallback
    return q.upper(), ""
