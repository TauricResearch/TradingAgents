"""Replaying the intraday rules over recorded signals, offline.

The replay drives the real engine (``IntradayPaper``) hour by hour against the
history store, with the signals the live account recorded (or any other series),
so a change of its parameters or a rule laid over the signals can be measured on
the same hours the live account traded, before anything changes live.
"""

from __future__ import annotations

import itertools
import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from trader import report, rules
from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.intraday.paper import IntradayPaper
from trader.intraday.settings import ATR_BAR, DECISION_MINUTE, DEFAULT_PARAMS, Params
from trader.ledger import Fill, Ledger, Position
from trader.okx import OKXError
from trader.settings import WATCHLIST, Coin

DIRECTIONS = ("Long", "Short")
GUARD_SCOPES = ("coin", "side", "account")

# Makes the hour's signals on the spot: (decision time, the market as of then, the
# positions held) -> signals. A rerun (Issue #28) passes one; a replay of recorded
# signals passes none.
SignalerFn = Callable[[int, "HistoricalOKX", dict[str, Position]], list["Signal"]]


@dataclass(frozen=True)
class Signal:
    ts: int
    coin: str                 # the research key the engine expects, e.g. BTC-USD
    signal: str | None        # Long, Short, Flat, or None when the hour produced none
    conviction: int | None = None


@dataclass(frozen=True)
class Policy:
    """Rules laid over the raw signals before the engine sees them. Everything is off
    by default: the live account follows the signals as they are."""

    # Unit fraction taken at conviction 1, 2 and 3; None sizes every direction alike.
    conviction_weights: tuple[float, float, float] | None = None
    # A reversal (Long after Short or the other way) below this conviction keeps
    # the position instead; 0 follows every reversal.
    flip_min_conviction: int = 0
    # After a stop-out the coin stays flat this many hours; 0 re-enters at once.
    stop_cooldown_hours: int = 0
    # Favorable move from entry, in hourly ATRs, required before the hourly stop
    # tightens toward the price; 0 tightens every hour.
    trail_after_atr: float = 0.0
    # Hourly efficiency ratio (over er_bars hours) below which directional targets
    # are scaled by er_scale; 0 disables it.
    er_threshold: float = 0.0
    er_scale: float = 0.5
    er_bars: int = 24
    # Consecutive Flat signals required while holding a position before flattening
    # (earlier Flats keep the position); 1 flattens on the first Flat.
    flat_confirm: int = 1
    # The three below gate new entries only. A signal that would open a position, or
    # reverse one, is taken as Flat until it passes all of them (so a refused reversal
    # still closes the old position); a position held on the signal's side is left alone.
    # Lowest conviction that opens a position; 0 opens at any.
    entry_min_conviction: int = 0
    # Consecutive signals of one direction required to open (a Flat between them
    # starts the count again, an hour without a signal does not); 1 opens on the first.
    entry_confirm: int = 1
    # Hourly efficiency ratio (over er_bars hours) required to open; 0 disables it.
    entry_er_threshold: float = 0.0
    # After a position closes, however it closed (a Flat, a stop-out, a reversal), the
    # coin opens nothing for this many hours; a reversal then only closes the old
    # position. 0 re-enters at once.
    close_cooldown_hours: int = 0
    # Stop-outs within stop_guard_window_hours that pause new entries for
    # stop_guard_pause_hours after the last of them; 0 disables it. The scope says
    # whose: "coin" counts a coin's stop-outs and pauses that coin, "side" counts and
    # pauses one direction of a coin, "account" counts every coin's and pauses them
    # all. A paused signal that would open or reverse a position is taken as Flat; a
    # position held on the signal's side is left alone.
    stop_guard_stops: int = 0
    stop_guard_window_hours: int = 24
    stop_guard_pause_hours: int = 12
    stop_guard_scope: str = "coin"
    # Each position's stop trails the price at the distance it was opened with
    # (stop_mult times the ATR of that hour) instead of the current ATR's, so it does
    # not tighten when the ATR shrinks; False follows the current ATR.
    stop_at_entry_atr: bool = False

    def __post_init__(self) -> None:
        if self.trail_after_atr < 0:
            raise ValueError(f"trail_after_atr must be >= 0, got {self.trail_after_atr}")
        if not 0.0 <= self.er_threshold <= 1.0:
            raise ValueError(f"er_threshold must be in [0, 1], got {self.er_threshold}")
        if not 0.0 <= self.er_scale <= 1.0:
            raise ValueError(f"er_scale must be in [0, 1], got {self.er_scale}")
        if self.er_bars < 1:
            raise ValueError(f"er_bars must be >= 1, got {self.er_bars}")
        if self.flat_confirm < 1:
            raise ValueError(f"flat_confirm must be >= 1, got {self.flat_confirm}")
        if self.entry_min_conviction < 0:
            raise ValueError(f"entry_min_conviction must be >= 0, got {self.entry_min_conviction}")
        if self.entry_confirm < 1:
            raise ValueError(f"entry_confirm must be >= 1, got {self.entry_confirm}")
        if not 0.0 <= self.entry_er_threshold <= 1.0:
            raise ValueError(f"entry_er_threshold must be in [0, 1], got {self.entry_er_threshold}")
        if self.close_cooldown_hours < 0:
            raise ValueError(f"close_cooldown_hours must be >= 0, got {self.close_cooldown_hours}")
        if self.stop_guard_stops < 0:
            raise ValueError(f"stop_guard_stops must be >= 0, got {self.stop_guard_stops}")
        if self.stop_guard_window_hours < 1:
            raise ValueError(f"stop_guard_window_hours must be >= 1, got {self.stop_guard_window_hours}")
        if self.stop_guard_pause_hours < 1:
            raise ValueError(f"stop_guard_pause_hours must be >= 1, got {self.stop_guard_pause_hours}")
        if self.stop_guard_scope not in GUARD_SCOPES:
            raise ValueError(
                f"stop_guard_scope must be one of {', '.join(GUARD_SCOPES)}, got {self.stop_guard_scope!r}"
            )

    def labels(self) -> dict[str, float]:
        """The engine's weights for the labels this policy emits."""
        if self.conviction_weights is None:
            base = {d: DEFAULT_PARAMS.weights[d] for d in DIRECTIONS}
        else:
            base = {}
            for level, w in enumerate(self.conviction_weights, start=1):
                base[f"Long{level}"] = w
                base[f"Short{level}"] = -w
        weights = {"Flat": 0.0, **base}
        if self.er_threshold > 0 and self.er_scale > 0:
            for label, w in base.items():
                weights[f"{label}_chop"] = w * self.er_scale
        return weights


DEFAULT_POLICY = Policy()


@dataclass
class Result:
    params: Params
    policy: Policy
    capital: float
    equity: list[tuple[int, float]] = field(default_factory=list)  # after each hour
    fills: list[Fill] = field(default_factory=list)
    daily: list[tuple[int, float]] = field(default_factory=list)   # midnight snapshots
    funding: float = 0.0
    exposure: list[float] = field(default_factory=list)            # gross / equity per hour
    halted: bool = False

    @property
    def final_equity(self) -> float:
        return self.equity[-1][1] if self.equity else self.capital

    def metrics(self) -> dict[str, float | int | None]:
        values = [e for _, e in self.equity] or [self.capital]
        daily = [e for _, e in self.daily]
        trades = [f for f in self.fills if f.reason == "trade"]
        stops = [f for f in self.fills if f.reason == "stop"]
        return {
            "return": self.final_equity / self.capital - 1,
            "max_drawdown": report.max_drawdown(values),
            "sharpe": report.sharpe(daily) if len(daily) >= 3 else None,
            "hours": len(self.equity),
            "trades": len(trades),
            "stops": len(stops),
            "kills": sum(1 for f in self.fills if f.reason == "kill"),
            "fees": sum(f.fee for f in self.fills),
            "funding": self.funding,
            "turnover": sum(abs(f.qty * f.price) for f in self.fills),
            "avg_exposure": sum(self.exposure) / len(self.exposure) if self.exposure else 0.0,
            "halted": self.halted,
        }


def efficiency_ratio(market: HistoricalOKX, inst: str, now_ms: int, bars: int = 24) -> float | None:
    """Kaufman efficiency ratio over the last ``bars`` closed hourly changes before
    ``now_ms``: ``|net move| / sum(|hourly moves|)``, in ``[0, 1]``; None when the
    history holds fewer than ``bars + 1`` usable hourly candles."""
    hour = now_ms - now_ms % HOUR_MS
    try:
        hourly = market.bars(inst, ATR_BAR, hour - (bars + 5) * HOUR_MS, hour)
    except OKXError:
        return None
    usable = [b for b in hourly if rules.usable_prices(b.open, b.high, b.low, b.close)]
    if len(usable) < bars + 1:
        return None
    closes = [b.close for b in usable[-(bars + 1):]]
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    return 0.0 if path == 0 else abs(closes[-1] - closes[0]) / path


class _Overlay:
    """Applies a Policy to one hour's raw signals, remembering what it needs between
    hours: the last direction taken per coin, the cooldowns running, the consecutive
    Flat count while a position is held, the run of same-direction signals, and the
    recent stop-outs with the pauses they set, by the stop guard's scope."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.last_direction: dict[str, str] = {}
        self.cooldown_until: dict[str, int] = {}
        self.flat_runs: dict[str, int] = {}
        self.direction_runs: dict[str, tuple[str, int]] = {}
        self.stop_times: dict[tuple[str, ...], list[int]] = {}
        self.paused_until: dict[tuple[str, ...], int] = {}

    def apply(
        self, signals: list[Signal], now_ms: int, *,
        market: HistoricalOKX | None = None,
        swap_of: dict[str, str] | None = None,
        positions: dict[str, Position] | None = None,
    ) -> dict[str, str | None]:
        labels: dict[str, str | None] = {}
        for s in signals:
            inst = (swap_of or {}).get(s.coin)
            pos = (positions or {}).get(inst) if inst else None
            side = None if pos is None or pos.qty == 0 else "Long" if pos.qty > 0 else "Short"
            labels[s.coin] = self._label(s, now_ms, market, inst, side)
        return labels

    def _label(
        self, s: Signal, now_ms: int, market: HistoricalOKX | None,
        inst: str | None, side: str | None,
    ) -> str | None:
        """``side`` is the direction of the position held, None when flat."""
        p, raw = self.policy, s.signal
        if raw is None:
            return None
        if raw not in DIRECTIONS:
            self.direction_runs.pop(s.coin, None)
            if p.flat_confirm > 1 and side is not None:
                self.flat_runs[s.coin] = self.flat_runs.get(s.coin, 0) + 1
                if self.flat_runs[s.coin] < p.flat_confirm:
                    return None
            self.flat_runs.pop(s.coin, None)
            self.last_direction.pop(s.coin, None)
            return raw
        self.flat_runs.pop(s.coin, None)
        direction, run = self.direction_runs.get(s.coin, (raw, 0))
        self.direction_runs[s.coin] = (raw, run + 1 if direction == raw else 1)
        if now_ms < self.cooldown_until.get(s.coin, 0):
            self.last_direction.pop(s.coin, None)
            return "Flat"
        last = self.last_direction.get(s.coin)
        if p.flip_min_conviction and last and raw != last and (s.conviction or 0) < p.flip_min_conviction:
            return None
        if side != raw and not self._may_enter(s, now_ms, market, inst, side):
            self.last_direction.pop(s.coin, None)
            return "Flat"
        chop = False
        if p.er_threshold > 0 and market is not None and inst is not None:
            er = efficiency_ratio(market, inst, now_ms, p.er_bars)
            chop = er is not None and er < p.er_threshold
        if chop and p.er_scale == 0.0:
            self.last_direction.pop(s.coin, None)
            return "Flat"
        self.last_direction[s.coin] = raw
        if p.conviction_weights is None:
            base = raw
        else:
            level = min(max(s.conviction or 1, 1), len(p.conviction_weights))
            base = f"{raw}{level}"
        return f"{base}_chop" if chop else base

    def _may_enter(
        self, s: Signal, now_ms: int, market: HistoricalOKX | None, inst: str | None,
        side: str | None,
    ) -> bool:
        p = self.policy
        # A reversal is a close: the new side waits out the cooldown the close starts.
        if p.close_cooldown_hours and side is not None:
            return False
        if now_ms < self.paused_until.get(self._guard_key(s.coin, s.signal), 0):
            return False
        if (s.conviction or 0) < p.entry_min_conviction:
            return False
        if self.direction_runs[s.coin][1] < p.entry_confirm:
            return False
        if p.entry_er_threshold > 0 and market is not None and inst is not None:
            er = efficiency_ratio(market, inst, now_ms, p.er_bars)
            if er is not None and er < p.entry_er_threshold:
                return False
        return True

    def stopped_out(self, coin: str, at_ms: int, direction: str) -> None:
        """A stop closed the coin's position at ``at_ms``; ``direction`` is the side it held."""
        p = self.policy
        self.flat_runs.pop(coin, None)
        if p.stop_cooldown_hours:
            self._cool(coin, at_ms + p.stop_cooldown_hours * HOUR_MS)
        if p.stop_guard_stops:
            key = self._guard_key(coin, direction)
            since = at_ms - p.stop_guard_window_hours * HOUR_MS
            self.stop_times[key] = [t for t in self.stop_times.get(key, []) if t > since] + [at_ms]
            if len(self.stop_times[key]) >= p.stop_guard_stops:
                self.paused_until[key] = at_ms + p.stop_guard_pause_hours * HOUR_MS

    def closed(self, coin: str, at_ms: int) -> None:
        """The coin's position closed at ``at_ms``, whatever closed it."""
        if self.policy.close_cooldown_hours:
            self._cool(coin, at_ms + self.policy.close_cooldown_hours * HOUR_MS)

    def _cool(self, coin: str, until_ms: int) -> None:
        self.cooldown_until[coin] = max(self.cooldown_until.get(coin, 0), until_ms)
        self.last_direction.pop(coin, None)

    def _guard_key(self, coin: str, direction: str | None) -> tuple[str, ...]:
        scope = self.policy.stop_guard_scope
        if scope == "account":
            return ()
        return (coin,) if scope == "coin" else (coin, direction or "")


def _restate_stops(
    ledger: Ledger, market: HistoricalOKX, before: dict[str, Position],
    after: dict[str, Position], new_fills: list[Fill], now_ms: int, params: Params,
    policy: Policy, distances: dict[str, float],
) -> None:
    """Put the policy's stop rules in place of the hour's tightening, for each position
    that survived the hour on its side (``before`` to ``after``).

    With ``trail_after_atr`` the pre-hour stop holds until the favorable move from entry
    reaches that many hourly ATRs. With ``stop_at_entry_atr`` the stop then trails the
    price at the distance the position opened with, which ``distances`` keeps per
    contract from the hour it opens, instead of the current ATR's. A same-side add
    still tightens toward its fill, at the same distance.
    """
    hour = now_ms - now_ms % HOUR_MS
    changed = False
    for inst in [i for i in distances if i not in after]:
        del distances[inst]
    for inst, cur in after.items():
        old = before.get(inst)
        opened = old is None or (cur.qty > 0) != (old.qty > 0)
        if opened or any(f.inst == inst and f.reason == "stop" for f in new_fills):
            distances[inst] = abs(cur.entry - cur.stop)  # the engine's fresh stop stands
            continue
        try:
            hourly = market.bars(inst, ATR_BAR, hour - (params.atr_bars + 5) * HOUR_MS, hour)
            atr_value = rules.atr(
                [b.high for b in hourly], [b.low for b in hourly], [b.close for b in hourly],
                days=params.atr_bars,
            )
            price = market.last_price(inst)
        except (OKXError, ValueError):
            continue
        if not rules.usable_quote(price, atr_value):
            continue
        gain = (price - old.entry) if old.qty > 0 else (old.entry - price)
        earned = policy.trail_after_atr == 0 or gain >= policy.trail_after_atr * atr_value
        fixed = distances.get(inst) if policy.stop_at_entry_atr else None
        if earned and fixed is None:
            continue  # the engine's tightening stands
        distance = params.stop_mult * atr_value if fixed is None else fixed
        wanted = _trailed(old.stop, price, cur.qty, distance) if earned else old.stop
        trades = [f for f in new_fills if f.inst == inst and f.reason == "trade"]
        if trades and abs(cur.qty) > abs(old.qty):
            wanted = _trailed(wanted, trades[-1].price, cur.qty, distance)
        if cur.stop != wanted:
            cur.stop = wanted
            changed = True
    if changed:
        ledger.commit(positions=after, cash=ledger.get("cash"))


def _trailed(stop: float, price: float, qty: float, distance: float) -> float:
    """``stop`` tightened to ``distance`` from ``price``: below a long, above a short."""
    return rules.tighten(stop, price - distance if qty > 0 else price + distance, qty)


def replay(
    store: HistoryStore, signals: list[Signal], start_ms: int, end_ms: int, *,
    params: Params = DEFAULT_PARAMS, policy: Policy = DEFAULT_POLICY,
    watchlist: tuple[Coin, ...] = WATCHLIST, capital: float = 10_000.0,
    ledger_path: Path | None = None, signaler: SignalerFn | None = None,
    market: HistoricalOKX | None = None,
) -> Result:
    """Run the intraday engine from ``start_ms`` to ``end_ms`` (whole hours, UTC) on
    ``signals``, each hour deciding on the signals recorded in that hour, at the
    minute after the last of them (``DECISION_MINUTE`` when the hour has none).

    With a ``signaler`` the hour's signals are made at ``DECISION_MINUTE`` instead,
    after the hour's minutes are replayed, seeing the positions held then, as the live
    job does; ``signals`` is then ignored.

    The ledger the engine books into is a scratch file (``ledger_path`` to keep it).
    """
    if ledger_path is None:
        ledger_path = Path(tempfile.mkdtemp(prefix="trader-replay-")) / "ledger.sqlite"
    start = start_ms - start_ms % HOUR_MS
    end = end_ms - end_ms % HOUR_MS
    ledger = Ledger(ledger_path)
    # A scratch ledger need not survive a crash: skip the fsync on every statement.
    ledger.db.execute("PRAGMA synchronous=OFF")
    ledger.initialize(capital, start)
    # The baseline is the web's business; the engine would otherwise fetch spot
    # candles for it on its first run. The first snapshot is the engine's too.
    ledger.commit(
        positions={}, cash=capital, snapshots=[(start, capital)],
        meta={"validation_start": start, "baseline_ref": {}},
    )
    market = market if market is not None else HistoricalOKX(store, start)
    market.at(start)
    needs_labels = policy.conviction_weights is not None or policy.er_threshold > 0
    engine_params = replace(params, weights=policy.labels()) if needs_labels else params
    paper = IntradayPaper(ledger, market, watchlist, params=engine_params)
    overlay = _Overlay(policy)
    by_coin = {c.swap: c.research for c in watchlist}
    swap_of = {c.research: c.swap for c in watchlist}
    result = Result(params=params, policy=policy, capital=capital)

    by_hour: dict[int, list[Signal]] = {}
    for s in sorted(signals, key=lambda s: s.ts):
        by_hour.setdefault(s.ts - s.ts % HOUR_MS, []).append(s)

    distances: dict[str, float] = {}  # each open position's stop distance at its opening

    def tell(fills: list[Fill], closed: set[str]) -> None:
        """Tell the overlay of the stop-outs among ``fills`` and of the positions closed:
        a stop or the kill switch always closes one, a trade the contracts in ``closed``."""
        for f in fills:
            coin = by_coin.get(f.inst)
            if coin is None:
                continue
            if f.reason == "stop":
                overlay.stopped_out(coin, f.ts, "Long" if f.qty < 0 else "Short")
            if f.reason != "trade" or f.inst in closed:
                overlay.closed(coin, f.ts)

    seen_fills = 0
    for hour in range(start, end, HOUR_MS):
        hourly = [] if signaler is not None else by_hour.get(hour, [])
        if signaler is not None or not hourly:
            now = hour + DECISION_MINUTE * MINUTE_MS
        else:
            now = max(s.ts for s in hourly)
            now = min(now - now % MINUTE_MS + MINUTE_MS, hour + HOUR_MS - MINUTE_MS)
        market.at(now)
        paper.replay(now)
        fills = ledger.fills()
        tell(fills[seen_fills:], set())
        seen_fills = len(fills)
        positions = ledger.positions()
        if signaler is not None:
            hourly = signaler(now, market, positions)
        latest: dict[str, Signal] = {s.coin: s for s in hourly}  # the last one per coin
        labels = overlay.apply(
            list(latest.values()), now, market=market, swap_of=swap_of, positions=positions,
        )
        if labels:
            paper.execute(labels, now)
            fills, after = ledger.fills(), ledger.positions()
            new_fills = fills[seen_fills:]
            tell(new_fills, {
                inst for inst, old in positions.items()
                if inst not in after or (after[inst].qty > 0) != (old.qty > 0)
            })
            if policy.trail_after_atr > 0 or policy.stop_at_entry_atr:
                _restate_stops(
                    ledger, market, positions, after, new_fills, now, engine_params, policy, distances,
                )
            seen_fills = len(fills)
        result.equity.append((now, _mark(paper, market)))
        result.exposure.append(_gross(paper, market) / result.equity[-1][1])
    # The minutes of the last hour: stops, funding and the closing midnight snapshot.
    market.at(end)
    paper.replay(end)
    result.fills = ledger.fills()
    result.daily = ledger.equity_series()
    result.funding = ledger.db.execute("SELECT COALESCE(SUM(amount), 0) FROM funding").fetchone()[0]
    result.halted = bool(ledger.get("halted"))
    return result


def _mark(paper: IntradayPaper, market: HistoricalOKX) -> float:
    prices = {}
    for inst, pos in paper.ledger.positions().items():
        try:
            prices[inst] = market.last_price(inst)
        except OKXError:
            prices[inst] = pos.entry
    return paper.equity(prices)


def _gross(paper: IntradayPaper, market: HistoricalOKX) -> float:
    gross = 0.0
    for inst, pos in paper.ledger.positions().items():
        try:
            gross += abs(pos.qty) * market.last_price(inst)
        except OKXError:
            gross += abs(pos.qty) * pos.entry
    return gross


# -- signal sources -----------------------------------------------------------

def signals_from_ledger(path: Path, start_ms: int = 0, end_ms: int | None = None) -> list[Signal]:
    """The signals an intraday ledger recorded in ``[start_ms, end_ms)``."""
    db = Ledger(path, readonly=True).db
    rows = db.execute(
        "SELECT ts, coin, signal, conviction FROM signals WHERE ts >= ? AND ts < ? ORDER BY ts, id",
        (start_ms, end_ms if end_ms is not None else 1 << 62),
    ).fetchall()
    return [Signal(ts, coin, signal, conviction) for ts, coin, signal, conviction in rows]


def signals_from_json(path: Path) -> list[Signal]:
    """Signals from a JSON list of {ts, coin, signal, conviction} objects."""
    rows = json.loads(path.read_text())
    return [Signal(int(r["ts"]), r["coin"], r.get("signal"), r.get("conviction")) for r in rows]


# -- grids -------------------------------------------------------------------

def _flag(text: str) -> bool:
    if text in ("on", "off"):
        return text == "on"
    raise ValueError(f"expected on or off, got {text!r}")


_PARAM_TYPES = {"risk": float, "stop_mult": float, "atr_bars": int, "rebalance_threshold": float}
_POLICY_TYPES = {
    "flip_min_conviction": int,
    "stop_cooldown_hours": int,
    "trail_after_atr": float,
    "er_threshold": float,
    "er_scale": float,
    "er_bars": int,
    "flat_confirm": int,
    "entry_min_conviction": int,
    "entry_confirm": int,
    "entry_er_threshold": float,
    "close_cooldown_hours": int,
    "stop_guard_stops": int,
    "stop_guard_window_hours": int,
    "stop_guard_pause_hours": int,
    "stop_guard_scope": str,
    "stop_at_entry_atr": _flag,
}


def parse_grid(param_specs: list[str], policy_specs: list[str]) -> list[tuple[Params, Policy]]:
    """Every combination of ``name=v1,v2,...`` specs: params by the engine's knobs,
    policies by ``conviction_weights=w1/w2/w3`` (or ``off``) and the knobs of
    ``_POLICY_TYPES``. No specs give the single default pair."""
    axes: list[list[tuple[str, str, object]]] = []
    for spec in param_specs:
        name, values = _split(spec)
        if name not in _PARAM_TYPES:
            raise ValueError(f"unknown param {name!r}; choose from {sorted(_PARAM_TYPES)}")
        axes.append([("param", name, _PARAM_TYPES[name](v)) for v in values])
    for spec in policy_specs:
        name, values = _split(spec)
        if name == "conviction_weights":
            axes.append([("policy", name, _weights(v)) for v in values])
        elif name in _POLICY_TYPES:
            axes.append([("policy", name, _POLICY_TYPES[name](v)) for v in values])
        else:
            raise ValueError(
                f"unknown policy knob {name!r}; choose from"
                f" {sorted([*_POLICY_TYPES, 'conviction_weights'])}"
            )
    pairs = []
    for combo in itertools.product(*axes):
        params, policy = DEFAULT_PARAMS, Policy()
        for kind, name, value in combo:
            if kind == "param":
                params = replace(params, **{name: value})
            else:
                policy = replace(policy, **{name: value})
        pairs.append((params, policy))
    return pairs


def _split(spec: str) -> tuple[str, list[str]]:
    name, _, values = spec.partition("=")
    if not values:
        raise ValueError(f"expected name=value[,value...], got {spec!r}")
    return name.strip(), [v.strip() for v in values.split(",")]


def _weights(text: str) -> tuple[float, float, float] | None:
    if text == "off":
        return None
    parts = [float(p) for p in text.split("/")]
    if len(parts) != 3:
        raise ValueError(f"conviction_weights wants w1/w2/w3, got {text!r}")
    return (parts[0], parts[1], parts[2])


def describe(params: Params, policy: Policy) -> str:
    """One line naming what differs from the live defaults; "默认" when nothing does."""
    parts = []
    for name in _PARAM_TYPES:
        if getattr(params, name) != getattr(DEFAULT_PARAMS, name):
            parts.append(f"{name}={getattr(params, name):g}")
    if policy.conviction_weights is not None:
        parts.append("conviction_weights=" + "/".join(f"{w:g}" for w in policy.conviction_weights))
    for name in _POLICY_TYPES:
        val = getattr(policy, name)
        if val != getattr(DEFAULT_POLICY, name):
            text = "on" if val is True else f"{val:g}" if isinstance(val, float) else str(val)
            parts.append(f"{name}={text}")
    return " ".join(parts) or "默认"


