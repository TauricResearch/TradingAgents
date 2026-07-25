"""Read-only market/chart projection from a run's persisted artifacts.

The workbench must never fetch a new quote merely to decorate the UI.  This
module only projects OHLCV rows and dated research records that have already
been stored as observable artifacts during the run.  It deliberately accepts
several vendor-neutral JSON shapes because provider captures use their native
formats (records and pandas ``orient=split`` are both in use).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from math import isfinite
from typing import Any

from .store import RunStore, RunStoreError

_MAX_ARTIFACTS = 64
_MAX_ARTIFACT_BYTES = 5_000_000
_MAX_BARS = 500
_MAX_EVENTS = 200


def build_market_view(store: RunStore, run_id: str) -> dict[str, Any]:
    """Return a bounded, truthful visual projection for one persisted run.

    Invalid or unrelated artifacts are skipped rather than becoming inferred
    prices/news.  An empty response is a valid result and means the execution
    did not capture chartable records.
    """
    bars: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    bar_sources: list[str] = []
    event_sources: list[str] = []
    skipped = 0

    for artifact in _artifact_metadata(store, run_id)[:_MAX_ARTIFACTS]:
        if artifact["media_type"] != "application/json" or artifact["byte_size"] > _MAX_ARTIFACT_BYTES:
            continue
        try:
            raw = store.read_artifact(run_id, artifact["artifact_id"])
            value = _decode_json(raw)
        except (RunStoreError, UnicodeDecodeError, ValueError):
            skipped += 1
            continue
        if value is None:
            skipped += 1
            continue

        extracted_bars = _bars_from_value(value, artifact["artifact_id"])
        extracted_events = _events_from_value(value, artifact["artifact_id"])
        if extracted_bars:
            bars.extend(extracted_bars)
            bar_sources.append(artifact["artifact_id"])
        if extracted_events:
            events.extend(extracted_events)
            event_sources.append(artifact["artifact_id"])

    # A provider can capture the same rows in raw and normalized form.  Keep
    # the latest valid row for a timestamp and make source lineage explicit.
    bars_by_time = {bar["timestamp"]: bar for bar in bars}
    ordered_bars = [bars_by_time[key] for key in sorted(bars_by_time)][-_MAX_BARS:]
    events_by_key = {
        (event["timestamp"], event["title"], event.get("url", "")): event
        for event in events
    }
    ordered_events = sorted(
        events_by_key.values(), key=lambda event: event["timestamp"], reverse=True
    )[:_MAX_EVENTS]

    return {
        "bars": ordered_bars,
        "events": ordered_events,
        "coverage": {
            "bar_source_artifact_ids": list(dict.fromkeys(bar_sources)),
            "event_source_artifact_ids": list(dict.fromkeys(event_sources)),
            "skipped_artifact_count": skipped,
            "as_of_sequence": store.read_snapshot(run_id).latest_sequence,
        },
    }


def _artifact_metadata(store: RunStore, run_id: str) -> list[dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for event in store.read_events(run_id):
        if event.type != "artifact.written":
            continue
        payload = event.payload
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        artifacts.setdefault(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "media_type": str(payload.get("media_type") or "application/octet-stream"),
                "byte_size": int(payload.get("byte_size") or 0),
            },
        )
    return list(artifacts.values())


def _decode_json(raw: bytes) -> Any | None:
    import json

    value = json.loads(raw.decode("utf-8"))
    return value if isinstance(value, (dict, list)) else None


def _bars_from_value(value: Any, artifact_id: str) -> list[dict[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for candidate in _record_candidates(value, keys=("bars", "ohlcv", "prices", "records", "data")):
        rows.extend(candidate)
    return [bar for row in rows if (bar := _normalise_bar(row, artifact_id)) is not None]


def _events_from_value(value: Any, artifact_id: str) -> list[dict[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for candidate in _record_candidates(value, keys=("events", "news", "results", "items")):
        rows.extend(candidate)
    return [event for row in rows if (event := _normalise_event(row, artifact_id)) is not None]


def _record_candidates(value: Any, *, keys: tuple[str, ...]) -> Iterable[list[Mapping[str, Any]]]:
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, Mapping)]
        if records:
            yield records
        return
    if not isinstance(value, Mapping):
        return
    split = _split_records(value)
    if split:
        yield split
    for key in keys:
        child = value.get(key)
        if isinstance(child, list):
            records = [item for item in child if isinstance(item, Mapping)]
            if records:
                yield records
        elif isinstance(child, Mapping):
            nested_split = _split_records(child)
            if nested_split:
                yield nested_split
            else:
                records = [item for item in child.values() if isinstance(item, Mapping)]
                if records:
                    yield records


def _split_records(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    columns = value.get("columns")
    data = value.get("data")
    index = value.get("index")
    if not (
        isinstance(columns, list)
        and isinstance(data, list)
        and isinstance(index, list)
        and len(data) == len(index)
        and all(isinstance(column, str) for column in columns)
    ):
        return []
    records: list[Mapping[str, Any]] = []
    for timestamp, values in zip(index, data, strict=False):
        if not isinstance(values, list) or len(values) != len(columns):
            continue
        record = dict(zip(columns, values, strict=False))
        record.setdefault("timestamp", timestamp)
        records.append(record)
    return records


def _normalise_bar(row: Mapping[str, Any], artifact_id: str) -> dict[str, Any] | None:
    timestamp = _timestamp(_first(row, "timestamp", "date", "Date", "trade_date", "datetime"))
    open_ = _number(_first(row, "open", "Open"))
    high = _number(_first(row, "high", "High"))
    low = _number(_first(row, "low", "Low"))
    close = _number(_first(row, "close", "Close", "adj_close", "Adj Close"))
    if timestamp is None or None in (open_, high, low, close):
        return None
    assert open_ is not None and high is not None and low is not None and close is not None
    if min(open_, high, low, close) <= 0 or high < max(open_, low, close) or low > min(open_, close):
        return None
    volume = _number(_first(row, "volume", "Volume"))
    return {
        "timestamp": timestamp,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        **({"volume": volume} if volume is not None and volume >= 0 else {}),
        "artifact_id": artifact_id,
    }


def _normalise_event(row: Mapping[str, Any], artifact_id: str) -> dict[str, Any] | None:
    title = _first(row, "title", "headline", "name")
    timestamp = _timestamp(_first(row, "published", "published_date", "published_time", "timestamp", "date"))
    if not isinstance(title, str) or not title.strip() or timestamp is None:
        return None
    event: dict[str, Any] = {
        "timestamp": timestamp,
        "title": title.strip()[:280],
        "artifact_id": artifact_id,
    }
    for source, target in (("url", "url"), ("publisher", "source"), ("source", "source")):
        value = row.get(source)
        if isinstance(value, str) and value.strip():
            event[target] = value.strip()[:500]
    sentiment = _first(row, "sentiment", "sentiment_label", "overall_sentiment_label")
    if isinstance(sentiment, str) and sentiment.strip():
        event["sentiment"] = sentiment.strip()[:48].lower()
    score = _number(_first(row, "score", "sentiment_score", "overall_sentiment_score"))
    if score is not None:
        event["score"] = score
    return event


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date().isoformat() if len(raw) == 10 else parsed.isoformat()
