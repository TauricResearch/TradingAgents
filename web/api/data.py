"""Read the accounts and the research records and shape them for the API.

Everything here reads: the ledgers are opened read-only, the research records are
the files the trader wrote, settings.json is read as the trader reads it, and OKX
is asked only for prices and daily closes, through a small cache so a dashboard
refresh does not hit OKX every time.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from trader import jobs, overrides, prices, report, rules, settings as strategy_constants
from trader.intraday import report as intraday_report
from trader.intraday.paper import HOUR_MS
from trader.ledger import Fill, Ledger, Position
from trader.okx import DAY_MS, OKX, REQUEST_ERRORS, Bar
from trader.paper import Paper, _move
from trader.research import build_config
from trader.settings import BENCHMARK, BUDGET_LEARNING_DAYS, WATCHLIST, Coin, Settings
from tradingagents.backtest import BacktestSummary, summarize
from tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from tradingagents.llm_clients.factory import tier_provider
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

PRICE_TTL = 30       # seconds a last price is reused
BARS_TTL = 10 * 60   # seconds a daily candle series is reused
FAILURE_TTL = 20     # seconds OKX is left alone after a request to it failed
MARKET_ERRORS = REQUEST_ERRORS  # what a failed request to OKX raises
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
    intraday: bool = False  # the hourly account (ADR 0006): its LLM spend is in the signals table
    # The account that executes on the exchange (ADR 0008): it follows the intraday
    # account's signals, so it has no LLM spend, ratings or signals of its own.
    demo: bool = False

    def coin_of(self, inst: str) -> str | None:
        """The research ticker traded through swap ``inst``; None for an unknown contract."""
        return next((c.research for c in self.watchlist if c.swap == inst), None)


def accounts(settings: Settings) -> dict[str, Account]:
    """The accounts the API serves, by id, the daily paper account first: the dashboard
    opens the first one. The intraday account (ADR 0006) and the demo account (ADR 0008)
    read the daily research records and keep no memory log, so their paths name files
    that never exist."""
    return {
        "paper": Account(
            "paper", "paper", settings.ledger_path, settings.home / "logs",
            settings.memory_log_path, WATCHLIST,
        ),
        "intraday": Account(
            "intraday", "paper", settings.intraday_ledger_path, settings.home / "logs",
            settings.home / "intraday" / "none.md", WATCHLIST, intraday=True,
        ),
        "demo": Account(
            "demo", "demo", settings.demo_ledger_path, settings.home / "logs",
            settings.home / "demo" / "none.md", WATCHLIST, demo=True,
        ),
    }


@contextmanager
def open_ledger(account: Account) -> Iterator[Ledger]:
    """The account's ledger, read-only, closed on exit."""
    ledger = Ledger(account.ledger_path, readonly=True)
    try:
        yield ledger
    finally:
        ledger.db.close()


class MarketUnavailable(RuntimeError):
    """OKX could not be asked and no earlier answer is held; ``Market.status`` says why."""


class Market:
    """OKX quotes behind a TTL cache: a last price for PRICE_TTL, candles for BARS_TTL.

    When a request to OKX fails (MARKET_ERRORS), the value fetched before, however
    old, is served instead, OKX is left alone for FAILURE_TTL, and ``status`` reports
    the failure until a request succeeds again; a quote never fetched raises
    MarketUnavailable. One request at a time: FastAPI calls this from worker threads.
    """

    def __init__(self, okx: OKX):
        self.okx = okx
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}  # key -> (expires at, value)
        self._failed_at: float | None = None  # monotonic time of the last failure, else None
        self._failed_since_ms: int | None = None  # when the failures began, UTC milliseconds
        self._error: str | None = None

    def last_price(self, inst: str) -> float:
        return self._cached(("last", inst), PRICE_TTL, lambda: self.okx.last_price(inst))

    def bars(self, inst: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        key = ("bars", inst, bar, start_ms, end_ms)
        return self._cached(key, BARS_TTL, lambda: self.okx.bars(inst, bar, start_ms, end_ms))

    def status(self) -> dict:
        """``{"ok": True}`` after a request to OKX succeeded last; else ``ok`` False with
        the ``error`` and ``since`` when the failures began (ISO 8601)."""
        with self._lock:
            if self._failed_at is None:
                return {"ok": True, "error": None, "since": None}
            return {"ok": False, "error": self._error, "since": _iso(self._failed_since_ms)}

    def _cached(self, key: tuple, ttl: float, fetch: Callable[[], object]):
        with self._lock:
            now = time.monotonic()
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
            if self._failed_at is not None and now - self._failed_at < FAILURE_TTL:
                return self._stale(hit)
            try:
                value = fetch()
            except MARKET_ERRORS as exc:
                self._failed_at = time.monotonic()
                if self._failed_since_ms is None:
                    self._failed_since_ms = _ms(_now())
                self._error = f"{type(exc).__name__}: {exc}"[:200]
                return self._stale(hit)
            self._failed_at = self._failed_since_ms = self._error = None
            if key[0] == "bars":  # one candle series per instrument and bar size
                for old in [k for k in self._cache if k[:3] == key[:3] and k != key]:
                    del self._cache[old]
            self._cache[key] = (time.monotonic() + ttl, value)
            return value

    def _stale(self, hit: tuple[float, object] | None):
        if hit is None:
            raise MarketUnavailable(self._error)
        return hit[1]


# -- strategy -----------------------------------------------------------------

# The constants of trader.settings the guide quotes, by their names there.
_CONSTANTS = (
    "RISK_PER_UNIT", "STOP_ATR_MULT", "ATR_DAYS", "RATING_WEIGHTS", "MAX_COIN_EXPOSURE",
    "MAX_GROSS_EXPOSURE", "REBALANCE_THRESHOLD", "TAKER_FEE", "SLIPPAGE", "KILL_DRAWDOWN",
    "MAX_ATTEMPTS", "RETRY_WAIT_SECONDS", "BUDGET_LEARNING_DAYS", "BUDGET_HEADROOM",
    "ANALYSTS", "BENCHMARK",
)


def strategy(settings: Settings) -> dict:
    """GET /api/strategy: the rules the trader runs on, so the guide quotes the code.
    Lower-cased constant names, plus the models and the settlement window of the config."""
    config = build_config(settings)
    out = {name.lower(): getattr(strategy_constants, name) for name in _CONSTANTS}
    out.update(
        watchlist=[c.research for c in WATCHLIST],
        holding_period_days=config["holding_period_days"],
        deep_model=config["deep_think_llm"],
        quick_model=config["quick_think_llm"],
    )
    return out


# -- models -------------------------------------------------------------------

TIERS = ("quick", "deep")  # the catalog's modes, in the order a model's ``modes`` lists them
HISTORY_SHOWN = 20
# Display names of the catalog's providers; a provider missing here shows its id.
PROVIDER_NAMES = {
    "anthropic": "Anthropic", "openai": "OpenAI", "google": "Google", "xai": "xAI",
    "deepseek": "DeepSeek", "qwen": "通义千问", "qwen-cn": "通义千问（中国站）",
    "glm": "智谱 GLM", "glm-cn": "智谱 GLM（中国站）", "kimi": "Kimi", "minimax": "MiniMax",
    "minimax-cn": "MiniMax（中国站）", "mistral": "Mistral", "groq": "Groq", "nvidia": "NVIDIA",
    "ollama": "Ollama（本地）", "azure": "Azure", "bedrock": "Bedrock", "chatgpt": "ChatGPT",
    "openai_compatible": "OpenAI 兼容",
}


def models(settings: Settings, accounts: dict[str, Account]) -> dict:
    """GET /api/models: the models the research runs on, the catalog to choose from, and
    the switches made so far.

    ``settings`` must be read for this request (``Settings.with_overrides``), so
    ``current`` is what the accounts' next run uses: the models and providers of
    ``build_config``, the prices of the settings with the official table's note on the
    model (``price_note``, null when the table lacks the model or has nothing to say),
    ``source`` "settings" when settings.json names the models, else "env", and per
    account with a research fingerprint whether it names the current models
    (``applied``). ``providers`` is the upstream catalog, less the "custom" sentinel, each
    model with its official price, that price's source, date and note, and the modes it
    is offered for; a current model the catalog lacks is appended to its provider,
    ``in_catalog`` false. ``history`` is settings.json's, newest first, HISTORY_SHOWN
    entries at most. ``write_protected`` is whether POST /api/settings/llm wants the
    Bearer token of TRADER_WEB_TOKEN.
    """
    config = build_config(settings)
    current = {
        tier: (config[f"{tier}_think_llm"], tier_provider(config, tier)) for tier in TIERS
    }
    saved = overrides.load(settings.home)
    return {
        "current": {
            "deep": _tier(current["deep"], settings.price_deep),
            "quick": _tier(current["quick"], settings.price_quick),
            "source": "settings" if saved else "env",
            "updated_at": saved.get("updated_at") if saved else None,
            "applied": _applied(accounts, current["deep"][0], current["quick"][0]),
        },
        "providers": _providers(current),
        "history": (saved or {}).get("history", [])[:HISTORY_SHOWN],
        "write_protected": settings.web_token is not None,
    }


def has_key(provider: str) -> bool:
    """Whether the provider's API key is in the environment; a provider that needs no key
    (its env var is None: ollama, bedrock, chatgpt) has one. Unknown providers do not."""
    key_env = PROVIDER_API_KEY_ENV.get(provider, "")
    return key_env is None or bool(os.getenv(key_env, "").strip())


def _tier(model_and_provider: tuple[str, str], price: tuple[float, float] | None) -> dict:
    model, provider = model_and_provider
    return {
        "model": model,
        "provider": provider,
        "price": list(price) if price else None,
        "price_note": _price_note(prices.lookup(model)),
    }


def _price_note(price: prices.Price | None) -> str | None:
    return (price.note if price else None) or None


def _applied(accounts: dict[str, Account], deep: str, quick: str) -> dict[str, bool]:
    """Per account whose ledger holds a research fingerprint: whether it names the current
    models. The daily account's is jobs.fingerprint's {version, deep, quick, code}; the
    intraday account's is the signaler's {model, prompt}, its model the deep one."""
    out = {}
    for account in accounts.values():
        if not account.ledger_path.is_file():
            continue
        with open_ledger(account) as ledger:
            stored = ledger.get("fingerprint")
        if not stored:
            continue
        if "model" in stored:
            out[account.id] = stored["model"] == deep
        else:
            out[account.id] = (stored.get("deep"), stored.get("quick")) == (deep, quick)
    return out


def _providers(current: dict[str, tuple[str, str]]) -> list[dict]:
    """The catalog's providers, then any provider only a current model names."""
    out: dict[str, dict] = {}
    for provider, modes in MODEL_OPTIONS.items():
        listed: dict[str, dict] = {}
        for mode in TIERS:
            for label, model_id in modes.get(mode, []):
                if model_id == "custom":
                    continue
                entry = listed.setdefault(model_id, _model(model_id, label, in_catalog=True))
                entry["modes"].append(mode)
        out[provider] = _provider(provider, list(listed.values()))
    for tier in TIERS:
        model_id, provider = current[tier]
        entry = out.setdefault(provider, _provider(provider, []))
        model = next((m for m in entry["models"] if m["id"] == model_id), None)
        if model is None:
            model = _model(model_id, model_id, in_catalog=False)
            entry["models"].append(model)
        if not model["in_catalog"] and tier not in model["modes"]:
            model["modes"].append(tier)
    return list(out.values())


def _provider(provider: str, listed: list[dict]) -> dict:
    return {
        "id": provider,
        "name": PROVIDER_NAMES.get(provider, provider),
        "has_key": has_key(provider),
        "key_env": PROVIDER_API_KEY_ENV.get(provider),
        "models": listed,
    }


def _model(model_id: str, label: str, in_catalog: bool) -> dict:
    price = prices.lookup(model_id)
    return {
        "id": model_id,
        "label": label,
        "modes": [],
        "price": [price.input, price.output] if price else None,
        "price_source": price.source if price else None,
        "price_as_of": price.as_of if price else None,
        "price_until": price.until if price else None,
        "price_note": _price_note(price),
        "in_catalog": in_catalog,
    }


# -- account ------------------------------------------------------------------


def summary(account: Account) -> dict:
    """One entry of GET /api/accounts; the ledger's fields are null until it exists."""
    capital = start = halted = None
    if account.ledger_path.is_file():
        with open_ledger(account) as ledger:
            capital, halted = ledger.get("capital"), ledger.get("halted")
            start = _iso(ledger.get("validation_start"))
    return {
        "id": account.id, "kind": account.kind, "intraday": account.intraday,
        "demo": account.demo, "capital": capital,
        "validation_start": start, "halted": halted,
        "watchlist": [
            {"research": c.research, "swap": c.swap, "spot": c.spot} for c in account.watchlist
        ],
    }


def overview(account: Account, ledger: Ledger, market: Market) -> dict:
    """GET /api/accounts/{id}/overview. What needs a quote OKX cannot give right now is
    null (``equity``, ``drawdown``, a position's price fields, the baselines); ``market``
    says whether OKX answered (``Market.status``). The ledger's own figures always show."""
    now = _now()
    trade_date = jobs.trade_date_for(now)
    paper = Paper(ledger, market, account.watchlist)
    positions = ledger.positions()
    prices = {inst: _quote(market, inst) for inst in positions}
    equity = _marked(ledger, positions, prices)
    capital, cash, peak = ledger.get("capital"), ledger.get("cash"), ledger.get("peak")
    series = _net_equity(account, ledger)
    values = [v for _, v in series]
    try:
        equal, btc = (
            report.baselines(paper, [t for t, _ in series], values[0]) if series else ([], [])
        )
    except MarketUnavailable:
        equal, btc = [], []
    if account.demo:  # follows the intraday signals: no LLM calls of its own (ADR 0008)
        llm = latest = None
    elif account.intraday:  # spend in the signals table, no budget and no ratings (ADR 0006)
        llm, latest = _intraday_llm(ledger, now), None
    else:
        today, unknown_today = ledger.cost_of(trade_date)
        month, unknown_month = ledger.cost_since(jobs.month_start_ms(now))
        llm = {
            "trade_date": trade_date,
            "today": today,
            "month": month,
            # budget_cap() would set the cap on a ledger it finds ready; a reader only looks.
            "cap": ledger.get("budget_cap"),
            "learned_days": sum(1 for _, c in ledger.daily_costs(trade_date) if c is not None),
            "learning_days": BUDGET_LEARNING_DAYS,
            "unknown": unknown_today or unknown_month,
        }
        latest = _latest(account, ledger, trade_date)
    return {
        "equity": equity,
        "cash": cash,
        "capital": capital,
        "peak": peak,
        "drawdown": rules.drawdown(equity, peak) if equity is not None else None,
        "halted": ledger.get("halted"),
        "processed_to": _iso(ledger.get("processed_to")),
        "validation_start": _iso(ledger.get("validation_start")),
        "days": max(len(series) - 1, 0),
        "today": _today(ledger, equity, now),
        "totals": _totals(capital, cash, equity, positions, prices),
        "performance": {
            "strategy": _performance(values),
            "equal_weight": _performance(equal),
            "btc": _performance(btc),
        },
        "llm": llm,
        "positions": [
            _position(account, inst, pos, prices[inst]) for inst, pos in positions.items()
        ],
        "latest": latest,
        "market": market.status(),
    }


def _quote(market: Market, inst: str) -> float | None:
    """The last price of ``inst``; None when OKX cannot give one now."""
    try:
        return market.last_price(inst)
    except MarketUnavailable:
        return None


def _marked(ledger: Ledger, positions: dict, prices: dict[str, float | None]) -> float | None:
    """Cash plus the positions marked at ``prices``; None when a price is missing."""
    if any(price is None for price in prices.values()):
        return None
    return ledger.get("cash") + sum(
        p.qty * (prices[inst] - p.entry) for inst, p in positions.items()
    )


def _today(ledger: Ledger, equity: float | None, now: datetime) -> dict:
    """The day's PnL: the live equity against the latest midnight snapshot at or before
    today's UTC midnight. The hourly job writes today's at its first run after midnight;
    until then the base is yesterday's, and ``since`` says which. Null without a
    snapshot (``since`` null too) or without the quotes that price ``equity``."""
    midnight = _ms(now.replace(hour=0, minute=0, second=0, microsecond=0))
    row = ledger.db.execute(
        "SELECT ts, equity FROM equity WHERE ts <= ? ORDER BY ts DESC LIMIT 1", (midnight,)
    ).fetchone()
    if row is None or equity is None:
        return {"since": _iso(row[0]) if row else None, "pnl": None, "pct": None}
    since, base = row
    return {"since": _iso(since), "pnl": equity - base, "pct": (equity - base) / base}


def _totals(
    capital: float, cash: float, equity: float | None, positions: dict,
    prices: dict[str, float | None],
) -> dict:
    """The account's sums the way an exchange shows them. Realized is what trading has
    put into the cash since the account opened (fees and funding included); the marked
    sums are null while a position has no quote: a partial sum would read as the whole."""
    marked = equity is not None
    notional = sum(abs(p.qty) * prices[i] for i, p in positions.items()) if marked else None
    return {
        "unrealized": equity - cash if marked else None,
        "notional": notional,
        "leverage": notional / equity if marked and equity else None,
        "realized": cash - capital,
        "pnl": equity - capital if marked else None,
        "pnl_pct": (equity - capital) / capital if marked else None,
    }


def _net_equity(account: Account, ledger: Ledger) -> list[tuple[int, float]]:
    """The midnight equity less the LLM spend: the attempts' for the daily account, the
    signals' for the intraday one; the demo account spends nothing, and its equity is
    the exchange's, already net of fees and funding."""
    if account.demo:
        start = ledger.get("validation_start")
        return ledger.equity_series(start) if start is not None else []
    if account.intraday:
        return intraday_report.net_equity(ledger)
    return report.net_equity(ledger)


def _intraday_llm(ledger: Ledger, now: datetime) -> dict:
    """The intraday account's ``llm``: the signals' spend since UTC midnight and since the
    month began. No budget cap and no learning days: the spend comes off the performance."""
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today, unknown_today = ledger.signal_cost_since(_ms(day))
    month, unknown_month = ledger.signal_cost_since(jobs.month_start_ms(now))
    return {
        "trade_date": day.date().isoformat(),
        "today": today,
        "month": month,
        "cap": None,
        "learned_days": 0,
        "learning_days": 0,
        "unknown": unknown_today or unknown_month,
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


def _position(account: Account, inst: str, pos, price: float | None) -> dict:
    """One open position; the fields priced at ``price`` are null without one.
    ``unrealized_pct`` is the return on the position's value at entry, the sign of the
    side applied, so a short reads positive when the price fell."""
    unrealized = pos.qty * (price - pos.entry) if price is not None else None
    return {
        "inst": inst,
        "coin": account.coin_of(inst),
        "qty": pos.qty,
        "entry": pos.entry,
        "stop": pos.stop,
        "price": price,
        "notional": abs(pos.qty) * price if price is not None else None,
        "unrealized": unrealized,
        "unrealized_pct": (
            unrealized / (abs(pos.qty) * pos.entry) if unrealized is not None else None
        ),
        "stop_distance": (
            abs(pos.stop - price) / price if pos.stop is not None and price is not None else None
        ),
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
    """The midnight equity of the validation period against the baselines, and live
    equity. Without quotes from OKX the live equity and the baselines are null and
    ``market`` says so; the midnight series is the ledger's and always shows."""
    positions = ledger.positions()
    live = _marked(ledger, positions, {inst: _quote(market, inst) for inst in positions})
    start = ledger.get("validation_start")
    raw = ledger.equity_series(start) if start is not None else []
    points = []
    if raw:
        net = _net_equity(account, ledger)  # the same midnights, less the LLM spend
        try:
            baselines = _baselines(market, account.watchlist, [t for t, _ in raw], net[0][1])
        except MarketUnavailable:
            baselines = [(None, None)] * len(raw)
        points = [
            {"ts": _iso(ts), "strategy": value, "strategy_net": net_value,
             "equal_weight": equal, "btc": btc}
            for (ts, value), (_, net_value), (equal, btc) in zip(raw, net, baselines, strict=True)
        ]
    return {
        "points": points,
        "live": {"ts": _iso(_ms(_now())), "equity": live},
        "market": market.status(),
    }


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


def daily(account: Account, ledger: Ledger, market: Market, limit: int) -> dict:
    """GET /api/accounts/{id}/daily: the validation period day by day, newest first,
    and by month. A day runs from one UTC midnight snapshot to the next; the day of the
    last snapshot runs to the live equity and is ``partial`` (null PnL without quotes).
    Each day counts its fills and sums its funding and LLM spend (the attempts' for the
    daily account, the signals' for the intraday one; unknown costs count as zero)."""
    start = ledger.get("validation_start")
    series = ledger.equity_series(start) if start is not None else []
    if not series:
        return {"days": [], "months": [], "market": market.status()}
    positions = ledger.positions()
    live = _marked(ledger, positions, {inst: _quote(market, inst) for inst in positions})
    fills_by_day = Counter(_day_of(f.ts) for f in ledger.fills(start))
    funding_by_day: Counter = Counter()
    for ts, amount in ledger.db.execute("SELECT ts, amount FROM funding WHERE ts >= ?", (start,)):
        funding_by_day[_day_of(ts)] += amount
    costs = ledger.signal_costs(start) if account.intraday else ledger.costs(start)
    cost_by_day: Counter = Counter()
    for ts, cost in costs:
        cost_by_day[_day_of(ts)] += cost or 0.0
    days = []
    for (ts, open_), following in zip(series, [*series[1:], None], strict=True):
        close = following[1] if following else live
        days.append({
            "date": datetime.fromtimestamp(ts / 1000, UTC).date().isoformat(),
            "start_ts": _iso(ts),
            "open": open_,
            "close": close,
            "pnl": close - open_ if close is not None else None,
            "pct": (close - open_) / open_ if close is not None else None,
            "fills": fills_by_day.get(ts, 0),
            "funding": funding_by_day.get(ts, 0.0),
            "llm_cost": cost_by_day.get(ts, 0.0),
            "partial": following is None,
        })
    return {
        "days": days[::-1][:limit],
        "months": _months(days)[::-1],
        "market": market.status(),
    }


def _day_of(ts: int) -> int:
    """The UTC midnight that starts the day of ``ts``, in milliseconds."""
    return ts - ts % DAY_MS


def _months(days: list[dict]) -> list[dict]:
    """The days (oldest first) by calendar month: equity at the month's first midnight
    to its last day's close, oldest month first; ``partial`` while the month has the
    day in progress."""
    out: list[dict] = []
    for day in days:
        month = day["date"][:7]
        if not out or out[-1]["month"] != month:
            out.append({
                "month": month, "open": day["open"], "close": None, "pnl": None, "pct": None,
                "days": 0, "partial": False,
            })
        current, close = out[-1], day["close"]
        current.update(
            close=close,
            pnl=close - current["open"] if close is not None else None,
            pct=(close - current["open"]) / current["open"] if close is not None else None,
            days=current["days"] + 1,
            partial=day["partial"],
        )
    return out


def _replayed(ledger: Ledger) -> list[tuple[Fill, float, float]]:
    """Every fill with the PnL it realized and the signed position it left, in time
    order. The ledger only stores the fills, so they are booked again from the first
    one with the account's own rule (``paper._move``: weighted average entry, a
    reduce realizes on the part closed, a flip on all of the old side)."""
    positions: dict[str, Position] = {}
    out: list[tuple[Fill, float, float]] = []
    for f in ledger.fills():
        old = positions[f.inst].qty if f.inst in positions else 0.0
        new = old + f.qty
        if abs(new) < 1e-9:  # a closing fill is the position rounded, not its negation to the bit
            new = 0.0
        # _move returns realized less the fee it computes on the same notional; add it back.
        net = _move(positions, f.inst, new, f.price, 0.0, f.ts, f.reason, [])
        out.append((f, net + rules.fee((new - old) * f.price), new))
    return out


def fills(account: Account, ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    rows = [row for row in _replayed(ledger) if row[0].ts >= since_ms][-limit:]
    return [
        {
            "ts": _iso(f.ts), "inst": f.inst, "coin": account.coin_of(f.inst), "qty": f.qty,
            "price": f.price, "fee": f.fee, "reason": f.reason, "trade_date": f.trade_date,
            "realized": realized, "realized_net": realized - f.fee, "position_after": after,
        }
        for f, realized, after in reversed(rows)
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


def events(ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    """The events since ``since_ms``, newest first, at most ``limit``."""
    rows = ledger.db.execute(
        "SELECT ts, kind, text FROM events WHERE ts >= ? ORDER BY id DESC LIMIT ?",
        (since_ms, limit),
    )
    return [{"ts": _iso(ts), "kind": kind, "text": text} for ts, kind, text in rows]


def attempts(ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    """The research attempts since ``since_ms``, newest first, at most ``limit``."""
    rows = ledger.db.execute(
        "SELECT trade_date, coin, ts, rating, error, tokens_in, tokens_out, cost_usd"
        " FROM attempts WHERE ts >= ? ORDER BY id DESC LIMIT ?", (since_ms, limit),
    )
    return [
        {
            "trade_date": trade_date, "coin": coin, "ts": _iso(ts), "rating": rating,
            "error": error, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost,
        }
        for trade_date, coin, ts, rating, error, tokens_in, tokens_out, cost in rows
    ]


def signals(account: Account, ledger: Ledger, since_ms: int, limit: int) -> list[dict]:
    """The intraday account's hourly signals, newest first. The daily account has none:
    []. Its ledger is not asked, as a reader does not create the signals table and a
    ledger from before it lacks it. The demo account's are followed_signals."""
    if not account.intraday:
        return []
    return [_signal(row) for row in ledger.signals(since_ms, limit)]


def _signal(row: tuple) -> dict:
    ts, coin, signal, conviction, reason, error, tokens_in, tokens_out, cost = row
    return {
        "ts": _iso(ts), "coin": coin, "signal": signal, "conviction": conviction,
        "reason": reason, "error": error, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": cost,
    }


# What the demo's events of an hour say it did about that hour's signals: an order that
# failed, was refused or did not fill names its contract; a skipped hour (no intraday
# decision in time) and a blocked one (the reconciliation found problems) are whole.
_FOLLOWED_BY_EVENT = {
    "order_failed": "failed", "order_refused": "failed", "order_pending": "failed",
    "skipped": "skipped", "problem": "blocked",
}


def followed_signals(
    account: Account, ledger: Ledger, source: Ledger, since_ms: int, limit: int,
) -> list[dict]:
    """GET /api/accounts/demo/signals: the intraday signals the demo account follows
    (ADR 0008), newest first, each with ``followed``, what the demo did about it that
    hour: executed (a trade of that contract filled), no_change (the hour was handled,
    nothing to trade), skipped, blocked, failed (see _FOLLOWED_BY_EVENT), pending (the
    demo has not handled that hour yet) or None (before the demo account existed)."""
    rows = source.signals(since_ms, limit)
    if not rows:
        return []
    born = ledger.get("processed_to")
    born_hour = born - born % HOUR_MS if born is not None else None
    decided = ledger.get("decided_hour")
    first_hour = min(row[0] for row in rows) // HOUR_MS * HOUR_MS
    swaps = {coin.research: coin.swap for coin in account.watchlist}
    executed = {
        (fill.ts - fill.ts % HOUR_MS, fill.inst) for fill in ledger.fills(first_hour) if fill.reason == "trade"
    }
    by_contract: dict[tuple[int, str], str] = {}
    by_hour: dict[int, str] = {}
    for ts, kind, text in ledger.db.execute(
        "SELECT ts, kind, text FROM events WHERE ts >= ? ORDER BY id", (first_hour,)
    ):
        status = _FOLLOWED_BY_EVENT.get(kind)
        if status is None:
            continue
        hour = ts - ts % HOUR_MS
        if status == "failed":
            for inst in swaps.values():
                if inst in text:
                    by_contract[(hour, inst)] = status
        else:
            by_hour[hour] = status

    def followed(ts: int, coin: str) -> str | None:
        hour = ts - ts % HOUR_MS
        inst = swaps.get(coin)
        if born_hour is None or hour < born_hour:
            return None
        if (hour, inst) in executed:
            return "executed"
        if (hour, inst) in by_contract:
            return by_contract[(hour, inst)]
        if hour in by_hour:
            return by_hour[hour]
        if decided is None or hour > decided:
            return "pending"
        return "no_change"

    return [{**_signal(row), "followed": followed(row[0], row[1])} for row in rows]


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


# A record's final rating by path, with the (mtime, size) of the file it was read
# from: a record is written once, so the index reads each file once, not per request.
_RATINGS: dict[Path, tuple[tuple[int, int], str | None]] = {}


def research_index(account: Account, ledger: Ledger) -> list[dict]:
    """Every research record, newest trade date first and in watchlist order within a
    date. The rating is the record's, else the attempts'; cost and tokens are the attempts'."""
    totals = _attempt_totals(ledger)
    rank = {coin.research: i for i, coin in enumerate(account.watchlist)}
    rows = []
    seen = set()
    for path in account.results_dir.glob("*/**/full_states_log_*.json"):
        match = RECORD_NAME.match(path.name)
        if not match:
            continue
        seen.add(path)
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
    for gone in [p for p in _RATINGS if p not in seen and p.is_relative_to(account.results_dir)]:
        del _RATINGS[gone]
    rows.sort(key=lambda r: (rank.get(r["coin"], len(rank)), r["coin"]))
    rows.sort(key=lambda r: r["trade_date"], reverse=True)
    return rows


def _final_rating(path: Path) -> str | None:
    """The record's final rating, read from the file once per (mtime, size) of it."""
    try:
        stat = path.stat()
    except OSError:
        return None
    version = (stat.st_mtime_ns, stat.st_size)
    hit = _RATINGS.get(path)
    if hit is not None and hit[0] == version:
        return hit[1]
    rating = _read_rating(path)
    _RATINGS[path] = (version, rating)
    return rating


def _read_rating(path: Path) -> str | None:
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


# -- the demo account (ADR 0008) ----------------------------------------------------


def execution(account: Account, ledger: Ledger) -> dict:
    """GET /api/accounts/{id}/execution: the demo account's last reconciliation with the
    exchange, as its job left it in the ledger (ADR 0008): the exchange's equity and
    wallet, what it held and had pending, the hour last followed and the problems found.
    Nothing here is live; ``synced_at`` says how old it is."""
    positions = ledger.positions()
    held = ledger.get("exchange_positions") or {}
    return {
        "synced_at": _iso(ledger.get("synced_at")),
        "equity": ledger.get("equity"),
        "cash": ledger.get("cash"),
        "halted": ledger.get("halted"),
        "decided_hour": _iso(ledger.get("decided_hour")),
        "problems": list(ledger.get("problems") or []),
        "positions": [
            {
                "inst": inst,
                "coin": account.coin_of(inst),
                "contracts": p.get("contracts"),
                "avg_price": p.get("avg_price"),
                "unrealized": p.get("unrealized"),
                "leverage": p.get("leverage"),
                "margin_mode": p.get("margin_mode"),
                "liquidation_price": p.get("liquidation_price"),
                "stop": positions[inst].stop if inst in positions else None,
            }
            for inst, p in sorted(held.items())
        ],
        "stops": [
            {
                "inst": s.get("inst"),
                "coin": account.coin_of(s.get("inst", "")),
                "side": s.get("side"),
                "contracts": s.get("contracts"),
                "trigger": s.get("trigger"),
                "client_id": s.get("client_id"),
            }
            for s in ledger.get("pending_stops") or []
        ],
    }


def mirror(account: Account, ledger: Ledger, source: Ledger, limit: int) -> dict:
    """GET /api/accounts/{id}/mirror: the demo account beside the intraday account it
    follows (ADR 0008). ``positions`` puts both sides of each coin together; ``trades``
    lists the demo's trades newest first, each with the intraday fill of the same hour
    and contract and the slippage between the two prices (basis points, positive when
    the demo paid more for what it bought or got less for what it sold); ``equity``
    is both accounts' return since the demo's first midnight, where both have a snapshot."""
    mine, theirs = ledger.positions(), source.positions()
    positions = [
        {
            "inst": coin.swap,
            "coin": coin.research,
            "demo": _side(mine.get(coin.swap)),
            "intraday": _side(theirs.get(coin.swap)),
            "same_side": _sign(mine.get(coin.swap)) == _sign(theirs.get(coin.swap)),
        }
        for coin in account.watchlist
    ]
    start = ledger.get("validation_start")
    trades, equity = [], []
    if start is not None:
        source_fills = {
            (f.ts - f.ts % HOUR_MS, f.inst): f
            for f in source.fills(start) if f.reason == "trade"
        }
        for f in reversed([f for f in ledger.fills(start) if f.reason == "trade"][-limit:]):
            hour = f.ts - f.ts % HOUR_MS
            match = source_fills.get((hour, f.inst))
            slippage = None
            if match is not None and match.price:
                side = 1.0 if f.qty > 0 else -1.0
                slippage = (f.price - match.price) / match.price * side * 10_000
            trades.append({
                "hour": _iso(hour),
                "inst": f.inst,
                "coin": account.coin_of(f.inst),
                "demo": {"ts": _iso(f.ts), "qty": f.qty, "price": f.price, "fee": f.fee},
                "intraday": (
                    {"ts": _iso(match.ts), "qty": match.qty, "price": match.price, "fee": match.fee}
                    if match is not None else None
                ),
                "slippage_bps": slippage,
            })
        own = dict(ledger.equity_series(start))
        other = dict(source.equity_series(start))
        shared = sorted(set(own) & set(other))
        if shared:
            base_own, base_other = own[shared[0]], other[shared[0]]
            equity = [
                {
                    "ts": _iso(ts),
                    "demo": own[ts] / base_own - 1 if base_own else None,
                    "intraday": other[ts] / base_other - 1 if base_other else None,
                }
                for ts in shared
            ]
    slippages = [t["slippage_bps"] for t in trades if t["slippage_bps"] is not None]
    return {
        "positions": positions,
        "trades": trades,
        "equity": equity,
        "summary": {
            "trades": len(trades),
            "matched": len(slippages),
            "avg_slippage_bps": sum(slippages) / len(slippages) if slippages else None,
            "demo_return": equity[-1]["demo"] if equity else None,
            "intraday_return": equity[-1]["intraday"] if equity else None,
        },
    }


def _side(pos: Position | None) -> dict | None:
    if pos is None:
        return None
    return {"qty": pos.qty, "entry": pos.entry, "stop": pos.stop}


def _sign(pos: Position | None) -> int:
    if pos is None or pos.qty == 0:
        return 0
    return 1 if pos.qty > 0 else -1


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _iso(ms: int | None) -> str | None:
    """UTC milliseconds as "2026-11-07T00:00:00Z"; None stays None."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
