"""Pure evaluation over already-committed decisions and labels."""

from __future__ import annotations

import statistics
from typing import Any

from tradingagents.research.artifacts import (
    ArtifactRef,
    FilesystemArtifactStore,
    require_payload_reference,
)
from tradingagents.research.contracts import (
    DecisionBatch,
    EvaluationReport,
    EvidenceSnapshot,
    OutcomeBatch,
    parse_contract,
)
from tradingagents.research.decision_validation import (
    replay_decision_batch,
    validate_decision_batch_protocol,
    validate_snapshot_protocol,
)
from tradingagents.research.outcome_validation import validate_outcome_observation
from tradingagents.research_protocol import build_identity
from tradingagents.research_statistics import newey_west_mean_test


def _max_drawdown(equity: list[float]) -> float | None:
    if not equity:
        return None
    peak = equity[0]
    drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            drawdown = max(drawdown, 1.0 - value / peak)
    return drawdown


def evaluate(
    *,
    decisions: DecisionBatch,
    decision_ref: ArtifactRef,
    labels: OutcomeBatch,
    label_ref: ArtifactRef,
) -> EvaluationReport:
    require_payload_reference(
        decision_ref, kind="decisions", payload=decisions.model_dump(mode="json")
    )
    require_payload_reference(
        label_ref, kind="labels", payload=labels.model_dump(mode="json")
    )
    if labels.decision_artifact_id != decision_ref.artifact_id or (
        labels.decision_payload_sha256 != decision_ref.payload_sha256
    ):
        raise ValueError("label batch is not bound to these exact decisions")
    if (
        labels.run_id != decisions.run_id
        or labels.universe != decisions.universe
        or labels.benchmark != decisions.benchmark
    ):
        raise ValueError("decision and label batches describe different experiments")
    validate_decision_batch_protocol(decisions)
    by_date = {row.decision_date: row for row in labels.outcomes}
    decision_dates = {row.decision_date for row in decisions.decisions}
    if set(by_date) != decision_dates:
        raise ValueError("label batch must contain exactly one row for every decision")
    for decision in decisions.decisions:
        label = by_date[decision.decision_date]
        validate_outcome_observation(
            label.observation,
            decision_date=decision.decision_date,
            universe=decisions.universe,
            benchmark=decisions.benchmark,
            error_type=label.error_type,
        )

    trading_cost_bps = float(decisions.allocator["trading_cost_bps"])
    slippage_bps = float(decisions.allocator["slippage_bps"])
    equity = [1.0]
    benchmark_equity = 1.0
    completed_returns: list[float] = []
    excess_returns: list[float] = []
    realized_turnovers: list[float] = []
    interval_rows: list[dict[str, Any]] = []
    prior_drifted_weights = dict.fromkeys(decisions.universe, 0.0)
    prior_drifted_cash_weight = 1.0
    blocked_by_missing = False
    first_missing_decision_date = None
    for decision in decisions.decisions:
        label = by_date[decision.decision_date]
        if blocked_by_missing:
            interval_rows.append(
                {
                    "decision_date": decision.decision_date.isoformat(),
                    "status": "blocked_by_missing_predecessor",
                    "label_status": label.status,
                    "strategy_return": None,
                    "benchmark_return": None,
                    "excess_return": None,
                    "planned_target_turnover": decision.turnover,
                    "realized_entry_turnover": None,
                }
            )
            continue
        if label.status == "missing":
            blocked_by_missing = True
            first_missing_decision_date = decision.decision_date.isoformat()
            interval_rows.append(
                {
                    "decision_date": decision.decision_date.isoformat(),
                    "status": "missing_label",
                    "label_status": label.status,
                    "strategy_return": None,
                    "benchmark_return": None,
                    "excess_return": None,
                    "planned_target_turnover": decision.turnover,
                    "realized_entry_turnover": None,
                }
            )
            continue
        observation = label.observation
        realized_turnover = sum(
            abs(
                decision.target_weights[symbol]
                - prior_drifted_weights[symbol]
            )
            for symbol in decisions.universe
        )
        asset_growth = {
            symbol: decision.target_weights[symbol]
            * (1.0 + float(observation.asset_returns[symbol]))
            for symbol in decisions.universe
        }
        cash_growth = decision.cash_weight * (1.0 + observation.cash_return)
        gross_growth = sum(asset_growth.values()) + cash_growth
        if gross_growth <= 0.0:
            raise ValueError("portfolio gross growth must remain positive")
        entry_cost = (
            realized_turnover
            * (trading_cost_bps + slippage_bps)
            / 10_000.0
        )
        if not 0.0 <= entry_cost < 1.0:
            raise ValueError("portfolio entry cost must be in [0, 1)")
        net_return = (1.0 - entry_cost) * gross_growth - 1.0
        benchmark_return = float(observation.benchmark_return)
        equity.append(equity[-1] * (1.0 + net_return))
        benchmark_equity *= 1.0 + benchmark_return
        completed_returns.append(net_return)
        excess_returns.append(net_return - benchmark_return)
        realized_turnovers.append(realized_turnover)
        prior_drifted_weights = {
            symbol: asset_growth[symbol] / gross_growth
            for symbol in decisions.universe
        }
        prior_drifted_cash_weight = cash_growth / gross_growth
        interval_rows.append(
            {
                "decision_date": decision.decision_date.isoformat(),
                "status": "complete",
                "label_status": label.status,
                "strategy_return": net_return,
                "benchmark_return": benchmark_return,
                "excess_return": net_return - benchmark_return,
                "planned_target_turnover": decision.turnover,
                "realized_entry_turnover": realized_turnover,
                "post_return_asset_weights": dict(prior_drifted_weights),
                "post_return_cash_weight": prior_drifted_cash_weight,
            }
        )
    completed = len(completed_returns)
    accounting_complete = completed == len(decisions.decisions)
    total_return = equity[-1] - 1.0 if accounting_complete else None
    benchmark_return = benchmark_equity - 1.0 if accounting_complete else None
    return EvaluationReport(
        run_id=decisions.run_id,
        build_id=build_identity(),
        decision_artifact_id=decision_ref.artifact_id,
        outcome_artifact_id=label_ref.artifact_id,
        intervals_total=len(decisions.decisions),
        intervals_completed=completed,
        intervals_missing=len(decisions.decisions) - completed,
        total_return=total_return,
        benchmark_return=benchmark_return,
        excess_return=(
            total_return - benchmark_return
            if total_return is not None and benchmark_return is not None
            else None
        ),
        max_drawdown=_max_drawdown(equity) if accounting_complete else None,
        mean_interval_return=(
            statistics.fmean(completed_returns) if accounting_complete else None
        ),
        total_turnover=sum(realized_turnovers) if accounting_complete else None,
        interval_returns=tuple(interval_rows),
        diagnostics={
            "accounting_complete": accounting_complete,
            "first_missing_decision_date": first_missing_decision_date,
            "observed_prefix_intervals": completed,
            "observed_prefix_realized_turnover": sum(realized_turnovers),
            "newey_west_excess_mean": (
                newey_west_mean_test(excess_returns) if accounting_complete else None
            ),
            "cost_semantics": (
                "entry turnover is target minus prior post-return drifted asset "
                "weights; cost is realized turnover times trading-cost plus "
                "slippage basis points"
            ),
        },
    )


def evaluate_from_artifacts(
    *,
    artifact_store: FilesystemArtifactStore,
    decision_artifact_id: str,
    label_artifact_id: str,
) -> ArtifactRef:
    decision_ref, decision_payload = artifact_store.load_with_ref(
        "decisions", decision_artifact_id
    )
    label_ref, label_payload = artifact_store.load_with_ref(
        "labels", label_artifact_id
    )
    decisions = parse_contract(DecisionBatch, decision_payload)
    labels = parse_contract(OutcomeBatch, label_payload)
    snapshot_ref, snapshot_payload = artifact_store.load_with_ref(
        "snapshot", decisions.snapshot_artifact_id
    )
    snapshot = parse_contract(EvidenceSnapshot, snapshot_payload)
    validate_snapshot_protocol(snapshot, decisions.checkpoint)
    replay_decision_batch(
        decisions,
        snapshot=snapshot,
        snapshot_ref=snapshot_ref,
    )
    report = evaluate(
        decisions=decisions,
        decision_ref=decision_ref,
        labels=labels,
        label_ref=label_ref,
    )
    return artifact_store.commit("evaluation", report.model_dump(mode="json"))
