"""Per-pair live-arming state (go-live Phase 4).

Arming is deliberate, expiring, and auditable. A pair is PAPER until an
operator completes the ceremony (``tradingagents-pro arm-live``); arming
carries a tier (shadow/canary/live), an expiry (default 30 days), and is
cleared by any disarm, expiry, or loss-limit breach. Every transition is
persisted atomically to the /data volume and appended to the hash-chained
audit log, so the arming decision and its evidence are tamper-evident.

This module holds STATE only — it grants no capability. The router still
runs every deterministic gate; arming just decides whether a pair's
orders may leave the paper venue at all (Phase 6 wiring). Nothing here is
an override path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from tradingagents.contracts import utc_now

TIERS = ("shadow", "canary", "live")
DEFAULT_TTL_DAYS = 30


@dataclass
class PairArming:
    pair: str
    tier: str = "paper"          # paper | shadow | canary | live
    armed_at: str = ""           # ISO8601
    expires_at: str = ""         # ISO8601; empty = non-expiring (paper)
    disarm_reason: str = ""      # set when a live tier was disarmed

    @property
    def is_live_tier(self) -> bool:
        return self.tier in ("canary", "live")

    def expired(self, now=None) -> bool:
        if not self.expires_at:
            return False
        now = now or utc_now()
        from datetime import datetime

        return now >= datetime.fromisoformat(self.expires_at)

    def effective_tier(self, now=None) -> str:
        """Tier honored right now — expiry silently demotes to paper
        (the reason is surfaced separately)."""
        if self.tier != "paper" and self.expired(now):
            return "paper"
        return self.tier


class ArmingStore:
    """Persistent per-pair arming with an audited transition log."""

    def __init__(self, path: str | Path, audit=None, pairs=("BTC-USD", "XAUUSD")):
        self.path = Path(path)
        self._audit = audit
        self._pairs = tuple(pairs)
        self._state: dict[str, PairArming] = {
            p: PairArming(pair=p) for p in self._pairs
        }
        self._mtime: float = 0.0
        self._load()

    # --- persistence ---------------------------------------------------------------

    def _maybe_reload(self) -> None:
        """The CLI ceremony and the running service are separate processes
        sharing arming.json — reads pick up external writes (Phase 6)."""
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return
        if mtime != self._mtime:
            self._load()

    def _load(self) -> None:
        import json

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "corrupt arming state %s; defaulting all pairs to paper",
                self.path, exc_info=True)
            return
        for pair, data in raw.items():
            self._state[pair] = PairArming(**data)

    def _save(self) -> None:
        from tradingagents.pro.persistence import atomic_write_json

        atomic_write_json(self.path,
                          {p: asdict(a) for p, a in self._state.items()})

    def _record(self, event: str, payload: dict) -> None:
        if self._audit is not None:
            self._audit.append(event, payload)

    # --- transitions ---------------------------------------------------------------

    def arm(self, pair: str, tier: str, operator: str,
            ttl_days: int = DEFAULT_TTL_DAYS) -> PairArming:
        if pair not in self._state:
            raise ValueError(f"unknown pair {pair!r}; known {self._pairs}")
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
        if not operator:
            raise ValueError("operator identity required to arm")
        now = utc_now()
        record = PairArming(
            pair=pair, tier=tier, armed_at=now.isoformat(),
            expires_at=(now + timedelta(days=ttl_days)).isoformat(),
        )
        self._state[pair] = record
        self._save()
        self._record("arming_armed", {
            "pair": pair, "tier": tier, "operator": operator,
            "expires_at": record.expires_at, "ttl_days": ttl_days,
        })
        return record

    def disarm(self, pair: str, reason: str, operator: str = "") -> PairArming:
        if pair not in self._state:
            raise ValueError(f"unknown pair {pair!r}")
        record = PairArming(pair=pair, tier="paper", disarm_reason=reason)
        self._state[pair] = record
        self._save()
        self._record("arming_disarmed", {
            "pair": pair, "reason": reason, "operator": operator,
        })
        return record

    def disarm_all(self, reason: str, operator: str = "") -> None:
        for pair in self._pairs:
            self.disarm(pair, reason, operator)

    # --- queries ---------------------------------------------------------------------

    def get(self, pair: str) -> PairArming:
        self._maybe_reload()
        return self._state[pair]

    def effective_tier(self, pair: str, now=None) -> str:
        self._maybe_reload()
        record = self._state.get(pair)
        return record.effective_tier(now) if record else "paper"

    def is_live(self, pair: str, now=None) -> bool:
        """True only for canary/live tiers that have not expired — the
        gate Phase 6 consults before letting an order reach a live venue."""
        self._maybe_reload()
        record = self._state.get(pair)
        return bool(record and record.effective_tier(now) in ("canary", "live"))

    def status(self, now=None) -> dict:
        """Dashboard view: per-pair label with expiry demotion surfaced."""
        self._maybe_reload()
        out = {}
        for pair, record in self._state.items():
            effective = record.effective_tier(now)
            demoted = record.tier != "paper" and effective == "paper"
            if effective == "paper":
                label = "PAPER"
                if demoted:
                    label = f"LIVE — DISARMED (arming expired {record.expires_at[:10]})"
                elif record.disarm_reason:
                    label = f"LIVE — DISARMED ({record.disarm_reason})"
            else:
                label = f"LIVE — ARMED ({effective})"
            out[pair] = {
                "pair": pair,
                "tier": effective,
                "configured_tier": record.tier,
                "label": label,
                "armed_at": record.armed_at,
                "expires_at": record.expires_at,
                "expired": demoted,
                "disarm_reason": record.disarm_reason,
            }
        return out
