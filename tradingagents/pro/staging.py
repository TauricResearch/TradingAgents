"""Staged rollout: shadow-fill tracking + the promotion report (Phase 6).

Three per-pair tiers, selected by the arming ceremony and honored by the
router's mode routing:

- **shadow** — decisions run live, orders fill on the PAPER venue, and
  this module records what the LIVE fill would have been (cross the real
  spread: BUY at ask, SELL at bid) so paper-vs-live divergence is
  measured, not assumed.
- **canary** — live venue at the venue-minimum size, everything else at
  its tightest.
- **live** — live venue at configured sizing.

Promotion is never automatic. ``promotion_report`` scores each pair
against the thresholds the operator wrote in live.yaml (suggested
defaults: ≥28 days shadow, ≥14 days canary, zero unexplained
reconciliation incidents) and the human re-runs the arming ceremony at
the new tier.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowFill:
    symbol: str
    side: str
    quantity: float
    paper_fill_price: float
    live_estimate: float          # ask for BUY, bid for SELL (spread crossed)
    divergence_bps: float         # +ve = live would have been worse
    at: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class ShadowFillTracker:
    """Records the would-have-been live fill for shadow-mode paper fills.

    ``quote_fn(symbol) -> SpotQuote`` is the live read path (Delta market
    data); a quote failure records nothing and never blocks the trade —
    shadow exists to measure, not to gate.
    """

    def __init__(self, quote_fn, store_path: str | Path | None = None,
                 metrics=None):
        self._quote_fn = quote_fn
        self._path = Path(store_path) if store_path else None
        self._metrics = metrics

    def record(self, symbol: str, side: str, quantity: float,
               paper_fill_price: float) -> ShadowFill | None:
        try:
            quote = self._quote_fn(symbol)
            live_estimate = quote.ask if side == "BUY" else quote.bid
        except Exception:
            logger.warning("shadow fill: live quote unavailable for %s; "
                           "divergence not recorded", symbol, exc_info=True)
            return None
        if not live_estimate or paper_fill_price <= 0:
            return None
        sign = 1 if side == "BUY" else -1
        divergence_bps = sign * 10_000.0 * (
            live_estimate - paper_fill_price) / paper_fill_price
        fill = ShadowFill(
            symbol=symbol, side=side, quantity=quantity,
            paper_fill_price=paper_fill_price, live_estimate=live_estimate,
            divergence_bps=round(divergence_bps, 4),
            at=datetime.now(timezone.utc).isoformat(),
        )
        if self._path is not None:
            from tradingagents.pro.persistence import append_line_fsync

            append_line_fsync(self._path, json.dumps(fill.as_dict(),
                                                     sort_keys=True))
        if self._metrics is not None:
            self._metrics.inc("shadow_fills_total", symbol=symbol)
            self._metrics.set_gauge("shadow_divergence_bps",
                                    divergence_bps, symbol=symbol)
        return fill

    def load(self) -> list[dict]:
        if self._path is None or not self._path.exists():
            return []
        out = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # torn final line
        return out


# --- promotion report -------------------------------------------------------------


def _tier_since(audit_entries, pair: str, tier: str) -> datetime | None:
    """Most recent arming_armed for this pair+tier (from the audit chain)."""
    latest = None
    for entry in audit_entries:
        if (entry.get("event") == "arming_armed"
                and entry.get("payload", {}).get("pair") == pair
                and entry.get("payload", {}).get("tier") == tier):
            latest = datetime.fromisoformat(entry["ts"])
    return latest


def promotion_report(*, pairs, arming, recorder_runs, journal,
                     audit_entries, shadow_fills, promotion_thresholds,
                     now: datetime | None = None) -> dict:
    """Everything the operator needs to decide a tier promotion, per pair.
    Pure function over existing stores — read-only, deterministic."""
    now = now or datetime.now(timezone.utc)
    thresholds = {
        "min_shadow_days": float(promotion_thresholds.get("min_shadow_days", 28)),
        "min_canary_days": float(promotion_thresholds.get("min_canary_days", 14)),
        "max_reconciliation_incidents": int(
            promotion_thresholds.get("max_reconciliation_incidents", 0)),
    }
    drift_events = sum(
        1 for e in audit_entries
        if e.get("event") == "reconciliation"
        and not e.get("payload", {}).get("in_sync", True)
    )
    report: dict = {"generated_at": now.isoformat(),
                    "thresholds": thresholds,
                    "reconciliation_incidents": drift_events,
                    "pairs": {}}
    for pair in pairs:
        record = arming.get(pair)
        tier = record.effective_tier(now)
        runs = [r for r in recorder_runs if r.symbol == pair]
        rejections = sum(1 for r in runs if r.rejection)
        pair_shadow = [f for f in shadow_fills if f.get("symbol") == pair]
        mean_div = (sum(abs(f["divergence_bps"]) for f in pair_shadow)
                    / len(pair_shadow)) if pair_shadow else None
        shadow_started = _tier_since(audit_entries, pair, "shadow")
        canary_started = _tier_since(audit_entries, pair, "canary")
        shadow_days = ((now - shadow_started).total_seconds() / 86400
                       if shadow_started else 0.0)
        canary_days = ((now - canary_started).total_seconds() / 86400
                       if canary_started else 0.0)
        mode_stats = (journal.get("by_mode") or {})

        blockers: list[str] = []
        if drift_events > thresholds["max_reconciliation_incidents"]:
            blockers.append(
                f"{drift_events} reconciliation incident(s) exceed the "
                f"allowed {thresholds['max_reconciliation_incidents']}")
        next_tier = {"paper": "shadow", "shadow": "canary",
                     "canary": "live"}.get(tier)
        if tier == "shadow" and shadow_days < thresholds["min_shadow_days"]:
            blockers.append(f"shadow {shadow_days:.1f}d < required "
                            f"{thresholds['min_shadow_days']:.0f}d")
        if tier == "canary" and canary_days < thresholds["min_canary_days"]:
            blockers.append(f"canary {canary_days:.1f}d < required "
                            f"{thresholds['min_canary_days']:.0f}d")

        report["pairs"][pair] = {
            "tier": tier,
            "next_tier": next_tier,
            "decisions": len(runs),
            "gate_rejection_rate": (rejections / len(runs)) if runs else None,
            "shadow_days": round(shadow_days, 1),
            "canary_days": round(canary_days, 1),
            "shadow_fills": len(pair_shadow),
            "mean_abs_divergence_bps": (round(mean_div, 2)
                                        if mean_div is not None else None),
            "journal_by_mode": dict(mode_stats),
            "promotion_ready": not blockers and next_tier is not None,
            "blockers": blockers,
        }
    return report


def render_promotion_report(report: dict) -> str:
    lines = ["promotion report", "-" * 44,
             f"reconciliation incidents: {report['reconciliation_incidents']} "
             f"(allowed {report['thresholds']['max_reconciliation_incidents']})"]
    for pair, info in report["pairs"].items():
        lines.append(f"\n{pair}: tier={info['tier']}"
                     + (f" -> candidate {info['next_tier']}"
                        if info["next_tier"] else " (top tier)"))
        lines.append(f"  decisions {info['decisions']} · gate-rejection rate "
                     f"{info['gate_rejection_rate'] if info['gate_rejection_rate'] is not None else '—'}")
        lines.append(f"  shadow {info['shadow_days']}d ({info['shadow_fills']} "
                     f"fills, mean |divergence| "
                     f"{info['mean_abs_divergence_bps'] or '—'} bps) · "
                     f"canary {info['canary_days']}d")
        if info["promotion_ready"]:
            lines.append("  READY — promotion is still a human decision: "
                         "re-run the arming ceremony at the new tier")
        else:
            for blocker in info["blockers"] or ["nothing to promote"]:
                lines.append(f"  BLOCKED: {blocker}")
    lines.append("-" * 44)
    lines.append("promotion is never automatic.")
    return "\n".join(lines)
