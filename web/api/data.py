"""Read the paper account and the research records and shape them for the API.

Everything here reads: the ledger is opened read-only, the research records are
the files the trader wrote, and OKX is asked only for prices and daily closes,
through a small cache so a dashboard refresh does not hit OKX every time.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trader import jobs, report, rules
from trader.ledger import Ledger
from trader.okx import DAY_MS, OKX, Bar
from trader.paper import Paper
from trader.settings import BENCHMARK, BUDGET_LEARNING_DAYS, WATCHLIST, Coin, Settings
from tradingagents.backtest import BacktestSummary, summarize

PRICE_TTL = 30       # seconds a last price is reused
BARS_TTL = 10 * 60   # seconds a daily candle series is reused
RECORD_NAME = re.compile(r"^full_states_log_(\d{4}-\d{2}-\d{2})\.json$")


@dataclass(frozen=True)
class Account:
    """One account the API serves: where its records are and what it trades."""

    id: str
    kind: str              # "paper"
    ledger_path: Path
    results_dir: Path      # research records: <coin>/.../full_states_log_<trade_date>.json
    memory_log_path: Path  # the settled ratings, scored by tradingagents.backtest
    watchlist: tuple[Coin, ...]

    def coin_of(self, inst: str) -> str | None:
        """The research ticker traded through swap ``inst``; None for an unknown contract."""
        return next((c.research for c in self.watchlist if c.swap == inst), None)


def accounts(settings: Settings) -> dict[str, Account]:
    """The accounts the API serves, by id: the one paper account for now."""
    return {
        "paper": Account(
            "paper", "paper", settings.ledger_path, settings.home / "logs",
            settings.memory_log_path, WATCHLIST,
        )
    }


@contextmanager
def open_ledger(account: Account) -> Iterator[Ledger]:
    """The account's ledger, read-only, closed on exit."""
    ledger = Ledger(account.ledger_path, readonly=True)
    try:
        yield ledger
    finally:
        ledger.db.close()


class Market:
    """OKX quotes behind a TTL cache: a last price for PRICE_TTL, candles for BARS_TTL."""

    def __init__(self, okx: OKX):
        self.okx = okx
        self._cache: dict[tuple, tuple[float, object]] = {}  # key -> (expires at, value)

    def last_price(self, inst: str) -> float:
        return self._cached(("last", inst), PRICE_TTL, lambda: self.okx.last_price(inst))

    def bars(self, inst: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        key = ("bars", inst, bar, start_ms, end_ms)
        return self._cached(key, BARS_TTL, lambda: self.okx.bars(inst, bar, start_ms, end_ms))

    def _cached(self, key: tuple, ttl: float, fetch: Callable[[], object]):
        hit = self._cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        value = fetch()
        self._cache[key] = (time.monotonic() + ttl, value)
        return value


# -- account ------------------------------------------------------------------


def summary(account: Account) -> dict:
    """One entry of GET /api/accounts; the ledger's fields are null until it exists."""
    capital = start = halted = None
    if account.ledger_path.is_file():
        with open_ledger(account) as ledger:
            capital, halted = ledger.get("capital"), ledger.get("halted")
            start = _iso(ledger.get("validation_start"))
    return {
        "id": account.id, "kind": account.kind, "capital": capital,
        "validation_start": start, "halted": halted,
        "watchlist": [
            {"research": c.research, "swap": c.swap, "spot": c.spot} for c in account.watchlist
        ],
    }


def overview(account: Account, ledger: Ledger, market: Market) -> dict:
    now = _now()
    trade_date = jobs.trade_date_for(now)
    paper = Paper(ledger, market, account.watchlist)
    positions = ledger.positions()
    prices = {inst: market.last_price(inst) for inst in positions}
    equity, peak = paper.equity(prices), ledger.get("peak")
    series = report.net_equity(ledger)
    values = [v for _, v in series]
    equal, btc = report.baselines(paper, [t for t, _ in series], values[0]) if series else ([], [])
    today, unknown_today = ledger.cost_of(trade_date)
    month, unknown_month = ledger.cost_since(jobs.month_start_ms(now))
    return {
        "equity": equity,
        "cash": ledger.get("cash"),
        "peak": peak,
        "drawdown": rules.drawdown(equity, peak),
        "halted": ledger.get("halted"),
        "processed_to": _iso(ledger.get("processed_to")),
        "validation_start": _iso(ledger.get("validation_start")),
        "days": max(len(series) - 1, 0),
        "performance": {
            "strategy": _performance(values),
            "equal_weight": _performance(equal),
            "btc": _performance(btc),
        },
        "llm": {
            "trade_date": trade_date,
            "today": today,
            "month": month,
            # budget_cap() would set the cap on a ledger it finds ready; a reader only looks.
            "cap": ledger.get("budget_cap"),
            "learned_days": sum(1 for _, c in ledger.daily_costs(trade_date) if c is not None),
            "learning_days": BUDGET_LEARNING_DAYS,
            "unknown": unknown_today or unknown_month,
        },
        "positions": [
            _position(account, inst, pos, prices[inst]) for inst, pos in positions.items()
        ],
        "latest": _latest(account, ledger, trade_date),
    }


def _performance(values: list[float]) -> dict | None:
    """The metrics of report.performance_line; None with fewer than two points."""
    if len(values) < 2:
        return None
    ann, mdd = report.annualized(values), report.max_drawdown(values)
    return {
        "cumulative": values[-1] / values[0] - 1,
        "annualized": ann,
        "sharpe": report.sharpe(values),
        "max_drawdown": mdd,
        "calmar": ann / mdd if mdd else None,
    }


def _position(account: Account, inst: str, pos, price: float) -> dict:
    return {
        "inst": inst,
        "coin": account.coin_of(inst),
        "qty": pos.qty,
        "entry": pos.entry,
        "stop": pos.stop,
        "price": price,
        "notional": abs(pos.qty) * price,
        "unrealized": pos.qty * (price - pos.entry),
        "stop_distance": abs(pos.stop - price) / price if pos.stop is not None else None,
    }


def _latest(account: Account, ledger: Ledger, trade_date: str) -> dict:
    """The state of the trade date's run: each coin's research and its fills."""
    fills = ledger.db.execute(
        "SELECT inst, qty, price FROM fills WHERE trade_date = ? ORDER BY id", (trade_date,)
    ).fetchall()
    totals = _attempt_totals(ledger)
    coins = []
    for coin in account.watchlist:
        state, detail = jobs.coin_state(ledger, trade_date, coin.research)
        total = totals.get((trade_date, coin.research))
        coins.append({
            "coin": coin.research,
            "state": state,
            "rating": detail if state == "done" else None,
            "error": detail if state == "failed" else None,
            "cost_usd": total["cost_usd"] if total else None,
            "fills": [{"qty": q, "price": p} for inst, q, p in fills if inst == coin.swap],
        })
    return {"trade_date": trade_date, "executed": ledger.executed(trade_date), "coins": coins}


def _attempt_totals(ledger: Ledger) -> dict[tuple[str, str], dict]:
    """Per (trade_date, coin): the rating of the attempt that gave one, the tokens of
    every attempt, and their cost, None once an attempt's cost is unknown."""
    rows = ledger.db.execute(
        "SELECT trade_date, coin, rating, tokens_in, tokens_out, cost_usd FROM attempts ORDER BY id"
    )
    totals: dict[tuple[str, str], dict] = {}
    for trade_date, coin, rating, tokens_in, tokens_out, cost in rows:
        total = totals.setdefault(
            (trade_date, coin), {"rating": None, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
        )
        total["rating"] = total["rating"] or rating
        total["tokens_in"] += tokens_in or 0
        total["tokens_out"] += tokens_out or 0
        known = cost is not None and total["cost_usd"] is not None
        total["cost_usd"] = total["cost_usd"] + cost if known else None
    return totals


def equity(account: Account, ledger: Ledger, market: Market) -> dict:
    """The midnight equity of the validation period against the baselines, and live equity."""
    paper = Paper(ledger, market, account.watchlist)
    live = paper.equity({inst: market.last_price(inst) for inst in ledger.positions()})
    start = ledger.get("validation_start")
    raw = ledger.equity_series(start) if start is not None else []
    points = []
    if raw:
        net = report.net_equity(ledger)  # the same midnights, less the LLM spend
        baselines = _baselines(market, account.watchlist, [t for t, _ in raw], net[0][1])
        points = [
            {"ts": _iso(ts), "strategy": value, "strategy_net": net_value,
             "equal_weight": equal, "btc": btc}
            for (ts, value), (_, net_value), (equal, btc) in zip(raw, net, baselines, strict=True)
        ]
    return {"points": points, "live": {"ts": _iso(_ms(_now())), "equity": live}}


def _baselines(
    market: Market, watchlist: tuple[Coin, ...], midnights: list[int], capital: float
) -> list[tuple[float | None, float | None]]:
    """(equal-weight, BTC-only) buy-and-hold at each midnight, as report.baselines
    prices them, with (None, None) at a midnight whose closes OKX lacks."""
    start = midnights[0]
    closes = {
        coin.research: {
            b.ts: b.close for b in market.bars(coin.spot, "1Dutc", start - DAY_MS, midnights[-1])
        }
        for coin in watchlist
    }
    out = []
    for midnight in midnights:
        if not all(midnight - DAY_MS in s and start - DAY_MS in s for s in closes.values()):
            out.append((None, None))
            continue
        ratios = {c: s[midnight - DAY_MS] / s[start - DAY_MS] for c, s in closes.items()}
        btc = capital * ratios["BTC-USD"] if "BTC-USD" in ratios else None
        out.append((capital * sum(ratios.values()) / len(ratios), btc))
    return out


def fills(account: Account, ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    return [
        {
            "ts": _iso(f.ts), "inst": f.inst, "coin": account.coin_of(f.inst), "qty": f.qty,
            "price": f.price, "fee": f.fee, "reason": f.reason, "trade_date": f.trade_date,
        }
        for f in reversed(ledger.fills(since_ms)[-limit:])
    ]


def funding(account: Account, ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    rows = ledger.db.execute(
        "SELECT ts, inst, rate, amount FROM funding WHERE ts >= ? ORDER BY ts DESC, inst LIMIT ?",
        (since_ms, limit),
    )
    return [
        {"ts": _iso(ts), "inst": inst, "coin": account.coin_of(inst), "rate": rate, "amount": amt}
        for ts, inst, rate, amt in rows
    ]


def events(ledger: Ledger) -> list[dict]:
    rows = ledger.db.execute("SELECT ts, kind, text FROM events ORDER BY id DESC")
    return [{"ts": _iso(ts), "kind": kind, "text": text} for ts, kind, text in rows]


def attempts(ledger: Ledger) -> list[dict]:
    rows = ledger.db.execute(
        "SELECT trade_date, coin, ts, rating, error, tokens_in, tokens_out, cost_usd"
        " FROM attempts ORDER BY id DESC"
    )
    return [
        {
            "trade_date": trade_date, "coin": coin, "ts": _iso(ts), "rating": rating,
            "error": error, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
        }
        for trade_date, coin, ts, rating, error, tokens_in, tokens_out, cost in rows
    ]


def accuracy(account: Account) -> dict:
    """The rating accuracy of the settled ratings; all zero before any rating settled."""
    try:
        scored = summarize(account.memory_log_path)
    except FileNotFoundError:
        scored = BacktestSummary(resolved=0, pending=0, by_rating={})
    return {
        "resolved": scored.resolved,
        "pending": scored.pending,
        "unscored": scored.unscored,
        "holding": scored.holding,
        "benchmark": BENCHMARK,
        "by_rating": {
            rating: {"count": s.count, "hit_rate": s.hit_rate, "mean_alpha": s.mean_alpha}
            for rating, s in scored.by_rating.items()
        },
    }


# -- research -----------------------------------------------------------------


def research_index(account: Account, ledger: Ledger) -> list[dict]:
    """Every research record, newest trade date first and in watchlist order within a
    date. The rating is the record's, else the attempts'; cost and tokens are the attempts'."""
    totals = _attempt_totals(ledger)
    rank = {coin.research: i for i, coin in enumerate(account.watchlist)}
    rows = []
    for path in account.results_dir.glob("*/**/full_states_log_*.json"):
        match = RECORD_NAME.match(path.name)
        if not match:
            continue
        coin, trade_date = path.relative_to(account.results_dir).parts[0], match.group(1)
        total = totals.get((trade_date, coin)) or {}
        rows.append({
            "coin": coin,
            "trade_date": trade_date,
            "rating": _final_rating(path) or total.get("rating"),
            "cost_usd": total.get("cost_usd"),
            "tokens_in": total.get("tokens_in"),
            "tokens_out": total.get("tokens_out"),
        })
    rows.sort(key=lambda r: (rank.get(r["coin"], len(rank)), r["coin"]))
    rows.sort(key=lambda r: r["trade_date"], reverse=True)
    return rows


def _final_rating(path: Path) -> str | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # being written, or not a record
        return None
    return record.get("final_rating") if isinstance(record, dict) else None


def research_record(account: Account, coin: str, trade_date: str) -> bytes | None:
    """The record file of one research run, as written; None when there is none.
    ``coin`` and ``trade_date`` are validated by the route, as they name a path."""
    paths = sorted(account.results_dir.glob(f"{coin}/**/full_states_log_{trade_date}.json"))
    return paths[0].read_bytes() if paths else None


# -- time ---------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _iso(ms: int | None) -> str | None:
    """UTC milliseconds as "2026-11-07T00:00:00Z"; None stays None."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
