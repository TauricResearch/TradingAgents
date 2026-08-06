"""Offline, outcome-identical replay of one durable formal marker interval.

The verifier reads only immutable database rows and calls the same pure
``advance_mark`` function used by the marker worker. It never calls a market
provider or wall clock. Its compact receipt binds the authenticated price
batch, every input, the champion result, and all eight synchronized strategy
results to the exact marker build.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from tradingagents.formal_activation import build_marker_replay_receipt
from tradingagents.outcome_semantics import outcome_semantics_id
from tradingagents.paper_trading import PaperStore, advance_mark
from tradingagents.research_protocol import (
    GLOBAL_EVENT_V2_PROTOCOL,
    GLOBAL_EVENT_V2_PROTOCOL_ID,
    canonical_json,
    content_id,
)

_MARK_FIELDS = (
    "session_date",
    "captured_utc",
    "nav",
    "benchmark_nav",
    "period_return",
    "benchmark_period_return",
    "turnover",
    "trading_cost",
    "borrow_cost",
    "weights",
    "opens",
    "benchmark_open",
    "target_decision_date",
)


class FormalMarkerRehearsalError(ValueError):
    """Raised when a stored marker interval cannot be reproduced exactly."""


def _mark_payload(row: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    missing = [field for field in _MARK_FIELDS if field not in row]
    if missing:
        raise FormalMarkerRehearsalError(f"{label} lacks an exact mark payload")
    payload = {field: row[field] for field in _MARK_FIELDS}
    if not isinstance(payload["weights"], Mapping) or not isinstance(
        payload["opens"], Mapping
    ):
        raise FormalMarkerRehearsalError(f"{label} mark vectors are malformed")
    payload["weights"] = dict(payload["weights"])
    payload["opens"] = dict(payload["opens"])
    return payload


def _stored_mark_pair(
    store: PaperStore,
    *,
    run_id: str,
    session_date: str,
    strategy_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if strategy_id is None:
        table = "paper_marks"
        strategy_clause = ""
        parameters: dict[str, Any] = {
            "run_id": run_id,
            "session_date": session_date,
        }
    else:
        table = "paper_strategy_marks"
        strategy_clause = " AND strategy_id=:strategy_id"
        parameters = {
            "run_id": run_id,
            "session_date": session_date,
            "strategy_id": strategy_id,
        }
    current_rows = store._rows(  # noqa: SLF001 - immutable verifier projection
        f"SELECT * FROM {table} WHERE run_id=:run_id "
        f"AND session_date=:session_date{strategy_clause}",
        parameters,
    )
    previous_rows = store._rows(  # noqa: SLF001 - immutable verifier projection
        f"SELECT * FROM {table} WHERE run_id=:run_id "
        f"AND session_date<:session_date{strategy_clause} "
        "ORDER BY session_date DESC LIMIT 1",
        parameters,
    )
    if len(current_rows) != 1 or len(previous_rows) != 1:
        raise FormalMarkerRehearsalError(
            "marker replay requires one stored completed interval"
        )
    normalized: list[dict[str, Any]] = []
    for label, row in (("current", current_rows[0]), ("previous", previous_rows[0])):
        projected = dict(row)
        try:
            projected["weights"] = json.loads(projected.pop("weights_json"))
            projected["opens"] = json.loads(projected.pop("opens_json"))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise FormalMarkerRehearsalError(
                f"stored {label} mark vectors are malformed"
            ) from exc
        normalized.append(_mark_payload(projected, label=label))
    return normalized[0], normalized[1]


def _replay_one(
    *,
    previous: dict[str, Any],
    stored: dict[str, Any],
    target: dict[str, Any],
    config: Mapping[str, Any],
    asset_returns: Mapping[str, float],
    benchmark_return: float,
    cash_return: float,
) -> dict[str, Any]:
    replayed = advance_mark(
        previous=previous,
        session_date=stored["session_date"],
        captured_utc=float(stored["captured_utc"]),
        opens=dict(stored["opens"]),
        benchmark_open=float(stored["benchmark_open"]),
        target=target,
        trading_cost_bps=float(config["cost_bps"]),
        slippage_bps=float(config["slippage_bps"]),
        annual_borrow_bps=float(config["annual_borrow_bps"]),
        asset_returns=dict(asset_returns),
        benchmark_period_return_override=float(benchmark_return),
        cash_period_return=float(cash_return),
    )
    if canonical_json(replayed) != canonical_json(stored):
        raise FormalMarkerRehearsalError(
            "stored marker output differs from deterministic replay"
        )
    return replayed


def verify_formal_marker_rehearsal(
    store: PaperStore,
    *,
    run_id: str,
    marker_build_id: str,
    session_date: str | None = None,
) -> dict[str, Any]:
    """Replay one non-initialized marked interval without external calls."""

    config = store.run_config(run_id)
    protocol = GLOBAL_EVENT_V2_PROTOCOL
    if (
        config.get("engine") != "formal-global-v2"
        or config.get("protocol_id") != GLOBAL_EVENT_V2_PROTOCOL_ID
        or config.get("tickers") != list(protocol["universe"]["symbols"])
        or config.get("benchmark") != protocol["portfolio"]["benchmark"]
        or config.get("outcome_semantics_id") != outcome_semantics_id()
    ):
        raise FormalMarkerRehearsalError(
            "marker replay run configuration differs from the frozen protocol"
        )
    if session_date is None:
        rows = store._rows(  # noqa: SLF001 - immutable verifier projection
            "SELECT mark.session_date FROM paper_marks AS mark "
            "JOIN paper_price_capture_batches AS batch "
            "ON batch.run_id=mark.run_id AND batch.session_date=mark.session_date "
            "WHERE mark.run_id=:run_id AND batch.return_vector_id IS NOT NULL "
            "ORDER BY mark.session_date DESC LIMIT 1",
            {"run_id": run_id},
        )
        if len(rows) != 1:
            raise FormalMarkerRehearsalError(
                "marker replay requires a durable non-initial price interval"
            )
        session_date = rows[0]["session_date"]

    symbols = [*config["tickers"], config["benchmark"]]
    batch = store.price_capture_batch(run_id, session_date)
    vector = store.return_vector_for_session(run_id, session_date, symbols)
    if (
        batch is None
        or vector is None
        or batch.get("paper_build_id") != marker_build_id
        or batch.get("capture_batch_id") is None
        or batch.get("return_vector_id") != vector.get("return_vector_id")
    ):
        raise FormalMarkerRehearsalError(
            "marker replay lacks an authenticated same-build return vector"
        )
    champion, previous_champion = _stored_mark_pair(
        store, run_id=run_id, session_date=session_date
    )
    decision_date = champion.get("target_decision_date")
    champion_target = store.target_for_entry(run_id, session_date)
    if (
        not isinstance(decision_date, str)
        or not decision_date
        or champion_target is None
        or champion_target.get("decision_date") != decision_date
        or vector.get("from_session") != previous_champion["session_date"]
        or vector.get("to_session") != session_date
    ):
        raise FormalMarkerRehearsalError(
            "marker replay requires one target-applied consecutive interval"
        )
    components = vector.get("components")
    cash_component = vector.get("cash_component")
    if not isinstance(components, Mapping) or not isinstance(cash_component, Mapping):
        raise FormalMarkerRehearsalError("marker replay return vector is malformed")
    try:
        asset_returns = {
            ticker: float(components[ticker]["open_return"])
            for ticker in config["tickers"]
        }
        benchmark_return = float(
            components[config["benchmark"]]["open_return"]
        )
        cash_return = float(cash_component["open_return"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalMarkerRehearsalError(
            "marker replay return vector is incomplete"
        ) from exc

    champion_replay = _replay_one(
        previous=previous_champion,
        stored=champion,
        target=champion_target,
        config=config,
        asset_returns=asset_returns,
        benchmark_return=benchmark_return,
        cash_return=cash_return,
    )
    strategies = list(protocol["strategies"])
    if store.formal_strategies(run_id) != sorted(strategies):
        raise FormalMarkerRehearsalError(
            "marker replay strategy registry differs from the frozen protocol"
        )
    strategy_inputs: list[dict[str, Any]] = []
    strategy_outputs: list[dict[str, str]] = []
    for strategy_id in strategies:
        stored, previous = _stored_mark_pair(
            store,
            run_id=run_id,
            session_date=session_date,
            strategy_id=strategy_id,
        )
        target = store.strategy_target_for_entry(
            run_id, strategy_id, session_date
        )
        if (
            target is None
            or target.get("decision_date") != decision_date
            or stored.get("target_decision_date") != decision_date
            or previous["session_date"] != vector["from_session"]
        ):
            raise FormalMarkerRehearsalError(
                "marker replay strategy target lineage is incomplete"
            )
        replayed = _replay_one(
            previous=previous,
            stored=stored,
            target=target,
            config=config,
            asset_returns=asset_returns,
            benchmark_return=benchmark_return,
            cash_return=cash_return,
        )
        strategy_inputs.append(
            {
                "strategy_id": strategy_id,
                "previous": previous,
                "target": target,
            }
        )
        strategy_outputs.append(
            {
                "strategy_id": strategy_id,
                "mark_id": content_id(replayed, prefix="mark_"),
            }
        )

    marker_inputs = {
        "schema_version": 1,
        "run_id": run_id,
        "session_date": session_date,
        "marker_build_id": marker_build_id,
        "config": config,
        "capture_batch_id": batch["capture_batch_id"],
        "return_vector": vector,
        "previous_champion": previous_champion,
        "champion_target": champion_target,
        "strategy_inputs": strategy_inputs,
    }
    return build_marker_replay_receipt(
        run_id=run_id,
        decision_date=decision_date,
        entry_date=session_date,
        session_date=session_date,
        protocol_id=GLOBAL_EVENT_V2_PROTOCOL_ID,
        build_id=marker_build_id,
        outcome_semantics_id=config["outcome_semantics_id"],
        capture_batch_id=batch["capture_batch_id"],
        return_vector_id=vector["return_vector_id"],
        marker_input_id=content_id(marker_inputs, prefix="marker_input_"),
        champion_mark_id=content_id(champion_replay, prefix="mark_"),
        strategy_mark_ids=strategy_outputs,
    )


__all__ = [
    "FormalMarkerRehearsalError",
    "verify_formal_marker_rehearsal",
]
