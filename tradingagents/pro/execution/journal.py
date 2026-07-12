"""OMS write-ahead journal (go-live Phase 2).

Append-only JSONL with an explicit fsync contract:

- ``intent`` is fsynced BEFORE any network send — an order the venue
  might know about is always an order the journal knows about.
- ACKED, every terminal transition, and ``protection_pending`` fsync
  (crash-vulnerable windows the boot recovery must see).
- Intermediate events flush only — they are reconstructible from the
  venue via the resolve loop, so losing them costs a REST call, not
  correctness.

Replay rebuilds the ManagedOrder table; corrupt trailing lines (torn
write at crash) are tolerated, corruption mid-file is not.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from tradingagents.contracts import utc_now
from tradingagents.pro.execution.interface import OrderSpec, OrderState
from tradingagents.pro.execution.orders import ManagedOrder

logger = logging.getLogger(__name__)

FSYNC_EVENTS = frozenset({"intent", "protection_pending"})
FSYNC_STATES = frozenset({
    OrderState.ACKED, OrderState.FILLED, OrderState.CANCELED,
    OrderState.REJECTED, OrderState.ABANDONED,
})


class OrderJournal:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else None
        self._handle = None
        self._seq = 0

    # --- writing ---------------------------------------------------------------

    def append(self, event: str, coid: str, payload: dict | None = None, *,
               fsync: bool = False) -> None:
        record = {
            "seq": self._seq,
            "ts": utc_now().isoformat(),
            "event": event,
            "coid": coid,
            "payload": payload or {},
        }
        self._seq += 1
        if self._path is None:
            return
        if self._handle is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8")
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._handle.flush()
        if fsync:
            os.fsync(self._handle.fileno())

    def intent(self, order: ManagedOrder) -> None:
        self.append("intent", order.client_order_id, {
            "spec": _spec_to_json(order.spec),
            "leg": order.leg,
            "bracket_group": order.bracket_group,
        }, fsync=True)

    def submitting(self, coid: str) -> None:
        self.append("submitting", coid)

    def transition(self, order: ManagedOrder, from_state: OrderState) -> None:
        self.append("transition", order.client_order_id, {
            "from": from_state.value,
            "to": order.state.value,
            "venue_order_id": order.venue_order_id,
            "filled_quantity": order.filled_quantity,
            "avg_fill_price": order.avg_fill_price,
            "commission": order.commission,
            "reason": order.reason,
        }, fsync=order.state in FSYNC_STATES)

    def protection_pending(self, entry_coid: str, deadline_ts: float,
                           plan: dict | None = None) -> None:
        # the plan payload rides along so recovery can still place the
        # protection for an entry that filled while we were dead
        self.append("protection_pending", entry_coid,
                    {"deadline": deadline_ts, "plan": plan or {}}, fsync=True)

    def protection_confirmed(self, entry_coid: str) -> None:
        self.append("protection_confirmed", entry_coid)

    # --- replay ----------------------------------------------------------------

    def replay(self) -> tuple[dict[str, ManagedOrder], dict[str, dict]]:
        """Rebuild (orders, pending_protection) from disk. Pending values
        are ``{"deadline": ts, "plan": {...}}``."""
        orders: dict[str, ManagedOrder] = {}
        pending: dict[str, dict] = {}
        if self._path is None or not self._path.exists():
            return orders, pending
        lines = self._path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if i == len(lines) - 1:
                    logger.warning("torn final journal line dropped (crash)")
                    continue
                raise
            self._seq = max(self._seq, record["seq"] + 1)
            event, coid = record["event"], record["coid"]
            payload = record.get("payload", {})
            if event == "intent":
                orders[coid] = ManagedOrder(
                    spec=_spec_from_json(payload["spec"]),
                    leg=payload.get("leg", "entry"),
                    bracket_group=payload.get("bracket_group", ""),
                )
            elif event == "submitting" and coid in orders:
                orders[coid].sent = True
            elif event == "transition" and coid in orders:
                order = orders[coid]
                order.state = OrderState(payload["to"])
                order.venue_order_id = payload.get("venue_order_id", "")
                order.filled_quantity = payload.get("filled_quantity", 0.0)
                order.avg_fill_price = payload.get("avg_fill_price", 0.0)
                order.commission = payload.get("commission", 0.0)
                order.reason = payload.get("reason", "")
            elif event == "protection_pending":
                pending[coid] = {"deadline": payload.get("deadline", 0.0),
                                 "plan": payload.get("plan", {})}
            elif event == "protection_confirmed":
                pending.pop(coid, None)
        return orders, pending

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _spec_to_json(spec: OrderSpec) -> dict:
    data = asdict(spec)
    data["created_at"] = spec.created_at.isoformat()
    return data


def _spec_from_json(data: dict) -> OrderSpec:
    from datetime import datetime

    payload = dict(data)
    payload["created_at"] = datetime.fromisoformat(payload["created_at"])
    return OrderSpec(**payload)
