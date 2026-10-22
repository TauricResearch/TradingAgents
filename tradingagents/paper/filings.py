"""Optional SEC primary-source metadata and tagged-facts collector.

No made-up CIK, filings or financial amounts. With no identifiable SEC User-Agent
it performs ZERO HTTP requests and gives a conspicuous incomplete-evidence
result. Values are explicit official XBRL entries with periods, forms, units and
dates; NOT automatically TTM or audited reconciliations.

A contemporary SEC snapshot is NOT safe for arbitrary historical backtests.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timezone
from urllib.request import Request, urlopen

_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_SYMBOL = re.compile(r"^[A-Z]{1,5}(?:[.-][A-Z])?$")
_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K", "8-K"}
_FACT_NAMES = {
    "filed_cash_usd": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "filed_revenue_usd": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "filed_net_income_usd": ["NetIncomeLoss"],
    "filed_operating_cash_usd": ["NetCashProvidedByUsedInOperatingActivities"],
    "filed_capex_usd": ["PaymentsToAcquirePropertyPlantAndEquipment"],
}


def _missing(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail, "filings": [], "financial_facts": {},
            "source_url": "https://www.sec.gov/edgar/search/", "data_asof_utc": None}


def parse_filings(cik: int, data: dict, *, asof: date, limit: int = 4) -> list[dict]:
    """Accept only dated, well-formed SEC references, newest first."""
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    acc = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    reports = recent.get("reportDate") or []
    docs = recent.get("primaryDocument") or []
    length = min(len(forms), len(acc), len(dates), len(docs))
    result = []
    for i in range(length):
        if forms[i] not in _FORMS:
            continue
        try:
            submitted = date.fromisoformat(dates[i])
        except (TypeError, ValueError):
            continue
        if submitted > asof:
            continue
        code = str(acc[i])
        doc = str(docs[i])
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", code):
            continue
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", doc):
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{code.replace('-', '')}/{doc}"
        result.append({"form": forms[i], "filed": dates[i],
                       "period_end": str(reports[i]) if i < len(reports) else None,
                       "accession": code, "url": base})
        if len(result) >= limit:
            break
    return result


def parse_facts(data: dict, *, asof: date) -> dict:
    """Extract labelled filed facts with explicit windows, never infer TTM."""
    usgaap = (data.get("facts") or {}).get("us-gaap") or {}
    output = {}
    for label, candidates in _FACT_NAMES.items():
        for tag in candidates:
            units = ((usgaap.get(tag) or {}).get("units") or {}).get("USD") or []
            eligible = []
            for item in units:
                try:
                    submitted = date.fromisoformat(item["filed"])
                    ended = date.fromisoformat(item["end"])
                    amount = float(item["val"])
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
                if submitted > asof or ended > asof or not (-1e16 < amount < 1e16):
                    continue
                if item.get("form") not in {"10-K", "10-Q", "20-F", "40-F"}:
                    continue
                start = item.get("start")
                if start:
                    try:
                        days = (ended - date.fromisoformat(start)).days
                    except ValueError:
                        continue
                    if days < 70 or days > 380:
                        continue
                eligible.append((ended, submitted, item))
            if eligible:
                _, _, best = max(eligible, key=lambda z: (z[0], z[1]))
                output[label] = {"value_usd": round(float(best["val"]), 2),
                                 "form": best["form"], "filed": best["filed"],
                                 "period_start": best.get("start"), "period_end": best["end"],
                                 "concept": f"us-gaap:{tag}", "unit": "USD",
                                 "limitation": "Tagged filed fact, not automatically a comparable TTM metric"}
                break
    return output


class SecEvidence:
    """Opt-in SEC evidence; preserves the original upstream data without rewrites."""

    def __init__(self, user_agent: str | None = None, *, timeout: int = 8):
        self.agent = (user_agent if user_agent is not None else os.environ.get("KORAL_SEC_USER_AGENT", "")).strip()
        self.timeout = timeout
        self._tickers: dict | None = None
        self._last_http: float = 0

    @property
    def enabled(self) -> bool:
        return len(self.agent) >= 12 and bool(re.search(r"\S+@\S+\.\S+", self.agent))

    def _get(self, url: str) -> dict:
        delay = 0.2 - (time.monotonic() - self._last_http)
        if delay > 0:
            time.sleep(delay)
        request = Request(url, headers={"User-Agent": self.agent, "Accept": "application/json"})
        self._last_http = time.monotonic()
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read(18_000_000)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("SEC response must be an object")
        return parsed

    def lookup(self, ticker: str) -> int | None:
        if not _SYMBOL.fullmatch(ticker):
            return None
        if self._tickers is None:
            obj = self._get(_TICKERS)
            self._tickers = {str(row.get("ticker", "")).upper(): int(row["cik_str"])
                             for row in obj.values() if isinstance(row, dict)
                             and str(row.get("cik_str", "")).isdigit()}
        return self._tickers.get(ticker)

    def collect(self, ticker: str, *, now: datetime | None = None) -> dict:
        """Never raises. Missing data is explicit rather than substituted."""
        if not self.enabled:
            return _missing("NOT_CONFIGURED", "Set KORAL_SEC_USER_AGENT with an identifiable contact email to enable SEC queries")
        now = now or datetime.now(timezone.utc)
        asof = now.date()
        try:
            cik = self.lookup(ticker)
            if cik is None:
                return _missing("CIK_UNRESOLVED", "Ticker not resolved in SEC's current association directory")
            submission = self._get(_SUBMISSIONS.format(cik=cik))
            filings = parse_filings(cik, submission, asof=asof)
            if not filings:
                return _missing("NO_RECENT_FILINGS", "No usable SEC filing metadata available")
            facts = {}
            warning = "SEC metadata available; financial values may be missing or company-specific"
            try:
                facts = parse_facts(self._get(_FACTS.format(cik=cik)), asof=asof)
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError, KeyError):
                warning = "SEC filing metadata retrieved, but XBRL facts unavailable"
            return {"status": "AVAILABLE", "detail": warning,
                    "cik": cik, "company_name": str(submission.get("name", ""))[:150],
                    "filings": filings, "financial_facts": facts,
                    "source_url": _SUBMISSIONS.format(cik=cik),
                    "data_asof_utc": now.isoformat(timespec="seconds"),
                    "limitation": "Official filing/index metadata and XBRL tags do NOT verify all vendor financial figures or establish point-in-time backtest suitability"}
        except (OSError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return _missing("FETCH_FAILED", f"SEC retrieval unavailable ({type(exc).__name__}); no facts inferred")
