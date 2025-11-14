from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.services.auto_trade import AutoTradeResult, TickerDecision

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> str:
    return datetime.utcnow().strftime(ISO_FORMAT)


@dataclass
class PlanStepRecord:
    id: str
    description: str
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PlanStepRecord":
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex[:8]),
            description=str(payload.get("description") or ""),
            status=str(payload.get("status") or "pending"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class HypothesisRecord:
    id: str
    ticker: str
    action: str
    priority: float
    status: str
    rationale: str
    notes: str
    plan: List[PlanStepRecord]
    created_at: str
    updated_at: str
    source_snapshot: str
    strategy: Dict[str, Any] = field(default_factory=dict)
    triggers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "action": self.action,
            "priority": self.priority,
            "status": self.status,
            "rationale": self.rationale,
            "notes": self.notes,
            "plan": [step.to_dict() for step in self.plan],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_snapshot": self.source_snapshot,
            "strategy": dict(self.strategy),
            "triggers": list(self.triggers),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HypothesisRecord":
        plan_payload = payload.get("plan") or []
        plan_steps = [PlanStepRecord.from_dict(step) for step in plan_payload]
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex),
            ticker=str(payload.get("ticker") or ""),
            action=str(payload.get("action") or "HOLD"),
            priority=float(payload.get("priority") or 0.0),
            status=str(payload.get("status") or "monitoring"),
            rationale=str(payload.get("rationale") or ""),
            notes=str(payload.get("notes") or ""),
            plan=plan_steps,
            created_at=str(payload.get("created_at") or _utcnow()),
            updated_at=str(payload.get("updated_at") or _utcnow()),
            source_snapshot=str(payload.get("source_snapshot") or ""),
            strategy=dict(payload.get("strategy") or {}),
            triggers=[str(item) for item in payload.get("triggers") or []],
        )

    def next_open_step(self) -> Optional[PlanStepRecord]:
        for step in self.plan:
            if step.status.lower() not in {"done", "complete", "completed"}:
                return step
        return None


class HypothesisStore:
    """Persist hypotheses derived from auto-trade runs for autopilot follow-up."""

    def __init__(self, root_dir: Path) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "hypotheses.json"

    def list(self) -> List[HypothesisRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError:
                payload = []
        records = [HypothesisRecord.from_dict(item) for item in payload or []]
        records.sort(key=lambda rec: rec.created_at, reverse=True)
        return records

    def record_result(self, result: AutoTradeResult) -> List[HypothesisRecord]:
        records = self.list()
        new_records: List[HypothesisRecord] = []
        for decision in result.decisions:
            record = self._record_from_decision(decision, result)
            records.append(record)
            new_records.append(record)
        self._save(records)
        return new_records

    def get(self, hypothesis_id: str) -> Optional[HypothesisRecord]:
        for record in self.list():
            if record.id == hypothesis_id:
                return record
        return None

    def upsert(self, updated_record: HypothesisRecord) -> None:
        records = self.list()
        replaced = False
        for idx, record in enumerate(records):
            if record.id == updated_record.id:
                records[idx] = updated_record
                replaced = True
                break
        if not replaced:
            records.append(updated_record)
        self._save(records)

    def update_plan_step(
        self,
        hypothesis_id: str,
        step_id: str,
        *,
        status: Optional[str] = None,
        metadata_patch: Optional[Dict[str, Any]] = None,
    ) -> Optional[HypothesisRecord]:
        record = self.get(hypothesis_id)
        if not record:
            return None
        for step in record.plan:
            if step.id == step_id:
                if status:
                    step.status = status
                if metadata_patch:
                    step.metadata.update(metadata_patch)
                record.updated_at = _utcnow()
                self.upsert(record)
                return record
        return None

    def _save(self, records: List[HypothesisRecord]) -> None:
        records.sort(key=lambda rec: rec.created_at, reverse=True)
        serializable = [record.to_dict() for record in records]
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(serializable, handle, indent=2)
        tmp_path.replace(self.path)

    def _record_from_decision(self, decision: TickerDecision, result: AutoTradeResult) -> HypothesisRecord:
        record_id = uuid.uuid4().hex
        created = _utcnow()
        plan_steps = self._plan_steps(decision)
        notes = decision.final_notes or decision.sequential_plan.notes or ""
        rationale = str(decision.hypothesis.get("rationale") or notes)
        triggers = decision.action_queue or []
        return HypothesisRecord(
            id=record_id,
            ticker=decision.ticker,
            action=(decision.final_decision or decision.immediate_action or "hold").upper(),
            priority=decision.priority,
            status="monitoring",
            rationale=rationale,
            notes=notes,
            plan=plan_steps,
            created_at=created,
            updated_at=created,
            source_snapshot=result.account_snapshot.fetched_at.isoformat(),
            strategy=decision.strategy.to_dict() if decision.strategy else {},
            triggers=[trigger for trigger in triggers if trigger],
        )

    def _plan_steps(self, decision: TickerDecision) -> List[PlanStepRecord]:
        steps: List[PlanStepRecord] = []
        actions = decision.sequential_plan.actions or []
        for idx, description in enumerate(actions, 1):
            steps.append(
                PlanStepRecord(
                    id=f"{decision.ticker.lower()}_{idx}",
                    description=str(description),
                    status="pending",
                    metadata={
                        "next_decision": decision.sequential_plan.next_decision,
                    },
                )
            )
        if not steps:
            steps.append(
                PlanStepRecord(
                    id=f"{decision.ticker.lower()}_plan",
                    description=f"Monitor hypothesis for {decision.ticker} (auto-generated)",
                )
            )
        return steps
