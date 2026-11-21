"""Company dossier: one listed company's statements, ratios, ownership, management,
dividends and filings, gathered from the sources that serve each piece reliably,
cached on disk, and summarized for the analysts.

Sources by market (each optional; a source that is missing its key or package is
skipped silently, one that fails is named in ``sources``):

US (NYSE / NASDAQ)
    Yahoo Finance (yfinance): statements (four years, five quarters), the profile,
    officers, valuation and return ratios, institutional and fund holders, insider
    transactions and roster, dividends, earnings dates, analyst targets.
    SEC EDGAR: key figures as filed, ten years and more, and the filing list
    (10-K, 10-Q, 8-K, Form 4). Its figures carry filing dates, so a run dated in
    the past is served what had been filed by then.
    Alpha Vantage OVERVIEW, only with ALPHA_VANTAGE_API_KEY: fills ratios Yahoo lacks.

Borsa Istanbul (``.IS``)
    Is Yatirim (through borsapy): statements in TRY as filed to KAP, annual and
    interim, market cap, F/K, PD/DD, FD/FAVOK, net debt, free float, foreign share,
    dividends, analyst targets. KAP: sector, market, indices, auditor, board,
    management, shareholders of 5% or more, free float, subsidiaries, every
    disclosure (insider trades among them) and the expected-disclosure calendar.
    Yahoo: employee count, officers and the business summary only; its ratios and
    statements for BIST are not used (often USD statements against a TRY quote).

Other markets: Yahoo alone.

Every piece is cached under ``<data_cache_dir>/fundamentals/<SYMBOL>/`` with its
own lifetime (disclosures an hour, statements a day); a refresh that fails keeps
serving the last good copy, marked stale.
"""

from __future__ import annotations

import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.dataflows.vendors import bist

logger = logging.getLogger(__name__)

HOUR = 3600
DAY = 24 * HOUR

# ---------------------------------------------------------------- disk cache


def cache_root() -> Path:
    return Path(get_config()["data_cache_dir"]) / "fundamentals"


def _cache_path(symbol: str, part: str) -> Path:
    return cache_root() / safe_ticker_component(symbol.upper()) / f"{part}.json"


class _Result:
    __slots__ = ("data", "fetched", "stale", "error", "skipped")

    def __init__(self, data=None, fetched=None, stale=False, error=None, skipped=None):
        self.data, self.fetched, self.stale, self.error, self.skipped = data, fetched, stale, error, skipped


def _part(symbol: str, part: str, ttl: float, fn: Callable[[], Any], refresh: bool = False) -> _Result:
    """``fn()`` through the disk cache: fresh copy if young enough, else fetch, else the old copy."""
    path = _cache_path(symbol, part)
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if cached and not refresh and time.time() - cached.get("ts", 0) < ttl:
        return _Result(cached.get("data"), cached.get("ts"))
    try:
        data = fn()
    except VendorNotConfiguredError as exc:
        return _Result(skipped=str(exc))
    except NoMarketDataError as exc:
        return _Result(skipped=f"veri yok: {exc.detail or exc}")
    except Exception as exc:  # any vendor failure: serve the last good copy if there is one
        logger.warning("fundamentals %s/%s failed: %s", symbol, part, exc)
        msg = f"{type(exc).__name__}: {str(exc)[:200]}"
        if cached:
            return _Result(cached.get("data"), cached.get("ts"), stale=True, error=msg)
        return _Result(error=msg)
    now = time.time()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"ts": now, "data": data}, ensure_ascii=False, default=str)
        replace_file(path, lambda temp: Path(temp).write_text(payload, encoding="utf-8"))
    except OSError as exc:
        logger.warning("fundamentals cache write failed for %s/%s: %s", symbol, part, exc)
    return _Result(data, now)


# ---------------------------------------------------------------- helpers


def _f(v) -> float | None:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _iso(v) -> str | None:
    if v is None:
        return None
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d")
        except ValueError:
            return None
    s = str(v)
    return s[:10] if s and s != "NaT" else None


def _records(df, limit: int = 50) -> list[dict]:
    """A DataFrame as plain records: timestamps as dates, NaN as None."""
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for _, row in df.head(limit).iterrows():
        rec = {}
        for k, v in row.items():
            if hasattr(v, "strftime"):
                rec[str(k)] = _iso(v)
            elif isinstance(v, float):
                rec[str(k)] = v if math.isfinite(v) else None
            elif v is None or (hasattr(v, "__class__") and v.__class__.__name__ in ("NAType", "NaTType")):
                rec[str(k)] = None
            else:
                try:
                    rec[str(k)] = v.item() if hasattr(v, "item") else v
                except (ValueError, AttributeError):
                    rec[str(k)] = str(v)
        out.append(rec)
    return out


def market_of(symbol: str) -> str:
    """'BIST', 'US', 'OTHER'; raises ValueError for instruments that are not company shares."""
    s = (symbol or "").strip().upper()
    if not s:
        raise ValueError("Sembol boş.")
    if bist.is_bist(s):
        return "BIST"
    if any(c in s for c in "=^/") or s.endswith(("-USD", "-USDT", "-EUR", "-TRY")):
        raise ValueError(f"{s} bir şirket hissesi değil; temel veriler yalnız hisse senetleri için var.")
    if "." in s:
        return "OTHER"
    try:
        from tradingagents.dataflows.vendors.sec_edgar import cik_for

        if cik_for(s):
            return "US"
    except Exception:  # SEC unreachable: decide by Yahoo below
        pass
    if _kap_member(s):
        return "BIST"
    return "US" if len(s) <= 5 else "OTHER"


def _kap_member(code: str) -> bool:
    """Whether a bare code ("THYAO") is a Borsa Istanbul company on KAP."""
    if not code.isalpha() or not 3 <= len(code) <= 6:
        return False
    try:
        bist._borsapy()
        from borsapy._providers.kap import get_kap_provider

        return bool(get_kap_provider().get_member_oid(code))
    except Exception:
        return False


def canonical(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.endswith(".E"):
        s = s[:-2] + ".IS"
    return s


def resolve(symbol: str) -> tuple[str, str]:
    """(symbol as served, market): a bare BIST code gains its ``.IS`` suffix."""
    s = canonical(symbol)
    market = market_of(s)
    if market == "BIST" and not bist.is_bist(s):
        s += ".IS"
    return s, market


# ---------------------------------------------------------------- Yahoo

# Yahoo's statement lines in Turkish, for the screen; the original stays in label_en.
_YAHOO_TR = {
    "Total Revenue": "Toplam gelir", "Operating Revenue": "Faaliyet gelirleri", "Cost Of Revenue": "Satışların maliyeti",
    "Gross Profit": "Brüt kâr", "Operating Expense": "Faaliyet giderleri", "Research And Development": "Ar-Ge giderleri",
    "Selling General And Administration": "Satış, genel ve yönetim giderleri", "Operating Income": "Faaliyet kârı",
    "EBITDA": "FAVÖK", "EBIT": "FVÖK", "Normalized EBITDA": "Normalleştirilmiş FAVÖK", "Interest Expense": "Faiz gideri",
    "Interest Income": "Faiz geliri", "Net Interest Income": "Net faiz geliri", "Pretax Income": "Vergi öncesi kâr",
    "Tax Provision": "Vergi karşılığı", "Net Income": "Net kâr", "Net Income Common Stockholders": "Hissedarlara ait net kâr",
    "Diluted EPS": "Seyreltilmiş HBK", "Basic EPS": "HBK", "Diluted Average Shares": "Seyreltilmiş ort. hisse sayısı",
    "Basic Average Shares": "Ort. hisse sayısı", "Total Expenses": "Toplam giderler", "Reconciled Depreciation": "Amortisman",
    "Total Assets": "Toplam varlıklar", "Current Assets": "Dönen varlıklar", "Cash And Cash Equivalents": "Nakit ve benzerleri",
    "Cash Cash Equivalents And Short Term Investments": "Nakit ve kısa vadeli yatırımlar", "Other Short Term Investments": "Diğer kısa vadeli yatırımlar",
    "Receivables": "Alacaklar", "Accounts Receivable": "Ticari alacaklar", "Inventory": "Stoklar", "Other Current Assets": "Diğer dönen varlıklar",
    "Total Non Current Assets": "Duran varlıklar", "Net PPE": "Maddi duran varlıklar (net)", "Goodwill And Other Intangible Assets": "Şerefiye ve maddi olmayan varlıklar",
    "Goodwill": "Şerefiye", "Current Liabilities": "Kısa vadeli yükümlülükler", "Accounts Payable": "Ticari borçlar", "Payables": "Borçlar",
    "Current Debt": "Kısa vadeli borçlanma", "Current Debt And Capital Lease Obligation": "Kısa vadeli borç ve kiralama",
    "Long Term Debt": "Uzun vadeli borçlanma", "Long Term Debt And Capital Lease Obligation": "Uzun vadeli borç ve kiralama",
    "Total Liabilities Net Minority Interest": "Toplam yükümlülükler", "Total Non Current Liabilities Net Minority Interest": "Uzun vadeli yükümlülükler",
    "Stockholders Equity": "Özkaynaklar (ana ortaklık)", "Common Stock Equity": "Adi hisse özkaynağı",
    "Total Equity Gross Minority Interest": "Toplam özkaynaklar", "Retained Earnings": "Geçmiş yıl kârları", "Total Debt": "Toplam borç",
    "Net Debt": "Net borç", "Working Capital": "İşletme sermayesi", "Tangible Book Value": "Maddi defter değeri",
    "Ordinary Shares Number": "Hisse sayısı", "Share Issued": "İhraç edilmiş hisse", "Treasury Shares Number": "Geri alınmış hisse",
    "Invested Capital": "Yatırılan sermaye", "Minority Interest": "Azınlık payları",
    "Operating Cash Flow": "İşletme faaliyetlerinden nakit", "Investing Cash Flow": "Yatırım faaliyetlerinden nakit",
    "Financing Cash Flow": "Finansman faaliyetlerinden nakit", "Free Cash Flow": "Serbest nakit akışı", "Capital Expenditure": "Yatırım harcamaları (CAPEX)",
    "Cash Dividends Paid": "Ödenen temettü", "Repurchase Of Capital Stock": "Hisse geri alımı", "Issuance Of Debt": "Borç ihracı",
    "Repayment Of Debt": "Borç geri ödemesi", "Depreciation And Amortization": "Amortisman ve itfa", "Stock Based Compensation": "Hisse bazlı ödemeler",
    "Change In Working Capital": "İşletme sermayesindeki değişim", "End Cash Position": "Dönem sonu nakit", "Beginning Cash Position": "Dönem başı nakit",
    "Changes In Cash": "Nakitteki değişim", "Net Income From Continuing Operations": "Sürdürülen faaliyetler net kârı",
}

_YAHOO_KEY_ROWS = {
    "Total Revenue", "Gross Profit", "Operating Income", "EBITDA", "Net Income Common Stockholders", "Net Income", "Diluted EPS",
    "Total Assets", "Current Assets", "Current Liabilities", "Stockholders Equity", "Total Debt", "Net Debt", "Cash And Cash Equivalents",
    "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow", "Cash Dividends Paid", "Investing Cash Flow", "Financing Cash Flow",
    "Total Liabilities Net Minority Interest",
}


def _yf():
    import yfinance as yf

    return yf


def _retry(fn):
    from tradingagents.dataflows.vendors.yahoo.common import yf_retry

    return yf_retry(fn)


def _yahoo_table(df) -> dict | None:
    if df is None or getattr(df, "empty", True):
        return None
    df = df.dropna(axis=1, how="all")
    if df.empty:
        return None
    cols = sorted(df.columns, reverse=True)
    df = df[cols]
    rows = []
    for label in reversed(list(df.index)):   # Yahoo lists details first and totals last
        values = [_f(v) for v in df.loc[label].tolist()] if not hasattr(df.loc[label], "columns") else [_f(v) for v in df.loc[label].iloc[0].tolist()]
        if all(v is None for v in values):
            continue
        name = str(label)
        rows.append({"label": _YAHOO_TR.get(name, name), "label_en": name, "level": 0 if name in _YAHOO_KEY_ROWS else 1,
                     "key": name in _YAHOO_KEY_ROWS, "values": values})
    return {"columns": [_iso(c) for c in cols], "period_ends": [_iso(c) for c in cols], "rows": rows}


_INFO_KEYS = (
    "longName", "shortName", "sector", "industry", "country", "city", "website", "fullTimeEmployees", "longBusinessSummary",
    "exchange", "fullExchangeName", "currency", "financialCurrency", "quoteType", "marketCap", "enterpriseValue",
    "sharesOutstanding", "floatShares", "impliedSharesOutstanding", "heldPercentInsiders", "heldPercentInstitutions",
    "currentPrice", "regularMarketPrice", "previousClose", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "beta",
    "trailingPE", "forwardPE", "priceToBook", "enterpriseToEbitda", "enterpriseToRevenue", "priceToSalesTrailing12Months",
    "trailingPegRatio", "pegRatio", "dividendYield", "dividendRate", "payoutRatio", "exDividendDate", "fiveYearAvgDividendYield",
    "grossMargins", "ebitdaMargins", "operatingMargins", "profitMargins", "returnOnEquity", "returnOnAssets",
    "debtToEquity", "currentRatio", "quickRatio", "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
    "trailingEps", "forwardEps", "bookValue", "totalRevenue", "ebitda", "netIncomeToCommon", "freeCashflow",
    "operatingCashflow", "totalCash", "totalDebt", "targetMeanPrice", "targetHighPrice", "targetLowPrice", "targetMedianPrice",
    "numberOfAnalystOpinions", "recommendationKey", "recommendationMean", "auditRisk", "boardRisk", "compensationRisk",
    "shareHolderRightsRisk", "overallRisk", "governanceEpochDate",
)


def _yahoo_info(symbol: str) -> dict:
    info = _retry(lambda: _yf().Ticker(symbol).info) or {}
    if not info or not any(info.get(k) for k in ("longName", "shortName", "marketCap", "sector")):
        raise NoMarketDataError(symbol, symbol, "Yahoo has no profile")
    out = {k: info.get(k) for k in _INFO_KEYS if info.get(k) is not None}
    out["officers"] = [{"name": o.get("name"), "title": o.get("title"), "age": o.get("age"),
                        "year_born": o.get("yearBorn"), "pay": o.get("totalPay"), "fiscal_year": o.get("fiscalYear")}
                       for o in (info.get("companyOfficers") or [])[:15]]
    return out


def _yahoo_statements(symbol: str) -> dict:
    def get():
        t = _yf().Ticker(symbol)
        return {
            "annual": {"income": _yahoo_table(t.income_stmt), "balance": _yahoo_table(t.balance_sheet),
                       "cashflow": _yahoo_table(t.cashflow)},
            "quarterly": {"income": _yahoo_table(t.quarterly_income_stmt), "balance": _yahoo_table(t.quarterly_balance_sheet),
                          "cashflow": _yahoo_table(t.quarterly_cashflow)},
        }
    out = _retry(get)
    if not out or not any(out["annual"].values()):
        raise NoMarketDataError(symbol, symbol, "Yahoo has no statements")
    return out


def _yahoo_holders(symbol: str) -> dict:
    def get():
        t = _yf().Ticker(symbol)
        major = {}
        mh = t.major_holders
        if mh is not None and not mh.empty:
            for k, row in mh.iterrows():
                major[str(k)] = _f(row.iloc[0])
        return {
            "major": major,
            "institutional": _records(t.institutional_holders, 15),
            "funds": _records(t.mutualfund_holders, 15),
            "insider_transactions": _records(t.insider_transactions, 40),
            "insider_roster": _records(t.insider_roster_holders, 20),
            "insider_purchases": _records(t.insider_purchases, 10),
        }
    return _retry(get) or {}


def _yahoo_dividends(symbol: str) -> list[dict]:
    def get():
        s = _yf().Ticker(symbol).dividends
        if s is None or s.empty:
            return []
        return [{"date": _iso(k), "amount": _f(v)} for k, v in s.items()][::-1][:60]
    return _retry(get) or []


def _yahoo_earnings(symbol: str) -> list[dict]:
    def get():
        df = _yf().Ticker(symbol).get_earnings_dates(limit=12)
        if df is None or df.empty:
            return []
        out = []
        for idx, row in df.iterrows():
            out.append({"date": _iso(idx), "eps_estimate": _f(row.get("EPS Estimate")),
                        "eps_reported": _f(row.get("Reported EPS")), "surprise_pct": _f(row.get("Surprise(%)"))})
        return out
    try:
        return _retry(get) or []
    except Exception:
        return []


# ---------------------------------------------------------------- SEC EDGAR

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_FORMS = ("10-K", "10-Q", "8-K", "20-F", "6-K", "40-F", "4", "DEF 14A", "S-1", "SC 13D", "SC 13G", "13F-HR", "10-K/A", "10-Q/A")


def _sec_filings(symbol: str) -> dict:
    from tradingagents.dataflows.vendors import sec_edgar

    cik = sec_edgar.cik_for(symbol)
    if not cik:
        raise NoMarketDataError(symbol, symbol, "not a US SEC filer")
    data = sec_edgar._fetch_json(_SUBMISSIONS_URL.format(cik=cik))
    recent = (data.get("filings") or {}).get("recent") or {}
    forms, dates = recent.get("form") or [], recent.get("filingDate") or []
    acc, docs, desc = recent.get("accessionNumber") or [], recent.get("primaryDocument") or [], recent.get("primaryDocDescription") or []
    out = []
    for i, form in enumerate(forms):
        if form not in _SEC_FORMS:
            continue
        a = (acc[i] if i < len(acc) else "").replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{docs[i]}" if a and i < len(docs) else None
        out.append({"date": dates[i] if i < len(dates) else None, "form": form,
                    "title": (desc[i] if i < len(desc) else "") or form, "url": url})
        if len(out) >= 150:
            break
    return {"cik": cik, "name": data.get("name"), "sic": data.get("sicDescription"), "fiscal_year_end": data.get("fiscalYearEnd"),
            "state": data.get("stateOfIncorporation"), "filings": out}


_SEC_LABELS_TR = {
    "Total Assets": "Toplam varlıklar", "Current Assets": "Dönen varlıklar", "Cash and Equivalents": "Nakit ve benzerleri",
    "Total Liabilities": "Toplam yükümlülükler", "Current Liabilities": "Kısa vadeli yükümlülükler", "Stockholders Equity": "Özkaynaklar",
    "Revenue": "Gelir", "Cost of Revenue": "Satışların maliyeti", "Gross Profit": "Brüt kâr", "Operating Income": "Faaliyet kârı",
    "Net Income": "Net kâr", "Diluted EPS": "Seyreltilmiş HBK", "Operating Cash Flow": "İşletme faaliyetlerinden nakit",
    "Investing Cash Flow": "Yatırım faaliyetlerinden nakit", "Financing Cash Flow": "Finansman faaliyetlerinden nakit",
    "Capital Expenditure": "Yatırım harcamaları (CAPEX)",
}


def sec_key_table(symbol: str, freq: str = "annual", as_of_date: str | None = None, periods: int = 12) -> dict | None:
    """SEC EDGAR key lines as filed by ``as_of_date``: one row per line, newest period first."""
    from tradingagents.dataflows.vendors import sec_edgar

    cik = sec_edgar.cik_for(symbol)
    if not cik:
        return None
    facts = sec_edgar._cached_json(sec_edgar._FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    if not gaap:
        return None
    as_of = as_of_date or date.today().isoformat()
    quarterly = freq == "quarterly"
    spans = (sec_edgar._SPANS["quarterly"],) if quarterly else (sec_edgar._SPANS["annual"],)
    forms = () if quarterly else sec_edgar._ANNUAL_FORMS
    lines = []
    for kind in ("income_statement", "balance_sheet", "cashflow"):
        for label, tags in sec_edgar._STATEMENTS[kind]:
            values, unit = sec_edgar._as_of(gaap, tags, as_of, spans, forms)
            lines.append((label, {end: v for (end, idx), v in values.items() if idx == 0}, unit))
    ends = sorted({e for _, vals, _ in lines for e in vals}, reverse=True)[:periods]
    if not ends:
        return None
    rows = [{"label": _SEC_LABELS_TR.get(label, label), "label_en": label, "level": 0, "key": True,
             "unit": unit, "values": [vals.get(e) for e in ends]} for label, vals, unit in lines if any(e in vals for e in ends)]
    return {"columns": ends, "period_ends": ends, "rows": rows, "as_of": as_of}


# ---------------------------------------------------------------- Alpha Vantage


def _alpha_overview(symbol: str) -> dict:
    from tradingagents.dataflows.vendors.alpha_vantage.common import _make_api_request, get_api_key

    get_api_key()   # raises VendorNotConfiguredError without a key: skipped silently
    text = _make_api_request("OVERVIEW", {"symbol": symbol})
    try:
        data = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        return {}
    if not isinstance(data, dict) or not data.get("Symbol"):
        raise NoMarketDataError(symbol, symbol, "Alpha Vantage has no overview")
    return {k: v for k, v in data.items() if v not in (None, "", "None", "-")}


# ---------------------------------------------------------------- BIST parts


def _bist_holders(symbol: str) -> list[dict]:
    bp = bist._borsapy()
    df = bp.Ticker(bist.bist_code(symbol)).major_holders
    if df is None or df.empty:
        return []
    return [{"holder": str(k), "pct": _f(r.iloc[0])} for k, r in df.iterrows()]


def _bist_market(symbol: str) -> dict:
    out = bist.market_metrics(symbol)
    out.update(bist.quote(symbol))
    return out


# ---------------------------------------------------------------- key figures and ratios

# Is Yatirim item codes (industrial layout) for the lines ratios are built on.
_ISY = {
    "revenue": ("3C",), "gross": ("3D",), "ebit": ("3DF",), "net": ("3Z", "3L"), "pretax": ("3I",),
    "assets": ("1BL",), "cur_assets": ("1A",), "cur_liab": ("2A",), "equity": ("2O", "2N"), "equity_total": ("2N",),
    "cash": ("1AA",), "st_invest": ("1AB",), "inventory": ("1AF",), "st_debt": ("2AA",), "lt_debt": ("2BA",),
    "da": ("4B", "4CAB"), "ocf": ("4C",), "capex": ("4CAI",), "fcf": ("4CB",), "dividends_paid": ("4CBB",),
    "eps": ("3ZD",),
}
# Bank layout: lines found by label, as codes differ between the two layouts.
_ISY_BANK_LABELS = {
    "assets": ("AKTİF TOPLAMI",), "equity": ("XVI. ÖZKAYNAKLAR",), "loans": ("VI. KREDİLER", "6.1 Krediler"),
    "deposits": ("I. MEVDUAT",), "net": ("XXIII. NET DÖNEM KARI/ZARARI (XVII+XXII)",),
    "revenue": ("VIII. FAALİYET GELİRLERİ/GİDERLERİ TOPLAMI (III+IV+V+VI+VII)",), "nii": ("III. NET FAİZ GELİRİ/GİDERİ (I - II)",),
    "ebit": ("XI. NET FAALİYET KARI/ZARARI (VIII-IX-X)",), "pretax": ("XV. SÜRDÜRÜLEN FAALİYETLER VERGİ ÖNCESİ K/Z (XI+XII+XIII+XIV)",),
}

_YAHOO_FIG = {
    "revenue": ("Total Revenue", "Operating Revenue"), "gross": ("Gross Profit",), "ebit": ("Operating Income", "EBIT"),
    "ebitda": ("EBITDA", "Normalized EBITDA"), "net": ("Net Income Common Stockholders", "Net Income"), "pretax": ("Pretax Income",),
    "assets": ("Total Assets",), "cur_assets": ("Current Assets",), "cur_liab": ("Current Liabilities",),
    "equity": ("Stockholders Equity", "Common Stock Equity"), "cash": ("Cash And Cash Equivalents",),
    "st_invest": ("Other Short Term Investments",), "inventory": ("Inventory",), "debt": ("Total Debt",),
    "ocf": ("Operating Cash Flow",), "capex": ("Capital Expenditure",), "fcf": ("Free Cash Flow",),
    "dividends_paid": ("Cash Dividends Paid",), "eps": ("Diluted EPS", "Basic EPS"), "shares": ("Ordinary Shares Number", "Share Issued"),
    "da": ("Depreciation And Amortization", "Reconciled Depreciation"),
}


def _row_values(table: dict | None, *, codes=(), labels=(), labels_en=()) -> list[float | None] | None:
    if not table:
        return None
    for want in codes:
        for r in table["rows"]:
            if r.get("code") == want:
                return r["values"]
    for want in labels:
        for r in table["rows"]:
            if r.get("label", "").strip().upper() == want.upper():
                return r["values"]
    for want in labels_en:
        for r in table["rows"]:
            if r.get("label_en") == want:
                return r["values"]
    return None


def figures(tables: dict, source: str, bank: bool = False) -> dict[str, dict[str, float | None]]:
    """{period_end: {revenue, net, equity, ...}} from one frequency's three tables."""
    ends = []
    for t in tables.values():
        if t:
            ends = sorted(set(ends) | set(t["period_ends"]), reverse=True)
    out: dict[str, dict] = {e: {} for e in ends}
    for name in set(_ISY) | set(_YAHOO_FIG) | set(_ISY_BANK_LABELS):
        for kind in ("income", "balance", "cashflow"):
            t = tables.get(kind)
            if not t:
                continue
            if source == "isy":
                vals = (_row_values(t, labels=_ISY_BANK_LABELS.get(name, ())) if bank
                        else _row_values(t, codes=_ISY.get(name, ())))
            else:
                vals = _row_values(t, labels_en=_YAHOO_FIG.get(name, ()))
            if vals is None:
                continue
            for e, v in zip(t["period_ends"], vals):
                if v is not None and out[e].get(name) is None:
                    out[e][name] = v
            break
    for e, f in out.items():
        if source == "isy" and not bank:
            if f.get("st_debt") is not None or f.get("lt_debt") is not None:
                f["debt"] = (f.get("st_debt") or 0) + (f.get("lt_debt") or 0)
            if f.get("ebit") is not None and f.get("da") is not None:
                f["ebitda"] = f["ebit"] + abs(f["da"])
            if f.get("eps") == 0:
                f["eps"] = None
        if f.get("debt") is not None:
            f["net_debt"] = f["debt"] - (f.get("cash") or 0) - (f.get("st_invest") or 0)
        if f.get("fcf") is None and f.get("ocf") is not None and f.get("capex") is not None:
            f["fcf"] = f["ocf"] - abs(f["capex"])
    return out


_FLOW = ("revenue", "gross", "ebit", "ebitda", "net", "pretax", "ocf", "capex", "fcf", "dividends_paid", "da", "nii")


def ttm(quarterly_cum: dict[str, dict], annual: dict[str, dict]) -> tuple[dict, str | None]:
    """Trailing twelve months from year-to-date interim figures: YTD + last year - YTD a year ago."""
    if not quarterly_cum:
        return {}, None
    latest = max(quarterly_cum)
    cur = quarterly_cum[latest]
    if latest[5:7] == "12":
        return {k: cur.get(k) for k in _FLOW}, latest
    year = int(latest[:4])
    prev_year_end = f"{year - 1}-12-31"
    prev_same = f"{year - 1}{latest[4:]}"
    a, p = annual.get(prev_year_end) or quarterly_cum.get(prev_year_end) or {}, quarterly_cum.get(prev_same) or {}
    out = {}
    for k in _FLOW:
        if cur.get(k) is not None and a.get(k) is not None and p.get(k) is not None:
            out[k] = cur[k] + a[k] - p[k]
    return out, latest


def ttm_from_quarters(quarters: dict[str, dict]) -> tuple[dict, str | None]:
    """Trailing twelve months as the sum of the last four single quarters (Yahoo)."""
    ends = sorted(quarters, reverse=True)[:4]
    if len(ends) < 4:
        return {}, None
    out = {}
    for k in _FLOW:
        vals = [quarters[e].get(k) for e in ends]
        if all(v is not None for v in vals):
            out[k] = sum(vals)
    return out, ends[0]


def _div(a, b):
    a, b = _f(a), _f(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(a, b):
    v = _div(a, b)
    return None if v is None else v * 100


def ratio_history(annual: dict[str, dict], bank: bool = False) -> dict:
    """Ratios per fiscal year, newest first, from the annual statements."""
    ends = sorted(annual, reverse=True)
    rows = {
        "Brüt marj %": lambda f, p: _pct(f.get("gross"), f.get("revenue")),
        "FAVÖK marjı %": lambda f, p: _pct(f.get("ebitda"), f.get("revenue")),
        "Faaliyet marjı %": lambda f, p: _pct(f.get("ebit"), f.get("revenue")),
        "Net marj %": lambda f, p: _pct(f.get("net"), f.get("revenue")),
        "Özkaynak kârlılığı (ROE) %": lambda f, p: _pct(f.get("net"), f.get("equity")),
        "Aktif kârlılığı (ROA) %": lambda f, p: _pct(f.get("net"), f.get("assets")),
        "Borç / özkaynak (x)": lambda f, p: _div(f.get("debt"), f.get("equity")),
        "Net borç / FAVÖK (x)": lambda f, p: _div(f.get("net_debt"), f.get("ebitda")),
        "Cari oran (x)": lambda f, p: _div(f.get("cur_assets"), f.get("cur_liab")),
        "Satış büyümesi %": lambda f, p: None if not p else _pct((f.get("revenue") or 0) - (p.get("revenue") or 0), p.get("revenue")) if f.get("revenue") is not None and p.get("revenue") else None,
        "Net kâr büyümesi %": lambda f, p: None if not p or not p.get("net") or f.get("net") is None or p["net"] <= 0 else _pct(f["net"] - p["net"], p["net"]),
    }
    if bank:
        rows = {k: v for k, v in rows.items() if not k.startswith(("Brüt", "FAVÖK", "Faaliyet", "Borç", "Net borç", "Cari"))}
        rows["Kredi / mevduat (x)"] = lambda f, p: _div(f.get("loans"), f.get("deposits"))
    table = {"columns": [e[:4] for e in ends], "period_ends": ends, "rows": []}
    for label, fn in rows.items():
        vals = []
        for i, e in enumerate(ends):
            prev = annual.get(ends[i + 1]) if i + 1 < len(ends) else None
            try:
                vals.append(fn(annual[e], prev))
            except (TypeError, ZeroDivisionError):
                vals.append(None)
        if any(v is not None for v in vals):
            table["rows"].append({"label": label, "values": vals})
    return table


def _ratio(out: list, key, label, value, unit, source, note=None, group=""):
    v = _f(value)
    if v is None:
        return
    out.append({"key": key, "label": label, "value": v, "unit": unit, "source": source, "note": note, "group": group})


# ---------------------------------------------------------------- collect


def collect(symbol: str, refresh: bool = False) -> dict:
    """The whole dossier for ``symbol`` (cached parts, refetched when stale or on ``refresh``)."""
    symbol, market = resolve(symbol)
    safe_ticker_component(symbol)
    if market == "BIST":
        return _collect_bist(symbol, refresh)
    return _collect_yahoo_sec(symbol, market, refresh)


def _run_parts(symbol: str, parts: dict[str, tuple[float, Callable[[], Any]]], refresh: bool) -> dict[str, _Result]:
    with ThreadPoolExecutor(max_workers=min(8, len(parts))) as pool:
        futures = {name: pool.submit(_part, symbol, name, ttl, fn, refresh) for name, (ttl, fn) in parts.items()}
        return {name: f.result() for name, f in futures.items()}


_SOURCE_LABELS = {
    "yahoo_info": "Yahoo Finance: profil ve oranlar", "yahoo_statements": "Yahoo Finance: mali tablolar",
    "yahoo_holders": "Yahoo Finance: ortaklar ve içeriden işlemler", "yahoo_dividends": "Yahoo Finance: temettüler",
    "yahoo_earnings": "Yahoo Finance: bilanço tarihleri", "sec_filings": "SEC EDGAR: bildirim listesi",
    "sec_facts": "SEC EDGAR: dosyalanan temel kalemler", "alpha_vantage": "Alpha Vantage: OVERVIEW",
    "isy_annual": "İş Yatırım: yıllık mali tablolar", "isy_quarterly": "İş Yatırım: ara dönem mali tablolar",
    "isy_market": "İş Yatırım: piyasa değeri ve çarpanlar", "isy_dividends": "İş Yatırım: temettü geçmişi",
    "isy_holders": "İş Yatırım: ortaklık yapısı", "analyst": "hedeffiyat.com.tr: analist hedefleri",
    "kap_company": "KAP: şirket genel bilgileri", "kap_disclosures": "KAP: bildirimler", "kap_calendar": "KAP: beklenen bildirimler",
}


def _sources(results: dict[str, _Result]) -> list[dict]:
    out = []
    for name, r in results.items():
        state = ("ok" if r.data not in (None, {}, []) and not r.stale else "stale" if r.stale
                 else "skipped" if r.skipped else "error" if r.error else "empty")
        out.append({"key": name, "label": _SOURCE_LABELS.get(name, name), "state": state,
                    "fetched": datetime.fromtimestamp(r.fetched).isoformat(timespec="minutes") if r.fetched else None,
                    "note": r.error or r.skipped})
    return out


def _collect_yahoo_sec(symbol: str, market: str, refresh: bool) -> dict:
    parts: dict[str, tuple[float, Callable]] = {
        "yahoo_info": (6 * HOUR, lambda: _yahoo_info(symbol)),
        "yahoo_statements": (DAY, lambda: _yahoo_statements(symbol)),
        "yahoo_holders": (DAY, lambda: _yahoo_holders(symbol)),
        "yahoo_dividends": (DAY, lambda: _yahoo_dividends(symbol)),
        "yahoo_earnings": (12 * HOUR, lambda: _yahoo_earnings(symbol)),
        "alpha_vantage": (DAY, lambda: _alpha_overview(symbol)),
    }
    if market == "US":
        parts["sec_filings"] = (6 * HOUR, lambda: _sec_filings(symbol))
        parts["sec_facts"] = (DAY, lambda: {"annual": sec_key_table(symbol, "annual"),
                                            "quarterly": sec_key_table(symbol, "quarterly", periods=12)})
    res = _run_parts(symbol, parts, refresh)
    info = res["yahoo_info"].data or {}
    st = res["yahoo_statements"].data or {}
    holders = res["yahoo_holders"].data or {}
    av = res["alpha_vantage"].data or {}
    sec = res.get("sec_filings").data if res.get("sec_filings") else None
    facts = res.get("sec_facts").data if res.get("sec_facts") else None
    if not info and not st and not sec:
        errs = "; ".join(f"{k}: {r.error or r.skipped}" for k, r in res.items() if r.error or r.skipped)
        raise NoMarketDataError(symbol, symbol, f"no source had data ({errs})")

    quote_ccy = info.get("currency") or "USD"
    main_ccy = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(quote_ccy, quote_ccy)
    report_ccy = info.get("financialCurrency") or main_ccy
    mismatch = report_ccy != main_ccy

    annual_t = (st.get("annual") or {})
    quarterly_t = (st.get("quarterly") or {})
    fa = figures(annual_t, "yahoo") if annual_t else {}
    fq = figures(quarterly_t, "yahoo") if quarterly_t else {}
    t12, t12_end = ttm_from_quarters(fq)

    ratios: list[dict] = []
    src = "Yahoo Finance"
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    _ratio(ratios, "price", "Son fiyat", price, f"money:{quote_ccy}", src, group="Piyasa")
    _ratio(ratios, "market_cap", "Piyasa değeri", info.get("marketCap"), f"money:{main_ccy}", src, group="Piyasa")
    _ratio(ratios, "ev", "Firma değeri (FD)", info.get("enterpriseValue"), f"money:{main_ccy}", src, group="Piyasa")
    _ratio(ratios, "beta", "Beta (5 yıl)", info.get("beta"), "x", src, group="Piyasa")
    _ratio(ratios, "pe", "F/K (son 12 ay)", info.get("trailingPE"), "x", src, group="Değerleme")
    _ratio(ratios, "fpe", "İleriye dönük F/K", info.get("forwardPE"), "x", src, group="Değerleme")
    _ratio(ratios, "peg", "PEG", info.get("trailingPegRatio") or info.get("pegRatio"), "x", src, group="Değerleme")
    note = "rapor para birimi fiyatınkinden farklı; çarpanları dikkatle okuyun" if mismatch else None
    _ratio(ratios, "pb", "PD/DD", info.get("priceToBook"), "x", src, note, group="Değerleme")
    _ratio(ratios, "ev_ebitda", "FD/FAVÖK", info.get("enterpriseToEbitda"), "x", src, note, group="Değerleme")
    _ratio(ratios, "ev_sales", "FD/Satışlar", info.get("enterpriseToRevenue"), "x", src, note, group="Değerleme")
    _ratio(ratios, "ps", "F/Satışlar", info.get("priceToSalesTrailing12Months"), "x", src, note, group="Değerleme")
    dy = info.get("dividendYield")
    _ratio(ratios, "div_yield", "Temettü verimi", dy, "%", src, group="Temettü")
    _ratio(ratios, "payout", "Temettü dağıtım oranı", None if info.get("payoutRatio") is None else info["payoutRatio"] * 100, "%", src, group="Temettü")
    for key, label, field in (("gross_m", "Brüt marj", "grossMargins"), ("ebitda_m", "FAVÖK marjı", "ebitdaMargins"),
                              ("op_m", "Faaliyet marjı", "operatingMargins"), ("net_m", "Net marj", "profitMargins"),
                              ("roe", "Özkaynak kârlılığı (ROE)", "returnOnEquity"), ("roa", "Aktif kârlılığı (ROA)", "returnOnAssets")):
        v = info.get(field)
        _ratio(ratios, key, label, None if v is None else v * 100, "%", src, group="Kârlılık")
    de = info.get("debtToEquity")
    _ratio(ratios, "de", "Borç / özkaynak", None if de is None else de / 100, "x", src, group="Borçluluk ve likidite")
    if t12.get("ebitda") and fq:
        latest_q = fq[max(fq)]
        _ratio(ratios, "nd_ebitda", "Net borç / FAVÖK", _div(latest_q.get("net_debt"), t12["ebitda"]), "x", "hesaplanan (Yahoo tabloları)", group="Borçluluk ve likidite")
    _ratio(ratios, "current", "Cari oran", info.get("currentRatio"), "x", src, group="Borçluluk ve likidite")
    _ratio(ratios, "quick", "Asit-test oranı", info.get("quickRatio"), "x", src, group="Borçluluk ve likidite")
    for key, label, field in (("rev_g", "Satış büyümesi (çeyrek, yıllık)", "revenueGrowth"),
                              ("eps_g", "Kâr büyümesi (çeyrek, yıllık)", "earningsQuarterlyGrowth")):
        v = info.get(field)
        _ratio(ratios, key, label, None if v is None else v * 100, "%", src, group="Büyüme")
    _ratio(ratios, "eps", "HBK (son 12 ay)", info.get("trailingEps"), f"money:{main_ccy}", src, group="Hisse başına")
    _ratio(ratios, "feps", "Beklenen HBK", info.get("forwardEps"), f"money:{main_ccy}", src, group="Hisse başına")
    _ratio(ratios, "bvps", "Defter değeri / hisse", info.get("bookValue"), f"money:{main_ccy}", src, group="Hisse başına")
    _ratio(ratios, "fcf", "Serbest nakit akışı (son 12 ay)", info.get("freeCashflow") or t12.get("fcf"), f"money:{report_ccy}", src, group="Nakit")
    _ratio(ratios, "revenue_ttm", "Satışlar (son 12 ay)", info.get("totalRevenue") or t12.get("revenue"), f"money:{report_ccy}", src, group="Nakit")
    _ratio(ratios, "net_ttm", "Net kâr (son 12 ay)", info.get("netIncomeToCommon") or t12.get("net"), f"money:{report_ccy}", src, group="Nakit")
    have = {r["key"] for r in ratios}
    av_map = (("pe", "F/K (son 12 ay)", "PERatio", "x", "Değerleme"), ("peg", "PEG", "PEGRatio", "x", "Değerleme"),
              ("pb", "PD/DD", "PriceToBookRatio", "x", "Değerleme"), ("ev_ebitda", "FD/FAVÖK", "EVToEBITDA", "x", "Değerleme"),
              ("ps", "F/Satışlar", "PriceToSalesRatioTTM", "x", "Değerleme"), ("beta", "Beta", "Beta", "x", "Piyasa"))
    for key, label, field, unit, group in av_map:
        if key not in have and av.get(field):
            _ratio(ratios, key, label, av.get(field), unit, "Alpha Vantage", group=group)
    for key, label, field, group in (("net_m", "Net marj", "ProfitMargin", "Kârlılık"), ("op_m", "Faaliyet marjı", "OperatingMarginTTM", "Kârlılık"),
                                     ("roe", "Özkaynak kârlılığı (ROE)", "ReturnOnEquityTTM", "Kârlılık"),
                                     ("roa", "Aktif kârlılığı (ROA)", "ReturnOnAssetsTTM", "Kârlılık"),
                                     ("div_yield", "Temettü verimi", "DividendYield", "Temettü")):
        if key not in have and _f(av.get(field)) is not None:
            _ratio(ratios, key, label, _f(av[field]) * 100, "%", "Alpha Vantage", group=group)

    major = holders.get("major") or {}
    ownership_summary = []
    for key, label, unit in (("insidersPercentHeld", "İçeriden (yönetim ve büyük ortaklar)", "%"),
                             ("institutionsPercentHeld", "Kurumsal yatırımcılar", "%"),
                             ("institutionsFloatPercentHeld", "Kurumsal (halka açık paylar içinde)", "%"),
                             ("institutionsCount", "Kurumsal yatırımcı sayısı", "n")):
        v = major.get(key)
        if v is not None:
            ownership_summary.append({"label": label, "value": v * 100 if unit == "%" else v, "unit": unit, "source": "Yahoo Finance"})
    shares, floats = info.get("sharesOutstanding"), info.get("floatShares")
    if shares:
        ownership_summary.append({"label": "Dolaşımdaki hisse", "value": shares, "unit": "n", "source": "Yahoo Finance"})
    if floats:
        ownership_summary.append({"label": "Halka açık hisse (float)", "value": floats, "unit": "n", "source": "Yahoo Finance"})
        if shares:
            ownership_summary.append({"label": "Halka açıklık oranı", "value": floats / shares * 100, "unit": "%", "source": "Yahoo Finance"})

    def holder_rows(rows):
        return [{"holder": r.get("Holder"), "pct": None if r.get("pctHeld") is None else r["pctHeld"] * 100,
                 "shares": r.get("Shares"), "value": r.get("Value"), "date": r.get("Date Reported"),
                 "change_pct": None if r.get("pctChange") is None else r["pctChange"] * 100} for r in rows]

    insider_tx = [{"date": r.get("Start Date"), "insider": r.get("Insider"), "position": r.get("Position"),
                   "text": r.get("Text") or r.get("Transaction"), "shares": r.get("Shares"), "value": r.get("Value"),
                   "ownership": r.get("Ownership")} for r in holders.get("insider_transactions") or []]
    roster = [{"name": r.get("Name"), "position": r.get("Position"), "last": r.get("Most Recent Transaction"),
               "date": r.get("Latest Transaction Date"), "shares": r.get("Shares Owned Directly")}
              for r in holders.get("insider_roster") or []]
    purchases = [{"label": r.get("Insider Purchases Last 6m"), "shares": r.get("Shares"), "count": r.get("Trans")}
                 for r in holders.get("insider_purchases") or []]
    filings = (sec or {}).get("filings") or []
    form4 = [f for f in filings if f["form"] == "4"]

    statements: dict[str, Any] = {}
    if annual_t:
        statements["annual"] = {**annual_t, "source": "Yahoo Finance", "currency": report_ccy}
    if quarterly_t:
        statements["quarterly"] = {**quarterly_t, "source": "Yahoo Finance", "currency": report_ccy}
    if facts and facts.get("annual"):
        statements["sec_annual"] = {"facts": facts["annual"], "source": "SEC EDGAR (dosyalandığı gibi)", "currency": "USD"}
    if facts and facts.get("quarterly"):
        statements["sec_quarterly"] = {"facts": facts["quarterly"], "source": "SEC EDGAR (dosyalandığı gibi)", "currency": "USD"}

    analyst = {}
    for k_out, k_in in (("mean", "targetMeanPrice"), ("high", "targetHighPrice"), ("low", "targetLowPrice"),
                        ("median", "targetMedianPrice"), ("count", "numberOfAnalystOpinions"),
                        ("recommendation", "recommendationKey"), ("recommendation_mean", "recommendationMean")):
        if info.get(k_in) is not None:
            analyst[k_out] = info[k_in]
    if av.get("AnalystTargetPrice") and "mean" not in analyst:
        analyst["mean"] = _f(av["AnalystTargetPrice"])
    if analyst:
        analyst["source"] = "Yahoo Finance" + (" / Alpha Vantage" if av else "")
        analyst["currency"] = quote_ccy

    return {
        "symbol": symbol, "market": market, "name": info.get("longName") or info.get("shortName") or (sec or {}).get("name") or symbol,
        "currency": quote_ccy, "report_currency": report_ccy, "currency_mismatch": mismatch,
        "generated": datetime.now().isoformat(timespec="minutes"),
        "profile": {
            "sector": info.get("sector"), "industry": info.get("industry"), "sic": (sec or {}).get("sic"),
            "country": info.get("country"), "city": info.get("city"), "website": info.get("website"),
            "employees": info.get("fullTimeEmployees"), "summary": info.get("longBusinessSummary"),
            "exchange": info.get("fullExchangeName") or info.get("exchange"), "cik": (sec or {}).get("cik"),
            "fiscal_year_end": (sec or {}).get("fiscal_year_end"), "state": (sec or {}).get("state"),
            "governance_risk": {k: info.get(k) for k in ("auditRisk", "boardRisk", "compensationRisk", "shareHolderRightsRisk", "overallRisk") if info.get(k) is not None},
        },
        "ratios": ratios,
        "ttm": {"period_end": t12_end, **{k: v for k, v in t12.items() if v is not None}},
        "ratio_history": ratio_history(fa) if fa else None,
        "key_figures": {"annual": fa, "quarterly": fq},
        "statements": statements,
        "dividends": res["yahoo_dividends"].data or [],
        "ownership": {"summary": ownership_summary, "major": [], "institutional": holder_rows(holders.get("institutional") or []),
                      "funds": holder_rows(holders.get("funds") or [])},
        "insiders": {"transactions": insider_tx, "roster": roster, "summary": purchases,
                     "filings": form4[:30]},
        "management": {"officers": info.get("officers") or [], "board": []},
        "subsidiaries": [],
        "filings": [f for f in filings if f["form"] != "4"][:60],
        "calendar": {"earnings": res["yahoo_earnings"].data or []},
        "analyst": analyst,
        "notes": (["Raporlama para birimi (" + report_ccy + ") fiyatın para biriminden (" + main_ccy + ") farklı; "
                   "Yahoo'nun PD/DD ve FD/FAVÖK gibi çarpanları iki para birimini karıştırabilir."] if mismatch else []),
        "notes_en": ([f"Statements are in {report_ccy} but the quote is in {main_ccy}: Yahoo's P/B and EV/EBITDA may mix the two currencies."]
                     if mismatch else []),
        "sources": _sources(res),
    }


def _collect_bist(symbol: str, refresh: bool) -> dict:
    parts: dict[str, tuple[float, Callable]] = {
        "isy_annual": (DAY, lambda: bist.statements(symbol, False, 10)),
        "isy_quarterly": (DAY, lambda: bist.statements(symbol, True, 13)),
        "isy_market": (2 * HOUR, lambda: _bist_market(symbol)),
        "isy_dividends": (DAY, lambda: bist.dividends(symbol)),
        "isy_holders": (DAY, lambda: _bist_holders(symbol)),
        "analyst": (DAY, lambda: bist.analyst_view(symbol)),
        "kap_company": (DAY, lambda: bist.kap_company(symbol)),
        "kap_disclosures": (HOUR, lambda: bist.disclosures(symbol, 80)),
        "kap_calendar": (DAY, lambda: bist.earnings_calendar(symbol)),
        "yahoo_info": (DAY, lambda: _yahoo_info(symbol)),
    }
    res = _run_parts(symbol, parts, refresh)
    ann = res["isy_annual"].data or {}
    qtr = res["isy_quarterly"].data or {}
    mk = res["isy_market"].data or {}
    kap = res["kap_company"].data or {}
    info = res["yahoo_info"].data or {}
    if not ann and not qtr and not kap:
        errs = "; ".join(f"{k}: {r.error or r.skipped}" for k, r in res.items() if r.error or r.skipped)
        raise NoMarketDataError(symbol, bist.bist_code(symbol), f"no source had data ({errs})")
    bank = (ann.get("group") or qtr.get("group")) == "UFRS"

    at = ann.get("tables") or {}
    qt_cum = qtr.get("tables") or {}
    qt = {k: (bist.discrete_quarters(v) if k in ("income", "cashflow") else v) for k, v in qt_cum.items() if v}
    fa = figures(at, "isy", bank) if at else {}
    fq_cum = figures(qt_cum, "isy", bank) if qt_cum else {}
    fq = figures(qt, "isy", bank) if qt else {}
    t12, t12_end = ttm(fq_cum, fa)
    latest_bal = fq_cum[max(fq_cum)] if fq_cum else (fa[max(fa)] if fa else {})
    if not t12 and fa:
        t12, t12_end = {k: fa[max(fa)].get(k) for k in _FLOW}, max(fa)

    kp = kap.get("profile") or {}
    ff = kap.get("free_float") or {}
    shares = ff.get("total_shares") or kp.get("paid_capital")
    mcap = _f(mk.get("market_cap"))
    price = _f(mk.get("last")) or (mcap / shares if mcap and shares else None)
    if not mcap and price and shares:
        mcap = price * shares

    ratios: list[dict] = []
    calc = "hesaplanan (İş Yatırım tabloları)"
    _ratio(ratios, "price", "Son fiyat", price, "money:TRY", "borsapy (TradingView)", group="Piyasa")
    _ratio(ratios, "market_cap", "Piyasa değeri", mcap, "money:TRY", "İş Yatırım", group="Piyasa")
    nd = latest_bal.get("net_debt")
    _ratio(ratios, "ev", "Firma değeri (FD)", None if mcap is None or nd is None else mcap + nd, "money:TRY", calc, group="Piyasa")
    _ratio(ratios, "pe", "F/K (son 12 ay)", _div(mcap, t12.get("net")) if (t12.get("net") or 0) > 0 else None, "x", calc,
           None if (t12.get("net") or 0) > 0 else "son 12 ay zarar: F/K anlamsız", group="Değerleme")
    _ratio(ratios, "pb", "PD/DD", _div(mcap, latest_bal.get("equity")), "x", calc, group="Değerleme")
    if not bank:
        _ratio(ratios, "ev_ebitda", "FD/FAVÖK", _div(None if mcap is None or nd is None else mcap + nd, t12.get("ebitda")), "x", calc, group="Değerleme")
        _ratio(ratios, "ps", "F/Satışlar", _div(mcap, t12.get("revenue")), "x", calc, group="Değerleme")
    for key, label, field in (("isy_pe", "F/K (İş Yatırım)", "pe_ratio"), ("isy_pb", "PD/DD (İş Yatırım)", "pb_ratio"),
                              ("isy_ev_ebitda", "FD/FAVÖK (İş Yatırım)", "ev_ebitda")):
        _ratio(ratios, key, label, mk.get(field), "x", "İş Yatırım", group="Değerleme")
    divs = res["isy_dividends"].data or []
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    dps = sum(d["amount"] or 0 for d in divs if d.get("date") and d["date"] >= year_ago)
    _ratio(ratios, "div_yield", "Temettü verimi (son 12 ay)", _pct(dps, price) if dps and price else (0 if price else None), "%", calc, group="Temettü")
    _ratio(ratios, "payout", "Temettü dağıtım oranı (son yıl)",
           _pct(abs(fa[max(fa)]["dividends_paid"]), fa[max(fa)].get("net"))
           if fa and fa[max(fa)].get("dividends_paid") is not None and (fa[max(fa)].get("net") or 0) > 0 else None,
           "%", calc, group="Temettü")
    if not bank:
        for key, label, num in (("gross_m", "Brüt marj", "gross"), ("ebitda_m", "FAVÖK marjı", "ebitda"),
                                ("op_m", "Faaliyet marjı", "ebit"), ("net_m", "Net marj", "net")):
            _ratio(ratios, key, label + " (son 12 ay)", _pct(t12.get(num), t12.get("revenue")), "%", calc, group="Kârlılık")
    _ratio(ratios, "roe", "Özkaynak kârlılığı (ROE, son 12 ay)", _pct(t12.get("net"), latest_bal.get("equity")), "%", calc, group="Kârlılık")
    _ratio(ratios, "roa", "Aktif kârlılığı (ROA, son 12 ay)", _pct(t12.get("net"), latest_bal.get("assets")), "%", calc, group="Kârlılık")
    if bank:
        _ratio(ratios, "ldr", "Kredi / mevduat", _div(latest_bal.get("loans"), latest_bal.get("deposits")), "x", calc, group="Bankacılık")
        _ratio(ratios, "nii_ttm", "Net faiz geliri (son 12 ay)", t12.get("nii"), "money:TRY", calc, group="Bankacılık")
    else:
        _ratio(ratios, "de", "Borç / özkaynak", _div(latest_bal.get("debt"), latest_bal.get("equity")), "x", calc, group="Borçluluk ve likidite")
        _ratio(ratios, "net_debt", "Net borç", nd, "money:TRY", calc, group="Borçluluk ve likidite")
        _ratio(ratios, "nd_ebitda", "Net borç / FAVÖK", _div(nd, t12.get("ebitda")), "x", calc, group="Borçluluk ve likidite")
        _ratio(ratios, "current", "Cari oran", _div(latest_bal.get("cur_assets"), latest_bal.get("cur_liab")), "x", calc, group="Borçluluk ve likidite")
        ca, inv = latest_bal.get("cur_assets"), latest_bal.get("inventory") or 0
        _ratio(ratios, "quick", "Asit-test oranı", _div(None if ca is None else ca - inv, latest_bal.get("cur_liab")), "x", calc, group="Borçluluk ve likidite")
    if fq_cum:
        last = max(fq_cum)
        prev = f"{int(last[:4]) - 1}{last[4:]}"
        cur, old = fq_cum[last], fq_cum.get(prev) or fa.get(prev) or {}
        span = {"03": "3 ay", "06": "6 ay", "09": "9 ay", "12": "12 ay"}[last[5:7]]
        _ratio(ratios, "rev_g", f"{'Faaliyet geliri' if bank else 'Satış'} büyümesi ({span}, yıllık, nominal TL)", _pct((cur.get("revenue") or 0) - (old.get("revenue") or 0), old.get("revenue")) if cur.get("revenue") is not None and old.get("revenue") else None, "%", calc, group="Büyüme")
        if (old.get("net") or 0) > 0 and cur.get("net") is not None:
            _ratio(ratios, "net_g", f"Net kâr büyümesi ({span}, yıllık, nominal TL)", _pct(cur["net"] - old["net"], old["net"]), "%", calc, group="Büyüme")
    _ratio(ratios, "eps", "HBK (son 12 ay)", _div(t12.get("net"), shares), "money:TRY", calc, group="Hisse başına")
    _ratio(ratios, "bvps", "Defter değeri / hisse", _div(latest_bal.get("equity"), shares), "money:TRY", calc, group="Hisse başına")
    _ratio(ratios, "fcf", "Serbest nakit akışı (son 12 ay)", t12.get("fcf"), "money:TRY", calc, group="Nakit")
    _ratio(ratios, "revenue_ttm", "Satışlar (son 12 ay)" if not bank else "Faaliyet gelirleri (son 12 ay)", t12.get("revenue"), "money:TRY", calc, group="Nakit")
    _ratio(ratios, "net_ttm", "Net kâr (ana ortaklık, son 12 ay)", t12.get("net"), "money:TRY", calc, group="Nakit")
    _ratio(ratios, "beta", "Beta (Yahoo)", info.get("beta"), "x", "Yahoo Finance", group="Piyasa")

    ownership_summary = []
    if ff.get("pct") is not None:
        ownership_summary.append({"label": "Fiili dolaşımdaki pay oranı", "value": ff["pct"], "unit": "%", "source": f"KAP ({ff.get('date') or ''})".strip()})
    if mk.get("free_float") is not None:
        ownership_summary.append({"label": "Halka açıklık (İş Yatırım)", "value": mk["free_float"], "unit": "%", "source": "İş Yatırım"})
    if mk.get("foreign_ratio") is not None:
        ownership_summary.append({"label": "Yabancı payı (halka açık kısımda)", "value": mk["foreign_ratio"], "unit": "%", "source": "İş Yatırım"})
    if info.get("heldPercentInstitutions") is not None:
        ownership_summary.append({"label": "Kurumsal yatırımcılar (Yahoo tahmini)", "value": info["heldPercentInstitutions"] * 100, "unit": "%", "source": "Yahoo Finance"})
    if shares:
        ownership_summary.append({"label": "Toplam pay adedi", "value": shares, "unit": "n", "source": "KAP"})
    if ff.get("shares"):
        ownership_summary.append({"label": "Fiili dolaşımdaki pay adedi", "value": ff["shares"], "unit": "n", "source": "KAP"})
    if kp.get("paid_capital"):
        ownership_summary.append({"label": "Ödenmiş sermaye", "value": kp["paid_capital"], "unit": "money:TRY", "source": "KAP"})
    if kp.get("authorized_capital"):
        ownership_summary.append({"label": "Kayıtlı sermaye tavanı", "value": kp["authorized_capital"], "unit": "money:TRY", "source": "KAP"})

    major = kap.get("holders") or [{"holder": h["holder"], "pct": h["pct"]} for h in (res["isy_holders"].data or [])]
    disc = res["kap_disclosures"].data or []

    statements: dict[str, Any] = {}
    src = "İş Yatırım (KAP'a gönderilen tablolar)"
    if at:
        statements["annual"] = {**at, "source": src, "currency": "TRY"}
    if qt:
        statements["quarterly"] = {**qt, "source": src + "; tek çeyrek = birikimli farkı", "currency": "TRY"}
    if qt_cum:
        statements["quarterly_cum"] = {**qt_cum, "source": src + "; yıl başından birikimli", "currency": "TRY"}

    analyst = dict(res["analyst"].data or {})
    if analyst:
        analyst["currency"] = "TRY"

    return {
        "symbol": symbol, "market": "BIST", "name": info.get("longName") or info.get("shortName") or bist.bist_code(symbol),
        "currency": "TRY", "report_currency": "TRY", "currency_mismatch": False, "bank": bank,
        "generated": datetime.now().isoformat(timespec="minutes"),
        "profile": {
            "sector": kp.get("sector") or info.get("sector"), "industry": info.get("industry"),
            "sector_en": info.get("sector"), "activity": kp.get("activity"), "market_segment": kp.get("market"),
            "indices": kp.get("indices") or [], "auditor": kp.get("auditor"), "address": kp.get("address"),
            "website": kp.get("website") or info.get("website"), "registered": kp.get("registered"),
            "employees": info.get("fullTimeEmployees"), "summary": info.get("longBusinessSummary"),
            "country": info.get("country") or "Turkey", "exchange": "Borsa İstanbul", "kap_url": kap.get("url"),
        },
        "ratios": ratios,
        "ttm": {"period_end": t12_end, **{k: v for k, v in t12.items() if v is not None}},
        "ratio_history": ratio_history(fa, bank) if fa else None,
        "key_figures": {"annual": fa, "quarterly": fq},
        "statements": statements,
        "dividends": divs,
        "ownership": {"summary": ownership_summary, "major": major, "institutional": [], "funds": [],
                      "indirect": kap.get("indirect_holders"), "share_groups": kap.get("share_groups") or [],
                      "isy_holders": res["isy_holders"].data or []},
        "insiders": {"transactions": [], "roster": [], "summary": [], "filings": bist.insider_disclosures(disc)[:30]},
        "management": {"officers": info.get("officers") or [], "board": kap.get("board") or [], "executives": kap.get("management") or []},
        "subsidiaries": kap.get("subsidiaries") or [],
        "filings": disc,
        "calendar": {"expected": res["kap_calendar"].data or []},
        "analyst": analyst,
        "notes": [
            "Ara dönem tabloları KAP'ta yıl başından birikimli yayımlanır; tek çeyrekler ardışık dönemlerin farkıdır.",
            "2023'ten itibaren TMS 29 (enflasyon muhasebesi) uygulanır; nominal TL büyüme oranları enflasyonu içerir.",
        ] + (["Banka: bilanço ve gelir tablosu banka (UFRS) düzeninde; brüt marj, FAVÖK ve cari oran bankalar için anlamsızdır."] if bank else []),
        "notes_en": [
            "KAP interim statements are cumulative from the start of the fiscal year; single quarters are differences of consecutive filings.",
            "TMS 29 (IAS 29 inflation accounting) applies from 2023: TRY growth rates are nominal and include inflation; prefer margins, returns and multiples.",
            "Ratios 'computed from Is Yatirim statements' use the filed statements and the current market cap; Is Yatirim's own multiples are listed alongside.",
        ] + (["Bank: statements follow the bank (UFRS) layout; gross margin, EBITDA and the current ratio do not apply."] if bank else []),
        "sources": _sources(res),
    }


# ---------------------------------------------------------------- report for the analysts


def _m(v, ccy: str = "") -> str:
    """Money in millions (or billions above 10bn), compact."""
    v = _f(v)
    if v is None:
        return "n/a"
    a = abs(v)
    if a >= 1e10:
        return f"{v / 1e9:,.1f}bn"
    if a >= 1e5:
        return f"{v / 1e6:,.0f}m"
    return f"{v:,.2f}"


_RATIO_EN = {
    "price": "Last price", "market_cap": "Market cap", "ev": "Enterprise value", "beta": "Beta", "pe": "P/E (TTM)",
    "fpe": "Forward P/E", "peg": "PEG", "pb": "P/B", "ev_ebitda": "EV/EBITDA", "ev_sales": "EV/Sales", "ps": "P/S (TTM)",
    "isy_pe": "P/E (Is Yatirim)", "isy_pb": "P/B (Is Yatirim)", "isy_ev_ebitda": "EV/EBITDA (Is Yatirim)",
    "div_yield": "Dividend yield (TTM)", "payout": "Payout ratio", "gross_m": "Gross margin", "ebitda_m": "EBITDA margin",
    "op_m": "Operating margin", "net_m": "Net margin", "roe": "Return on equity", "roa": "Return on assets",
    "de": "Debt / equity", "net_debt": "Net debt", "nd_ebitda": "Net debt / EBITDA", "current": "Current ratio",
    "quick": "Quick ratio", "rev_g": "Revenue growth", "net_g": "Net income growth", "eps_g": "Earnings growth (quarter, YoY)",
    "eps": "EPS (TTM)", "feps": "Forward EPS", "bvps": "Book value / share", "fcf": "Free cash flow (TTM)",
    "revenue_ttm": "Revenue (TTM)", "net_ttm": "Net income, parent (TTM)", "ldr": "Loans / deposits", "nii_ttm": "Net interest income (TTM)",
}
_OWN_EN = {
    "Fiili dolaşımdaki pay oranı": "Free float (KAP, shares in actual circulation)", "Halka açıklık (İş Yatırım)": "Free float (Is Yatirim)",
    "Yabancı payı (halka açık kısımda)": "Foreign share of the free float", "Kurumsal yatırımcılar (Yahoo tahmini)": "Institutions (Yahoo estimate)",
    "Toplam pay adedi": "Total shares", "Fiili dolaşımdaki pay adedi": "Shares in actual circulation", "Ödenmiş sermaye": "Paid-in capital",
    "Kayıtlı sermaye tavanı": "Authorized capital ceiling", "İçeriden (yönetim ve büyük ortaklar)": "Held by insiders",
    "Kurumsal yatırımcılar": "Held by institutions", "Kurumsal (halka açık paylar içinde)": "Institutions as % of float",
    "Kurumsal yatırımcı sayısı": "Number of institutions", "Dolaşımdaki hisse": "Shares outstanding",
    "Halka açık hisse (float)": "Float shares", "Halka açıklık oranı": "Float / shares outstanding",
}


def _fmt_ratio(r: dict) -> str:
    unit = r["unit"]
    if unit == "%":
        return f"{r['value']:.1f}%"
    if unit == "x":
        return f"{r['value']:.2f}x"
    if unit.startswith("money:"):
        return f"{_m(r['value'])} {unit[6:]}"
    return f"{r['value']:,.0f}"


_KEY_FIG_LABELS = (("revenue", "Revenue"), ("gross", "Gross profit"), ("ebitda", "EBITDA"), ("ebit", "Operating profit"),
                   ("net", "Net income (parent)"), ("assets", "Total assets"), ("equity", "Equity (parent)"),
                   ("debt", "Financial debt"), ("net_debt", "Net debt"), ("ocf", "Operating cash flow"),
                   ("capex", "Capex"), ("fcf", "Free cash flow"), ("loans", "Loans"), ("deposits", "Deposits"),
                   ("nii", "Net interest income"))


def _fig_table(figs: dict[str, dict], ends: list[str], label_of: Callable[[str], str]) -> list[str]:
    lines = ["| Line | " + " | ".join(label_of(e) for e in ends) + " |", "|---|" + "---|" * len(ends)]
    for key, label in _KEY_FIG_LABELS:
        vals = [figs[e].get(key) for e in ends]
        if all(v is None for v in vals):
            continue
        lines.append(f"| {label} | " + " | ".join(_m(v) for v in vals) + " |")
    return lines


def _hist_filter(items: list[dict], as_of: str | None, field: str = "date") -> list[dict]:
    if not as_of:
        return items
    return [i for i in items if (i.get(field) or "")[:10] and (i.get(field) or "")[:10] <= as_of]


def dossier_report(symbol: str, as_of_date: str | None = None, collected: dict | None = None) -> str:
    """The dossier as a compact Markdown brief for an analyst; point-in-time for a past ``as_of_date``."""
    from tradingagents.dataflows.date_window import is_historical

    d = collected or collect(symbol)
    hist = as_of_date if is_historical(as_of_date) else None
    ccy = d.get("report_currency") or d.get("currency")
    bist_mkt = d["market"] == "BIST"
    p = d.get("profile") or {}
    out = [f"# Company dossier: {d['symbol']} — {d.get('name')} ({'Borsa Istanbul' if bist_mkt else p.get('exchange') or d['market']})",
           f"Compiled {d.get('generated')}; money in {ccy} (m = millions, bn = billions) unless stated."
           + (" Quote currency differs from reporting currency." if d.get("currency_mismatch") else "")]
    ok = [s["label"] for s in d.get("sources", []) if s["state"] in ("ok", "stale")]
    out.append("Sources: " + "; ".join(ok) + ".")
    if hist:
        out.append(f"\n**Point-in-time for {hist}:** live snapshots (price, ratios, holders, management) are withheld; "
                   "statements are limited to periods that had been filed by then.")

    if not hist:
        out.append("\n## Profile")
        for label, key in (("Sector", "sector"), ("Industry", "industry"), ("Activity (KAP)", "activity"), ("Market segment", "market_segment"),
                           ("Country", "country"), ("Employees", "employees"), ("Auditor", "auditor"), ("Website", "website"),
                           ("SIC", "sic"), ("Fiscal year end", "fiscal_year_end")):
            if p.get(key):
                out.append(f"- {label}: {p[key]}")
        if p.get("indices"):
            out.append(f"- Indices: {', '.join(p['indices'][:12])}")
        if p.get("summary"):
            out.append(f"- Business: {p['summary'][:700]}")
        if p.get("governance_risk"):
            out.append("- ISS governance risk (1 low – 10 high): " + ", ".join(f"{k} {v}" for k, v in p["governance_risk"].items()))

        out.append("\n## Valuation and ratios (latest; TTM = trailing twelve months)")
        out.append("| Metric | Value | Source |")
        out.append("|---|---|---|")
        for r in d.get("ratios", []):
            label = _RATIO_EN.get(r["key"], r["label"])
            if r["key"] in ("rev_g", "net_g") and "(" in r["label"]:   # "(9 ay, yıllık, nominal TL)"
                months = r["label"].split("(")[1].split()[0]
                label += f" ({months} months year to date vs a year earlier, nominal {d.get('report_currency')})"
            source = r["source"]
            if source.startswith("hesaplanan ("):
                source = "computed from " + source[len("hesaplanan ("):].rstrip(")").replace("tabloları", "statements")
            note = {"son 12 ay zarar: F/K anlamsız": "loss over the last 12 months: P/E not meaningful"}.get(r.get("note") or "", r.get("note"))
            out.append(f"| {label} | {_fmt_ratio(r)} | {source}{' — ' + note if note else ''} |")
        if d.get("ttm", {}).get("period_end"):
            out.append(f"TTM ends {d['ttm']['period_end']}.")

    figs = d.get("key_figures") or {}
    fa, fq = figs.get("annual") or {}, figs.get("quarterly") or {}
    if hist and bist_mkt:
        fa = {e: v for e, v in fa.items() if (date.fromisoformat(hist) - date.fromisoformat(e)).days >= bist.ANNUAL_LAG_DAYS}
        fq = {e: v for e, v in fq.items() if (date.fromisoformat(hist) - date.fromisoformat(e)).days >= (bist.ANNUAL_LAG_DAYS if e[5:7] == "12" else bist.INTERIM_LAG_DAYS)}
    elif hist:
        fa, fq = {}, {}
    if fa:
        ends = sorted(fa, reverse=True)[:6]
        out.append(f"\n## Key financials — fiscal years ({ccy})")
        out += _fig_table(fa, ends, lambda e: e[:4])
        if not hist:
            rh = d.get("ratio_history") or {}
            if rh.get("rows"):
                cols = rh["columns"][:6]
                out.append("\n### Ratio history")
                out.append("| Ratio | " + " | ".join(cols) + " |")
                out.append("|---|" + "---|" * len(cols))
                for row in rh["rows"]:
                    out.append(f"| {row['label']} | " + " | ".join("n/a" if v is None else f"{v:.1f}" if '%' in row['label'] else f"{v:.2f}" for v in row["values"][:6]) + " |")
    if fq:
        ends = sorted(fq, reverse=True)[:6]
        out.append(f"\n## Key financials — single quarters ({ccy})"
                   + (" — derived from KAP's year-to-date filings" if bist_mkt else ""))
        out += _fig_table(fq, ends, (lambda e: f"{e[:4]}Q{(int(e[5:7]) + 2) // 3}") if bist_mkt else (lambda e: e[:7]))
    if hist and not bist_mkt and d["market"] == "US":
        try:
            sec = sec_key_table(d["symbol"], "annual", hist, periods=5)
        except Exception:
            sec = None
        if sec:
            out.append(f"\n## SEC EDGAR key lines as filed by {hist} (USD)")
            out.append("| Line | " + " | ".join(sec["columns"]) + " |")
            out.append("|---|" + "---|" * len(sec["columns"]))
            for row in sec["rows"]:
                out.append(f"| {row['label_en']} | " + " | ".join("n/a" if v is None else (_m(v) if row.get('unit') == 'USD' else f"{v:.2f}") for v in row["values"]) + " |")

    divs = _hist_filter(d.get("dividends") or [], hist)
    if divs:
        out.append("\n## Dividends (latest first, per share)")
        out.append("; ".join(f"{x['date']}: {x['amount']:.4g}" + (f" (gross {x['gross_rate']:.1f}% of nominal)" if x.get("gross_rate") else "")
                             for x in divs[:8] if x.get("amount") is not None))

    if not hist:
        own = d.get("ownership") or {}
        out.append("\n## Ownership")
        for s in own.get("summary") or []:
            val = (f"{s['value']:.2f}%" if s["unit"] == "%" else f"{s['value']:,.0f}" if s["unit"] == "n" and abs(s["value"]) < 1e5
                   else _m(s["value"]) + (" " + s["unit"][6:] if s["unit"].startswith("money:") else ""))
            out.append(f"- {_OWN_EN.get(s['label'], s['label'])}: {val} ({s['source']})")
        if own.get("major"):
            out.append(f"- Major shareholders ({'KAP: direct holders of 3% or more of capital or votes' if bist_mkt else 'Yahoo'}): " + "; ".join(
                f"{h['holder']} {h['pct']:.2f}%" for h in own["major"] if h.get("pct") is not None))
        if own.get("indirect"):
            out.append(f"- Indirect holders: {own['indirect'][:300]}")
        if own.get("institutional"):
            out.append("- Top institutions: " + "; ".join(
                f"{h['holder']} {h['pct']:.2f}%" + (f" ({h['change_pct']:+.1f}% q/q)" if h.get("change_pct") is not None else "")
                for h in own["institutional"][:8] if h.get("pct") is not None))
        if own.get("funds"):
            out.append("- Top funds: " + "; ".join(f"{h['holder']} {h['pct']:.2f}%" for h in own["funds"][:5] if h.get("pct") is not None))

    ins = d.get("insiders") or {}
    if (ins.get("summary") or ins.get("transactions")) and not hist:
        out.append("\n## Insider activity")
        for s in ins.get("summary") or []:
            lab, sh = s.get("label"), _f(s.get("shares"))
            if lab and sh is not None:
                amount = f"{sh * 100:.2f}%" if lab.startswith("%") else f"{sh:,.0f} shares"
                out.append(f"- {lab} (last 6 months): {amount}" + (f" in {s['count']} trades" if s.get("count") else ""))
        for t in (ins.get("transactions") or [])[:10]:
            sh = "" if _f(t.get("shares")) is None else f" {_f(t['shares']):,.0f} sh"
            val = "" if not _f(t.get("value")) else f", {_m(t['value'])}"
            out.append(f"- {t.get('date')}: {t.get('insider')} ({t.get('position')}) — {t.get('text') or ''}{sh}{val}")
    kap_ins = _hist_filter(ins.get("filings") or [], hist)
    if kap_ins:
        out.append(f"\n## Insider / buy-back filings ({'KAP' if bist_mkt else 'SEC Form 4'}, latest first)")
        out += [f"- {f.get('date')}: {f.get('title') or f.get('form')}" for f in kap_ins[:10]]

    if not hist:
        mg = d.get("management") or {}
        if mg.get("board"):
            out.append("\n## Board (KAP)")
            out += [f"- {b['name']} — {b.get('title') or ''}{'; ' + b['executive'] if b.get('executive') else ''}"
                    f"{'; ' + b['independent'] if b.get('independent') else ''}{'; since ' + b['since'] if b.get('since') else ''}"
                    for b in mg["board"][:12]]
        if mg.get("executives"):
            out.append("\n## Management (KAP)")
            out += [f"- {m['name']} — {m.get('title') or ''}" for m in mg["executives"][:10]]
        elif mg.get("officers"):
            out.append("\n## Officers")
            out += [f"- {o.get('name')} — {o.get('title')}" + (f" (pay {_m(o['pay'])})" if o.get("pay") else "") for o in mg["officers"][:8]]
        if d.get("subsidiaries"):
            out.append("\n## Subsidiaries (KAP)")
            out += [f"- {s['name']} — {s.get('activity') or ''}" for s in d["subsidiaries"][:10]]

    filings = _hist_filter(d.get("filings") or [], hist)
    if filings:
        out.append(f"\n## Recent filings ({'KAP disclosures' if bist_mkt else 'SEC EDGAR'}, latest first)")
        out += [f"- {f.get('date')}: {f.get('form') + ' — ' if f.get('form') else ''}{f.get('title')}" for f in filings[:15]]

    if not hist:
        cal = d.get("calendar") or {}
        if cal.get("expected"):
            out.append("\n## Expected KAP filings")
            out += [f"- {c.get('subject')} ({c.get('period')} {c.get('year')}): {c.get('start')} – {c.get('end')}" for c in cal["expected"][:5]]
        if cal.get("earnings"):
            up = [e for e in cal["earnings"] if e.get("eps_reported") is None][:2]
            past = [e for e in cal["earnings"] if e.get("eps_reported") is not None][:4]
            if up or past:
                out.append("\n## Earnings dates")
                out += [f"- Next: {e['date']} (EPS est. {e.get('eps_estimate')})" for e in up]
                out += [f"- {e['date']}: EPS {e.get('eps_reported')} vs est. {e.get('eps_estimate')} (surprise {e.get('surprise_pct')}%)" for e in past]
        an = d.get("analyst") or {}
        if an:
            out.append("\n## Analyst consensus")
            out.append(", ".join(f"{k} {v}" for k, v in an.items() if k not in ("source", "currency") and v is not None)
                       + f" ({an.get('source')}, {an.get('currency')})")
    notes = list(d.get("notes_en") or d.get("notes") or [])
    if notes:
        out.append("\n## Notes")
        out += [f"- {n}" for n in notes]
    missing = [f"{s['label']} ({s['note']})" for s in d.get("sources", []) if s["state"] == "error"]
    if missing:
        out.append("- Unavailable this time: " + "; ".join(missing))
    return "\n".join(out) + "\n"
