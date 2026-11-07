"""The valuation reports: fetch point-in-time inputs, run the deterministic maths, render text.

``dcf_report`` and ``peer_report`` are what the valuation analyst's tools return. They
never raise for a data problem: a missing or withheld input becomes an UNAVAILABLE
notice that says why, and no figure is estimated to fill the gap. All arithmetic is
in ``wacc``, ``dcf`` and ``multiples``; the model only reads the text.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorError
from tradingagents.dataflows.router import route_to_vendor
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.fred import get_latest_observation
from tradingagents.dataflows.vendors.yahoo.market import get_final_closes
from tradingagents.dataflows.vendors.yahoo.valuation import MINOR_UNITS
from tradingagents.memory.settlement import resolve_benchmark
from tradingagents.valuation import dcf as dcf_math, multiples as mult, wacc as wacc_math
from tradingagents.valuation.wacc import ValuationError

logger = logging.getLogger(__name__)

# A latest close older than this many days before the as-of date is stale.
MAX_PRICE_AGE_DAYS = 10


# ---------------------------------------------------------------- formatting


def _money(value: float | None, currency: str = "") -> str:
    if value is None:
        return "n/a"
    magnitude = abs(value)
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if magnitude >= scale:
            text = f"{value / scale:,.2f}{suffix}"
            break
    else:
        text = f"{value:,.2f}"
    return f"{text} {currency}".strip()


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _x(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}x"


def _price(value: float | None, currency: str = "") -> str:
    return "n/a" if value is None else f"{value:,.2f} {currency}".strip()


def unavailable(title: str, ticker: str, as_of: str, reason: str) -> str:
    """The notice a tool returns when it cannot produce a figure."""
    return (
        f"# {title} for {ticker} as of {as_of}\n\n"
        f"UNAVAILABLE: {reason}\n\n"
        "No value is estimated in its place. Report this as unavailable and say why; "
        "do not substitute a figure of your own."
    )


# ---------------------------------------------------------------- inputs


def _fetch(method: str, *args) -> tuple[dict | None, str]:
    """(data, "") on success, else (None, reason). A vendor sentinel string is a reason."""
    try:
        out = route_to_vendor(method, *args)
    except Exception as exc:  # noqa: BLE001 - a data problem must not end the run
        logger.warning("%s failed: %s", method, exc)
        return None, f"{method} failed ({type(exc).__name__}: {exc})"
    if isinstance(out, str):
        return None, out.replace("\n", " ")
    return out, ""


def risk_free_rate(as_of: str, cfg: dict) -> tuple[float, str]:
    """(rate, provenance): FRED's 10y Treasury as published by ``as_of``, else the configured default."""
    reason = "disabled in config"
    if cfg.get("valuation_use_fred_risk_free", True):
        try:
            value, date = get_latest_observation("DGS10", as_of)
            return value / 100, f"FRED 10y Treasury (DGS10) {value:.2f}% on {date}"
        except Exception as exc:  # noqa: BLE001 - no key, outage or no observation: use the default
            reason = f"{type(exc).__name__}: {exc}"
    rate = cfg["valuation_risk_free_rate"]
    return rate, f"config default {rate:.2%} (FRED not used: {reason})"


def _history(ticker: str, as_of: str, cfg: dict) -> pd.Series:
    """Final closes up to ``as_of`` over the beta window; raises ValuationError when unusable."""
    closes = get_final_closes(ticker, as_of, int(cfg["valuation_beta_years"] * 365) + 14)
    if closes.empty:
        raise ValuationError(f"no closing prices for {ticker} up to {as_of}")
    age = (datetime.strptime(as_of, "%Y-%m-%d") - closes.index[-1].to_pydatetime()).days
    if age > MAX_PRICE_AGE_DAYS:
        raise ValuationError(f"the latest close for {ticker} is {closes.index[-1]:%Y-%m-%d}, {age} days before {as_of} (stale)")
    return closes


def _price_in_main_unit(closes: pd.Series, quote_currency: str | None) -> tuple[float, str, str]:
    """(price, currency, note): the last close, with a minor unit (pence) converted to its main unit."""
    price = float(closes.iloc[-1])
    if quote_currency in MINOR_UNITS:
        return price / 100, MINOR_UNITS[quote_currency], f"price quoted in {quote_currency}, divided by 100 to {MINOR_UNITS[quote_currency]}"
    return price, quote_currency or "", ""


def _beta(ticker: str, closes: pd.Series, as_of: str, cfg: dict) -> tuple[wacc_math.BetaResult, str]:
    benchmark = resolve_benchmark(ticker, cfg)
    bench = get_final_closes(benchmark, as_of, int(cfg["valuation_beta_years"] * 365) + 14)
    if bench.empty:
        raise ValuationError(f"no closing prices for the benchmark {benchmark}")
    return wacc_math.beta_from_closes(closes, bench), benchmark


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- DCF


def dcf_report(ticker: str, as_of: str, cfg: dict | None = None) -> str:
    """DCF valuation text for ``ticker`` as of ``as_of``, or an UNAVAILABLE notice saying why."""
    title = "DCF valuation"
    try:
        return _dcf_report(ticker, as_of, cfg or get_config(), title)
    except (ValuationError, VendorError) as exc:
        return unavailable(title, ticker, as_of, str(exc))


def _dcf_report(ticker: str, as_of: str, cfg: dict, title: str) -> str:
    data, reason = _fetch("get_valuation_inputs", ticker, as_of)
    if data is None:
        raise ValuationError(f"no company inputs could be read: {reason}")

    closes = _history(ticker, as_of, cfg)
    quote_ccy = data.get("quote_currency") or ("USD" if data["source"] == "sec_edgar" else None)
    price, ccy, price_note = _price_in_main_unit(closes, quote_ccy)
    price_date = f"{closes.index[-1]:%Y-%m-%d}"
    reporting = data.get("currency")
    if reporting and ccy and reporting != ccy:
        raise ValuationError(
            f"the company reports in {reporting} but trades in {ccy}; no FX rate is applied, "
            "so a per-share value would be in the wrong currency")
    shares = data.get("shares")
    if not shares or shares <= 0:
        raise ValuationError("the source gives no share count")

    rf, rf_note = risk_free_rate(as_of, cfg)
    erp, g_term = cfg["valuation_equity_risk_premium"], cfg["valuation_terminal_growth"]
    beta, benchmark = _beta(ticker, closes, as_of, cfg)
    ke = wacc_math.cost_of_equity(rf, beta.beta, erp)

    header = [
        f"# DCF valuation for {ticker} as of {as_of}",
        f"- Price: {_price(price, ccy)} (final close {price_date}); source of inputs: {data['source']}",
        *(f"- Note: {n}" for n in ([price_note] if price_note else []) + list(data.get("notes", []))),
    ]

    if data.get("is_financial"):
        return "\n".join(header) + "\n\n" + _financial_section(data, price, ccy, ke, g_term, beta, benchmark, rf_note, erp)

    # --- free cash flow history
    periods = [p for p in data["periods"] if p.get("capex") is not None]
    dropped = len(data["periods"]) - len(periods)
    if not periods:
        raise ValuationError("no fiscal year has both operating cash flow and capital expenditure")
    fcfs = [dcf_math.free_cash_flow(p["cfo"], p["capex"]) for p in periods]
    base = fcfs[-1]
    history_rows = [[p["end"], _money(p["cfo"], ccy), _money(p["capex"], ccy), _money(f, ccy)]
                    for p, f in zip(periods, fcfs, strict=True)]
    history = _table(["Fiscal year end", "Operating cash flow", "Capex", "Free cash flow"], history_rows)
    if base <= 0:
        raise ValuationError(
            f"the latest fiscal year's free cash flow is {_money(base, ccy)} (not positive), so a "
            "growth DCF does not apply. Fiscal-year history:\n\n" + history)

    for name, value in (("total debt", data.get("total_debt")), ("cash", data.get("cash"))):
        if value is None:
            raise ValuationError(f"the source gives no {name}, so enterprise value cannot be bridged to equity")
    debt, cash = data["total_debt"], data["cash"]

    # --- growth, tax, cost of capital
    growth0, growth_note = dcf_math.historical_growth(fcfs, cfg["valuation_growth_floor"], cfg["valuation_growth_cap"])
    if growth0 is None:
        growth0 = cfg["valuation_default_growth"]
        growth_note = f"{growth_note}; using the configured default {growth0:.1%}"
    tax, tax_note = wacc_math.effective_tax_rate(
        data.get("income_tax"), data.get("pretax_income"), cfg["valuation_tax_rate_default"])
    kd = wacc_math.after_tax_cost_of_debt(data.get("interest_expense"), debt, tax)
    market_cap = price * shares
    w = wacc_math.wacc(market_cap, debt, ke, kd)

    years = int(cfg["valuation_forecast_years"])
    path = dcf_math.fade_growth(growth0, g_term, years)
    result = dcf_math.run_dcf(base, path, w.wacc, g_term, debt, cash, shares)
    upside = result.value_per_share / price - 1
    rates, growths, grid = dcf_math.sensitivity(base, path, w.wacc, g_term, debt, cash, shares)

    warnings = []
    if result.terminal_share > 0.75:
        warnings.append(f"The terminal value is {result.terminal_share:.0%} of enterprise value, so the result "
                        "rests mostly on the long-run assumptions.")
    if kd is not None and not 0.01 <= kd / (1 - tax) <= 0.15:
        warnings.append(f"Implied pre-tax cost of debt {kd / (1 - tax):.1%} (interest expense / total debt) is outside "
                        "1%-15%; the interest figure may not match the debt figure's period.")
    if not 0.3 <= beta.beta <= 2.5:
        warnings.append(f"Beta {beta.beta:.2f} is unusual; the weekly sample is noisy.")
    if dropped:
        warnings.append(f"{dropped} fiscal year(s) with no capital expenditure figure were left out of the history.")
    if data.get("interest_expense") is None:
        warnings.append("No interest expense is available, so the cost of debt is not applied: WACC equals the cost of equity.")

    assumptions = _table(["Assumption", "Value", "Source"], [
        ["Risk-free rate", _pct(rf, 2), rf_note],
        ["Equity risk premium", _pct(erp, 2), "config valuation_equity_risk_premium"],
        ["Beta", f"{beta.beta:.2f}", f"{beta.weeks} weekly returns {beta.start}..{beta.end} vs {benchmark}"],
        ["Cost of equity (CAPM)", _pct(ke, 2), "rf + beta x ERP"],
        ["After-tax cost of debt", _pct(kd, 2) if kd is not None else "n/a", f"interest expense / total debt x (1 - t); {tax_note}"],
        ["Capital weights (E / D)", f"{w.equity_weight:.1%} / {w.debt_weight:.1%}",
         f"market cap {_money(market_cap, ccy)}; debt {_money(debt, ccy)} at book value"],
        ["WACC", _pct(w.wacc, 2), "weights x costs"],
        ["Base free cash flow", _money(base, ccy), f"fiscal year ended {periods[-1]['end']}"],
        ["Initial FCF growth", _pct(growth0), growth_note],
        ["Terminal growth", _pct(g_term, 2), "config valuation_terminal_growth"],
        ["Forecast years", str(years), "growth fades linearly from initial to terminal"],
        ["Net debt bridge", f"debt {_money(debt, ccy)}, cash {_money(cash, ccy)}", data["source"]],
        ["Shares outstanding", f"{shares:,.0f}", data["source"]],
    ])
    projection = _table(["Year", "Growth", "FCF", "PV of FCF"], [
        [str(t), _pct(g), _money(f, ccy), _money(pv, ccy)]
        for t, (g, f, pv) in enumerate(zip(result.growth, result.fcf, result.pv_fcf, strict=True), start=1)])
    bridge = _table(["Step", "Value"], [
        ["Sum of PV of FCF", _money(sum(result.pv_fcf), ccy)],
        ["Terminal value (Gordon)", _money(result.terminal_value, ccy)],
        ["PV of terminal value", f"{_money(result.pv_terminal, ccy)} ({result.terminal_share:.0%} of EV)"],
        ["Enterprise value", _money(result.enterprise_value, ccy)],
        ["Less: total debt", _money(debt, ccy)],
        ["Plus: cash", _money(cash, ccy)],
        ["Equity value", _money(result.equity_value, ccy)],
        ["Value per share", _price(result.value_per_share, ccy)],
        ["Price", _price(price, ccy)],
        ["Upside vs price", f"{upside:+.1%}"],
    ])
    sens = _table(["WACC \\ terminal g"] + [_pct(g, 2) for g in growths], [
        [_pct(r, 2)] + [_price(v) if v is not None else "n/a" for v in row] for r, row in zip(rates, grid, strict=True)])

    sections = ["\n".join(header), "## Assumptions", assumptions, "## Free cash flow history", history,
                "## Forecast", projection, "## Valuation", bridge,
                f"## Sensitivity: value per share ({ccy}), WACC x terminal growth", sens]
    if warnings:
        sections += ["## Warnings", "\n".join(f"- {x}" for x in warnings)]
    return "\n\n".join(sections)


def _financial_section(data, price, ccy, ke, growth, beta, benchmark, rf_note, erp) -> str:
    ratios = mult.bank_ratios(price, data.get("equity"), data.get("net_income"), data.get("shares"))
    justified = mult.justified_pb(ratios.roe, ke, growth) if ratios.roe is not None else None
    implied = justified * ratios.book_value_per_share if justified is not None and ratios.book_value_per_share else None
    rows = [
        ["Book value per share", _price(ratios.book_value_per_share, ccy)],
        ["EPS (latest fiscal year)", _price(ratios.eps, ccy)],
        ["P/B", _x(ratios.pb)],
        ["P/E", _x(ratios.pe)],
        ["ROE", _pct(ratios.roe)],
        ["Cost of equity (CAPM)", f"{_pct(ke, 2)} (beta {beta.beta:.2f} vs {benchmark}; ERP {erp:.2%}; {rf_note})"],
        ["Long-run growth g", _pct(growth, 2)],
        ["Justified P/B = (ROE - g) / (Ke - g)", _x(justified)],
        ["Implied price = justified P/B x book value", _price(implied, ccy)],
    ]
    out = [
        "## DCF does not apply",
        f"A free-cash-flow DCF does not fit this company ({data.get('financial_reason') or 'a bank or insurer'}): "
        "for a bank or insurer, debt and cash flows are operating items, so there is no enterprise value or free "
        "cash flow to discount. Value it on P/B, P/E and ROE instead.",
        _table(["Measure", "Value"], rows),
    ]
    if implied is not None and price:
        out.append(f"Implied price vs price: {implied / price - 1:+.1%}")
    return "\n\n".join(out)


# ---------------------------------------------------------------- peers


def peer_report(ticker: str, as_of: str, cfg: dict | None = None) -> str:
    """Peer-multiple comparison text for ``ticker`` as of ``as_of``, or an UNAVAILABLE notice saying why."""
    title = "Peer multiples"
    try:
        return _peer_report(ticker, as_of, cfg or get_config(), title)
    except (ValuationError, VendorError) as exc:
        return unavailable(title, ticker, as_of, str(exc))


def _configured_peers(ticker: str, cfg: dict) -> list[str] | None:
    wanted = {ticker.upper(), normalize_symbol(ticker)}
    for key, peers in (cfg.get("valuation_peer_map") or {}).items():
        if key.upper() in wanted:
            return list(peers)
    return None


def _peer_report(ticker: str, as_of: str, cfg: dict, title: str) -> str:
    data, reason = _fetch("get_peer_snapshot", ticker, as_of, _configured_peers(ticker, cfg),
                          int(cfg["valuation_max_peers"]))
    if data is None:
        raise ValuationError(f"no peer data could be read: {reason}")
    closes = _history(ticker, as_of, cfg)
    target = data["target"]
    price, ccy, price_note = _price_in_main_unit(closes, target.get("quote_currency"))
    peers = data["peers"]
    if not peers:
        raise ValuationError(f"no peers were found ({data['peer_source']}). Set valuation_peer_map to name them")

    financial = data.get("is_financial")
    same_currency = not target.get("reporting_currency") or target.get("reporting_currency") == ccy
    implied = mult.implied_prices(price, target, peers, include_enterprise=same_currency and not financial)
    shown = [i for i in implied if not financial or i.multiple in ("pe", "pb")]

    rows = [[mult.LABELS[i.multiple], _x(i.own), _x(i.peer_median), str(i.peers_used),
             _price(i.implied_price, ccy) if i.implied_price is not None else f"n/a ({i.reason})"] for i in shown]
    table = _table(["Multiple", "Company", "Peer median", "Peers used", "Implied price"], rows)
    prices = [i.implied_price for i in shown if i.implied_price is not None]
    peers_table = _table(["Peer", "Name", "P/E", "EV/EBITDA", "P/S", "P/B"], [
        [p["symbol"], p.get("name") or "", *(_x(p.get(k)) for k in mult.MULTIPLES)] for p in peers])

    out = [
        f"# Peer multiples for {ticker} as of {as_of}",
        f"- Price: {_price(price, ccy)} (final close {closes.index[-1]:%Y-%m-%d}); company: {target.get('name') or ticker}",
        f"- Peers: {len(peers)} from the {data['peer_source']}; peer multiples are Yahoo's present-day trailing figures",
        "- Company multiples are computed here from Yahoo's trailing EPS, EBITDA, revenue and book value at that price",
        *(f"- Note: {n}" for n in ([price_note] if price_note else []) + list(data.get("notes", []))),
        "## Company vs peer median", table,
    ]
    if prices:
        mean = sum(prices) / len(prices)
        out.append(f"Average of the {len(prices)} implied prices: {_price(mean, ccy)} ({mean / price - 1:+.1%} vs price). "
                   f"Range {_price(min(prices), ccy)} to {_price(max(prices), ccy)}.")
    else:
        out.append("No multiple produced an implied price.")
    if financial:
        roes = [p["roe"] for p in peers if p.get("roe") is not None]
        median_roe = mult.peer_median(roes)[0]
        out.append(f"This is a bank or insurer, so only P/B and P/E apply. ROE: company {_pct(target.get('roe'))} "
                   f"vs peer median {_pct(median_roe)} ({len(roes)} peers).")
    if len(peers) < mult.MIN_PEERS:
        out.append(f"Warning: only {len(peers)} peer(s); a median of fewer than {mult.MIN_PEERS} is weak evidence.")
    if not same_currency:
        out.append(f"Warning: the company reports in {target.get('reporting_currency')} but trades in {ccy}; "
                   "EV/EBITDA and P/S implied prices are skipped because no FX rate is applied.")
    out += ["## Peers", peers_table]
    return "\n\n".join(out)
