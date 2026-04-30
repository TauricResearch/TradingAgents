"""Local preference cache for the Streamlit web console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.models import AnalysisRequest


MAX_RECENT_REQUESTS = 8


def preferences_path() -> Path:
    return Path(DEFAULT_CONFIG["data_cache_dir"]) / "web_preferences.json"


def load_preferences(path: Path | None = None) -> Dict[str, Any]:
    path = path or preferences_path()
    if not path.exists():
        return {"recent_requests": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"recent_requests": []}
    if not isinstance(data, dict):
        return {"recent_requests": []}
    recent = data.get("recent_requests", [])
    if not isinstance(recent, list):
        recent = []
    return {"recent_requests": recent[:MAX_RECENT_REQUESTS]}


def save_preferences(data: Dict[str, Any], path: Path | None = None) -> None:
    path = path or preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def remember_request(request: AnalysisRequest, path: Path | None = None) -> None:
    data = load_preferences(path)
    entry = request.to_cache_entry()
    recent = [
        item for item in data.get("recent_requests", [])
        if _cache_identity(item) != _cache_identity(entry)
    ]
    data["recent_requests"] = [entry] + recent[: MAX_RECENT_REQUESTS - 1]
    save_preferences(data, path)


def recent_requests(path: Path | None = None) -> List[AnalysisRequest]:
    data = load_preferences(path)
    requests = []
    for entry in data.get("recent_requests", []):
        try:
            requests.append(AnalysisRequest.from_cache_entry(entry))
        except (TypeError, ValueError):
            continue
    return requests


def latest_request(path: Path | None = None) -> Optional[AnalysisRequest]:
    requests = recent_requests(path)
    return requests[0] if requests else None


def _cache_identity(entry: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        entry.get("ticker"),
        entry.get("output_language"),
        tuple(entry.get("analysts", [])),
        entry.get("research_depth"),
        entry.get("llm_provider"),
        entry.get("quick_think_llm"),
        entry.get("deep_think_llm"),
    )
