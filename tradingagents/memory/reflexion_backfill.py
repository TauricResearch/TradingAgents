"""Deterministic out-of-band outcome back-fill for Reflexion memories."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.memory.macro_memory import MacroMemory
from tradingagents.memory.reflexion import ReflexionMemory
from tradingagents.report_paths import REPORTS_ROOT

logger = logging.getLogger(__name__)

PriceLoader = Callable[[str, str, str], str]

BUY_THRESHOLD_PCT = 1.0
SELL_THRESHOLD_PCT = -1.0
HOLD_THRESHOLD_ABS_PCT = 5.0
CYCLICAL_ETFS = ("XLY", "XLI")
DEFENSIVE_ETFS = ("XLP", "XLU")
VIX_SYMBOL = "^VIX"


@dataclass(frozen=True)
class EvaluationResult:
    outcome: dict[str, Any] | None
    skip_reason: str | None = None


@dataclass
class BackfillResult:
    evaluation_date: str
    dry_run: bool
    reflexion_pending: int = 0
    reflexion_evaluated: int = 0
    reflexion_updated: int = 0
    reflexion_skipped: int = 0
    macro_pending: int = 0
    macro_evaluated: int = 0
    macro_updated: int = 0
    macro_skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)


def _parse_date(raw: Any, *, field_name: str) -> date:
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {raw!r}") from exc


def _cutoff(evaluation_date: str, horizon_days: int) -> str:
    if horizon_days < 0:
        raise ValueError("horizon_days must be non-negative")
    cutoff_date = _parse_date(evaluation_date, field_name="evaluation_date") - timedelta(
        days=horizon_days
    )
    return cutoff_date.isoformat()


def select_pending_reflexion_records(
    memory: ReflexionMemory,
    *,
    evaluation_date: str,
    horizon_days: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Return eligible pending per-ticker decisions in deterministic order."""
    cutoff = _cutoff(evaluation_date, horizon_days)
    if memory._col is not None:
        cursor = (
            memory._col.find(
                {
                    "outcome": None,
                    "decision_date": {"$lte": cutoff},
                    "decision": {"$ne": "SKIP"},
                },
                {"_id": 0},
            )
            .sort([("decision_date", 1), ("ticker", 1), ("created_at", 1)])
            .limit(batch_size)
        )
        return list(cursor)

    records = [
        rec
        for rec in memory._load_all_local()
        if rec.get("outcome") is None
        and rec.get("decision_date", "") <= cutoff
        and str(rec.get("decision", "")).upper() != "SKIP"
    ]
    records.sort(
        key=lambda rec: (
            rec.get("decision_date", ""),
            rec.get("ticker", ""),
            rec.get("created_at", ""),
        )
    )
    return records[:batch_size]


def select_pending_macro_records(
    memory: MacroMemory,
    *,
    evaluation_date: str,
    horizon_days: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Return eligible pending macro regime records in deterministic order."""
    cutoff = _cutoff(evaluation_date, horizon_days)
    if memory._col is not None:
        cursor = (
            memory._col.find(
                {"outcome": None, "regime_date": {"$lte": cutoff}},
                {"_id": 0},
            )
            .sort([("regime_date", 1), ("run_id", 1), ("created_at", 1)])
            .limit(batch_size)
        )
        return list(cursor)

    records = [
        rec
        for rec in memory._load_all_local()
        if rec.get("outcome") is None and rec.get("regime_date", "") <= cutoff
    ]
    records.sort(
        key=lambda rec: (
            rec.get("regime_date", ""),
            rec.get("run_id") or "",
            rec.get("created_at", ""),
        )
    )
    return records[:batch_size]


def _route_price_loader(ticker: str, start_date: str, end_date: str) -> str:
    return route_to_vendor("get_stock_data", ticker, start_date, end_date)


def _parse_close_series(raw: str) -> list[tuple[str, float]]:
    rows: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            break
        rows.append(line)

    if not rows:
        raise ValueError("price response did not contain CSV rows")

    reader = csv.DictReader(io.StringIO("\n".join(rows)))
    if not reader.fieldnames:
        raise ValueError("price response did not contain CSV headers")

    date_field = _find_field(reader.fieldnames, ("date", "timestamp", "time"))
    close_field = _find_field(
        reader.fieldnames,
        ("adj close", "adjusted_close", "adjusted close", "close"),
    )
    if date_field is None or close_field is None:
        raise ValueError("price CSV missing date or close column")

    prices: list[tuple[str, float]] = []
    for row in reader:
        raw_date = str(row.get(date_field, "")).strip()
        raw_close = str(row.get(close_field, "")).strip()
        if not raw_date or not raw_close:
            continue
        price_date = raw_date[:10]
        try:
            _parse_date(price_date, field_name="price_date")
            close = float(raw_close)
        except ValueError:
            continue
        if close <= 0:
            continue
        prices.append((price_date, close))

    prices.sort(key=lambda item: item[0])
    if not prices:
        raise ValueError("price CSV did not contain parseable positive closes")
    return prices


def _find_field(fields: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {field.strip().lower(): field for field in fields}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _return_from_history(raw: str, start_date: str, end_date: str) -> tuple[float, float, float]:
    series = _parse_close_series(raw)
    prices_by_date = {price_date: close for price_date, close in series}
    if start_date not in prices_by_date or end_date not in prices_by_date:
        raise ValueError(f"missing endpoint price rows for {start_date} and/or {end_date}")
    start_price = prices_by_date[start_date]
    end_price = prices_by_date[end_date]
    pct = (end_price - start_price) / start_price * 100.0
    return start_price, end_price, pct


def evaluate_reflexion_record(
    record: dict[str, Any],
    *,
    evaluation_date: str,
    price_loader: PriceLoader = _route_price_loader,
) -> EvaluationResult:
    ticker = str(record.get("ticker") or "").upper()
    decision_date = str(record.get("decision_date") or "")
    decision = str(record.get("decision") or "").upper()
    if decision == "SKIP":
        return EvaluationResult(None, f"{ticker} {decision_date}: SKIP decisions are not evaluated")
    if not ticker or not decision_date:
        return EvaluationResult(
            None, f"missing ticker or decision_date in reflexion record: {record!r}"
        )

    try:
        raw = price_loader(ticker, decision_date, evaluation_date)
        price_at_decision, price_at_evaluation, pct_change = _return_from_history(
            raw, decision_date, evaluation_date
        )
    except Exception as exc:
        reason = f"{ticker} {decision_date}: price data unavailable or unparseable: {exc}"
        logger.warning("Reflexion backfill skipped record: %s", reason)
        return EvaluationResult(None, reason)

    if decision == "BUY":
        correct = pct_change >= BUY_THRESHOLD_PCT
    elif decision == "SELL":
        correct = pct_change <= SELL_THRESHOLD_PCT
    elif decision == "HOLD":
        correct = abs(pct_change) <= HOLD_THRESHOLD_ABS_PCT
    else:
        return EvaluationResult(None, f"{ticker} {decision_date}: unknown decision {decision!r}")

    return EvaluationResult(
        {
            "evaluation_date": evaluation_date,
            "price_at_decision": round(price_at_decision, 4),
            "price_at_evaluation": round(price_at_evaluation, 4),
            "price_change_pct": round(pct_change, 4),
            "correct": bool(correct),
        }
    )


def evaluate_macro_record(
    record: dict[str, Any],
    *,
    evaluation_date: str,
    price_loader: PriceLoader = _route_price_loader,
) -> EvaluationResult:
    regime_date = str(record.get("regime_date") or "")
    macro_call = str(record.get("macro_call") or "").lower()
    if not regime_date:
        return EvaluationResult(None, f"missing regime_date in macro record: {record!r}")

    try:
        vix_start, vix_end, vix_delta_pct = _return_from_history(
            price_loader(VIX_SYMBOL, regime_date, evaluation_date),
            regime_date,
            evaluation_date,
        )
        vix_delta = vix_delta_pct / 100.0
        cyclical_returns = [
            _return_from_history(
                price_loader(symbol, regime_date, evaluation_date),
                regime_date,
                evaluation_date,
            )[2]
            for symbol in CYCLICAL_ETFS
        ]
        defensive_returns = [
            _return_from_history(
                price_loader(symbol, regime_date, evaluation_date),
                regime_date,
                evaluation_date,
            )[2]
            for symbol in DEFENSIVE_ETFS
        ]
    except Exception as exc:
        reason = (
            f"{regime_date} {record.get('run_id')}: "
            f"macro price data unavailable or unparseable: {exc}"
        )
        logger.warning("Macro backfill skipped record: %s", reason)
        return EvaluationResult(None, reason)

    cyclicals_return_pct = sum(cyclical_returns) / len(cyclical_returns)
    defensives_return_pct = sum(defensive_returns) / len(defensive_returns)
    risk_on_held = vix_delta <= 0.25 and cyclicals_return_pct > defensives_return_pct
    risk_off_held = not risk_on_held and (
        vix_delta > 0.0 or defensives_return_pct > cyclicals_return_pct
    )
    neutral_held = not risk_on_held and not risk_off_held

    if macro_call == "risk-on":
        confirmed = risk_on_held
    elif macro_call == "risk-off":
        confirmed = risk_off_held
    elif macro_call in {"transition", "neutral"}:
        confirmed = neutral_held
    else:
        return EvaluationResult(None, f"{regime_date}: unknown macro_call {macro_call!r}")

    notes = (
        f"VIX {vix_start:.2f}->{vix_end:.2f} ({vix_delta_pct:.2f}%). "
        f"Cyclicals {cyclicals_return_pct:.2f}% vs defensives {defensives_return_pct:.2f}%."
    )
    return EvaluationResult(
        {
            "evaluation_date": evaluation_date,
            "vix_at_evaluation": round(vix_end, 4),
            "vix_delta_pct": round(vix_delta_pct, 4),
            "regime_confirmed": bool(confirmed),
            "notes": notes,
        }
    )


def run_backfill(
    *,
    config: dict[str, Any],
    evaluation_date: str,
    dry_run: bool = False,
    price_loader: PriceLoader = _route_price_loader,
) -> BackfillResult:
    """Evaluate and optionally persist pending Reflexion and MacroMemory outcomes."""
    _parse_date(evaluation_date, field_name="evaluation_date")
    batch_size = int(config.get("reflexion_backfill_batch_size", 100))
    reflexion_horizon = int(config.get("reflexion_evaluation_horizon_days", 5))
    macro_horizon = int(config.get("macro_evaluation_horizon_days", 21))

    reflexion_memory = ReflexionMemory(
        mongo_uri=config.get("mongo_uri"),
        db_name=config.get("mongo_db", "tradingagents"),
        fallback_path=config.get(
            "reflexion_fallback_path", _fallback_path(config, "reflexion.json")
        ),
    )
    macro_memory = MacroMemory(
        mongo_uri=config.get("mongo_uri"),
        db_name=config.get("mongo_db", "tradingagents"),
        fallback_path=config.get(
            "macro_memory_fallback_path", _fallback_path(config, "macro_memory.json")
        ),
    )
    result = BackfillResult(evaluation_date=evaluation_date, dry_run=dry_run)

    reflexion_records = select_pending_reflexion_records(
        reflexion_memory,
        evaluation_date=evaluation_date,
        horizon_days=reflexion_horizon,
        batch_size=batch_size,
    )
    result.reflexion_pending = len(reflexion_records)
    for record in reflexion_records:
        evaluated = evaluate_reflexion_record(
            record, evaluation_date=evaluation_date, price_loader=price_loader
        )
        if evaluated.outcome is None:
            result.reflexion_skipped += 1
            if evaluated.skip_reason:
                result.skip_reasons.append(evaluated.skip_reason)
            continue
        result.reflexion_evaluated += 1
        if not dry_run and reflexion_memory.record_outcome(
            str(record["ticker"]),
            str(record["decision_date"]),
            evaluated.outcome,
            run_id=record.get("run_id"),
        ):
            result.reflexion_updated += 1

    macro_records = select_pending_macro_records(
        macro_memory,
        evaluation_date=evaluation_date,
        horizon_days=macro_horizon,
        batch_size=batch_size,
    )
    result.macro_pending = len(macro_records)
    for record in macro_records:
        evaluated = evaluate_macro_record(
            record, evaluation_date=evaluation_date, price_loader=price_loader
        )
        if evaluated.outcome is None:
            result.macro_skipped += 1
            if evaluated.skip_reason:
                result.skip_reasons.append(evaluated.skip_reason)
            continue
        result.macro_evaluated += 1
        if not dry_run and macro_memory.record_outcome(
            str(record["regime_date"]),
            evaluated.outcome,
            run_id=record.get("run_id"),
        ):
            result.macro_updated += 1

    return result


def _fallback_path(config: dict[str, Any], filename: str) -> Path:
    configured = config.get("results_dir")
    root = Path(str(configured)) if configured else REPORTS_ROOT
    return root / filename
