from __future__ import annotations

from typing import Any

from tradingagents.agents.utils.recommendation_audit import build_pre_synthesis_scope_audit


def build_entity_resolution(final_state: dict[str, Any]) -> dict[str, Any]:
    ticker = final_state.get("company_of_interest", "")
    return build_pre_synthesis_scope_audit(ticker, final_state) if ticker else {"status": "missing"}
