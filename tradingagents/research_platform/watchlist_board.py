"""Local watchlist board assembled from cached artifacts and archived research."""

from __future__ import annotations

from datetime import date
from typing import Any

from .artifact_store import JsonArtifactStore
from .data_health import build_cache_data_health
from .run_archive import JsonResearchRunArchive
from .watchlist import JsonWatchlistStore

_EARLIEST_DATE = date(1900, 1, 1)


def build_watchlist_board(
    store: JsonArtifactStore,
    watchlist: JsonWatchlistStore,
) -> dict[str, Any]:
    """Return a compact, read-only research summary for explicit watchlist symbols."""

    archive = JsonResearchRunArchive(store.root)
    entries = watchlist.list_entries()
    items = [
        _build_item(store, archive, entry.symbol)
        | {"name": entry.name, "sectors": entry.sectors, "source": entry.source}
        for entry in entries
    ]
    return {
        "total": len(items),
        "researched": sum(item["latest_research_at"] is not None for item in items),
        "sectors": sorted({sector for entry in entries for sector in entry.sectors}),
        "items": items,
    }


def _build_item(
    store: JsonArtifactStore,
    archive: JsonResearchRunArchive,
    symbol: str,
) -> dict[str, Any]:
    bars = sorted(
        store.load_price_bars(symbol, _EARLIEST_DATE, date.max), key=lambda item: item.date
    )
    fundamentals = store.load_fundamentals(symbol)
    news = store.load_news(symbol, _EARLIEST_DATE, date.max)
    run_summaries = archive.list_runs(symbol)
    latest_run_id = run_summaries[0].run_id if run_summaries else None
    latest_run = archive.load_bundle(symbol, latest_run_id) if latest_run_id is not None else None
    health = build_cache_data_health(
        price_bars=bars,
        fundamentals=fundamentals,
        news=news,
        reference_as_of_date=(latest_run.as_of_date.date() if latest_run is not None else None),
    )
    latest_bar = bars[-1] if bars else None
    return {
        "symbol": symbol,
        "last_close": latest_bar.close if latest_bar is not None else None,
        "currency": latest_bar.currency if latest_bar is not None else None,
        "last_price_date": latest_bar.date.isoformat() if latest_bar is not None else None,
        "data_status": _summarize_health(health["items"]),
        "latest_research_at": (
            latest_run.generated_at.isoformat() if latest_run is not None else None
        ),
        "latest_run_id": latest_run_id,
        "decision": latest_run.signal.direction.value if latest_run and latest_run.signal else None,
        "risk_decision": (
            latest_run.risk_review.decision.value if latest_run and latest_run.risk_review else None
        ),
    }


def _summarize_health(items: list[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in items}
    if "missing" in statuses:
        return "missing"
    if "lagging" in statuses:
        return "lagging"
    if "aligned" in statuses:
        return "aligned"
    return "available"
