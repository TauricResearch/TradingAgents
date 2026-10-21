"""Deterministic, broker-disconnected GBP paper portfolio for US equities.

All signals are submitted AFTER the dated close; fills occur at the NEXT
available session's open. This is a forward paper ledger, not a historical
backtest and not a brokerage interface. No real trades can be sent here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
from math import floor, isfinite


@dataclass(frozen=True)
class Rules:
    initial_gbp: float = 10_000.0
    risk_fraction: float = 0.02
    combined_risk_fraction: float = 0.06
    max_positions: int = 5
    max_name_fraction: float = 0.30
    max_exposure_fraction: float = 1.00
    drawdown_halt_fraction: float = 0.10
    max_holding_sessions: int = 20
    slippage_fraction: float = 0.001
    fx_fee_fraction: float = 0.0015


@dataclass(frozen=True)
class Bar:
    open: float
    high: float
    low: float
    close: float

    def valid(self) -> bool:
        return all(isfinite(v) and v > 0 for v in (self.open, self.high, self.low, self.close)) and (
            self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high
        )


@dataclass
class Book:
    started: str
    cash_gbp: float = 10_000.0
    peak_gbp: float = 10_000.0
    halted: bool = False
    last_session: str | None = None
    positions: dict = field(default_factory=dict)
    orders: list = field(default_factory=list)
    events: list = field(default_factory=list)
    equity_history: list = field(default_factory=list)
    completed: list = field(default_factory=list)
    benchmark_start_gbp: float | None = None
    sequence: int = 0
    rules: dict = field(default_factory=lambda: asdict(Rules()))

    @classmethod
    def new(cls, started: str) -> Book:
        date.fromisoformat(started)
        return cls(started=started)

    @classmethod
    def load(cls, raw: dict) -> Book:
        unknown = set(raw) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown paper-book fields: {sorted(unknown)}")
        book = cls(**raw)
        if book.rules != asdict(Rules()):
            raise ValueError("Unrecognized risk configuration; refuse to load")
        return book

    @property
    def settings(self) -> Rules:
        return Rules(**self.rules)

    def equity(self) -> float:
        return self.cash_gbp + sum(
            p["shares"] * p["mark_usd"] * p["mark_gbp_per_usd"]
            for p in self.positions.values()
        )

    def _event(self, session: str, kind: str, **details):
        self.events.append({"date": session, "type": kind, **details})

    def _id(self) -> str:
        self.sequence += 1
        return f"P{self.sequence:06d}"

    def submit_signal(self, ticker: str, rating: str, close_usd: float,
                      session: str, stop_fraction: float = 0.08) -> bool:
        """Enqueue a single next-session order; LLM output cannot bypass the rules.

        BUY/Overweight opens when flat, Sell/Underweight exits if held; Hold/REVIEW
        produces no order. Deduplicates orders for the same ticker. A user cannot
        submit a signal before the corresponding session has been marked.
        """
        if session != self.last_session:
            raise ValueError("Signals must follow the latest completed session")
        ticker = ticker.strip().upper()
        if not ticker or not all(c.isalnum() or c in '.-' for c in ticker):
            raise ValueError("Invalid stock ticker")
        if not isfinite(close_usd) or close_usd <= 0:
            raise ValueError("Invalid closing price")
        if not 0.01 <= stop_fraction <= 0.30:
            raise ValueError("Stop distance must be between 1% and 30%")
        if any(o["ticker"] == ticker for o in self.orders):
            self._event(session, "IGNORED_DUPLICATE", ticker=ticker, rating=rating)
            return False
        held = ticker in self.positions
        action = None
        if rating in ("Buy", "Overweight") and not held and not self.halted:
            action = "BUY"
        elif rating in ("Sell", "Underweight") and held:
            action = "SELL"
        if action is None:
            self._event(session, "NO_ORDER", ticker=ticker, rating=rating)
            return False
        order = {"id": self._id(), "ticker": ticker, "side": action,
                 "created": session, "rating": rating}
        if action == "BUY":
            order["stop_usd"] = round(close_usd * (1 - stop_fraction), 6)
        self.orders.append(order)
        self._event(session, "ORDER_QUEUED", **order)
        return True

    def _sell(self, ticker: str, usd_price: float, fx: float, day: str, why: str):
        p = self.positions.pop(ticker)
        qty = p["shares"]
        execution_usd = usd_price * (1 - self.settings.slippage_fraction)
        proceeds = qty * execution_usd * fx * (1 - self.settings.fx_fee_fraction)
        pnl = proceeds - p["cost_gbp"]
        self.cash_gbp += proceeds
        trade = {"ticker": ticker, "shares": qty, "entry_date": p["entry_date"],
                 "exit_date": day, "reason": why, "entry_usd": p["entry_usd"],
                 "exit_usd": execution_usd, "pnl_gbp": round(pnl, 2),
                 "return_fraction": pnl / p["cost_gbp"]}
        self.completed.append(trade)
        self._event(day, "SELL_FILLED", **trade)

    def _risk_at_stops(self, fx: float) -> float:
        return sum(max(0.0, p["cost_gbp"] - p["shares"] * p["stop_usd"]
                       * (1 - self.settings.slippage_fraction) * fx
                       * (1 - self.settings.fx_fee_fraction))
                   for p in self.positions.values())

    def _buy(self, order: dict, usd_open: float, fx: float, day: str):
        rules = self.settings
        ticker = order["ticker"]
        if self.halted or len(self.positions) >= rules.max_positions:
            self._event(day, "ORDER_REJECTED", id=order["id"], reason="halt_or_position_limit")
            return
        execution_usd = usd_open * (1 + rules.slippage_fraction)
        stop_usd = order["stop_usd"]
        if stop_usd >= execution_usd:
            self._event(day, "ORDER_REJECTED", id=order["id"], reason="stop_above_entry")
            return
        equity_open = self.equity()
        entry_cost_per_share = execution_usd * fx * (1 + rules.fx_fee_fraction)
        stop_net_per_share = stop_usd * (1 - rules.slippage_fraction) * fx * (1 - rules.fx_fee_fraction)
        risk_per_share = entry_cost_per_share - stop_net_per_share
        room_gbp = equity_open * rules.combined_risk_fraction - self._risk_at_stops(fx)
        risk_budget = min(equity_open * rules.risk_fraction, room_gbp)
        existing_value = sum(p["shares"] * p["mark_usd"] * fx
                             for p in self.positions.values())
        spend_budget = min(self.cash_gbp, equity_open * rules.max_name_fraction,
                           equity_open * rules.max_exposure_fraction - existing_value)
        qty = floor(min(risk_budget / risk_per_share, spend_budget / entry_cost_per_share))
        if qty < 1:
            self._event(day, "ORDER_REJECTED", id=order["id"], reason="insufficient_cash_or_risk")
            return
        cost = qty * entry_cost_per_share
        self.cash_gbp -= cost
        self.positions[ticker] = {
            "ticker": ticker, "shares": qty, "entry_date": day,
            "entry_usd": execution_usd, "cost_gbp": cost, "stop_usd": stop_usd,
            "mark_usd": usd_open, "mark_gbp_per_usd": fx,
            "held_sessions": 0, "planned_risk_gbp": qty * risk_per_share,
        }
        self._event(day, "BUY_FILLED", id=order["id"], ticker=ticker, shares=qty,
                    usd_price=execution_usd, stop_usd=stop_usd,
                    cost_gbp=round(cost, 2), planned_risk_gbp=round(qty * risk_per_share, 2))

    def step(self, session: str, bars: dict[str, Bar], gbp_per_usd_open: float,
             gbp_per_usd_close: float, spy_close_usd: float) -> Book:
        """Return a new book; invalid input never mutates the saved ledger.

        Requires complete bars for every held/pending symbol, with SPY close and
        FX provided separately. A missing price fails closed. A session may be
        processed once, strictly after the paper account's start date.
        """
        date.fromisoformat(session)
        if session < self.started or (self.last_session and session <= self.last_session):
            raise ValueError("Session must be on/after start and strictly newer than last")
        if any(not isfinite(x) or x <= 0 for x in
               (gbp_per_usd_open, gbp_per_usd_close, spy_close_usd)):
            raise ValueError("Invalid currency or benchmark quote")
        required = set(self.positions) | {o["ticker"] for o in self.orders}
        missing = required - set(bars)
        if missing:
            raise ValueError(f"Missing session bar(s): {', '.join(sorted(missing))}")
        if any(not bars[ticker].valid() for ticker in required):
            raise ValueError("Invalid OHLC bar")
        b = deepcopy(self)
        # Mark *all* existing holdings to today's open before sizing new orders.
        for ticker, p in b.positions.items():
            p["mark_usd"] = bars[ticker].open
            p["mark_gbp_per_usd"] = gbp_per_usd_open
        pending, b.orders = b.orders, []
        for order in sorted(pending, key=lambda x: (x["side"] != "SELL", x["id"])):
            if order["created"] >= session:
                b.orders.append(order)  # never fill orders on their signal day
                continue
            ticker = order["ticker"]
            if order["side"] == "SELL" and ticker in b.positions:
                b._sell(ticker, bars[ticker].open, gbp_per_usd_open, session, "SIGNAL")
            elif order["side"] == "BUY" and ticker not in b.positions:
                b._buy(order, bars[ticker].open, gbp_per_usd_open, session)
            else:
                b._event(session, "ORDER_REJECTED", id=order["id"], reason="invalid_position")
        # Stops are checked on the same session after opening fills. A gap beyond
        # the stop fills at the worse OPEN, not the theoretical stop price.
        for ticker in list(b.positions):
            p = b.positions[ticker]
            bar = bars[ticker]
            if bar.low <= p["stop_usd"]:
                exit_usd = min(bar.open, p["stop_usd"])
                b._sell(ticker, exit_usd,
                        gbp_per_usd_open if bar.open <= p["stop_usd"] else gbp_per_usd_close,
                        session, "STOP")
                continue
            p["mark_usd"] = bar.close
            p["mark_gbp_per_usd"] = gbp_per_usd_close
            p["held_sessions"] += 1
            if p["held_sessions"] >= b.settings.max_holding_sessions:
                if not any(o["ticker"] == ticker for o in b.orders):
                    order = {"id": b._id(), "ticker": ticker, "side": "SELL",
                             "created": session, "rating": "TIME_EXIT"}
                    b.orders.append(order)
                    b._event(session, "ORDER_QUEUED", **order)
        equity = b.equity()
        b.peak_gbp = max(b.peak_gbp, equity)
        drawdown = 1 - equity / b.peak_gbp
        if drawdown >= b.settings.drawdown_halt_fraction and not b.halted:
            b.halted = True
            b.orders = [o for o in b.orders if o["side"] != "BUY"]
            b._event(session, "DRAWDOWN_HALT", drawdown=drawdown)
        spy_gbp = spy_close_usd * gbp_per_usd_close
        if b.benchmark_start_gbp is None:
            b.benchmark_start_gbp = spy_gbp
        b.equity_history.append({"date": session, "equity_gbp": round(equity, 2),
                                 "cash_gbp": round(b.cash_gbp, 2),
                                 "drawdown": round(drawdown, 6),
                                 "spy_benchmark_gbp": round(b.settings.initial_gbp * spy_gbp
                                                            / b.benchmark_start_gbp, 2)})
        b.last_session = session
        b._event(session, "SESSION_MARK", equity_gbp=round(equity, 2),
                 benchmark_gbp=b.equity_history[-1]["spy_benchmark_gbp"])
        return b
