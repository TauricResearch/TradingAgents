"""Read-only Layer 2 cache lookup for captured market-view events.

The chart is allowed to ask whether a previously generated public Layer 2
review is available, but it is never a new data-collection or model-execution
surface.  In particular, this module only accepts an event which can be
re-derived from the run's persisted market view and only reads the existing
content-addressed news Layer 2 cache.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.news_layers import FileDeepAnalysisCache, decide_layer2

from .market_view import build_market_view
from .store import RunStore


def build_market_event_layer2_view(
    store: RunStore,
    run_id: str,
    *,
    artifact_id: str,
    timestamp: str,
    title: str,
) -> dict[str, Any] | None:
    """Return a cached public review for one persisted chart event.

    ``None`` means that the supplied event is not a chart event in this run.
    A cache miss is deliberately represented in the returned payload instead
    of causing a model/vendor call.  This is both a cost boundary and prevents
    a visual click from fabricating a deeper conclusion.
    """
    event = _persisted_event(
        store,
        run_id,
        artifact_id=artifact_id,
        timestamp=timestamp,
        title=title,
    )
    if event is None:
        return None

    snapshot = store.read_snapshot(run_id)
    # A marker alone is not sufficient evidence for an LLM conclusion.  The
    # existing Layer 2 policy therefore records the explicit evidence-thin
    # reason and creates the same kind of content-addressed request key used
    # by news_advisor.py.  No raw title/prompt is stored in the cache key.
    trigger = decide_layer2(
        evidence_status="insufficient",
        subject=f"{snapshot.ticker}:{event['artifact_id']}:{event['title']}",
        data_as_of=event["timestamp"],
    )
    assert trigger.should_run and trigger.cache_key is not None

    configured = get_config().get("news_layer2_cache_dir")
    cache_dir = str(configured or "").strip()
    cached = FileDeepAnalysisCache(cache_dir).get(trigger.cache_key) if cache_dir else None
    response: dict[str, Any] = {
        "status": "cached" if cached is not None else "not_available",
        "event": event,
        "trigger": {
            "reasons": list(trigger.reasons),
            "cache_key": trigger.cache_key,
        },
        "cache_configured": bool(cache_dir),
    }
    if cached is not None:
        response["conclusion"] = _displayable_conclusion(cached)
    return response


def _persisted_event(
    store: RunStore,
    run_id: str,
    *,
    artifact_id: str,
    timestamp: str,
    title: str,
) -> dict[str, str] | None:
    """Re-check the exact event projection; never trust chart query strings."""
    for event in build_market_view(store, run_id)["events"]:
        if (
            event["artifact_id"] == artifact_id
            and event["timestamp"] == timestamp
            and event["title"] == title
        ):
            return {
                "artifact_id": artifact_id,
                "timestamp": timestamp,
                "title": title,
            }
    return None


def _displayable_conclusion(cached: Mapping[str, Any]) -> dict[str, Any]:
    """Narrow a sanitized cache entry to the stable public UI contract."""
    conclusion = str(cached.get("conclusion") or "").strip()[:500]
    return {
        "conclusion": conclusion,
        "evidence_gaps": _public_strings(cached.get("evidence_gaps"), limit=5),
        "material_risks": _public_strings(cached.get("material_risks"), limit=5),
        "source_ids": _public_strings(cached.get("source_ids"), limit=50),
    }


def _public_strings(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:240] for item in value[:limit] if str(item).strip()]
