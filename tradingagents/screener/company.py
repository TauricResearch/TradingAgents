"""One security's inputs to the metrics, read point in time from the India database.

``load_company`` reads a security as known on a day: the filings filed by then
(``india.statements``), prices up to then adjusted for the splits, bonuses and
rights in force by then, the shareholding patterns filed by then and the
corporate actions known by then. ``Company`` then works out, once each, the
periods and series the metrics read: the latest fiscal year, the trailing
twelve months, the latest quarter, the price on the day, the share count.

Shares outstanding, for market capitalisation, come from the newest of three
sources, best first:

1. NSE's issued-share count from the daily PR (mcap) file, the exchange's own
   figure, recorded whenever it changes;
2. the latest shareholding pattern's total shares, as at its quarter end;
3. equity capital over face value from the latest year-end balance sheet.

Each is multiplied by the split and bonus factors whose ex-date falls after the
source's own date and on or before the day, so it counts today's shares. Rights
issues change the count by an amount no factor gives; the next source to report
after one picks it up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property

from tradingagents.dataflows import formulas as f
from tradingagents.dataflows.vendors.india import store
from tradingagents.dataflows.vendors.india.statements import Statements, load_statements

PRICE_STALE_DAYS = 15  # a stock with no close this close to the day has no price
PRICE_YEARS = 5  # the longest price horizon any metric reads


@dataclass
class Shares:
    count: float
    source: str  # "NSE PR (mcap)" | "shareholding pattern" | "balance sheet"
    date: str  # when the source counted them


@dataclass
class Company:
    """Everything one security's metrics read, as known on ``day``."""

    security: dict
    statements: Statements
    prices: list[dict]  # adjusted daily rows, oldest first, up to ``day``
    shareholding: list[dict]  # quarterly patterns, oldest first
    actions: list[dict]  # corporate actions known by ``day``
    day: date  # the snapshot's day: its as-of date, or the newest price day for a live one
    dividends_known: bool = False  # the actions sync covers the year to ``day``
    pr_shares: dict | None = None  # NSE's issued-share count in force on ``day``

    # --- The statements ------------------------------------------------------------
    @property
    def financial(self) -> bool:
        return self.statements.financial is True

    @property
    def quarterly(self):
        return self.statements.quarterly

    @property
    def annual(self):
        return self.statements.annual

    @property
    def balance(self):
        return self.statements.balance

    @property
    def cashflow(self):
        return self.statements.cashflow

    @cached_property
    def fy(self) -> dict:
        """The newest fiscal year's income statement."""
        return self.annual[max(self.annual)] if self.annual else {}

    @cached_property
    def bs_end(self) -> str | None:
        """The newest year-end balance sheet's date: the year the Company page's
        ratios and its ROCE and ROE are for."""
        return max(self.balance) if self.balance else None

    @property
    def bs(self) -> dict:
        return self.balance[self.bs_end] if self.bs_end else {}

    @property
    def bs_income(self) -> dict:
        """The income statement of the balance sheet's year (blank when not filed)."""
        return self.annual.get(self.bs_end, {}) if self.bs_end else {}

    @cached_property
    def cf(self) -> dict:
        return self.cashflow[max(self.cashflow)] if self.cashflow else {}

    @cached_property
    def trailing(self) -> dict | None:
        return f.trailing_year(self.quarterly, self.annual)

    @cached_property
    def q_end(self) -> str | None:
        return max(self.quarterly) if self.quarterly else None

    @property
    def q(self) -> dict:
        return self.quarterly[self.q_end] if self.q_end else {}

    def quarter_before(self, months: int) -> dict | None:
        """The quarter ending ``months`` before the latest one (within 20 days)."""
        if not self.q_end:
            return None
        target = f.months_before(date.fromisoformat(self.q_end), months)
        return next((p for end, p in self.quarterly.items()
                     if abs((date.fromisoformat(end) - target).days) <= 20), None)

    def annual_series(self, fn) -> list[tuple[date, float]]:
        return f.series(self.annual, fn)

    @cached_property
    def roe_series(self) -> list[float]:
        """ROE by fiscal year with a balance sheet, oldest first: the Company page's."""
        return [v for end in sorted(self.balance)
                if (v := f.as_number(f.roe(self.annual.get(end, {}), self.balance[end]))) is not None]

    @cached_property
    def roce_series(self) -> list[float]:
        return [v for end in sorted(self.balance)
                if (v := f.as_number(f.roce(self.annual.get(end, {}), self.balance[end]))) is not None]

    # --- Prices ---------------------------------------------------------------------
    @cached_property
    def dates(self) -> list[date]:
        return [date.fromisoformat(r["date"]) for r in self.prices]

    @cached_property
    def closes(self) -> list[float]:
        return [r["close"] for r in self.prices]

    @cached_property
    def price(self) -> float | None:
        """The last close, unless the stock has not traded for ``PRICE_STALE_DAYS``."""
        if not self.prices or (self.day - self.dates[-1]).days > PRICE_STALE_DAYS:
            return None
        return self.closes[-1]

    @property
    def price_day(self) -> date | None:
        return self.dates[-1] if self.price is not None else None

    def close_ago(self, *, months: int = 0, years: int = 0) -> float | None:
        if self.price is None:
            return None
        last = self.dates[-1]
        target = f.years_before(last, years) if years else f.months_before(last, months)
        return f.close_before(self.dates, self.closes, target)

    def window(self, *, months: int = 0, years: int = 0) -> list[dict]:
        """Price rows after the same day ``months`` or ``years`` before the last one."""
        if self.price is None:
            return []
        memo = self.__dict__.setdefault("_windows", {})
        if (months, years) not in memo:
            last = self.dates[-1]
            start = f.years_before(last, years) if years else f.months_before(last, months)
            memo[months, years] = [r for r, d in zip(self.prices, self.dates, strict=True) if d > start]
        return memo[months, years]

    # --- Shares and dividends ---------------------------------------------------------
    def factor_between(self, after: str, until: date) -> float:
        """The product of the split and bonus factors (share-count multipliers) with an
        ex-date after ``after`` and on or before ``until``."""
        product = 1.0
        for a in self.actions:
            if a["type"] in ("split", "bonus") and a["factor"] and after < a["ex_date"] <= until.isoformat():
                product *= a["factor"]
        return product

    @cached_property
    def shares(self) -> Shares | None:
        candidates = []
        if self.pr_shares and self.pr_shares.get("shares"):
            candidates.append(Shares(float(self.pr_shares["shares"]), "NSE PR (mcap)", self.pr_shares["date"]))
        held = [r for r in self.shareholding if r.get("total_shares")]
        if held:
            candidates.append(Shares(float(held[-1]["total_shares"]), "shareholding pattern",
                                     held[-1]["quarter_end"]))
        counted = [e for e in sorted(self.balance) if self.balance[e].get("shares")]
        if counted:
            candidates.append(Shares(self.balance[counted[-1]]["shares"], "balance sheet", counted[-1]))
        if not candidates:
            return None
        best = candidates[0]
        return Shares(best.count * self.factor_between(best.date, self.day), best.source, best.date)

    @cached_property
    def market_cap(self) -> float | None:
        """In rupees."""
        if self.price is None or self.shares is None:
            return None
        return self.price * self.shares.count

    @cached_property
    def dividends_ttm(self) -> float | None:
        """Dividends per share with an ex-date in the year to ``day``, restated to
        today's share count; 0 when none was paid, None when the actions sync does
        not cover the year or a dividend's amount could not be read."""
        if not self.dividends_known:
            return None
        start = (self.day - timedelta(days=365)).isoformat()
        end = self.day.isoformat()
        seen, total = set(), 0.0
        for a in self.actions:
            if a["type"] != "dividend" or not start < a["ex_date"] <= end:
                continue
            if a["amount"] is None:
                return None
            key = (a["ex_date"], round(a["amount"], 4))
            if key in seen:  # the same dividend listed under two spellings of its purpose
                continue
            seen.add(key)
            total += a["amount"] / self.factor_between(a["ex_date"], self.day)
        return total

    # --- Shareholding -----------------------------------------------------------------
    @property
    def holding(self) -> dict | None:
        return self.shareholding[-1] if self.shareholding else None

    def holding_before(self, months: int) -> dict | None:
        """The pattern for the quarter ending ``months`` before the latest one (within 20 days)."""
        if not self.shareholding:
            return None
        target = f.months_before(date.fromisoformat(self.shareholding[-1]["quarter_end"]), months)
        return next((r for r in reversed(self.shareholding[:-1])
                     if abs((date.fromisoformat(r["quarter_end"]) - target).days) <= 20), None)


def dividends_covered(conn, day: date) -> bool:
    """Whether the corporate-actions sync has (nearly) every weekday of the year to
    ``day``, so a stock with no dividend in it truly paid none."""
    start = day - timedelta(days=365)
    expected = len(store.trading_days(start + timedelta(days=1), day))
    row = conn.execute("SELECT COUNT(*) FROM ingest_log WHERE job='actions' AND status IN ('ok','missing') "
                       "AND key > ? AND key <= ?", (start.isoformat(), day.isoformat())).fetchone()
    return expected > 0 and row[0] >= 0.95 * expected


def load_company(conn, security: dict, day: date, *, as_of=None, dividends_known: bool = False) -> Company:
    """``security`` as known on ``day``. ``as_of`` is the point-in-time cut (None for a
    live snapshot, which reads everything filed and ``day`` = the newest price day)."""
    isin = security["isin"]
    start = (f.years_before(day, PRICE_YEARS) - timedelta(days=20)).isoformat()
    cut = as_of if as_of is not None else day
    return Company(
        security=security,
        statements=load_statements(conn, security, as_of=as_of),
        prices=store.get_prices(isin, start=start, end=day.isoformat(), as_of=as_of, conn=conn),
        shareholding=store.get_shareholding(isin, as_of=as_of, conn=conn),
        actions=store.get_corporate_actions(isin, as_of=as_of, conn=conn),
        day=day,
        dividends_known=dividends_known,
        pr_shares=store.get_shares_outstanding(isin, as_of=cut, conn=conn),
    )
