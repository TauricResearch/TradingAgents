"""Deterministic client order IDs (go-live Phase 2).

Same decision + same leg → same coid, forever. The venue dedupes on
client_order_id, so a crash anywhere between "journaled" and "response
received" is safe to resubmit — the id is re-derivable from journaled
inputs alone. Format: ``ta`` + 24 hex chars (26 total; Delta caps
client_order_id at 32).
"""

from __future__ import annotations

import hashlib
import json

ENTRY = "entry"
STOP = "sl"
FLATTEN = "flatten"


def take_profit_leg(index: int) -> str:
    return f"tp{index + 1}"


def decision_hash(rec) -> str:
    """Hash of the execution-relevant recommendation fields — NOT rec.id
    (a uuid4 that would not survive re-derivation after a crash)."""
    body = {
        "symbol": rec.symbol,
        "action": getattr(rec.action, "value", rec.action),
        "quantity": rec.position_size.quantity,
        "entry": rec.entry_price,
        "stop": rec.stop_loss,
        "tps": [(tp.price, tp.size_fraction) for tp in rec.take_profits],
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def client_order_id(run_id: str, decision: str, leg: str) -> str:
    digest = hashlib.sha256(f"{run_id}|{decision}|{leg}".encode()).hexdigest()
    return f"ta{digest[:24]}"
