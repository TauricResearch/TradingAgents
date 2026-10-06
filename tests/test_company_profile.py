"""The Company page's data: Yahoo rows mapped to fields, screener rows and ratios
derived from them, growth, pros and cons, and the live-only boundary. No network:
yfinance is replaced by a fake ticker holding fixture frames."""

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows import company_profile as cp
from tradingagents.dataflows.errors import NoMarketDataError, VendorRateLimitError
from tradingagents.dataflows.vendors.yahoo import company_profile as yahoo, ohlcv

pytestmark = pytest.mark.unit

CR = 1e7
FY = ["2023-03-31", "2024-03-31", "2025-03-31", "2026-03-31"]
QUARTERS = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]


def frame(rows: dict, ends: list[str]) -> pd.DataFrame:
    """A statement as yfinance shapes it: a row per label, newest period first."""
    columns = [pd.Timestamp(e) for e in ends]
    return pd.DataFrame({c: [values[i] for values in rows.values()] for i, c in enumerate(columns)},
                        index=list(rows))[sorted(columns, reverse=True)]


def income(ends, sales):
    n = len(ends)
    return frame({
        "Total Revenue": [s * CR for s in sales],
        "Operating Income": [0.15 * s * CR for s in sales],
        "Reconciled Depreciation": [50 * CR] * n,
        "Interest Expense": [20 * CR] * n,
        "Pretax Income": [(0.15 * s + 10) * CR for s in sales],
        "Tax Provision": [0.25 * (0.15 * s + 10) * CR for s in sales],
        "Net Income Including Noncontrolling Interests": [0.75 * (0.15 * s + 10) * CR for s in sales],
        "Net Income Common Stockholders": [0.7 * (0.15 * s + 10) * CR for s in sales],
        "Diluted EPS": [0.7 * (0.15 * s + 10) for s in sales],
        "Cost Of Revenue": [0.6 * s * CR for s in sales],
    }, ends)


BALANCE = frame({
    "Common Stock": [10 * CR] * 4, "Stockholders Equity": [600 * CR] * 4,
    "Total Debt": [100 * CR] * 4, "Capital Lease Obligations": [20 * CR] * 4,
    "Total Assets": [1000 * CR] * 4, "Current Assets": [400 * CR] * 4,
    "Current Liabilities": [200 * CR] * 4, "Net PPE": [450 * CR] * 4,
    "Construction In Progress": [50 * CR] * 4, "Goodwill And Other Intangible Assets": [30 * CR] * 4,
    "Investments And Advances": [80 * CR] * 4, "Other Short Term Investments": [20 * CR] * 4,
    "Accounts Receivable": [100 * CR] * 4, "Inventory": [120 * CR] * 4,
    "Accounts Payable": [90 * CR] * 4, "Ordinary Shares Number": [1 * CR] * 4,
}, FY)

CASHFLOW = frame({
    "Operating Cash Flow": [150 * CR, 160 * CR, 170 * CR, 180 * CR],
    "Investing Cash Flow": [-100 * CR] * 4, "Financing Cash Flow": [-40 * CR] * 4,
    "Free Cash Flow": [60 * CR, 70 * CR, 80 * CR, 90 * CR],
}, FY)

INFO = {
    "longName": "Acme Industries Limited", "fullExchangeName": "NSE", "sector": "Industrials",
    "industry": "Specialty Industrial Machinery", "website": "https://acme.example",
    "currency": "INR", "financialCurrency": "INR", "quoteType": "EQUITY",
    "currentPrice": 250.0, "regularMarketChange": 5.0, "regularMarketChangePercent": 2.04,
    "marketCap": 2500 * CR, "fiftyTwoWeekHigh": 300.0, "fiftyTwoWeekLow": 200.0,
    "trailingPE": "Infinity", "bookValue": 60.0, "dividendYield": 2.5,
}


def history(start="2019-01-01", end="2026-10-02") -> pd.DataFrame:
    days = pd.bdate_range(start, end, tz="Asia/Kolkata")
    close = [100 + i * 0.05 for i in range(len(days))]
    return pd.DataFrame({"Close": close, "Volume": [1_000_000] * len(days)}, index=days)


class FakeTicker:
    calls: list = []
    tickers: dict = {}

    def __init__(self, symbol):
        self.symbol = symbol
        FakeTicker.calls.append(symbol)
        data = FakeTicker.tickers.get(symbol, {})
        self.info = data.get("info", {"trailingPegRatio": None})
        self._history = data.get("history", pd.DataFrame())
        self.quarterly_income_stmt = data.get("quarterly", pd.DataFrame())
        self.income_stmt = data.get("annual", pd.DataFrame())
        self.balance_sheet = data.get("balance", pd.DataFrame())
        self.cashflow = data.get("cashflow", pd.DataFrame())

    def history(self, **kwargs):
        return self._history


ACME = {"info": INFO, "history": history(), "annual": income(FY, [1000, 1100, 1210, 1331]),
        "quarterly": income(QUARTERS, [300, 310, 320, 330, 340]), "balance": BALANCE,
        "cashflow": CASHFLOW}


@pytest.fixture(autouse=True)
def fake_yahoo(monkeypatch):
    FakeTicker.calls = []
    FakeTicker.tickers = {"ACME.NS": ACME}
    monkeypatch.setattr(yahoo, "yf", SimpleNamespace(Ticker=FakeTicker))
    monkeypatch.setattr(yahoo, "_CACHE", {})


# --- Mapping Yahoo's rows ---------------------------------------------------------

def test_the_first_label_present_wins_and_a_missing_one_falls_through():
    both = frame({"Total Revenue": [5.0], "Operating Revenue": [4.0]}, ["2026-03-31"])
    alone = frame({"Operating Revenue": [4.0], "Total Revenue": [float("nan")]}, ["2026-03-31"])
    assert yahoo.statement_fields(both, yahoo.ALIASES["income"]) == {"2026-03-31": {"sales": 5.0}}
    assert yahoo.statement_fields(alone, yahoo.ALIASES["income"]) == {"2026-03-31": {"sales": 4.0}}


def test_a_tuple_of_labels_sums_those_present():
    parts = frame({"Goodwill": [3.0], "Other Intangible Assets": [float("nan")],
                   "Long Term Equity Investment": [2.0], "Investmentin Financial Assets": [5.0]},
                  ["2026-03-31"])
    fields = yahoo.statement_fields(parts, yahoo.ALIASES["balance"])["2026-03-31"]
    assert fields == {"intangibles": 3.0, "investments": 7.0}


def test_blank_periods_unknown_rows_and_repeated_labels_do_not_break_the_mapping():
    messy = pd.DataFrame([[float("nan"), 7.0], [float("nan"), float("nan")], [float("nan"), 9.0]],
                         index=["Pretax Income", "Some New Yahoo Row", "Pretax Income"],
                         columns=[pd.Timestamp("2026-03-31"), pd.Timestamp("2025-03-31")])
    assert yahoo.statement_fields(messy, yahoo.ALIASES["income"]) == {"2025-03-31": {"pbt": 7.0}}
    assert yahoo.statement_fields(pd.DataFrame(), yahoo.ALIASES["income"]) == {}
    assert yahoo.statement_fields(None, yahoo.ALIASES["income"]) == {}


def test_quote_fields_skip_blanks_and_non_numbers():
    quote = yahoo.quote_fields({"shortName": "ACME LTD", "longName": "", "regularMarketPrice": 9.5,
                                "trailingPE": "Infinity", "dividendYield": None})
    assert quote == {"name": "ACME LTD", "price": 9.5}


def test_price_rows_keep_the_exchange_date_and_one_row_per_day():
    index = pd.DatetimeIndex(["2026-10-01 00:00", "2026-10-02 00:00", "2026-10-02 15:29"]).tz_localize("Asia/Kolkata")
    rows = yahoo.price_rows(pd.DataFrame({"Close": [10.0, float("nan"), 11.0], "Volume": [5, 6, 7]}, index=index))
    assert rows == [("2026-10-01", 10.0, 5.0), ("2026-10-02", 11.0, 7.0)]


# --- Units ----------------------------------------------------------------------------

def test_rupee_figures_are_shown_in_crores_and_others_in_millions():
    inr, usd = cp.display_unit("INR"), cp.display_unit("USD")
    assert (inr["label"], inr["divisor"], inr["locale"]) == ("Rs. Crores", 1e7, "en-IN")
    assert (usd["label"], usd["divisor"]) == ("USD Millions", 1e6)
    assert cp.scale(12_345_678_900, cp.CRORE) == 1234.57
    assert cp.scale(2.5e9, cp.MILLION) == 2500.0
    assert cp.scale(None, cp.CRORE) is None


# --- Formulas -----------------------------------------------------------------------

P = {"sales": 1000.0, "operating_income": 150.0, "depreciation": 50.0, "interest": 20.0,
     "pbt": 160.0, "tax": 40.0, "net_income": 115.0, "cogs": 600.0}
B = {"share_capital": 10.0, "equity": 600.0, "total_debt": 100.0, "lease_liabilities": 20.0,
     "total_assets": 1000.0, "current_assets": 400.0, "current_liabilities": 200.0,
     "net_ppe": 450.0, "cwip": 50.0, "intangibles": 30.0, "investments": 80.0,
     "current_investments": 20.0, "receivables": 100.0, "inventory": 120.0, "payables": 90.0,
     "shares": 1.0}


def test_screener_rows_reconcile_to_profit_before_tax():
    op, oi = cp.operating_profit(P), cp.other_income(P)
    assert (op, oi, cp.expenses(P), cp.opm(P), cp.tax_rate(P)) == (200.0, 30.0, 800.0, 20.0, 25.0)
    assert op + oi - P["interest"] - P["depreciation"] == P["pbt"]
    derived = {k: v for k, v in P.items() if k != "operating_income"} | {"total_expenses": 850.0}
    assert cp.operating_profit(derived) == 200.0


def test_balance_sheet_rows_add_up_to_total_assets():
    assert (cp.reserves(B), cp.other_liabilities(B)) == (590.0, 300.0)
    assert (cp.fixed_assets(B), cp.investments(B, False), cp.other_assets(B, False)) == (430.0, 100.0, 420.0)
    assert cp.fixed_assets(B) + B["cwip"] + cp.investments(B, False) + cp.other_assets(B, False) == B["total_assets"]
    assert cp.investments(B, True) == 80.0  # a bank's short-term investments are inside it already
    assert cp.fixed_assets({"net_ppe": 450.0}) == 450.0  # no CWIP or intangibles row: zero


def test_working_capital_ratios_and_returns():
    assert cp.debtor_days(P, B) == pytest.approx(36.5)
    assert cp.inventory_days(P, B) == pytest.approx(73.0)
    assert cp.days_payable(P, B) == pytest.approx(54.75)
    assert cp.cash_conversion_cycle(P, B) == pytest.approx(54.75)
    assert cp.working_capital_days(P, B) == pytest.approx(73.0)
    assert cp.roce(P, B) == pytest.approx(22.5)
    assert cp.roe(P, B) == pytest.approx(19.1667, rel=1e-4)
    assert cp.interest_coverage(P) == pytest.approx(9.0)
    assert cp.leverage(B) == pytest.approx(80 / 600)
    assert cp.face_value(B) == 10.0


def test_a_missing_input_leaves_the_figure_blank():
    assert cp.operating_profit({"operating_income": 150.0}) is None
    assert cp.opm({"sales": 0.0, "operating_income": 1.0, "depreciation": 1.0}) is None
    assert cp.roce(P, {"total_assets": 1000.0}) is None
    assert cp.inventory_days({"sales": 10.0}, B) is None
    assert cp.net_cash_flow({"operating": 1.0, "investing": -1.0}) is None


def test_cagr_needs_positive_ends():
    assert cp.cagr(100, 121, 2) == pytest.approx(10.0)
    assert cp.cagr(100, 200, 1) == pytest.approx(100.0)
    assert cp.cagr(-5, 10, 3) is None
    assert cp.cagr(10, -5, 3) is None
    assert cp.cagr(10, 20, 0) is None
    assert cp.cagr(None, 20, 3) is None


def test_ttm_sums_four_consecutive_quarters():
    q = {e: {"sales": float(i + 1), "pbt": 1.0} for i, e in enumerate(QUARTERS)}
    q["2025-09-30"].pop("pbt")
    assert cp.ttm(q) == {"sales": 2.0 + 3 + 4 + 5}  # pbt is missing from one of them
    del q["2025-09-30"]
    assert cp.ttm(q) is None  # Jun 2025 to Dec 2025 skips a quarter
    assert cp.ttm({e: {"sales": 1.0} for e in QUARTERS[:3]}) is None


def test_missing_quarters_are_named():
    assert cp.missing_quarters(["2025-03-31", "2025-06-30", "2025-12-31", "2026-03-31"]) == ["Sep 2025"]
    assert cp.missing_quarters(QUARTERS) == []


# --- Growth -------------------------------------------------------------------------

def test_growth_lists_only_the_spans_the_data_covers():
    four = [(date(2023 + i, 3, 31), 100 * 1.1 ** i) for i in range(4)]
    assert cp.annual_growth(four) == [{"label": "3 Years", "value": 10.0}]
    five = [(date(2022, 3, 31), 50.0)] + four
    assert [i["label"] for i in cp.annual_growth(five)] == ["3 Years", "4 Years"]
    losses = [(date(2023, 3, 31), -10.0), (date(2026, 3, 31), 20.0)]
    assert cp.annual_growth(losses) == [{"label": "3 Years", "value": None}]
    assert cp.annual_growth(four[:1]) == []


def test_price_growth_and_roe_averages():
    days = [date(2020, 10, 2), date(2023, 10, 2), date(2025, 10, 2), date(2026, 10, 2)]
    items = cp.price_growth(days, [100.0, 150.0, 180.0, 200.0])
    assert [i["label"] for i in items] == ["1 Year", "3 Years", "6 Years"]
    assert items[0]["value"] == pytest.approx(11.11, abs=0.01)
    assert cp.roe_averages([10.0, 20.0, 30.0, 40.0]) == [
        {"label": "Last Year", "value": 40.0}, {"label": "3 Years", "value": 30.0},
        {"label": "4 Years", "value": 25.0}]


# --- Pros and cons ------------------------------------------------------------------

FACTS = {"revenue": "Sales", "leverage": None, "coverage": None, "roe_min_3y": None,
         "roe_avg_3y": None, "sales_cagr_3y": None, "profit_cagr_3y": None, "net_profit": None,
         "dividend_yield": None, "price_to_book": None, "opm_now": None, "opm_3y_ago": None,
         "fcf_years": 0, "fcf_negative": 0}


def test_rules_fire_on_the_figures_and_stay_silent_without_them():
    assert cp.pros_and_cons(FACTS, financial=False) == ([], [])
    pros, cons = cp.pros_and_cons(FACTS | {
        "leverage": 0.05, "roe_min_3y": 22.0, "roe_avg_3y": 24.0, "sales_cagr_3y": 3.2,
        "coverage": 2.1, "fcf_years": 4, "fcf_negative": 0, "opm_now": 12.0, "opm_3y_ago": 18.0,
    }, financial=False)
    assert pros == ["Almost debt-free: borrowings other than leases are under 10% of equity.",
                    "Return on equity above 20% in each of the last 3 years.",
                    "Positive free cash flow in each of the last 4 years."]
    assert cons == ["Low interest coverage: EBIT covers interest 2.1 times.",
                    "Sales growth below 5% a year over the last 3 years (3.2%).",
                    "Operating margin fell from 18.0% to 12.0% over the last 3 years."]


def test_rules_about_debt_and_margins_skip_banks():
    facts = FACTS | {"leverage": 4.0, "coverage": 1.2, "sales_cagr_3y": 18.0, "revenue": "Revenue"}
    assert cp.pros_and_cons(facts, financial=True) == (
        ["Revenue grew 18.0% a year over the last 3 years."], [])
    _, cons = cp.pros_and_cons(facts, financial=False)
    assert "High debt: borrowings other than leases are 4.0 times equity." in cons


def test_every_rule_formats_with_the_facts_it_reads():
    lively = FACTS | {k: 1.0 for k in FACTS if k not in ("revenue", "fcf_years", "fcf_negative")}
    for rule in cp.RULES:
        rule.message.format(**lively)


# --- The profile ----------------------------------------------------------------------

def test_a_profile_lays_out_an_indian_company_in_crores():
    p = yahoo.build_company_profile("acme.ns")
    assert (p["symbol"], p["name"], p["unit"]["label"], p["financial"]) == (
        "ACME.NS", "Acme Industries Limited", "Rs. Crores", False)
    ratios = {r["key"]: r["value"] for r in p["keyRatios"]}
    assert ratios["market_cap"] == 2500.0 and ratios["pe"] is None and ratios["face_value"] == 10.0
    # The latest year: EBIT 209.65 + 20 over capital employed 800; profit 0.7 * 209.65 over 600.
    assert (ratios["roce"], ratios["roe"]) == (28.71, 24.46)

    pl = p["profitLoss"]
    assert [x["label"] for x in pl["periods"]] == ["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026", "TTM"]
    rows = {r["key"]: r["values"] for r in pl["rows"]}
    assert rows["sales"][0] == 1000.0 and rows["operating_profit"][0] == 200.0 and rows["opm"][0] == 20.0
    assert rows["other_income"][0] == 30.0 and rows["expenses"][0] == 800.0
    assert rows["sales"][-1] == 310 + 320 + 330 + 340  # TTM: the four quarters to Jun 2026

    bs = {r["key"]: r["values"][0] for r in p["balanceSheet"]["rows"]}
    assert (bs["reserves"], bs["fixed_assets"], bs["investments"], bs["other_assets"]) == (590.0, 430.0, 100.0, 420.0)
    ratio_rows = {r["key"]: r["values"][0] for r in p["ratios"]["rows"]}
    assert (ratio_rows["debtor_days"], ratio_rows["inventory_days"], ratio_rows["roce"]) == (36.5, 73.0, 22.5)
    cash = {r["key"]: r["values"] for r in p["cashFlows"]["rows"]}
    assert cash["net"] == [10.0, 20.0, 30.0, 40.0]

    growth = {g["key"]: g["items"] for g in p["growth"]}
    assert growth["sales"] == [{"label": "3 Years", "value": 10.0}]
    assert [i["label"] for i in growth["price"]] == ["1 Year", "3 Years", "5 Years", "8 Years"]
    assert "Dividend yield of 2.50%." in p["pros"]
    assert p["source"] == {"name": "Yahoo Finance", "fetched": p["source"]["fetched"], "annual": 4, "quarterly": 5}
    assert len(p["chart"]["dates"]) == len(p["chart"]["close"]) == len(p["chart"]["volume"])


def test_a_bank_gets_a_lenders_layout():
    bank = income(FY, [1000, 1100, 1200, 1300])
    bank.loc["Interest Income"] = [3000 * CR] * 4
    bank = bank.drop(index=["Operating Income", "Cost Of Revenue"])
    FakeTicker.tickers["BANK.NS"] = {**ACME, "info": INFO | {"industry": "Banks - Regional"},
                                     "annual": bank, "quarterly": pd.DataFrame()}
    p = yahoo.build_company_profile("BANK.NS")
    assert p["financial"]
    assert [r["key"] for r in p["profitLoss"]["rows"]][:4] == [
        "interest_income", "interest", "net_interest_income", "other_income"]
    assert "opm" not in {r["key"] for r in p["profitLoss"]["rows"]}
    assert [r["key"] for r in p["ratios"]["rows"]] == ["roe"]
    assert "roce" not in {r["key"] for r in p["keyRatios"]}
    assert "do not apply" in p["ratios"]["note"]
    assert p["balanceSheet"]["rows"][3]["label"] == "Deposits & Other Liabilities"
    assert p["growth"][0]["title"] == "Compounded Revenue Growth"


def test_missing_statements_leave_empty_sections_not_errors():
    FakeTicker.tickers["THIN.NS"] = {"info": {"longName": "Thin Ltd", "currency": "INR"}}
    p = yahoo.build_company_profile("THIN.NS")
    for key in ("quarters", "profitLoss", "balanceSheet", "cashFlows", "ratios"):
        assert p[key]["periods"] == [] and p[key]["rows"] == []
    assert {r["key"]: r["value"] for r in p["keyRatios"]}["roe"] is None
    assert p["growth"] == [] and p["chart"]["dates"] == []


def test_stray_periods_and_quarter_gaps():
    stray = BALANCE.copy()
    stray[pd.Timestamp("2022-03-31")] = float("nan")
    stray.loc["Investments And Advances", pd.Timestamp("2022-03-31")] = 1.0
    gappy = income(["2025-03-31", "2025-06-30", "2025-12-31", "2026-03-31", "2026-06-30"], [1, 2, 3, 4, 5])
    FakeTicker.tickers["GAP.NS"] = {**ACME, "balance": stray, "quarterly": gappy}
    p = yahoo.build_company_profile("GAP.NS")
    assert [x["end"] for x in p["balanceSheet"]["periods"]] == FY  # no total assets in 2022
    assert p["quarters"]["note"] == "Yahoo Finance has no figures for Sep 2025."
    assert "TTM" not in [x["label"] for x in p["profitLoss"]["periods"]]
    assert "No TTM column" in p["profitLoss"]["note"]


def test_a_bse_listing_without_history_charts_its_nse_listing():
    FakeTicker.tickers["ACME.BO"] = {**ACME, "history": history("2026-10-02")}
    p = yahoo.build_company_profile("ACME.BO")
    assert FakeTicker.calls == ["ACME.BO", "ACME.NS"]
    assert p["chart"]["symbol"] == "ACME.NS" and "ACME.NS listing" in p["chart"]["note"]
    assert len(p["chart"]["dates"]) > 1000


def test_profiles_are_cached_for_fifteen_minutes(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(yahoo, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    first = yahoo.build_company_profile("ACME.NS")
    assert yahoo.build_company_profile("acme.ns") is first
    assert FakeTicker.calls == ["ACME.NS"]
    clock[0] += yahoo.CACHE_TTL_SECONDS + 1
    yahoo.build_company_profile("ACME.NS")
    assert FakeTicker.calls == ["ACME.NS", "ACME.NS"]


def test_an_unknown_symbol_is_no_data_and_an_outage_is_not(monkeypatch):
    monkeypatch.setattr(ohlcv, "vendor_reachable", lambda url: True)
    with pytest.raises(NoMarketDataError):
        yahoo.build_company_profile("NOSUCH.NS")
    monkeypatch.setattr(ohlcv, "vendor_reachable", lambda url: False)
    with pytest.raises(VendorRateLimitError):
        yahoo.build_company_profile("NOSUCH.NS")


def test_throttling_is_reported_and_other_read_errors_lose_one_section(monkeypatch):
    monkeypatch.setattr(ohlcv.time, "sleep", lambda s: None)

    class Throttled(FakeTicker):
        @property
        def info(self):
            raise YFRateLimitError()

        @info.setter
        def info(self, value):
            pass

    class NoBalanceSheet(FakeTicker):
        @property
        def balance_sheet(self):
            raise KeyError("balanceSheetHistory")

        @balance_sheet.setter
        def balance_sheet(self, value):
            pass

    monkeypatch.setattr(yahoo, "yf", SimpleNamespace(Ticker=Throttled))
    with pytest.raises(VendorRateLimitError):
        yahoo.build_company_profile("ACME.NS")
    monkeypatch.setattr(yahoo, "yf", SimpleNamespace(Ticker=NoBalanceSheet))
    p = yahoo.build_company_profile("ACME.NS")
    assert p["balanceSheet"]["periods"] == [] and p["profitLoss"]["periods"]


# --- The live-only boundary -----------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
LIVE_MODULES = {"tradingagents.dataflows.company_profile",
                "tradingagents.dataflows.vendors.yahoo.company_profile",
                "tradingagents.dataflows.vendors.india.profile"}
ALLOWED = {"cli/webui/server.py", "tradingagents/dataflows/vendors/yahoo/company_profile.py",
           "tradingagents/dataflows/vendors/india/profile.py"}


def _imported(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names |= {node.module} | {f"{node.module}.{a.name}" for a in node.names}
    return names


def test_only_the_browser_ui_reads_the_live_company_profile():
    """It is today's data with no point-in-time cut: an agent tool or a backtest built
    on it would see figures from after its analysis date."""
    importers = sorted(
        path.relative_to(ROOT).as_posix()
        for package in ("tradingagents", "cli")
        for path in (ROOT / package).rglob("*.py")
        if _imported(path) & LIVE_MODULES
    )
    assert importers and set(importers) <= ALLOWED
