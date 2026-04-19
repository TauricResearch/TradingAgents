"""Curated alias registry for scanner graph facts.

This is a living file. When a new surface form appears in scanner output
that doesn't resolve to a canonical node id, add it here in the same PR.
Build warnings for heuristic-only classifications are the update backlog.
"""
from __future__ import annotations

TICKER_ALIASES: dict[str, list[str]] = {
    "NVDA": ["Nvidia", "NVIDIA Corporation"],
    "ON": ["ON Semiconductor", "Onsemi"],
    "MSFT": ["Microsoft", "Microsoft Corporation"],
    "AAPL": ["Apple", "Apple Inc"],
    "AMZN": ["Amazon", "Amazon.com"],
    "GOOGL": ["Alphabet", "Google"],
    "META": ["Meta Platforms", "Facebook"],
    "TSLA": ["Tesla", "Tesla Inc"],
    "JPM": ["JPMorgan", "JPMorgan Chase"],
    "BAC": ["Bank of America"],
    "XOM": ["ExxonMobil", "Exxon Mobil"],
    "OXY": ["Occidental Petroleum"],
    "CVX": ["Chevron"],
    "RIG": ["Transocean"],
    "MRVL": ["Marvell", "Marvell Technology"],
    "AMD": ["Advanced Micro Devices"],
    "INTC": ["Intel", "Intel Corporation"],
    "QCOM": ["Qualcomm"],
    "AVGO": ["Broadcom"],
    "TSM": ["TSMC", "Taiwan Semiconductor"],
}

SECTOR_ALIASES: dict[str, list[str]] = {
    "Technology": ["Information Technology", "Tech", "IT Sector"],
    "Financials": ["Financial", "Financial Services", "Finance"],
    "Energy": ["Energy Sector", "Oil & Gas"],
    "Health Care": ["Healthcare", "Health Care Sector", "Pharma", "Biotech"],
    "Consumer Discretionary": ["Consumer Cyclical", "Retail"],
    "Consumer Staples": ["Consumer Defensive", "Staples"],
    "Industrials": ["Industrial", "Industrials Sector"],
    "Materials": ["Basic Materials", "Materials Sector"],
    "Real Estate": ["REITs", "Real Estate Sector"],
    "Utilities": ["Utilities Sector"],
    "Communication Services": ["Communications", "Telecom", "Media"],
}

INDEX_ALIASES: dict[str, list[str]] = {
    "S&P 500": ["SPX", "S&P", "SP500", "S&P500"],
    "NASDAQ": ["Nasdaq", "Nasdaq Composite", "NDX", "QQQ"],
    "Dow Jones": ["DJIA", "Dow", "Dow Jones Industrial Average"],
    "Russell 2000": ["RUT", "Russell", "Small Cap Index"],
}

MACRO_ALIASES: dict[str, list[str]] = {
    "VIX": ["CBOE Volatility Index", "Fear Index", "Volatility Index"],
    "CPI": ["Consumer Price Index", "Inflation"],
    "PCE": ["Personal Consumption Expenditures"],
    "Fed Funds Rate": ["Federal Funds Rate", "Fed Rate", "FOMC Rate"],
    "10Y Yield": ["10-Year Treasury", "US 10Y", "Treasury Yield"],
    "German CDS": ["German Credit Default Swap", "Germany CDS"],
    "DXY": ["US Dollar Index", "Dollar Index"],
}

COMMODITY_ALIASES: dict[str, list[str]] = {
    "Brent Crude": ["Brent", "Brent Oil", "ICE Brent"],
    "WTI Crude": ["WTI", "WTI Oil", "NYMEX Crude"],
    "Gold": ["XAUUSD", "Spot Gold"],
    "Silver": ["XAGUSD", "Spot Silver"],
    "Natural Gas": ["NG", "Nat Gas"],
    "Copper": ["COMEX Copper"],
}

FX_ALIASES: dict[str, list[str]] = {
    "EUR/USD": ["EURUSD", "Euro Dollar"],
    "JPY/USD": ["JPYUSD", "USD/JPY", "USDJPY", "Yen"],
    "CNY/USD": ["CNYUSD", "USD/CNY", "USDCNY", "Yuan", "Renminbi"],
    "GBP/USD": ["GBPUSD", "Cable", "British Pound"],
    "DXY": ["US Dollar Index"],
}


_REGISTRY_BY_NODE_TYPE: dict[str, dict[str, list[str]]] = {
    "Ticker": TICKER_ALIASES,
    "Sector": SECTOR_ALIASES,
    "MarketIndex": INDEX_ALIASES,
    "MacroIndicator": MACRO_ALIASES,
    "Commodity": COMMODITY_ALIASES,
    "CurrencyPair": FX_ALIASES,
}


def resolve_alias(
    label: str,
    registry: dict[str, list[str]],
) -> str | None:
    """Return the canonical key for *label*, or None if not found.

    Checks both the canonical keys and their alias lists.
    """
    label_norm = label.strip()
    if label_norm in registry:
        return label_norm
    for canonical, aliases in registry.items():
        if label_norm in aliases:
            return canonical
    return None


def aliases_for_node(node_id: str, node_type: str) -> list[str]:
    """Return curated aliases for a canonical node id/type."""
    registry = _REGISTRY_BY_NODE_TYPE.get(node_type)
    if not registry:
        return []
    return list(registry.get(node_id, []))


def resolve_alias_for_type(label: str, node_type: str) -> str | None:
    """Resolve *label* through the curated registry for one node type."""
    registry = _REGISTRY_BY_NODE_TYPE.get(node_type)
    if not registry:
        return None
    return resolve_alias(label, registry)
