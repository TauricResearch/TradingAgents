"""One company's filed statements, shaped the way the formulas read them.

The financials table is long and narrow (a row per period, field and vintage);
the formulas in ``dataflows.formulas`` read a statement as ``{period end:
{field: value}}``. This module turns one into the other, point in time:

- ``as_of`` sees only rows filed by then (``store.get_financials``), and for each
  period and field the latest of those, so a restatement counts from its own
  filing time and never earlier.
- Per-share figures (EPS) are restated to the share count in force at ``as_of``:
  divided by the splits and bonuses whose ex-date is after the figure was filed
  and on or before ``as_of``.
- One basis is read: the one asked for when it was filed, else consolidated,
  else standalone. Two bases are never mixed in one statement.

The Company page (``profile``) reads it with no ``as_of``: the latest of
everything. The screener's snapshot reads it at each snapshot date. Both then run
the same formulas on the same figures, which is what keeps a stock's ROCE the
same number on both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from tradingagents.dataflows.field_aliases import ALIASES
from tradingagents.dataflows.formulas import Statement
from tradingagents.dataflows.vendors.india import store

INCOME = set(ALIASES["xbrl"]["income"]) | {"total_expenses", "net_interest_income", "sales"}
BALANCE = set(ALIASES["xbrl"]["balance"])
CASHFLOW = set(ALIASES["xbrl"]["cashflow"]) | {"free_cash_flow"}
PER_SHARE = {"eps", "eps_basic"}


@dataclass
class Statements:
    """One basis of one company's filings, as known at ``as_of``."""

    basis: str
    bases: list[str]  # every basis filed, consolidated first
    quarterly: Statement = field(default_factory=dict)  # income statement by quarter end
    annual: Statement = field(default_factory=dict)  # income statement by fiscal year end
    balance: Statement = field(default_factory=dict)  # fiscal year-end balance sheets
    cashflow: Statement = field(default_factory=dict)  # fiscal years with an operating cash flow
    financial: bool | None = None  # a bank or NBFC filing format; None without results filings
    events: list[dict] = field(default_factory=list)  # splits, bonuses, rights in force by as_of
    filings: list[dict] = field(default_factory=list)  # the results and shareholding filings seen

    @property
    def empty(self) -> bool:
        return not (self.quarterly or self.annual or self.balance or self.cashflow)


def load_statements(conn, security: dict, basis: str | None = None, as_of=None) -> Statements:
    """The quarterly and annual income statements, year-end balance sheets and cash
    flows of ``security`` (a securities row), in rupees, as filed by ``as_of``."""
    isin = security["isin"]
    limit = store.cutoff(as_of)
    rows = store.get_financials(isin, as_of=as_of, conn=conn)
    bases = sorted({r["basis"] for r in rows}, key=lambda b: b != "consolidated")
    chosen = basis if basis in bases else (bases[0] if bases else basis or "consolidated")
    events = store.adjustment_events(isin, as_of=as_of, conn=conn)
    by_type: dict[str, dict[str, dict[str, float]]] = {"Q": {}, "A": {}, "I": {}}
    face_values: dict[str, float] = {}
    for r in rows:
        if r["basis"] != chosen or r["period_type"] not in by_type:
            continue
        value = r["value"]
        if r["field"] in PER_SHARE:
            value = value / store.per_share_factor(r["filed_at"], events)
        if r["field"] == "face_value":
            face_values[r["period_end"]] = value
        by_type[r["period_type"]].setdefault(r["period_end"], {})[r["field"]] = value
    quarterly = {e: {k: v for k, v in p.items() if k in INCOME} for e, p in by_type["Q"].items()}
    annual = {e: {k: v for k, v in p.items() if k in INCOME} for e, p in by_type["A"].items()}
    cashflow = {e: c for e, p in by_type["A"].items() if (c := {k: v for k, v in p.items() if k in CASHFLOW})
                and "operating" in c}
    year_ends = set(annual) | {e for e in by_type["I"] if date.fromisoformat(e).month == 3}
    balance = {}
    for end, fields in by_type["I"].items():
        if end not in year_ends:
            continue
        b = {k: v for k, v in fields.items() if k in BALANCE}
        fv = face_values.get(end) or security.get("face_value")
        if fv and b.get("share_capital"):
            b["shares"] = b["share_capital"] / fv
        balance[end] = b
    filings = [f for f in store.get_filings(isin, conn=conn) if limit is None or f["filed_at"] <= limit]
    formats = {f["format"] for f in filings if f["kind"] == "results"}
    return Statements(
        basis=chosen, bases=bases, quarterly=quarterly, annual=annual, balance=balance, cashflow=cashflow,
        financial=bool(formats & {"banking", "nbfc"}) if formats else None, events=events, filings=filings)
