"""Run Recorder — graph node + helper.

After Portfolio Manager finishes, this writes:
- one ``runs`` row in SQLite (status, decision, costs link)
- per-analyst markdown files under ``<data_dir>/runs/<run_id>/``
- one or more ``costs`` rows from the RunCostCallback's totals

This is the P7 boundary contract: every graph run produces a persisted
record. The smoke test in tests/smoke/test_f1_exit_gate.py asserts this
fires for every persona run during the exit-gate check.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tradingagents.persistence import store


_DECISION_RE = re.compile(r"\b(BUY|HOLD|SELL)\b", re.IGNORECASE)


# DeepSeek published prices, USD per 1M tokens (deepseek.com/pricing,
# standard / cache-miss rate). Cache-hit input is billed at a lower rate, so
# when the cost callback splits prompt tokens into hit/miss we bill each at the
# correct rate; otherwise all input tokens fall back to the miss (full) rate.
# These are deliberately conservative defaults used only for the usd_estimate
# instrumentation column — measurement, not enforcement (cost guards stay off).
_DEEPSEEK_PRICING = {
    # model substring -> (input_miss, input_hit, output) USD per 1M tokens
    "deepseek-reasoner": (0.55, 0.14, 2.19),
    "deepseek-chat":     (0.27, 0.07, 1.10),
}
# Fallback applied to any model whose name contains "deepseek" but isn't an
# exact known id (e.g. a dated alias). Uses the deepseek-chat rate.
_DEEPSEEK_DEFAULT_PRICING = (0.27, 0.07, 1.10)


def estimate_usd(
    model: str,
    *,
    in_tokens: int,
    out_tokens: int,
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
) -> Optional[float]:
    """Best-effort USD cost for one (run, model) cost row.

    Returns None when the model isn't a DeepSeek model we have prices for, so
    the costs.usd_estimate column stays NULL rather than silently reporting a
    wrong number (preserves the "we don't always know the price" contract).

    When the cost callback captured DeepSeek's cache split, the hit portion is
    billed at the (cheaper) cache-hit rate and the miss portion at the standard
    rate. Otherwise the full prompt is billed at the standard (miss) rate.
    """
    name = (model or "").lower()
    pricing = None
    for key, rates in _DEEPSEEK_PRICING.items():
        if key in name:
            pricing = rates
            break
    if pricing is None and "deepseek" in name:
        pricing = _DEEPSEEK_DEFAULT_PRICING
    if pricing is None:
        return None
    in_miss_rate, in_hit_rate, out_rate = pricing
    hit = cache_hit_tokens or 0
    miss = cache_miss_tokens or 0
    if hit or miss:
        billed_hit, billed_miss = hit, miss
    else:
        billed_hit, billed_miss = 0, in_tokens
    usd = (
        billed_hit * in_hit_rate
        + billed_miss * in_miss_rate
        + out_tokens * out_rate
    ) / 1_000_000
    return round(usd, 6)


def compute_cache_hit_ratio(
    cache_hit_tokens: Optional[int],
    cache_miss_tokens: Optional[int],
) -> Optional[float]:
    if cache_hit_tokens is None and cache_miss_tokens is None:
        return None
    hit = int(cache_hit_tokens or 0)
    miss = int(cache_miss_tokens or 0)
    total = hit + miss
    if total <= 0:
        return None
    return hit / total


def parse_decision(text: str) -> Optional[str]:
    """Extract BUY/HOLD/SELL from a free-form decision string. Returns None
    when no clear signal is present."""
    if not text:
        return None
    matches = _DECISION_RE.findall(text)
    if not matches:
        return None
    # Prefer the LAST occurrence — typical pattern is reasoning followed by
    # "FINAL TRANSACTION PROPOSAL: **BUY**".
    return matches[-1].upper()


class RunRecorder:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        data_dir: str,
        run_id: str,
        persona_id: Optional[str],
        cost_callback: Any,        # RunCostCallback (duck-typed to ease mocking)
        queue_job_id: Optional[int] = None,
    ) -> None:
        self._conn = conn
        self._data_dir = Path(data_dir)
        self._run_id = run_id
        self._persona_id = persona_id
        self._cost_callback = cost_callback
        self._queue_job_id = queue_job_id
        self._artifact_dir_rel = f"runs/{run_id}"

    def start(self, ticker: str, *, started_ts: str) -> None:
        store.insert_run(
            self._conn,
            run_id=self._run_id,
            ticker=ticker,
            persona_id=self._persona_id,
            started_ts=started_ts,
            artifact_dir=self._artifact_dir_rel,
            queue_job_id=self._queue_job_id,
        )

    def record(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Persist artifacts; return ``state`` unchanged so the graph node
        is a pass-through."""
        ticker = state.get("company_of_interest", "UNKNOWN")
        decision_src = state.get("final_trade_decision") or state.get(
            "trader_investment_plan", ""
        )
        decision = parse_decision(decision_src)

        # Filesystem artifacts
        run_path = self._data_dir / self._artifact_dir_rel
        (run_path / "analysts").mkdir(parents=True, exist_ok=True)
        for key in ("market", "sentiment", "news", "fundamentals", "derivatives"):
            content = state.get(f"{key}_report", "") or ""
            if content:
                (run_path / "analysts" / f"{key}.md").write_text(
                    content, encoding="utf-8"
                )
        (run_path / "trader_plan.md").write_text(
            state.get("trader_investment_plan", "") or "", encoding="utf-8"
        )
        (run_path / "risk_debate.md").write_text(
            json.dumps(state.get("risk_debate_state", {}), indent=2, default=str),
            encoding="utf-8",
        )
        (run_path / "pm_synthesis.md").write_text(
            state.get("final_trade_decision", "") or "", encoding="utf-8"
        )
        # IIC-FORGE F4: write event_context.md when this run was launched
        # in event_alert mode (Secretary.compose_event_alert path).
        event_ctx = state.get("event_context_text", "") or ""
        if event_ctx:
            (run_path / "event_context.md").write_text(event_ctx, encoding="utf-8")
        (run_path / "meta.json").write_text(json.dumps({
            "run_id": self._run_id,
            "persona_id": self._persona_id,
            "ticker": ticker,
            "trade_date": state.get("trade_date"),
            "decision": decision,
        }, indent=2), encoding="utf-8")

        # Costs
        totals = self._cost_callback.totals_by_model()
        for model_name, counts in totals.items():
            # cache_hit/miss are present when the callback captured DeepSeek's
            # prompt-cache usage; default to 0 for older callbacks / other
            # providers so this stays backward-compatible.
            cache_hit = counts.get("cache_hit_tokens", 0)
            cache_miss = counts.get("cache_miss_tokens", 0)
            usd = estimate_usd(
                model_name,
                in_tokens=counts["in_tokens"],
                out_tokens=counts["out_tokens"],
                cache_hit_tokens=cache_hit,
                cache_miss_tokens=cache_miss,
            )
            store.record_cost(
                self._conn,
                run_id=self._run_id,
                provider="deepseek" if "deepseek" in model_name else "unknown",
                model=model_name,
                in_tokens=counts["in_tokens"],
                out_tokens=counts["out_tokens"],
                usd_estimate=usd,
                cache_hit_tokens=cache_hit,
                cache_miss_tokens=cache_miss,
            )

        # DB finalize
        store.finalize_run(
            self._conn,
            run_id=self._run_id,
            ended_ts=datetime.now(timezone.utc).isoformat(),
            status="complete",
            decision=decision,
            confidence=None,   # F1 doesn't compute confidence; defer to F2
        )

        return state


def make_run_recorder_node(recorder: RunRecorder):
    """LangGraph node factory: returns a callable that records the state."""
    def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        return recorder.record(state)
    return _node
