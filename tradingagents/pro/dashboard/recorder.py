"""PipelineRecorder: turn streamed pipeline updates into a RunRecord.

The dashboard's debate timeline is exactly the ``stream_pipeline`` event
sequence; the recorder accumulates the partial updates (honoring the
evidence-by-team merge semantics) so the final state is available without
a second pipeline invocation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from tradingagents.contracts import MarketSnapshot, ProConfig, TradeRecommendation, utc_now
from tradingagents.pro.pipeline import stream_pipeline


@dataclass
class RunRecord:
    run_id: str
    started_at: datetime
    symbol: str
    asset: str
    node_sequence: list[str] = field(default_factory=list)
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


class PipelineRecorder:
    """``max_runs`` caps memory over long soaks: each RunRecord holds a full
    snapshot (bars, news, debate transcript), so an unbounded list would grow
    to hundreds of MB across a 30-day paper run. Oldest runs are dropped."""

    def __init__(self, max_runs: int = 500):
        if max_runs < 1:
            raise ValueError("max_runs must be >= 1")
        self.max_runs = max_runs
        self.runs: list[RunRecord] = []

    def record_run(
        self,
        llm,
        config: ProConfig,
        snapshot: MarketSnapshot,
        **pipeline_kwargs,
    ) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid.uuid4()),
            started_at=utc_now(),
            symbol=snapshot.symbol,
            asset=snapshot.asset.value,
            state={"snapshot": snapshot},
        )
        for event in stream_pipeline(llm, config, snapshot, **pipeline_kwargs):
            for node_name, update in event.items():
                run.node_sequence.append(node_name)
                if update:
                    _accumulate(run.state, update)
        self.runs.append(run)
        del self.runs[:-self.max_runs]
        return run
