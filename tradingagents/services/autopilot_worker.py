from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tradingagents.services.account import AccountService, AccountSnapshot
from tradingagents.services.auto_trade import AutoTradeResult, AutoTradeService, TickerDecision
from tradingagents.services.autopilot_events import AutopilotEventQueue, HypothesisEvent, _utcnow
from tradingagents.services.hypothesis_store import HypothesisRecord, HypothesisStore, PlanStepRecord


@dataclass
class ProcessedEvent:
    event: HypothesisEvent
    status: str
    message: str


class AutopilotWorker:
    """Processes hypothesis events and runs focused reevaluations."""

    def __init__(
        self,
        results_root: Path,
        auto_trader: AutoTradeService,
        account_service: AccountService,
    ) -> None:
        self.results_root = Path(results_root)
        self.store = HypothesisStore(self.results_root / "hypotheses")
        self.queue = AutopilotEventQueue(self.results_root / "autopilot")
        self.auto_trader = auto_trader
        self.account_service = account_service

    def enqueue_event(self, hypothesis_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> HypothesisEvent:
        event = HypothesisEvent(
            id=f"evt_{hypothesis_id}_{event_type}_{_utcnow()}",
            hypothesis_id=hypothesis_id,
            event_type=event_type,
            payload=payload or {},
            created_at=_utcnow(),
        )
        self.queue.enqueue(event)
        return event

    def list_events(self) -> List[HypothesisEvent]:
        return self.queue.list()

    def process_all(self) -> List[ProcessedEvent]:
        events = self.queue.dequeue_all()
        processed: List[ProcessedEvent] = []
        for event in events:
            status, message = self._handle_event(event)
            processed.append(ProcessedEvent(event=event, status=status, message=message))
        return processed

    def _handle_event(self, event: HypothesisEvent) -> Tuple[str, str]:
        record = self.store.get(event.hypothesis_id)
        if not record:
            return ("skipped", f"Hypothesis {event.hypothesis_id} not found")

        step = record.next_open_step()
        if not step:
            record.status = "completed"
            record.updated_at = _utcnow()
            self.store.upsert(record)
            return ("completed", "Hypothesis already completed; marked as completed")

        step.status = "done"
        step.metadata.setdefault("events", []).append(
            {
                "type": event.event_type,
                "payload": event.payload,
                "timestamp": event.created_at,
            }
        )
        record.updated_at = _utcnow()
        if record.next_open_step() is None:
            record.status = "completed"
        self.store.upsert(record)

        reevaluation_msg = self._reevaluate(record, event)
        return ("updated", f"Marked step '{step.description}' as done. {reevaluation_msg}")

    def _reevaluate(self, record: HypothesisRecord, event: HypothesisEvent) -> str:
        try:
            snapshot = self.account_service.refresh()
        except Exception as exc:
            return f"Failed to refresh account snapshot: {exc}"

        try:
            result = self.auto_trader.run(
                snapshot,
                focus_override=[record.ticker],
                allow_market_closed=True,
            )
        except Exception as exc:
            return f"Auto-trade reevaluation failed: {exc}"

        decision = self._extract_decision(result, record.ticker)
        if not decision:
            return "No decision returned for ticker"

        self._apply_decision(record, decision)
        record.updated_at = _utcnow()
        self.store.upsert(record)
        return f"Reevaluated with action {record.action}" 

    def _extract_decision(self, result: AutoTradeResult, ticker: str) -> Optional[TickerDecision]:
        for decision in result.decisions:
            if decision.ticker.upper() == ticker.upper():
                return decision
        return None

    def _apply_decision(self, record: HypothesisRecord, decision: TickerDecision) -> None:
        record.action = (decision.final_decision or decision.immediate_action or record.action).upper()
        record.priority = decision.priority
        record.notes = decision.final_notes or decision.sequential_plan.notes or record.notes
        record.plan = self._build_plan_from_decision(record.ticker, decision)
        record.triggers = decision.action_queue or record.triggers
        record.status = "monitoring"
        if getattr(decision, "strategy", None):
            record.strategy = decision.strategy.to_dict()

    def _build_plan_from_decision(self, ticker: str, decision: TickerDecision) -> List[PlanStepRecord]:
        steps: List[PlanStepRecord] = []
        actions = decision.sequential_plan.actions or []
        for idx, action in enumerate(actions, 1):
            steps.append(
                PlanStepRecord(
                    id=f"{ticker.lower()}_{idx}",
                    description=str(action),
                    status="pending",
                    metadata={
                        "next_decision": decision.sequential_plan.next_decision,
                        "source": "autopilot",
                    },
                )
            )
        if not steps:
            steps.append(
                PlanStepRecord(
                    id=f"{ticker.lower()}_plan",
                    description=f"Monitor hypothesis for {ticker}",
                    status="pending",
                )
            )
        return steps
