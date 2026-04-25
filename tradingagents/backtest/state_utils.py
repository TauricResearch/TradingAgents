# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared helpers for extracting structured data from agent state dicts.

Used by both BacktestEngine and TradeTracker to avoid duplication.
"""

from typing import Any, Dict


_REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
)


def extract_reports(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract analyst report summaries from agent state."""
    return {k: state.get(k, "") for k in _REPORT_KEYS if k in state}


def extract_debate(state: Dict[str, Any]) -> str:
    """Extract investment debate summary from agent state."""
    debate = state.get("investment_debate_state", {})
    if not debate or not isinstance(debate, dict):
        return str(debate) if debate else ""

    parts = []
    if debate.get("bull_history"):
        parts.append(f"Bull: {debate['bull_history']}")
    if debate.get("bear_history"):
        parts.append(f"Bear: {debate['bear_history']}")
    if debate.get("judge_decision"):
        parts.append(f"Judge: {debate['judge_decision']}")
    return " | ".join(parts)


def extract_risk(state: Dict[str, Any]) -> str:
    """Extract risk debate decision from agent state."""
    risk = state.get("risk_debate_state", {})
    if not risk or not isinstance(risk, dict):
        return str(risk) if risk else ""
    return risk.get("judge_decision", "")
