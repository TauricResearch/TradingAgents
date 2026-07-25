"""Lightweight progress events for data vendor calls."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DataProgressEvent:
    stage: str
    method: str
    vendor: str
    message: str
    run_id: str | None = None
    turn_id: str | None = None
    graph_task_id: str | None = None
    tool_call_id: str | None = None
    vendor_call_id: str | None = None
    artifact_id: str | None = None


ProgressSink = Callable[[DataProgressEvent], None]
_progress_sink: ProgressSink | None = None


def set_progress_sink(sink: ProgressSink | None) -> None:
    global _progress_sink
    _progress_sink = sink


def emit_progress(
    stage: str,
    method: str,
    vendor: str,
    message: str,
    *,
    vendor_call_id: str | None = None,
    artifact_id: str | None = None,
) -> None:
    if _progress_sink is None:
        return
    try:
        from tradingagents.observability.provenance import current_progress_correlation

        correlation = current_progress_correlation()
        if vendor_call_id is not None:
            correlation["vendor_call_id"] = vendor_call_id
        if artifact_id is not None:
            correlation["artifact_id"] = artifact_id
        _progress_sink(
            DataProgressEvent(
                stage=stage,
                method=method,
                vendor=vendor,
                message=message,
                **correlation,
            )
        )
    except Exception:
        return


@contextmanager
def capture_progress() -> Iterator[list[DataProgressEvent]]:
    events: list[DataProgressEvent] = []
    previous = _progress_sink
    set_progress_sink(events.append)
    try:
        yield events
    finally:
        set_progress_sink(previous)


@contextmanager
def progress_sink(sink: ProgressSink | None) -> Iterator[None]:
    previous = _progress_sink
    set_progress_sink(sink)
    try:
        yield
    finally:
        set_progress_sink(previous)


# ---------------------------------------------------------------------------
# Data-call progress emission helpers (moved from interface.py)
# ---------------------------------------------------------------------------


def _emit_data_progress(
    stage: str,
    method: str,
    vendor: str,
    args: tuple[Any, ...],
    detail: str | None = None,
    *,
    vendor_call_id: str | None = None,
    artifact_id: str | None = None,
) -> None:
    labels = {
        "start": "数据调用开始",
        "success": "数据调用成功",
        "failure": "数据调用失败",
        "skipped": "数据调用跳过",
    }
    context = _format_progress_context(method, args)
    parts = [f"{labels.get(stage, stage)}：{method}", vendor]
    if context and stage == "start":
        parts.append(context)
    if detail:
        parts.append(_sanitize_progress_text(detail))
    emit_progress(
        stage,
        method,
        vendor,
        " | ".join(parts),
        vendor_call_id=vendor_call_id,
        artifact_id=artifact_id,
    )


def _emit_supplement_progress(method: str, primary_vendor: str, next_vendor: str) -> None:
    emit_progress(
        "supplement",
        method,
        next_vendor,
        f"数据源补充：{method} | {primary_vendor} 覆盖不足，继续尝试 {next_vendor}",
    )


def _format_progress_context(method: str, args: tuple[Any, ...]) -> str:
    if not args:
        return ""
    if method in {"get_news", "get_stock_data"} and len(args) >= 3:
        return f"{args[0]} | {args[1]}~{args[2]}"
    if method == "get_global_news" and args:
        return str(args[0])
    if method in {"get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"}:
        parts = [str(args[0])]
        if len(args) >= 2 and args[-1]:
            parts.append(str(args[-1]))
        return " | ".join(parts)
    return " | ".join(str(value) for value in args[:3])


def _sanitize_progress_text(text: str) -> str:
    sanitized = str(text).replace("\n", " ").strip()
    for env_name, env_value in os.environ.items():
        if not env_value or len(env_value) < 8:
            continue
        if any(token in env_name.upper() for token in ("KEY", "TOKEN", "SECRET")):
            sanitized = sanitized.replace(env_value, "***")
    return sanitized[:220]
