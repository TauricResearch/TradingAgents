"""
Centillion Investment Partners - TradingAgents Configuration

Tailored for a long-only SMID cap fund focused on US and European stocks.
Two modes:
  1. Virtual portfolio tracking (paper trading to test alpha generation)
  2. Buy/sell recommendation engine for active portfolio + watchlist
"""

import os
from tradingagents.default_config import DEFAULT_CONFIG

# ---------------------------------------------------------------------------
# Base config — inherit defaults and override for Centillion's needs
# ---------------------------------------------------------------------------
CENTILLION_CONFIG = DEFAULT_CONFIG.copy()

# LLM provider — change to "anthropic" or "google" if you prefer
CENTILLION_CONFIG["llm_provider"] = "anthropic"
CENTILLION_CONFIG["deep_think_llm"] = "claude-sonnet-4-20250514"
CENTILLION_CONFIG["quick_think_llm"] = "claude-sonnet-4-20250514"

# More thorough analysis: 2 rounds of debate for better signal quality
CENTILLION_CONFIG["max_debate_rounds"] = 2
CENTILLION_CONFIG["max_risk_discuss_rounds"] = 2

# Data vendors — yfinance is free and covers US + European equities
CENTILLION_CONFIG["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

# ---------------------------------------------------------------------------
# Portfolio & Watchlist
# ---------------------------------------------------------------------------
# US SMID cap holdings/watchlist — add your actual tickers here
US_PORTFOLIO = [
    # Example SMID cap US names — replace with your actual holdings
    "CVLT",   # Commvault Systems
    "CSWI",   # CSW Industrials
    "EXPO",   # Exponent
    "LOPE",   # Grand Canyon Education
    "NOVT",   # Novanta
    "PCVX",   # Vaxcyte
    "STEP",   # StepStone Group
    "TNET",   # TriNet Group
    "ACIW",   # ACI Worldwide
    "CADE",   # Cadence Bank
]

US_WATCHLIST = [
    # Stocks you're considering but don't own yet
    "CORT",   # Corcept Therapeutics
    "ELF",    # e.l.f. Beauty
    "DUOL",   # Duolingo
    "GWRE",   # Guidewire Software
    "KNSL",   # Kingsdale Advisors
]

# European SMID cap — use Yahoo Finance tickers (exchange suffix)
# .L = London, .AS = Amsterdam, .DE = Frankfurt, .PA = Paris, .ST = Stockholm
EU_PORTFOLIO = [
    # Example European SMID names — replace with your actual holdings
    "DARK.L",   # Darktrace (London)
    "IMCD.AS",  # IMCD (Amsterdam)
    "RHM.DE",   # Rheinmetall (Frankfurt)
    "DSY.PA",   # Dassault Systèmes (Paris)
    "ALFA.ST",  # Alfa Laval (Stockholm)
]

EU_WATCHLIST = [
    "ASM.AS",   # ASM International
    "BESI.AS",  # BE Semiconductor
    "MONY.L",   # Moneysupermarket
]

# ---------------------------------------------------------------------------
# Combined universe
# ---------------------------------------------------------------------------
ALL_PORTFOLIO = US_PORTFOLIO + EU_PORTFOLIO
ALL_WATCHLIST = US_WATCHLIST + EU_WATCHLIST
ALL_TICKERS = ALL_PORTFOLIO + ALL_WATCHLIST

# ---------------------------------------------------------------------------
# Benchmarks for performance tracking
# ---------------------------------------------------------------------------
BENCHMARKS = {
    "us": "^RUT",       # Russell 2000
    "eu": "^STOXX",     # STOXX Europe 600
    "combined": "ACWI", # MSCI ACWI (broad global)
}
