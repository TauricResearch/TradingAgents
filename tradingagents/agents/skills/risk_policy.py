from __future__ import annotations

from typing import Any


def build_risk_policy(final_state: dict[str, Any]) -> dict[str, Any]:
    risk_state = final_state.get("risk_debate_state") if isinstance(final_state.get("risk_debate_state"), dict) else {}
    return {
        "status": "available" if risk_state else "missing",
        "risk_text": risk_state.get("history", ""),
        "note": "Require an explicit risk posture before final synthesis.",
    }
