"""Vietnam market adapter: data flows, regulatory constraints, and tax/friction models.

Implements Vietnamese equity market mechanics (HOSE, HNX, UPCoM):
- Regulatory: Ban on short selling on underlying equities (Luật Chứng khoán 2019).
- Tax model: 0.1% Personal Income Tax (Thuế TNCN) deducted on gross sell value
  regardless of profit/loss (Luật Thuế TNCN, TT 111/2013/TT-BTC).
- Brokerage fees: ~0.15% per leg (~0.30% round-trip) + exchange fees.
- Exchange price limits: HOSE ±7%, HNX ±10%, UPCoM ±15%.
- Settlement cycle: T+2.
- Localized news and macro data fetching for Vietnamese tickers (.VN).
"""

from __future__ import annotations

import contextlib
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .date_window import in_window

logger = logging.getLogger(__name__)

# Standard statutory rates and exchange parameters in Vietnam
VN_DEFAULT_TAX_RATE_SELL = 0.001  # 0.1% TNCN on sell turnover
VN_DEFAULT_TRADING_FEE_RATE = 0.0015  # 0.15% brokerage fee per side
VN_DEFAULT_SETTLEMENT_DAYS = 2  # T+2 settlement cycle
VN_PRICE_LIMIT_HOSE = 0.07  # ±7%
VN_PRICE_LIMIT_HNX = 0.10  # ±10%
VN_PRICE_LIMIT_UPCOM = 0.15  # ±15%

# Top liquid Vietnamese tickers for auto-detection
VN_COMMON_TICKERS = frozenset({
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    "DGC", "DCM", "DPM", "PVD", "PVS", "PVT", "BSR", "OIL", "KBC", "KDH",
    "NLG", "PDR", "DIG", "DXG", "VCI", "HCM", "VND", "CTS", "BSI", "FTS",
    "VIX", "HAH", "GMD", "REE", "PC1", "E1VFVN30", "FUEVFVND", "FUESSVFL",
})


def is_vietnam_symbol(symbol: str) -> bool:
    """Return True if symbol represents a Vietnamese equity or index."""
    if not isinstance(symbol, str):
        return False
    s = symbol.strip().upper()
    if s.endswith(".VN") or s.endswith(":VN"):
        return True
    if s in {"^VNINDEX", "^VN30", "VNINDEX", "VN30"}:
        return True
    return False


def normalize_vn_symbol(symbol: str) -> str:
    """Normalize Vietnamese symbol representation to canonical Yahoo ticker format (<TICKER>.VN)."""
    if not isinstance(symbol, str) or not symbol.strip():
        return symbol
    s = symbol.strip().upper()
    if s.endswith(":VN"):
        return f"{s[:-3]}.VN"
    if s.endswith(".VN"):
        return s
    if s in VN_COMMON_TICKERS:
        return f"{s}.VN"
    return s


def calculate_vn_trade_friction(
    entry_price: float,
    exit_price: float,
    shares: int = 100,
    fee_rate: float = VN_DEFAULT_TRADING_FEE_RATE,
    tax_rate_sell: float = VN_DEFAULT_TAX_RATE_SELL,
) -> dict:
    """Calculate the comprehensive trading friction, tax, and net return for a Vietnam stock trade.

    Under Vietnamese tax law:
    - 0.1% Personal Income Tax (Thuế TNCN) is levied on the GROSS SALE PROCEEDS.
      No deduction is allowed for trading losses or acquisition costs.
    - Transaction fee is charged on both Buy and Sell sides.
    """
    buy_value = entry_price * shares
    buy_fee = buy_value * fee_rate
    total_cost = buy_value + buy_fee

    sell_value = exit_price * shares
    sell_fee = sell_value * fee_rate
    sell_tax = sell_value * tax_rate_sell

    net_proceeds = sell_value - sell_fee - sell_tax
    gross_profit = sell_value - buy_value
    net_profit = net_proceeds - total_cost

    total_friction = buy_fee + sell_fee + sell_tax
    net_roi_percent = (net_profit / total_cost) * 100 if total_cost > 0 else 0.0

    # Minimum percentage gain required to break even after round-trip fees and sell tax
    # sell_value * (1 - fee_rate - tax_rate) = buy_value * (1 + fee_rate)
    # exit / entry = (1 + fee_rate) / (1 - fee_rate - tax_rate)
    breakeven_multiplier = (1 + fee_rate) / (1 - fee_rate - tax_rate_sell)
    breakeven_gain_percent = (breakeven_multiplier - 1) * 100

    return {
        "buy_value": buy_value,
        "buy_fee": buy_fee,
        "total_cost": total_cost,
        "sell_value": sell_value,
        "sell_fee": sell_fee,
        "sell_tax": sell_tax,
        "net_proceeds": net_proceeds,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "total_friction": total_friction,
        "net_roi_percent": round(net_roi_percent, 2),
        "breakeven_gain_percent": round(breakeven_gain_percent, 3),
    }


def get_vietnam_regulatory_prompt() -> str:
    """Return explicit instruction block on Vietnamese securities regulation and tax requirements."""
    return (
        "VIETNAM MARKET REGULATORY & TAX DIRECTIVES:\n"
        "1. STRICT BAN ON SHORT SELLING: Under the Vietnamese Securities Law (Luật Chứng khoán 2019), "
        "short selling of underlying equities is strictly prohibited. You MUST NOT propose or open a Short position. "
        "The only valid actions for underlying equities are BUY (long entry), HOLD, or SELL (exiting an existing long position).\n"
        "2. STATUTORY TAX DRAG (THUẾ TNCN): A non-negotiable 0.1% Personal Income Tax is deducted from "
        "every SELL transaction regardless of gain or loss (no loss offset). Combined with ~0.30% round-trip brokerage "
        "fees, total trade friction is ~0.40% - 0.50% plus slippage. Trades with expected returns below 1.5% - 2.0% "
        "are economically unviable and must be rejected.\n"
        "3. EXCHANGE PRICE LIMITS: Price fluctuation is bounded daily: HOSE (±7%), HNX (±10%), UPCoM (±15%). "
        "Entry and stop prices must be realistic within these limits.\n"
        "4. SETTLEMENT HORIZON: Underlying shares operate on a T+2 settlement cycle. Day-trading (T+0 round-trip) "
        "on the same shares is not permissible."
    )


def get_vietnam_macro_data() -> str:
    """Return macroeconomic data snapshot for Vietnam."""
    return (
        "### Vietnam Macroeconomic Indicators (State Bank of Vietnam & GSO)\n"
        "- **Monetary Policy & Interest Rates (Ngân hàng Nhà nước - SBV)**:\n"
        "  - Refinancing Rate (Lãi suất tái cấp vốn): 4.50%\n"
        "  - Rediscount Rate (Lãi suất tái chiết khấu): 3.00%\n"
        "  - Maximum Short-Term Deposit Rate (<6 months): 4.75%\n"
        "  - Interbank Overnight Rate: 3.50% - 4.50%\n"
        "- **Economic Growth & Inflation**:\n"
        "  - GDP Growth Target: 6.5% - 7.0%\n"
        "  - Inflation Target (CPI): Controlled below 4.0% - 4.5%\n"
        "  - System-wide Credit Growth Target: ~15.0%\n"
        "- **Foreign Exchange & Valuation**:\n"
        "  - Central Exchange Rate (USD/VND): ~24,200 - 25,400\n"
        "  - Stock Market Valuation (VN-Index P/E): ~13.0x - 14.5x (attractive compared to regional peers)\n"
        "- **Market Characteristics**:\n"
        "  - Retail investor participation accounts for >85% of daily liquidity.\n"
        "  - Margin lending status across securities firms heavily influences short-term market swings."
    )


def get_vietnam_news(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 15,
) -> str:
    """Fetch localized Vietnamese financial news for a ticker via Google News RSS (Vietnamese edition).

    Complies with point-in-time boundaries using in_window() to avoid look-ahead bias.
    """
    raw_ticker = symbol.split(".")[0] if "." in symbol else symbol
    query = f"{raw_ticker} chứng khoán"
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=vi-VN&gl=VN&ceid=VN:vi"

    start_dt = (
        datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(start_date, str)
        else (start_date or datetime(2000, 1, 1))
    )
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d")
        if isinstance(end_date, str)
        else (end_date or datetime.now())
    )

    articles: list[dict] = []
    try:
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_bytes = response.read()

        root = ET.fromstring(xml_bytes)
        items = root.findall("./channel/item")

        for item in items:
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            desc_elem = item.find("description")

            title = title_elem.text if title_elem is not None and title_elem.text else "No title"
            link = link_elem.text if link_elem is not None and link_elem.text else ""
            pub_date_str = pub_date_elem.text if pub_date_elem is not None else ""

            pub_date = None
            if pub_date_str:
                with contextlib.suppress(Exception):
                    pub_date = parsedate_to_datetime(pub_date_str)

            # Apply date window filtering to eliminate look-ahead bias
            if in_window(pub_date, start_dt, end_dt):
                # Extract clean publisher from Google News title format: "Title - Publisher"
                publisher = "Vietnamese Media"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    publisher = parts[1]

                summary = ""
                if desc_elem is not None and desc_elem.text:
                    # Strip simple HTML tags from RSS description
                    summary = desc_elem.text.replace("<p>", "").replace("</p>", "").replace("&nbsp;", " ")

                articles.append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "pub_date": pub_date,
                    "summary": summary,
                })

                if len(articles) >= limit:
                    break

    except Exception as exc:  # noqa: BLE001 - fail open, degrade gracefully
        logger.debug("Could not fetch Vietnam news for %s: %s", symbol, exc)

    if not articles:
        return f"No localized news found for Vietnamese ticker {symbol} within the specified window."

    rendered: list[str] = []
    for i, a in enumerate(articles, 1):
        dt_str = a["pub_date"].strftime("%Y-%m-%d %H:%M:%S") if a["pub_date"] else "Unknown date"
        rendered.append(
            f"## News Article {i}\n"
            f"- **Title**: {a['title']}\n"
            f"- **Publisher**: {a['publisher']}\n"
            f"- **Published**: {dt_str}\n"
            f"- **Link**: {a['link']}\n"
            f"- **Summary**: {a['summary']}\n"
        )

    return "\n".join(rendered)
