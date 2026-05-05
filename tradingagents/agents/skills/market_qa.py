from __future__ import annotations

from typing import Any


def build_market_qa(final_state: dict[str, Any]) -> dict[str, Any]:
    report = final_state.get("market_report")
    return {
        "status": "available" if isinstance(report, str) and report.strip() else "missing",
        "freshness": final_state.get("market_freshness", "unknown"),
        "notes": "Validate session timing and price freshness before synthesis.",
    }
