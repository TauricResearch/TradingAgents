import logging
from typing import Dict

logger = logging.getLogger(__name__)

VALID_SECTORS = {
    "technology",
    "healthcare",
    "finance",
    "energy",
    "consumer_goods",
    "industrials",
    "other",
}

TICKER_TO_SECTOR: Dict[str, str] = {
    "AAPL": "technology",
    "MSFT": "technology",
    "GOOGL": "technology",
    "GOOG": "technology",
    "AMZN": "technology",
    "META": "technology",
    "NVDA": "technology",
    "TSLA": "technology",
    "AMD": "technology",
    "INTC": "technology",
    "QCOM": "technology",
    "AVGO": "technology",
    "TXN": "technology",
    "ADBE": "technology",
    "CRM": "technology",
    "CSCO": "technology",
    "NFLX": "technology",
    "ORCL": "technology",
    "IBM": "technology",
    "NOW": "technology",
    "INTU": "technology",
    "ADSK": "technology",
    "SNPS": "technology",
    "CDNS": "technology",
    "PLTR": "technology",
    "SNOW": "technology",
    "DDOG": "technology",
    "CRWD": "technology",
    "OKTA": "technology",
    "NET": "technology",
    "MDB": "technology",
    "TWLO": "technology",
    "WDAY": "technology",
    "SPLK": "technology",
    "VMW": "technology",
    "HPQ": "technology",
    "DELL": "technology",
    "FTNT": "technology",
    "PANW": "technology",
    "ZS": "technology",
    "S": "technology",
    "VEEV": "technology",
    "ZM": "technology",
    "DOCU": "technology",
    "ASAN": "technology",
    "MNDY": "technology",
    "TEAM": "technology",
    "ANSS": "technology",
    "ROP": "technology",
    "JPM": "finance",
    "BAC": "finance",
    "WFC": "finance",
    "GS": "finance",
    "MS": "finance",
    "C": "finance",
    "BLK": "finance",
    "SCHW": "finance",
    "AXP": "finance",
    "V": "finance",
    "MA": "finance",
    "PYPL": "finance",
    "SQ": "finance",
    "COIN": "finance",
    "HOOD": "finance",
    "SOFI": "finance",
    "AFRM": "finance",
    "MQ": "finance",
    "BRK-B": "finance",
    "BRK-A": "finance",
    "JNJ": "healthcare",
    "UNH": "healthcare",
    "PFE": "healthcare",
    "ABBV": "healthcare",
    "MRK": "healthcare",
    "LLY": "healthcare",
    "MRNA": "healthcare",
    "BNTX": "healthcare",
    "CVS": "healthcare",
    "WBA": "healthcare",
    "MCK": "healthcare",
    "CAH": "healthcare",
    "HUM": "healthcare",
    "CI": "healthcare",
    "ELV": "healthcare",
    "XOM": "energy",
    "CVX": "energy",
    "COP": "energy",
    "SLB": "energy",
    "HAL": "energy",
    "BKR": "energy",
    "MPC": "energy",
    "VLO": "energy",
    "PSX": "energy",
    "OXY": "energy",
    "PXD": "energy",
    "DVN": "energy",
    "CEG": "energy",
    "NEE": "energy",
    "DUK": "energy",
    "SO": "energy",
    "D": "energy",
    "SRE": "energy",
    "WMT": "consumer_goods",
    "COST": "consumer_goods",
    "TGT": "consumer_goods",
    "HD": "consumer_goods",
    "LOW": "consumer_goods",
    "PG": "consumer_goods",
    "KO": "consumer_goods",
    "PEP": "consumer_goods",
    "NKE": "consumer_goods",
    "SBUX": "consumer_goods",
    "MCD": "consumer_goods",
    "CMG": "consumer_goods",
    "YUM": "consumer_goods",
    "DPZ": "consumer_goods",
    "DIS": "consumer_goods",
    "CMCSA": "consumer_goods",
    "VZ": "consumer_goods",
    "T": "consumer_goods",
    "TMUS": "consumer_goods",
    "EL": "consumer_goods",
    "CL": "consumer_goods",
    "KMB": "consumer_goods",
    "CLX": "consumer_goods",
    "KHC": "consumer_goods",
    "GIS": "consumer_goods",
    "K": "consumer_goods",
    "MDLZ": "consumer_goods",
    "HSY": "consumer_goods",
    "TSN": "consumer_goods",
    "BYND": "consumer_goods",
    "CAG": "consumer_goods",
    "STZ": "consumer_goods",
    "BUD": "consumer_goods",
    "DEO": "consumer_goods",
    "PM": "consumer_goods",
    "MO": "consumer_goods",
    "LULU": "consumer_goods",
    "DG": "consumer_goods",
    "DLTR": "consumer_goods",
    "ROST": "consumer_goods",
    "TJX": "consumer_goods",
    "AZO": "consumer_goods",
    "ORLY": "consumer_goods",
    "KMX": "consumer_goods",
    "ADDYY": "consumer_goods",
    "UBER": "consumer_goods",
    "LYFT": "consumer_goods",
    "ABNB": "consumer_goods",
    "DASH": "consumer_goods",
    "SNAP": "consumer_goods",
    "PINS": "consumer_goods",
    "TWTR": "consumer_goods",
    "SHOP": "consumer_goods",
    "TOST": "consumer_goods",
    "BA": "industrials",
    "LMT": "industrials",
    "RTX": "industrials",
    "GD": "industrials",
    "NOC": "industrials",
    "GE": "industrials",
    "HON": "industrials",
    "MMM": "industrials",
    "CAT": "industrials",
    "DE": "industrials",
    "UNP": "industrials",
    "UPS": "industrials",
    "FDX": "industrials",
    "DAL": "industrials",
    "UAL": "industrials",
    "AAL": "industrials",
    "LUV": "industrials",
    "F": "industrials",
    "GM": "industrials",
    "TM": "industrials",
    "HMC": "industrials",
    "VWAGY": "industrials",
    "RACE": "industrials",
    "RIVN": "industrials",
    "LCID": "industrials",
    "NIO": "industrials",
    "LNVGY": "industrials",
}

_sector_cache: Dict[str, str] = {}


def _llm_classify_sector(ticker: str) -> str:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    from tradingagents.dataflows.config import get_config

    config = get_config()
    llm_name = config.get("quick_think_llm", "gpt-4o-mini")
    llm_provider = config.get("llm_provider", "openai")
    backend_url = config.get("backend_url", "https://api.openai.com/v1")

    llm = ChatOpenAI(
        model=llm_name,
        base_url=backend_url,
        temperature=0,
    )

    system_prompt = (
        "You are a financial sector classifier. Given a stock ticker symbol, "
        "classify it into exactly one of the following sectors: "
        "technology, healthcare, finance, energy, consumer_goods, industrials, other. "
        "Respond with only the sector name in lowercase, nothing else."
    )

    user_prompt = f"Classify the stock ticker: {ticker}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    sector = response.content.strip().lower()

    if sector not in VALID_SECTORS:
        logger.warning(
            "LLM returned invalid sector '%s' for ticker %s, defaulting to 'other'",
            sector,
            ticker,
        )
        return "other"

    return sector


def classify_sector(ticker: str) -> str:
    ticker_upper = ticker.upper()

    if ticker_upper in TICKER_TO_SECTOR:
        return TICKER_TO_SECTOR[ticker_upper]

    if ticker_upper in _sector_cache:
        return _sector_cache[ticker_upper]

    logger.info("Using LLM fallback for sector classification of ticker: %s", ticker)

    try:
        sector = _llm_classify_sector(ticker_upper)
        _sector_cache[ticker_upper] = sector
        logger.info("Classified %s as %s via LLM", ticker, sector)
        return sector
    except (KeyError, ValueError, RuntimeError, ConnectionError, TimeoutError) as e:
        logger.error("LLM sector classification failed for %s: %s", ticker, str(e))
        _sector_cache[ticker_upper] = "other"
        return "other"
