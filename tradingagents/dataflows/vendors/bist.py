"""Borsa Istanbul companies: statements from Is Yatirim, company records from KAP.

Why these sources rather than Yahoo for a ``.IS`` symbol: Yahoo often keeps a
Turkish company's statements in the currency the group reports in (Turkish
Airlines: USD) while the quote is in TRY, so its price-to-book and EV/EBITDA
mix two currencies and come out meaningless (THYAO.IS: P/B 19, EV/EBITDA 222,
against 0.4 and 6 in TRY). Is Yatirim serves the statements every BIST company
files to KAP, in TRY, ten years and more back; KAP itself (the Public Disclosure
Platform) is the official record of the board, management, the shareholders
holding 5% or more, the free float and every disclosure.

- Is Yatirim ``MaliTablo``: balance sheet, income statement and cash flow, four
  periods per request, each line with a stable item code (labels repeat: there
  is a "Financial Loans" line under both short and long-term liabilities).
  Industrial companies file the XI_29 layout, banks the UFRS one. Interim
  periods are cumulative from the start of the fiscal year (6M, 9M), as KAP
  filings are; single quarters are derived by difference where both are filed.
- KAP company page: the record is embedded in the page as JSON items
  (``itemObject``), one per field, parsed by key rather than by layout.
- borsapy (Apache-2.0) is the client for both, for its sessions and headers.
  It is an optional dependency: without it this vendor reports itself as not
  configured and the router moves on.

Point in time: KAP stamps every filing, but the statement API reports periods,
not filing dates. A run dated in the past is served only periods whose
statutory filing deadline (70 days for interim, 100 for annual reports, with a
margin for the extensions SPK has granted) had passed by its date.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from typing import Any

from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError, VendorUnavailableError

logger = logging.getLogger(__name__)

# Days after a period's end by which its statements must be on KAP (SPK II-14.1:
# 60 days for consolidated interim, 70 for annual, extended in some years).
INTERIM_LAG_DAYS = 70
ANNUAL_LAG_DAYS = 100

_GROUPS = ("XI_29", "UFRS")   # industrial layout, bank layout
_PER_CALL = 4                 # Is Yatirim answers four periods per request


def is_bist(symbol: str) -> bool:
    s = (symbol or "").strip().upper()
    return s.endswith(".IS") or s.endswith(".E")


def bist_code(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    for suffix in (".IS", ".E"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


def _borsapy():
    try:
        import borsapy  # noqa: F401
        return borsapy
    except ImportError as exc:
        raise VendorNotConfiguredError("borsapy is not installed (pip install borsapy)") from exc


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None   # NaN is no value


def _tr_num(text) -> float | None:
    """A number as KAP writes it: '1.380.000.000,00', '49,12'."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace("%", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- Is Yatirim statements


def _period_end(year: int, month: int) -> str:
    last = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return f"{year:04d}-{month:02d}-{last:02d}"


def _periods(quarterly: bool, count: int) -> list[tuple[int, int]]:
    today = date.today()
    if quarterly:
        month = (today.month - 1) // 3 * 3          # last quarter that has ended
        year = today.year
        if month == 0:
            year, month = year - 1, 12
        out = []
        for _ in range(count):
            out.append((year, month))
            month -= 3
            if month <= 0:
                year, month = year - 1, 12
        return out
    return [(today.year - 1 - i, 12) for i in range(count)]


def _fetch_raw(code: str, group: str, periods: list[tuple[int, int]]) -> list[dict]:
    """Every line Is Yatirim has for ``periods``: [{code, tr, en, values: [...]}]."""
    _borsapy()
    from borsapy._providers.isyatirim import get_isyatirim_provider

    provider = get_isyatirim_provider()
    lines: dict[str, dict] = {}
    order: list[str] = []
    for start in range(0, len(periods), _PER_CALL):
        batch = periods[start : start + _PER_CALL]
        padded = batch + [batch[-1]] * (_PER_CALL - len(batch))   # it answers only full requests
        params: dict[str, Any] = {"companyCode": code, "exchange": "TRY", "financialGroup": group}
        for i, (year, month) in enumerate(padded, 1):
            params[f"year{i}"], params[f"period{i}"] = year, month
        try:
            data = provider._get(f"{provider.BASE_URL}/Data.aspx/MaliTablo", params=params).json()
        except Exception as exc:  # network, JSON
            if not lines:
                raise VendorUnavailableError(f"Is Yatirim request failed ({type(exc).__name__})") from exc
            break
        for item in (data or {}).get("value") or []:
            key = str(item.get("itemCode") or "")
            if not key:
                continue
            if key not in lines:
                lines[key] = {"code": key, "tr": (item.get("itemDescTr") or "").rstrip(),
                              "en": (item.get("itemDescEng") or "").strip() or None, "values": {}}
                order.append(key)
            for i, period in enumerate(batch, 1):
                lines[key]["values"][period] = _num(item.get(f"value{i}"))
    return [lines[k] for k in order]


def _kind(code: str) -> str | None:
    return {"1": "balance", "2": "balance", "3": "income", "4": "cashflow"}.get(code[:1])


def _level(label: str) -> int:
    lead = len(label) - len(label.lstrip(" "))
    return 0 if lead == 0 else 1 if lead <= 2 else 2


def statements(symbol: str, quarterly: bool, count: int) -> dict:
    """Statements as filed, by kind: {group, periods, tables: {balance, income, cashflow}}.

    Columns run newest first; a period with no figure in any line (not filed yet)
    is dropped.
    """
    code = bist_code(symbol)
    periods = _periods(quarterly, count)
    lines: list[dict] = []
    group = None
    for candidate in _GROUPS:
        lines = _fetch_raw(code, candidate, periods)
        if any(v for line in lines for v in line["values"].values()):
            group = candidate
            break
    if group is None:
        raise NoMarketDataError(symbol, code, "Is Yatirim has no statements for this company")
    filed = [p for p in periods if any(line["values"].get(p) for line in lines)]
    tables: dict[str, dict] = {}
    for kind in ("balance", "income", "cashflow"):
        rows = []
        for line in lines:
            if _kind(line["code"]) != kind:
                continue
            values = [line["values"].get(p) for p in filed]
            rows.append({"code": line["code"], "label": line["tr"].strip(), "label_en": line["en"],
                         "level": _level(line["tr"]), "values": values})
        tables[kind] = {
            "columns": [f"{y}/{m:02d}" if quarterly else str(y) for y, m in filed],
            "period_ends": [_period_end(y, m) for y, m in filed],
            "months": [m for _, m in filed],
            "rows": rows,
        }
    return {"group": group, "tables": tables, "currency": "TRY"}


def discrete_quarters(table: dict) -> dict:
    """Single quarters from year-to-date columns: 9M minus 6M is the third quarter.

    A quarter whose preceding cumulative period is missing is left empty rather
    than shown as a nine-month figure under a quarter's name.
    """
    ends = table["period_ends"]
    months = table.get("months") or [int(e[5:7]) for e in ends]
    index = {e: i for i, e in enumerate(ends)}
    out_rows = []
    for row in table["rows"]:
        values = []
        for i, end in enumerate(ends):
            v = row["values"][i]
            if months[i] == 3 or v is None:
                values.append(v)
                continue
            prev_end = _period_end(int(end[:4]), months[i] - 3)
            j = index.get(prev_end)
            prev = row["values"][j] if j is not None else None
            values.append(None if prev is None else v - prev)
        out_rows.append({**row, "values": values})
    return {**table, "rows": out_rows}


def withhold_unfiled(table: dict, as_of_date: str | None, quarterly: bool) -> dict:
    """``table`` without the periods whose filing deadline falls after ``as_of_date``."""
    if not as_of_date:
        return table
    lag = INTERIM_LAG_DAYS if quarterly else ANNUAL_LAG_DAYS
    cutoff = date.fromisoformat(as_of_date[:10])
    keep = [i for i, end in enumerate(table["period_ends"])
            if (cutoff - date.fromisoformat(end)).days >= (ANNUAL_LAG_DAYS if end[5:7] == "12" else lag)]
    pick = lambda seq: [seq[i] for i in keep]  # noqa: E731
    return {**table, "columns": pick(table["columns"]), "period_ends": pick(table["period_ends"]),
            "months": pick(table.get("months") or []) if table.get("months") else None,
            "rows": [{**r, "values": pick(r["values"])} for r in table["rows"]]}


# ---------------------------------------------------------------- Is Yatirim / borsapy extras


def market_metrics(symbol: str) -> dict:
    """Market cap, F/K, PD/DD, FD/FAVOK, net debt, free float and foreign share (Is Yatirim)."""
    _borsapy()
    from borsapy._providers.isyatirim import get_isyatirim_provider

    try:
        metrics = get_isyatirim_provider().get_company_metrics(bist_code(symbol)) or {}
    except Exception as exc:
        raise VendorUnavailableError(f"Is Yatirim metrics failed ({type(exc).__name__})") from exc
    return {k: v for k, v in metrics.items() if v is not None}


def quote(symbol: str) -> dict:
    bp = _borsapy()
    try:
        info = bp.Ticker(bist_code(symbol)).fast_info
        last = _num(getattr(info, "last_price", None))
        return {"last": last, "currency": "TRY"} if last else {}
    except Exception:
        return {}


def dividends(symbol: str) -> list[dict]:
    bp = _borsapy()
    try:
        df = bp.Ticker(bist_code(symbol)).dividends
    except Exception as exc:
        raise VendorUnavailableError(f"Is Yatirim dividends failed ({type(exc).__name__})") from exc
    out = []
    if df is None or df.empty:
        return out
    for idx, row in df.iterrows():
        out.append({"date": str(idx)[:10], "amount": _num(row.get("Amount")),
                    "gross_rate": _num(row.get("GrossRate")), "net_rate": _num(row.get("NetRate")),
                    "total": _num(row.get("TotalDividend"))})
    return sorted(out, key=lambda d: d["date"], reverse=True)


def analyst_view(symbol: str) -> dict:
    bp = _borsapy()
    t = bp.Ticker(bist_code(symbol))
    out: dict[str, Any] = {}
    try:
        targets = t.analyst_price_targets or {}
        out.update({k: targets.get(k) for k in ("low", "high", "mean", "median") if targets.get(k)})
        if targets.get("numberOfAnalysts"):
            out["count"] = targets["numberOfAnalysts"]
    except Exception:
        pass
    try:
        rec = t.recommendations_summary or {}
        if any(rec.values()):
            out["recommendations"] = rec
    except Exception:
        pass
    if out:
        out["source"] = "hedeffiyat.com.tr (borsapy)"
    return out


def earnings_calendar(symbol: str) -> list[dict]:
    """Disclosures KAP expects from the company: the next financial reports and their windows."""
    _borsapy()
    from borsapy._providers.kap import get_kap_provider

    try:
        df = get_kap_provider().get_calendar(bist_code(symbol))
    except Exception:
        return []
    if df is None or df.empty:
        return []
    return [{"start": _kap_date(r.get("StartDate")), "end": _kap_date(r.get("EndDate")),
             "subject": r.get("Subject"), "period": r.get("Period"), "year": r.get("Year")}
            for _, r in df.head(12).iterrows()]


def _kap_date(text) -> str | None:
    """'19.11.2026 23:33:44' or '20/11/2026' or '20210326000000' -> ISO."""
    if not text:
        return None
    s = str(text).strip()
    for fmt, n in (("%d.%m.%Y %H:%M:%S", 19), ("%d.%m.%Y", 10), ("%d/%m/%Y %H:%M:%S", 19), ("%d/%m/%Y", 10)):
        try:
            dt = datetime.strptime(s[:n], fmt)
            return dt.strftime("%Y-%m-%d %H:%M" if n == 19 else "%Y-%m-%d")
        except ValueError:
            continue
    if re.fullmatch(r"\d{8}(\d{6})?", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


# ---------------------------------------------------------------- KAP


def disclosures(symbol: str, limit: int = 60) -> list[dict]:
    """The company's latest KAP disclosures, newest first: date, title, link."""
    _borsapy()
    from borsapy._providers.kap import get_kap_provider

    try:
        df = get_kap_provider().get_disclosures(bist_code(symbol), limit=limit)
    except Exception as exc:
        raise VendorUnavailableError(f"KAP disclosures failed ({type(exc).__name__})") from exc
    if df is None or df.empty:
        return []
    return [{"date": _kap_date(r.get("Date")), "title": str(r.get("Title") or "").strip(), "url": r.get("URL")}
            for _, r in df.iterrows()]


_INSIDER_TITLES = ("pay alım satım", "pay alim satim", "geri alım", "geri alim")


def insider_disclosures(items: list[dict]) -> list[dict]:
    """Trades by insiders and buy-backs, as KAP titles them."""
    return [d for d in items if any(t in (d.get("title") or "").lower() for t in _INSIDER_TITLES)]


def _kap_items(html: str) -> dict[str, dict]:
    """The JSON record items embedded in a KAP company page, by item key."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', html, re.S)
    text = "".join(json.loads(c) for c in chunks) if chunks else html
    decoder, out = json.JSONDecoder(), {}
    for m in re.finditer(r'"itemObject":\s*', text):
        try:
            obj, _ = decoder.raw_decode(text, m.end())
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("itemKey") and obj["itemKey"] not in out:
            out[obj["itemKey"]] = obj
    return out


def _txt(v) -> str | None:
    if isinstance(v, dict):
        v = v.get("text")
    if v is None:
        return None
    s = re.sub(r"<[^>]+>", " ", str(v))
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def kap_company(symbol: str) -> dict:
    """The company's KAP record: profile, board, management, shareholders, free float, subsidiaries."""
    _borsapy()
    from borsapy._providers.kap import get_kap_provider

    kap = get_kap_provider()
    code = bist_code(symbol)
    try:
        oid = kap.get_member_oid(code)
    except Exception as exc:
        raise VendorUnavailableError(f"KAP lookup failed ({type(exc).__name__})") from exc
    if not oid:
        raise NoMarketDataError(symbol, code, "not a KAP member")
    try:
        response = kap._client.get(f"{kap.COMPANY_GENERAL_URL}/{oid}", timeout=25)
        response.raise_for_status()
    except Exception as exc:
        raise VendorUnavailableError(f"KAP company page failed ({type(exc).__name__})") from exc
    items = _kap_items(response.text)
    if not items:
        raise VendorUnavailableError("KAP company page had no readable record")

    def value(suffix):
        for key, obj in items.items():
            if key.endswith(suffix):
                return obj.get("value")
        return None

    def first(suffix):
        v = value(suffix)
        return v if isinstance(v, list) else []

    board = [{"name": _txt(m.get("nameSurname")), "title": _txt(m.get("title")),
              "profession": _txt(m.get("profession")),
              "executive": _txt(m.get("executiveOrNon")),
              "independent": _txt(m.get("independentBoardMemberOrNot")),
              "since": _kap_date(m.get("firstChosenDate")),
              "committees": _txt(m.get("committeesChargedAndTask")),
              "outside_roles": _txt(m.get("currentPositionsHeldOutsideTheCompany")),
              "share_pct": _tr_num(m.get("shareInCapital")) if m.get("shareInCapital") not in (None, "0") else None}
             for m in first("_yonetim_kurulu_uyeleri")]
    management = [{"name": _txt(m.get("nameSurname")), "title": _txt(m.get("title")),
                   "profession": _txt(m.get("profession"))}
                  for m in first("_yonetimde_soz_sahibi")]
    holders = []
    for h in first("_sermayede_dogrudan"):
        name = _txt(h.get("shareholder"))
        if not name or name.upper() == "TOPLAM":
            continue
        holders.append({"holder": name, "pct": _tr_num(h.get("ratioInCapital")),
                        "voting_pct": _tr_num(h.get("votingRightRatio")),
                        "capital": _tr_num(h.get("shareInCapital"))})
    float_rows = first("_fiili_dolasimdaki_pay")
    free_float = None
    if float_rows:
        f = float_rows[0]
        free_float = {"pct": _tr_num(f.get("actualOutstandingSharesRatio")),
                      "shares": _tr_num(f.get("actualSharesOutstanding")),
                      "total_shares": _tr_num(f.get("totalShares")),
                      "date": _kap_date(f.get("creationDate"))}
    subsidiaries = [{"name": _txt(s.get("companyTitle")), "activity": _txt(s.get("scopeOfActivitiesOfCompany")),
                     "capital": _tr_num(s.get("paidInOrIssuedCapital")),
                     "share": _tr_num(s.get("capitalShareOfCompany")),
                     "share_pct": _tr_num(s.get("shareRatioOfCompanyInCapital") or s.get("capitalShareRatio")),
                     "currency": _txt(s.get("monetaryUnit") or s.get("currency"))}
                    for s in first("_bagli_ortakliklar") if _txt(s.get("companyTitle"))]
    share_groups = [{"group": _txt(g.get("shareGroup")), "privileged": _txt(g.get("privilegedOrNot") or g.get("privilege")),
                     "nominal": _tr_num(g.get("nominalValueOfShares")), "pct": _tr_num(g.get("ratioOfShares") or g.get("shareRatio"))}
                    for g in first("_sermayeyi_temsil_eden")]
    indirect = value("_son_durum_sermayeye")
    return {
        "oid": oid,
        "url": f"https://www.kap.org.tr/tr/sirket-bilgileri/genel/{oid}",
        "profile": {
            "sector": _txt(value("_sektor")),
            "activity": _txt(value("_faaliyet_konu")),
            "market": _txt(value("_sermaye_arac_pazar")),
            "indices": [s.strip() for s in (_txt(value("_endeksler")) or "").split("/") if s.strip()],
            "auditor": _txt(value("_bdk")),
            "address": _txt(value("_merkez_adresi")),
            "website": _txt(value("_int_addres")),
            "registered": _kap_date(value("_tescil_tarihi")),
            "paid_capital": _tr_num(value("_odenmis_sermaye")),
            "authorized_capital": _tr_num(value("_kayitli_sermaye_tavani")),
        },
        "board": [b for b in board if b["name"]],
        "management": [m for m in management if m["name"]],
        "holders": holders,
        "indirect_holders": _txt(indirect) if not isinstance(indirect, list) else
            "; ".join(filter(None, (_txt(i.get("shareholder") or i.get("nameSurname")) for i in indirect))),
        "free_float": free_float,
        "subsidiaries": subsidiaries,
        "share_groups": [g for g in share_groups if g["group"]],
        "fetched": time.strftime("%Y-%m-%d"),
    }


# ---------------------------------------------------------------- router entry points


def _csv(symbol: str, kind: str, freq: str, as_of_date: str | None, title: str) -> str:
    if not is_bist(symbol):
        raise NoMarketDataError(symbol, symbol, "not a Borsa Istanbul symbol")
    quarterly = (freq or "").lower() == "quarterly"
    data = statements(symbol, quarterly, 9 if quarterly else 6)
    table = data["tables"][kind]
    if quarterly and kind in ("income", "cashflow"):
        table = discrete_quarters(table)
    if quarterly and len(table["columns"]) > 8:   # the ninth quarter was fetched only to difference the eighth
        table = {**table, "columns": table["columns"][:8], "period_ends": table["period_ends"][:8],
                 "months": (table.get("months") or [])[:8], "rows": [{**r, "values": r["values"][:8]} for r in table["rows"]]}
    from tradingagents.dataflows.date_window import is_historical
    if is_historical(as_of_date):
        table = withhold_unfiled(table, as_of_date, quarterly)
    if not table["columns"]:
        raise NoMarketDataError(symbol, bist_code(symbol), f"no {freq} {title.lower()} filed by {as_of_date}")
    head = (f"# {title} for {symbol.upper()} ({freq}), TRY millions; Is Yatirim / KAP filings "
            f"({'bank layout' if data['group'] == 'UFRS' else 'industrial layout'})\n")
    if quarterly and kind in ("income", "cashflow"):
        head += "# Single quarters: year-to-date filings differenced (9M - 6M); an empty cell has no prior filing to difference\n"
    if as_of_date and is_historical(as_of_date):
        head += f"# Only periods whose KAP filing deadline had passed by {as_of_date}\n"
    head += "# Figures under TMS 29 (inflation accounting, from 2023) are restated in later purchasing power\n\n"
    lines = ["Line," + ",".join(table["columns"])]
    for row in table["rows"]:
        if all(v in (None, 0) for v in row["values"]):
            continue
        label = (row.get("label_en") or row["label"]).replace(",", " ")
        cells = ["" if v is None else f"{v / 1e6:.0f}" if abs(v) >= 1e5 else f"{v:.2f}" for v in row["values"]]
        lines.append(("  " * row["level"]) + label + "," + ",".join(cells))
    return head + "\n".join(lines) + "\n"


def get_balance_sheet(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Balance sheet as filed to KAP, from Is Yatirim (Borsa Istanbul only)."""
    return _csv(ticker, "balance", freq, as_of_date, "Balance Sheet")


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Income statement as filed to KAP, from Is Yatirim (Borsa Istanbul only)."""
    return _csv(ticker, "income", freq, as_of_date, "Income Statement")


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str | None = None) -> str:
    """Cash flow statement as filed to KAP, from Is Yatirim (Borsa Istanbul only)."""
    return _csv(ticker, "cashflow", freq, as_of_date, "Cash Flow Statement")


def get_fundamentals(ticker: str, as_of_date: str | None = None) -> str:
    """The company dossier for a Borsa Istanbul symbol: ratios, ownership, board, KAP filings."""
    if not is_bist(ticker):
        raise NoMarketDataError(ticker, ticker, "not a Borsa Istanbul symbol")
    from tradingagents.dataflows.company_data import dossier_report

    return dossier_report(ticker, as_of_date)
