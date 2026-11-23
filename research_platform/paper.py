"""A paper portfolio that follows the recorded signals over historical closes.

A simulation for study: no broker, no orders, no real money. The rules are fixed and
deterministic, so the same signals and prices always give the same result.

Rules
-----
- Long only, no leverage: a buy never spends more than the free cash.
- A signal dated D is acted on at the ticker's first final close after D (the decision
  used closes up to D, so this is the earliest price it could have traded at).
- Target weight of the book, by rating:
    Buy          the risk-based size recorded for that date (ATR-stop sizing; see
                 risk_metrics), or ``fallback_size_pct`` when none was recorded
    Overweight   that size x ``overweight_scale``
    Hold         no trade
    Underweight  the current weight x ``underweight_scale``
    Sell         zero
- Commission and slippage are each charged in basis points of the traded value.
- With ``use_stops``, a position opened or added to by a signal carries that signal's
  long ATR stop. The first close below it sells the whole position at that close
  (a close-only check: an intraday break that recovers does not trigger, and a gap
  fills at the close, not at the stop).
- Each position is valued in its own quote units and the book adds them up as given:
  currencies are not converted. Keep one currency per portfolio for figures that mean
  something; the result notes when it mixed several.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import pandas as pd

from research_platform.config import PAPER_DEFAULTS
from research_platform.prices import CachedPrices, PriceLookup, today
from research_platform.store import Signal
from tradingagents.risk_metrics import metrics as rm


@dataclass
class Trade:
    date: str
    ticker: str
    action: str          # buy | sell
    reason: str          # the rating, or "stop"
    units: float
    price: float
    value: float         # absolute traded value
    cost: float
    note: str = ""


@dataclass
class PaperResult:
    equity: pd.Series                        # book value at each close
    cash: pd.Series
    trades: list[Trade]
    positions: dict[str, float]              # units held at the end
    benchmark: str | None = None
    benchmark_equity: pd.Series | None = None
    notes: list[str] = field(default_factory=list)
    stats: dict[str, float | str | None] = field(default_factory=dict)

    def trades_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.__dict__ for t in self.trades])

    def render(self) -> str:
        s = self.stats
        if not s:
            return "No simulation: " + ("; ".join(self.notes) or "no usable signals")

        def pct(key, signed=True):
            value = s.get(key)
            return "n/a" if value is None else (f"{value:+.2%}" if signed else f"{value:.2%}")

        sharpe = "n/a" if s.get("sharpe") is None else f"{s['sharpe']:.2f}"
        lines = [
            f"Period {s['start']} to {s['end']} · {s['trades']} trades ({s['stop_exits']} stop exits)",
            f"Total return {pct('total_return')} · annualized {pct('annual_return')}",
            f"Volatility {pct('volatility', False)} · max drawdown {pct('max_drawdown', False)} · Sharpe {sharpe}",
            f"Average invested share of the book {s['avg_exposure']:.0%} · costs paid {s['costs']:,.2f}",
        ]
        if self.benchmark_equity is not None:
            lines.append(f"Buy-and-hold {self.benchmark} over the same dates: {pct('benchmark_return')}")
        lines.extend(f"Note: {n}" for n in self.notes)
        return "\n".join(lines)


def _market(ticker: str) -> str:
    """The exchange suffix (``.SR``), ``crypto`` for a pair, or '' for a bare US symbol."""
    if "-" in ticker:
        return "crypto"
    return ticker[ticker.rfind("."):] if "." in ticker and not ticker.endswith((".A", ".B")) else ""


def _target_weight(rating: str, signal: Signal, current_weight: float, p: dict) -> float | None:
    full = signal.size_pct if signal.size_pct is not None else p["fallback_size_pct"]
    if rating == "Buy":
        return full
    if rating == "Overweight":
        return full * p["overweight_scale"]
    if rating == "Underweight":
        return current_weight * p["underweight_scale"]
    if rating == "Sell":
        return 0.0
    return None   # Hold


def simulate(
    signals: Iterable[Signal],
    prices: PriceLookup | None = None,
    params: dict | None = None,
    *,
    end: str | None = None,
    benchmark: str | None = "SPY",
    risk_free: float = 0.0,
) -> PaperResult:
    """Run the paper portfolio over every usable signal up to ``end`` (default today)."""
    p = {**PAPER_DEFAULTS, **(params or {})}
    prices = prices or CachedPrices()
    end = end or today()
    signals = sorted((s for s in signals if s.ok), key=lambda s: (s.date, s.ticker))
    notes: list[str] = []
    empty = pd.Series(dtype=float)
    if not signals:
        return PaperResult(empty, empty, [], {}, notes=["no usable signals recorded yet"])

    start = signals[0].date
    closes: dict[str, pd.Series] = {}
    for ticker in dict.fromkeys(s.ticker for s in signals):
        try:
            series = prices(ticker, start, end)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{ticker} skipped: prices unavailable ({exc})")
            continue
        if series.empty:
            notes.append(f"{ticker} skipped: no closes from {start} to {end}")
            continue
        closes[ticker] = series
    signals = [s for s in signals if s.ticker in closes]
    markets = {_market(s.ticker) for s in signals}
    if len(markets) > 1:
        notes.append("tickers from different markets (" + ", ".join(sorted(m or "US" for m in markets))
                     + "): their prices are added without currency conversion")

    if not closes:
        return PaperResult(empty, empty, [], {}, notes=notes)
    table = pd.DataFrame(closes).sort_index()
    table = table[table.index > pd.Timestamp(start)]
    if table.empty:
        notes.append("no close after the first signal yet")
        return PaperResult(empty, empty, [], {}, notes=notes)
    marks = table.ffill()   # a market closed on a day keeps its last close for valuation

    # Each signal executes on its own ticker's first real close after its date.
    due: dict[pd.Timestamp, list[Signal]] = {}
    for s in signals:
        traded = table[s.ticker].dropna()
        after = traded[traded.index > pd.Timestamp(s.date)]
        if after.empty:
            notes.append(f"{s.ticker} {s.date} {s.rating}: no close after it yet, not acted on")
            continue
        due.setdefault(after.index[0], []).append(s)

    cash = float(p["starting_cash"])
    units: dict[str, float] = {}
    stops: dict[str, float] = {}
    trades: list[Trade] = []
    equity, cash_curve = {}, {}
    cost_rate = (p["commission_bps"] + p["slippage_bps"]) / 10_000

    def book_value(day) -> float:
        return cash + sum(u * marks.at[day, t] for t, u in units.items() if u)

    def trade(day, ticker, delta_value, reason, note=""):
        nonlocal cash
        price = float(table.at[day, ticker])
        cost = abs(delta_value) * cost_rate
        if delta_value > 0 and delta_value + cost > cash:
            delta_value = max(cash / (1 + cost_rate), 0.0)
            cost = delta_value * cost_rate
            note = (note + "; " if note else "") + "scaled down to the free cash"
        if delta_value == 0:
            return
        qty = delta_value / price
        units[ticker] = units.get(ticker, 0.0) + qty
        if abs(units[ticker]) < 1e-12:
            units[ticker] = 0.0
        cash -= delta_value + cost
        trades.append(Trade(f"{day:%Y-%m-%d}", ticker, "buy" if qty > 0 else "sell", reason,
                            abs(qty), price, abs(delta_value), cost, note))

    for day in table.index:
        # 1. Stops, on positions carried into today.
        if p["use_stops"]:
            for ticker, level in list(stops.items()):
                close = table.at[day, ticker]
                if units.get(ticker) and not pd.isna(close) and close < level:
                    trade(day, ticker, -units[ticker] * float(close), "stop",
                          f"close {close:.4g} below stop {level:.4g}")
                    stops.pop(ticker)
        # 2. Signals due today.
        for s in due.get(day, []):
            value = book_value(day)
            held = units.get(s.ticker, 0.0) * float(table.at[day, s.ticker])
            weight = held / value if value > 0 else 0.0
            target = _target_weight(s.rating, s, weight, p)
            if target is None:
                continue
            delta = target * value - held
            if abs(delta) < 1e-9:
                continue
            trade(day, s.ticker, delta, s.rating,
                  "" if s.size_pct is not None or s.rating not in ("Buy", "Overweight")
                  else f"no recorded size; fallback {p['fallback_size_pct']:.0%}")
            if delta > 0 and p["use_stops"] and s.stop_long is not None:
                stops[s.ticker] = s.stop_long
            if not units.get(s.ticker):
                stops.pop(s.ticker, None)
        equity[day] = book_value(day)
        cash_curve[day] = cash

    equity_s, cash_s = pd.Series(equity), pd.Series(cash_curve)
    result = PaperResult(equity_s, cash_s, trades, {t: u for t, u in units.items() if u},
                         benchmark=benchmark, notes=notes)
    if benchmark:
        try:
            bench = prices(benchmark, start, end)
            bench = bench[bench.index >= equity_s.index[0]]
            if not bench.empty:
                result.benchmark_equity = bench / bench.iloc[0] * p["starting_cash"]
        except Exception as exc:  # noqa: BLE001
            notes.append(f"benchmark {benchmark} unavailable ({exc})")
    result.stats = _stats(result, p, risk_free)
    return result


def _stats(result: PaperResult, p: dict, risk_free: float) -> dict:
    eq = result.equity
    if eq.empty:
        return {}
    start_cash = p["starting_cash"]
    total = float(eq.iloc[-1] / start_cash - 1)
    days = max((eq.index[-1] - eq.index[0]).days, 1)
    returns = (pd.concat([pd.Series([start_cash], index=[eq.index[0] - pd.Timedelta(days=1)]), eq])
               .pct_change().dropna())
    vol = rm.annualized_volatility(returns, 252) if len(returns) > 1 else None
    try:
        sharpe = rm.sharpe_ratio(returns, risk_free, 252) if len(returns) > 1 else None
    except rm.RiskMetricsError:
        sharpe = None
    mdd = rm.max_drawdown(pd.concat([pd.Series([start_cash], index=[eq.index[0] - pd.Timedelta(days=1)]), eq]))[0]
    invested = 1 - (result.cash / eq).clip(lower=0, upper=1)
    stats = {
        "start": f"{eq.index[0]:%Y-%m-%d}", "end": f"{eq.index[-1]:%Y-%m-%d}",
        "final_equity": float(eq.iloc[-1]), "total_return": total,
        "annual_return": (1 + total) ** (365 / days) - 1 if days >= 30 else None,
        "volatility": vol, "sharpe": sharpe, "max_drawdown": mdd,
        "trades": len(result.trades), "stop_exits": sum(t.reason == "stop" for t in result.trades),
        "costs": sum(t.cost for t in result.trades), "avg_exposure": float(invested.mean()),
        "benchmark_return": None,
    }
    if result.benchmark_equity is not None and not result.benchmark_equity.empty:
        stats["benchmark_return"] = float(result.benchmark_equity.iloc[-1] / start_cash - 1)
    return stats
