"""PipelineRecorder: turn streamed pipeline updates into a RunRecord.

The dashboard's debate timeline is exactly the ``stream_pipeline`` event
sequence; the recorder accumulates the partial updates (honoring the
evidence-by-team merge semantics) so the final state is available without
a second pipeline invocation.

With ``store_dir`` set, every completed run is persisted as one JSON file
(atomic write) and reloaded on construction — run history survives
container restarts (v7: the operator saw an empty dashboard after every
rebuild). Contracts round-trip losslessly via model_dump/model_validate;
a corrupt file is skipped with a warning, never a crash.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tradingagents.contracts import (
    AgentEvidence,
    MarketRegime,
    MarketSnapshot,
    MetricReading,
    ProConfig,
    TradeRecommendation,
    utc_now,
)
from tradingagents.pro.pipeline import stream_pipeline

logger = logging.getLogger(__name__)


@dataclass
class RunRecord:
    run_id: str
    started_at: datetime
    symbol: str
    asset: str
    node_sequence: list[str] = field(default_factory=list)
    # per-node wall time, parallel to node_sequence: [{"node", "elapsed_s"}].
    # Runs persisted before this field exists load as [] (UI omits latency).
    node_times: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)

    @property
    def recommendation(self) -> TradeRecommendation | None:
        return self.state.get("recommendation")

    @property
    def rejection(self) -> dict | None:
        return self.state.get("rejection")

    @property
    def debate(self) -> list[dict]:
        return self.state.get("debate", [])

    @property
    def timeframe(self) -> str | None:
        return self.state.get("timeframe")

    def snapshot_summary(self) -> dict:
        snapshot: MarketSnapshot = self.state["snapshot"]
        return {
            "symbol": snapshot.symbol,
            "as_of": snapshot.as_of.isoformat(),
            "last_close": snapshot.bars[-1].close if snapshot.bars else None,
            "n_bars": len(snapshot.bars),
            "session": snapshot.session.value if snapshot.session else None,
            "missing_feeds": list(snapshot.missing_feeds),
            "regime": self.state.get("regime") and self.state["regime"].value,
        }


def _accumulate(state: dict, update: dict) -> None:
    for key, value in update.items():
        if key == "evidence_by_team" and isinstance(value, dict):
            merged = dict(state.get("evidence_by_team", {}))
            merged.update(value)
            state["evidence_by_team"] = merged
        else:
            state[key] = value


# --- persistence ------------------------------------------------------------------

def _state_to_json(state: dict) -> dict:
    """Project the typed pipeline state to plain JSON. Typed keys are
    whitelisted; unknown keys ride along when JSON-serializable."""
    out: dict = {}
    for key, value in state.items():
        if key == "snapshot" and isinstance(value, MarketSnapshot) or key == "recommendation" and isinstance(value, TradeRecommendation):
            out[key] = value.model_dump(mode="json")
        elif key == "evidence_by_team" and isinstance(value, dict):
            out[key] = {
                team: [e.model_dump(mode="json") for e in evidence]
                for team, evidence in value.items()
            }
        elif key == "risk_metrics" and isinstance(value, dict):
            out[key] = {
                name: m.model_dump(mode="json") for name, m in value.items()
            }
        elif key == "regime" and isinstance(value, MarketRegime):
            out[key] = value.value
        else:
            try:
                json.dumps(value)
                out[key] = value
            except (TypeError, ValueError):
                logger.debug("run state key %r not JSON-serializable; skipped", key)
    return out


def _state_from_json(raw: dict) -> dict:
    state: dict = dict(raw)
    if "snapshot" in state:
        state["snapshot"] = MarketSnapshot.model_validate(state["snapshot"])
    if state.get("recommendation") is not None:
        state["recommendation"] = TradeRecommendation.model_validate(
            state["recommendation"]
        )
    if "evidence_by_team" in state:
        state["evidence_by_team"] = {
            team: [AgentEvidence.model_validate(e) for e in evidence]
            for team, evidence in state["evidence_by_team"].items()
        }
    if "risk_metrics" in state:
        state["risk_metrics"] = {
            name: MetricReading.model_validate(m)
            for name, m in state["risk_metrics"].items()
        }
    if state.get("regime") is not None:
        state["regime"] = MarketRegime(state["regime"])
    return state


class PipelineRecorder:
    """``max_runs`` caps memory over long soaks: each RunRecord holds a full
    snapshot (bars, news, debate transcript), so an unbounded list would grow
    to hundreds of MB across a 30-day paper run. Oldest runs are dropped
    (and their files pruned when persisting)."""

    def __init__(self, max_runs: int = 500, store_dir: str | Path | None = None):
        if max_runs < 1:
            raise ValueError("max_runs must be >= 1")
        self.max_runs = max_runs
        self.store_dir = Path(store_dir) if store_dir else None
        self.runs: list[RunRecord] = []
        if self.store_dir is not None:
            self._load()

    # --- disk ----------------------------------------------------------------------

    def _load(self) -> None:
        assert self.store_dir is not None
        if not self.store_dir.is_dir():
            return
        loaded: list[RunRecord] = []
        for path in sorted(self.store_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                loaded.append(RunRecord(
                    run_id=raw["run_id"],
                    started_at=datetime.fromisoformat(raw["started_at"]),
                    symbol=raw["symbol"],
                    asset=raw["asset"],
                    node_sequence=list(raw.get("node_sequence", [])),
                    node_times=list(raw.get("node_times", [])),
                    state=_state_from_json(raw.get("state", {})),
                ))
            except Exception:
                logger.warning("skipping corrupt run file %s", path, exc_info=True)
        loaded.sort(key=lambda r: r.started_at)
        self.runs = loaded[-self.max_runs:]

    def _persist(self, run: RunRecord) -> None:
        assert self.store_dir is not None
        self.store_dir.mkdir(parents=True, exist_ok=True)
        from tradingagents.pro.persistence import atomic_write_text

        payload = json.dumps({
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat(),
            "symbol": run.symbol,
            "asset": run.asset,
            "node_sequence": run.node_sequence,
            "node_times": run.node_times,
            "state": _state_to_json(run.state),
        })
        atomic_write_text(self.store_dir / f"{run.run_id}.json", payload)
        # prune files beyond the cap, oldest first (mtime order suffices)
        files = sorted(self.store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for stale in files[:-self.max_runs]:
            stale.unlink(missing_ok=True)

    # --- recording -------------------------------------------------------------------

    def record_run(
        self,
        llm,
        config: ProConfig,
        snapshot: MarketSnapshot,
        on_node=None,
        **pipeline_kwargs,
    ) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid.uuid4()),
            started_at=utc_now(),
            symbol=snapshot.symbol,
            asset=snapshot.asset.value,
            state={"snapshot": snapshot},
        )
        clock = time.monotonic()
        for event in stream_pipeline(llm, config, snapshot, **pipeline_kwargs):
            now = time.monotonic()
            elapsed, clock = now - clock, now
            for node_name, update in event.items():
                run.node_sequence.append(node_name)
                # elapsed covers the whole event; attribute it to the first
                # node and 0 to siblings (parallel branches share one event)
                run.node_times.append(
                    {"node": node_name, "elapsed_s": round(elapsed, 3)}
                )
                elapsed = 0.0
                if on_node is not None:
                    try:
                        on_node(node_name)
                    except Exception:
                        logger.exception("on_node observer failed; continuing")
                if update:
                    _accumulate(run.state, update)
        # timeframe of the driving bars, for history display
        if snapshot.bars:
            run.state.setdefault("timeframe", snapshot.bars[-1].timeframe.value)
        self.runs.append(run)
        del self.runs[:-self.max_runs]
        if self.store_dir is not None:
            try:
                self._persist(run)
            except Exception:
                logger.exception("run %s not persisted; continuing", run.run_id)
        return run

    def repersist(self, run: RunRecord) -> None:
        """Re-write a run whose state changed after recording — e.g. the
        venue's order verdict landing after the pipeline already stamped
        execution_status (the phantom-SELL truth gap)."""
        if self.store_dir is not None:
            try:
                self._persist(run)
            except Exception:
                logger.exception("run %s not re-persisted; continuing", run.run_id)
