"""Read-only report and coverage views for archived research runs."""

from __future__ import annotations

from typing import Any

from .research_report import ResearchReportBundle, render_research_report


def build_report_workspace(bundle: ResearchReportBundle | None) -> dict[str, Any]:
    """Summarize the availability of evidence and review layers for one run."""

    if bundle is None:
        return {"available": False, "core_available": 0, "core_total": 3, "items": []}

    narrative_outputs = [
        output
        for output in bundle.agent_outputs
        if output.metadata.get("mode") == "openai_narrative"
    ]
    items = [
        _coverage_item(
            "market_data",
            "Market data",
            len(bundle.price_bars),
            f"{len(bundle.price_bars)} normalized daily bars",
        ),
        _coverage_item(
            "fundamentals",
            "Fundamentals",
            len(bundle.fundamentals),
            f"{len(bundle.fundamentals)} normalized snapshots",
        ),
        _coverage_item(
            "news",
            "News",
            len(bundle.news),
            f"{len(bundle.news)} normalized news items",
        ),
        _coverage_item(
            "narrative",
            "OpenAI narrative",
            len(narrative_outputs),
            f"{len(narrative_outputs)} structured narrative outputs",
            optional=True,
        ),
        _coverage_item(
            "manual_decision",
            "Manual decision",
            int(bundle.signal is not None),
            "Validated trade signal" if bundle.signal is not None else "No manual decision",
            optional=True,
        ),
        _coverage_item(
            "risk_review",
            "Risk review",
            int(bundle.risk_review is not None),
            "Deterministic risk review" if bundle.risk_review is not None else "No risk review",
            optional=True,
        ),
        _coverage_item(
            "backtest",
            "Backtest",
            int(bundle.backtest_result is not None),
            "Historical signal backtest" if bundle.backtest_result is not None else "No backtest",
            optional=True,
        ),
    ]
    core_available = sum(item["available"] for item in items[:3])
    return {
        "available": True,
        "core_available": core_available,
        "core_total": 3,
        "as_of_date": bundle.as_of_date.isoformat(),
        "generated_at": bundle.generated_at.isoformat(),
        "run_audit": (
            bundle.run_audit.model_dump(mode="json") if bundle.run_audit is not None else None
        ),
        "items": items,
    }


def render_archived_report(bundle: ResearchReportBundle | None) -> str:
    """Render a report only when a selected archived bundle exists."""

    if bundle is None:
        raise ValueError("archived research run was not found")
    return render_research_report(bundle)


def _coverage_item(
    key: str,
    label: str,
    count: int,
    detail: str,
    *,
    optional: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "available": count > 0,
        "optional": optional,
        "detail": detail,
    }
