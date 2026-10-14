"""Record signals before their outcome exists, then score later session opens.

This is a directional signal experiment, not an execution or portfolio simulator.
The ledger only appends: protocol, decisions, fill legs, and a fixed-sample verdict.
Price sources must supply a complete, consistently adjusted session series with
actual exchange open/close instants, not midnight labels for daily bars.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import closing, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import mean, stdev

_DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return value


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_fingerprint(config: dict) -> str:
    """Hash JSON-compatible run settings; the settings themselves are not saved."""
    return hashlib.sha256(_json(config).encode()).hexdigest()


@dataclass(frozen=True)
class EvaluationConfig:
    tickers: tuple[str, ...]
    horizon_sessions: int = 1
    cost_bps_per_side: float = 2.0
    min_sessions: int = 40
    min_sharpe: float = 1.0
    must_beat_baselines: bool = True
    sessions_per_year: int = 252

    def __post_init__(self):
        object.__setattr__(self, "tickers", tuple(self.tickers))
        if not self.tickers or len(set(self.tickers)) != len(self.tickers):
            raise ValueError("declare a non-empty universe without duplicate tickers")
        if any(not isinstance(t, str) or not t.strip() for t in self.tickers):
            raise ValueError("tickers must be non-empty strings")
        for name, minimum in (
            ("horizon_sessions", 1),
            ("min_sessions", 2),
            ("sessions_per_year", 1),
        ):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if not math.isfinite(self.cost_bps_per_side) or self.cost_bps_per_side < 0:
            raise ValueError("cost_bps_per_side must be finite and non-negative")
        if not math.isfinite(self.min_sharpe) or type(self.must_beat_baselines) is not bool:
            raise ValueError("declare a finite Sharpe threshold and a boolean baseline rule")


@dataclass(frozen=True)
class ModelDeclaration:
    model_id: str
    provider: str
    knowledge_cutoff: str | None = None

    def __post_init__(self):
        if not self.model_id or not self.provider:
            raise ValueError("declare each model id and provider")
        if self.knowledge_cutoff is not None:
            date.fromisoformat(self.knowledge_cutoff)


@dataclass(frozen=True)
class PriceBar:
    open_at: datetime
    open: float
    close_at: datetime | None = None
    close: float | None = None

    def __post_init__(self):
        _aware(self.open_at)
        if not math.isfinite(self.open) or self.open <= 0:
            raise ValueError("open must be finite and positive")
        if (self.close_at is None) != (self.close is None):
            raise ValueError("close_at and close must be supplied together")
        if self.close_at is not None:
            if _aware(self.close_at) <= self.open_at:
                raise ValueError("close must follow open")
            if not math.isfinite(self.close) or self.close <= 0:
                raise ValueError("close must be finite and positive")


# An adapter may read a cache, fetch a vendor, or return synthetic bars offline.
PriceSource = Callable[[str], Iterable[PriceBar]]


def _bars(source: PriceSource, ticker: str) -> list[PriceBar]:
    bars = sorted(source(ticker), key=lambda b: b.open_at)
    if len({b.open_at for b in bars}) != len(bars):
        raise ValueError(f"duplicate session opens for {ticker}")
    return bars


def _stats(returns: list[float], gross: list[float], annualization: float) -> dict:
    deviation = stdev(returns) if len(returns) >= 2 else 0
    return {
        "sessions": len(returns),
        "returns": returns,
        "mean_return": mean(returns) if returns else None,
        "sharpe": mean(returns) / deviation * math.sqrt(annualization) if deviation else None,
        "hit_rate": sum(r > 0 for r in gross) / len(gross) if gross else None,
        "positions": len(gross),
    }


class ForwardEvaluation:
    """An append-only SQLite ledger. Opening it never starts the graph or fetches prices."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        protocol = self._events().get(("protocol", "protocol"))
        if protocol is None or protocol["version"] != 1:
            raise ValueError("not a supported forward-evaluation ledger")
        self.protocol = protocol
        self.config = EvaluationConfig(**protocol["evaluation"])

    @classmethod
    def create(
        cls,
        path: str | Path,
        config: EvaluationConfig,
        models: Iterable[ModelDeclaration],
        run_config: dict,
    ) -> ForwardEvaluation:
        """Declare the experiment before any decisions/results; never replace a ledger."""
        models = [asdict(m) for m in models]
        if not models:
            raise ValueError("declare at least one model (unknown cutoff is None)")
        protocol = {
            "version": 1,
            "registered_at": _utcnow().isoformat(),
            "evaluation": asdict(config),
            "models": models,
            "config_fingerprint": config_fingerprint(run_config),
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also prevents an accidental experiment reset.
        with path.open("xb"):
            pass
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE events (kind TEXT, key TEXT, payload TEXT NOT NULL, "
                "PRIMARY KEY (kind, key))"
            )
            for operation in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER no_{operation.lower()} BEFORE {operation} ON events "
                    "BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END"
                )
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?)", ("protocol", "protocol", _json(protocol))
            )
        return cls(path)

    def _events(self) -> dict:
        with closing(sqlite3.connect(self.path)) as db:
            return {
                (kind, key): json.loads(payload)
                for kind, key, payload in db.execute("SELECT kind, key, payload FROM events")
            }

    def _append(self, kind: str, key: str, payload: dict) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if kind == "decision":
                # Stamp after fetching history AND acquiring the write lock. A
                # slow adapter must not backdate a decision past the entry open.
                recorded_at = _utcnow()
                payload["recorded_at"] = recorded_at.isoformat()
                payload["retrospective"] = recorded_at >= datetime.fromisoformat(
                    payload["entry_at"]
                )
            db.execute("INSERT INTO events VALUES (?, ?, ?)", (kind, key, _json(payload)))

    def record(
        self,
        ticker: str,
        decision_date: str,
        action: str,
        next_open: datetime,
        prices: PriceSource,
        run_config: dict,
        *,
        size: float | None = None,
        confidence: float | None = None,
    ) -> dict:
        """Record immediately after propagate(), before the scheduled next open.

        ``next_open`` comes from the exchange calendar in its timezone; it is not
        inferred by skipping already-traded bars. Late records remain visible as
        retrospective. Momentum uses only completed closes known at recording.
        Size/confidence are metadata, not invented quantities or sizing weights.
        """
        recorded_at = _utcnow()
        next_open = _aware(next_open)
        day = date.fromisoformat(decision_date)
        if day.isoformat() != decision_date or next_open.date() <= day:
            raise ValueError(
                "next_open must be a session after decision_date in the exchange timezone"
            )
        if ticker not in self.config.tickers:
            raise ValueError("ticker is outside the registered universe")
        action = action.capitalize() if action.upper() != "REVIEW" else "REVIEW"
        if action not in {*_DIRECTION, "REVIEW"}:
            raise ValueError("action must be a five-tier rating or REVIEW")
        if config_fingerprint(run_config) != self.protocol["config_fingerprint"]:
            raise ValueError("run settings changed; start a separate experiment")
        if size is not None and (not math.isfinite(size) or size < 0):
            raise ValueError("size must be finite and non-negative")
        if confidence is not None and (not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("confidence must be in [0, 1]")
        cutoff = min(recorded_at, next_open)
        closes = [
            b.close for b in _bars(prices, ticker) if b.close_at is not None and b.close_at < cutoff
        ]
        momentum = closes[-1] / closes[-22] - 1 if len(closes) >= 22 else None
        decision = {
            "ticker": ticker,
            "decision_date": decision_date,
            "action": action,
            "size": size,
            "confidence": confidence,
            "entry_at": next_open.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "momentum_21": momentum,
            "retrospective": recorded_at >= next_open,
            "models": self.protocol["models"],
            "config_fingerprint": self.protocol["config_fingerprint"],
        }
        # One sampling per ticker/date. A rerun cannot replace an unfavourable call.
        self._append("decision", _json([decision_date, ticker]), decision)
        return decision

    def score(self, prices: PriceSource) -> dict:
        """Append available fill legs, never future prices or revised already-filled legs."""
        now = _utcnow()
        events = self._events()
        cache = {}
        for (kind, key), decision in events.items():
            if kind != "decision" or decision["retrospective"]:
                continue
            if ("exit", key) in events or ("invalid", key) in events:
                continue
            ticker = decision["ticker"]
            if ticker not in cache:
                cache[ticker] = _bars(prices, ticker)
            entry_at = datetime.fromisoformat(decision["entry_at"])
            bars = [b for b in cache[ticker] if b.open_at <= now]
            # Check that the calendar supplied the actual NEXT session, not an
            # arbitrary later open selected after seeing an earlier outcome.
            after_date = [
                b
                for b in bars
                if b.open_at.astimezone(entry_at.tzinfo).date()
                > date.fromisoformat(decision["decision_date"])
            ]
            if after_date and after_date[0].open_at < entry_at:
                with suppress(sqlite3.IntegrityError):
                    self._append("invalid", key, {"reason": "scheduled entry is not the next open"})
                continue
            window = [b for b in bars if b.open_at >= entry_at]
            if not window or window[0].open_at != entry_at:
                continue  # missing entry: never silently shift to a later session
            for leg, index in (("entry", 0), ("exit", self.config.horizon_sessions)):
                if (leg, key) not in events and len(window) > index:
                    bar = window[index]
                    # Another scorer may already have appended this immutable leg.
                    with suppress(sqlite3.IntegrityError):
                        self._append(
                            leg,
                            key,
                            {
                                "at": bar.open_at.isoformat(),
                                "price": bar.open,
                                "scored_at": now.isoformat(),
                            },
                        )
        summary = self.summary()
        if summary["verdict"] != "insufficient" and ("verdict", "verdict") not in self._events():
            with suppress(sqlite3.IntegrityError):
                self._append(
                    "verdict",
                    "verdict",
                    {
                        "verdict": summary["verdict"],
                        "sessions": summary["verdict_sessions"],
                        "sharpes": summary["verdict_sharpes"],
                        "scored_at": now.isoformat(),
                    },
                )
        return self.summary()

    def summary(self) -> dict:
        """Equal-weight, unit directional returns; whole incomplete sessions stay out."""
        events = self._events()
        sessions = defaultdict(dict)
        retrospective = 0
        for (kind, key), decision in events.items():
            if kind == "decision":
                retrospective += decision["retrospective"]
                if not decision["retrospective"]:
                    sessions[decision["decision_date"]][decision["ticker"]] = (key, decision)
        series = {name: [] for name in ("signal", "equal_weight_long", "momentum_21")}
        gross = {name: [] for name in series}
        dates, pending, unscored, windows = [], [], [], []
        cost = 2 * self.config.cost_bps_per_side / 10_000
        for day, decisions in sorted(sessions.items()):
            if any(
                ("invalid", key) in events or d["action"] == "REVIEW" or d["momentum_21"] is None
                for key, d in decisions.values()
            ):
                unscored.append(day)
                continue
            if set(decisions) != set(self.config.tickers) or any(
                ("exit", key) not in events for key, _ in decisions.values()
            ):
                pending.append(day)
                continue
            windows.append(
                (
                    min(
                        datetime.fromisoformat(events[("entry", key)]["at"])
                        for key, _ in decisions.values()
                    ),
                    max(
                        datetime.fromisoformat(events[("exit", key)]["at"])
                        for key, _ in decisions.values()
                    ),
                )
            )
            daily = {name: [] for name in series}
            for key, decision in decisions.values():
                raw = events[("exit", key)]["price"] / events[("entry", key)]["price"] - 1
                momentum = decision["momentum_21"]
                directions = {
                    "signal": _DIRECTION[decision["action"]],
                    "equal_weight_long": 1,
                    "momentum_21": (momentum > 0) - (momentum < 0),
                }
                for name, direction in directions.items():
                    daily[name].append(direction * raw - cost if direction else 0.0)
                    if direction:
                        gross[name].append(direction * raw)
            dates.append(day)
            for name in series:
                series[name].append(mean(daily[name]))
        annualization = self.config.sessions_per_year / self.config.horizon_sessions
        stats = {
            name: _stats(returns, gross[name], annualization) for name, returns in series.items()
        }
        # The rule uses the FIRST minimum sample, not whichever later endpoint wins.
        required = self.config.min_sessions
        sample = {
            name: _stats(returns[:required], [], annualization)["sharpe"]
            for name, returns in series.items()
        }
        verdict = "insufficient"
        verdict_sessions = dates[:required]
        # Pending earlier sessions cannot be dropped to pick a winning sample.
        earlier_pending = bool(
            dates and any(day <= dates[min(required, len(dates)) - 1] for day in pending)
        )
        sample_windows = windows[:required]
        overlapping = any(
            entry < previous_exit
            for (_, previous_exit), (entry, _) in zip(
                sample_windows, sample_windows[1:], strict=False
            )
        )
        if len(dates) >= required and not earlier_pending and not overlapping:
            signal = sample["signal"]
            passed = signal is not None and signal >= self.config.min_sharpe
            if self.config.must_beat_baselines:
                passed = passed and all(
                    sample[b] is not None and signal > sample[b]
                    for b in ("equal_weight_long", "momentum_21")
                )
            verdict = "passed" if passed else "failed"
        saved = events.get(("verdict", "verdict"))
        if saved:
            verdict, verdict_sessions = saved["verdict"], saved["sessions"]
            sample = saved["sharpes"]
        return {
            "verdict": verdict,
            "verdict_sessions": verdict_sessions,
            "verdict_sharpes": sample,
            "session_dates": dates,
            "metrics": stats,
            "retrospective_decisions": retrospective,
            "pending_sessions": pending,
            "unscored_sessions": unscored,
            "overlapping_windows": overlapping,
            "invalid_decisions": sum(kind == "invalid" for kind, _ in events),
        }


def _load_prices(path: str) -> PriceSource:
    with open(path, encoding="utf-8") as file:
        payload = json.load(file)
    bars = {
        ticker: [
            PriceBar(
                open_at=datetime.fromisoformat(b["open_at"]),
                open=b["open"],
                close_at=datetime.fromisoformat(b["close_at"]) if b.get("close_at") else None,
                close=b.get("close"),
            )
            for b in rows
        ]
        for ticker, rows in payload.items()
    }
    return lambda ticker: bars.get(ticker, [])


def main(argv: list[str] | None = None) -> None:
    """Thin offline CLI; scheduling, graph calls, and price downloads stay external."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "record", "score", "summary"):
        command = commands.add_parser(name)
        command.add_argument("ledger")
        if name == "init":
            command.add_argument("--protocol", required=True)
        if name == "record":
            command.add_argument("--decision", required=True)
        if name in ("record", "score"):
            command.add_argument("--prices", required=True)
    args = parser.parse_args(argv)
    if args.command == "init":
        with open(args.protocol, encoding="utf-8") as file:
            protocol = json.load(file)
        ledger = ForwardEvaluation.create(
            args.ledger,
            EvaluationConfig(**protocol["evaluation"]),
            [ModelDeclaration(**m) for m in protocol["models"]],
            protocol["run_config"],
        )
        result = ledger.protocol
    else:
        ledger = ForwardEvaluation(args.ledger)
        if args.command == "record":
            with open(args.decision, encoding="utf-8") as file:
                decision = json.load(file)
            decision["next_open"] = datetime.fromisoformat(decision["next_open"])
            result = ledger.record(**decision, prices=_load_prices(args.prices))
        else:
            result = (
                ledger.score(_load_prices(args.prices))
                if args.command == "score"
                else ledger.summary()
            )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
