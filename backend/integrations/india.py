NIFTY_50 = [
    ("RELIANCE.NS", "Reliance Industries", "Energy"),
    ("HDFCBANK.NS", "HDFC Bank", "Banking"),
    ("BHARTIARTL.NS", "Bharti Airtel", "Telecom"),
    ("TCS.NS", "Tata Consultancy Services", "IT"),
    ("ICICIBANK.NS", "ICICI Bank", "Banking"),
    ("SBIN.NS", "State Bank of India", "Banking"),
    ("INFY.NS", "Infosys", "IT"),
    ("HINDUNILVR.NS", "Hindustan Unilever", "FMCG"),
    ("ITC.NS", "ITC", "FMCG"),
    ("LT.NS", "Larsen & Toubro", "Infrastructure"),
    ("BAJFINANCE.NS", "Bajaj Finance", "Financial Services"),
    ("HCLTECH.NS", "HCL Technologies", "IT"),
    ("MARUTI.NS", "Maruti Suzuki", "Auto"),
    ("SUNPHARMA.NS", "Sun Pharmaceutical", "Pharma"),
    ("KOTAKBANK.NS", "Kotak Mahindra Bank", "Banking"),
    ("AXISBANK.NS", "Axis Bank", "Banking"),
    ("NTPC.NS", "NTPC", "Power"),
    ("ULTRACEMCO.NS", "UltraTech Cement", "Cement"),
    ("TITAN.NS", "Titan Company", "Consumer"),
    ("ASIANPAINT.NS", "Asian Paints", "Consumer"),
    ("POWERGRID.NS", "Power Grid", "Power"),
    ("NESTLEIND.NS", "Nestle India", "FMCG"),
    ("TATASTEEL.NS", "Tata Steel", "Metals"),
    ("M&M.NS", "Mahindra & Mahindra", "Auto"),
    ("WIPRO.NS", "Wipro", "IT"),
    ("ADANIENT.NS", "Adani Enterprises", "Conglomerate"),
    ("ADANIPORTS.NS", "Adani Ports", "Infrastructure"),
    ("ONGC.NS", "ONGC", "Energy"),
    ("COALINDIA.NS", "Coal India", "Energy"),
    ("BAJAJFINSV.NS", "Bajaj Finserv", "Financial Services"),
    ("JSWSTEEL.NS", "JSW Steel", "Metals"),
    ("GRASIM.NS", "Grasim Industries", "Cement"),
    ("TECHM.NS", "Tech Mahindra", "IT"),
    ("HINDALCO.NS", "Hindalco", "Metals"),
    ("CIPLA.NS", "Cipla", "Pharma"),
    ("DRREDDY.NS", "Dr Reddy's Laboratories", "Pharma"),
    ("TATAMOTORS.NS", "Tata Motors", "Auto"),
    ("EICHERMOT.NS", "Eicher Motors", "Auto"),
    ("APOLLOHOSP.NS", "Apollo Hospitals", "Healthcare"),
    ("HEROMOTOCO.NS", "Hero MotoCorp", "Auto"),
    ("BPCL.NS", "Bharat Petroleum", "Energy"),
    ("INDUSINDBK.NS", "IndusInd Bank", "Banking"),
    ("DIVISLAB.NS", "Divi's Laboratories", "Pharma"),
    ("BAJAJ-AUTO.NS", "Bajaj Auto", "Auto"),
    ("TATACONSUM.NS", "Tata Consumer Products", "FMCG"),
    ("BRITANNIA.NS", "Britannia Industries", "FMCG"),
    ("SHRIRAMFIN.NS", "Shriram Finance", "Financial Services"),
    ("TRENT.NS", "Trent", "Retail"),
    ("BEL.NS", "Bharat Electronics", "Defence"),
    ("HDFCLIFE.NS", "HDFC Life", "Insurance"),
]

INDICES = [
    {"symbol": "^NSEI", "label": "NIFTY 50", "yahoo": "^NSEI"},
    {"symbol": "^NSEBANK", "label": "BANK NIFTY", "yahoo": "^NSEBANK"},
    {"symbol": "^BSESN", "label": "SENSEX", "yahoo": "^BSESN"},
    {"symbol": "^INDIAVIX", "label": "INDIA VIX", "yahoo": "^INDIAVIX"},
    {"symbol": "^CNXIT", "label": "NIFTY IT", "yahoo": "^CNXIT"},
    {"symbol": "NIFTY_FIN_SERVICE.NS", "label": "NIFTY FIN SERVICE", "yahoo": "NIFTY_FIN_SERVICE.NS"},
]

SECTOR_ETFS = [
    ("NIFTYBEES.NS", "Nifty 50 ETF"),
    ("BANKBEES.NS", "Bank Nifty ETF"),
    ("ITBEES.NS", "Nifty IT ETF"),
    ("PHARMABEES.NS", "Pharma ETF"),
]


def normalize_india_symbol(raw: str) -> tuple[str, str]:
    symbol = raw.strip().upper()
    if symbol.endswith(".BO"):
        return symbol, "BSE"
    if symbol.endswith(".NS"):
        return symbol, "NSE"
    if symbol.startswith("^"):
        return symbol, "INDEX"
    nse = {ticker for ticker, _, _ in NIFTY_50}
    if f"{symbol}.NS" in nse:
        return f"{symbol}.NS", "NSE"
    return f"{symbol}.NS", "NSE"


def search_catalog(query: str, limit: int = 12) -> list[dict]:
    q = query.strip().upper()
    rows = []
    for symbol, name, sector in NIFTY_50:
        hay = f"{symbol} {name} {sector}".upper()
        if not q or q in hay:
            rows.append({"symbol": symbol, "name": name, "sector": sector, "exchange": "NSE"})
        if len(rows) >= limit:
            break
    return rows


def catalog_name(symbol: str) -> str:
    for ticker, name, _sector in NIFTY_50:
        if ticker == symbol.upper():
            return name
    return symbol.upper()
