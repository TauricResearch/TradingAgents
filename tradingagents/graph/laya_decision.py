"""Optional shadow assessments through the Ollaya decision API."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import suppress

import requests

logger = logging.getLogger(__name__)

_COMMON_FIELDS = (
    "company_of_interest",
    "trade_date",
    "asset_type",
    "instrument_context",
    "portfolio_context",
)
_REPORT_FIELDS = ("market_report", "sentiment_report", "news_report", "fundamentals_report")
LAYA_STATE_BUDGET_BYTES = 600
_TEXT_TRUNCATION_MARKER = " ... "

_PHASES = {
    "research": {
        "question": "research_direction",
        "instructions": "Which direction is supported by the evidence?",
        "criteria": ["bullish", "bearish", "insufficient_evidence"],
        "fields": _COMMON_FIELDS + _REPORT_FIELDS + ("investment_debate_state", "investment_plan"),
    },
    "trader": {
        "question": "proposal_support",
        "instructions": "Is the trader's proposal supported by the available evidence?",
        "criteria": ["supported", "not_supported", "insufficient_evidence"],
        "fields": _COMMON_FIELDS + _REPORT_FIELDS + ("investment_plan", "trader_investment_plan"),
    },
    "risk": {
        "question": "risk_response",
        "instructions": "What response is justified by the risk debate and portfolio constraints?",
        "criteria": ["proceed", "reduce", "reject"],
        "fields": _COMMON_FIELDS + ("investment_plan", "trader_investment_plan", "risk_debate_state"),
    },
    "portfolio": {
        "question": "portfolio_action",
        "instructions": (
            "Choose the best fit for the evidence and portfolio constraints: Buy means initiate or "
            "add a position; Overweight means gradually increase exposure beyond a standard "
            "allocation; Hold means keep the position unchanged; Trim means reduce part of the "
            "position without exiting; Sell means exit or avoid entry. Choose Insufficient evidence "
            "when the information does not support an action. When weighing sentiment and context, "
            "prioritize credible instrument-specific sentiment over sector-level context, and sector "
            "context over broad or indirect news. Do not count volume or duplicated headlines as "
            "independent evidence. This is qualitative, not a numeric formula: verified company facts, "
            "fundamentals, market/technical evidence, portfolio constraints, and risk controls remain "
            "independent checks and can outweigh sentiment."
        ),
        "criteria": ["Buy", "Overweight", "Hold", "Trim", "Sell", "Insufficient evidence"],
        "fields": _COMMON_FIELDS + _REPORT_FIELDS + (
            "investment_plan",
            "trader_investment_plan",
            "risk_debate_state",
            "final_trade_decision",
        ),
    },
}

_PHASE_LABELS = {
    "research": "Research synthesis",
    "trader": "Trader proposal",
    "risk": "Risk review",
    "portfolio": "Final portfolio action",
}


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= len(_TEXT_TRUNCATION_MARKER):
        return value[:limit]
    remaining = limit - len(_TEXT_TRUNCATION_MARKER)
    head = (remaining + 1) // 2
    tail = remaining - head
    return value[:head] + _TEXT_TRUNCATION_MARKER + (value[-tail:] if tail else "")


def _compact_value(value, text_limit: int):
    if isinstance(value, str):
        return _clip_text(value, text_limit)
    if isinstance(value, dict):
        return {key: _compact_value(item, text_limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact_value(item, text_limit) for item in value[-2:]]
    if isinstance(value, tuple):
        return [_compact_value(item, text_limit) for item in value[-2:]]
    return value


def _serialized_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def _compact_snapshot(snapshot: dict) -> tuple[dict, int]:
    """Fit the shadow-only request state to Ollaya's small input window."""
    original_size = _serialized_size(snapshot)
    if original_size <= LAYA_STATE_BUDGET_BYTES:
        return snapshot, original_size

    text_lengths = []

    def collect_lengths(value):
        if isinstance(value, str):
            text_lengths.append(len(value))
        elif isinstance(value, dict):
            for item in value.values():
                collect_lengths(item)
        elif isinstance(value, (list, tuple)):
            for item in value[-2:]:
                collect_lengths(item)

    collect_lengths(snapshot)
    low, high = 0, max(text_lengths, default=0)
    compacted = _compact_value(snapshot, 0)
    while low <= high:
        limit = (low + high) // 2
        candidate = _compact_value(snapshot, limit)
        if _serialized_size(candidate) <= LAYA_STATE_BUDGET_BYTES:
            compacted = candidate
            low = limit + 1
        else:
            high = limit - 1

    return compacted, original_size


def render_laya_assessments(assessments: dict | None) -> str:
    """Render compact shadow results and their class probabilities for people."""
    if not assessments:
        return ""

    lines = []
    for phase, label in _PHASE_LABELS.items():
        assessment = assessments.get(phase)
        if not assessment:
            continue
        if assessment.get("status") != "ok":
            status = assessment.get("status", "unavailable")
            error_code = assessment.get("error_code")
            detail = f" ({error_code})" if error_code else ""
            lines.append(f"**{label}:** unavailable ({status}){detail}.")
            continue

        answer = assessment.get("answer") or {}
        choice = answer.get("choice", "No label")
        probabilities = answer.get("probabilities") or {}
        distribution = []
        for option in _PHASES[phase]["criteria"]:
            probability = probabilities.get(option)
            formatted = f"{float(probability):.1%}" if isinstance(probability, (int, float)) else "n/a"
            distribution.append(f"{option}: {formatted}")
        model = assessment.get("model")
        model_note = f"; model {model}" if model else ""
        probability_note = f"; {' | '.join(distribution)}" if distribution else ""
        lines.append(f"**{label}:** {choice}{probability_note}{model_note}.")

    if not lines:
        return ""
    lines.append(
        "*These are Laya's probabilities over action classes, not probabilities of profit or "
        "investment success. Assessments are shadow-only and do not change the Portfolio "
        "Manager's decision.*"
    )
    return "\n\n".join(lines)


class LayaDecisionAdapter:
    """Ask Laya for typed shadow assessments without changing trading decisions."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float,
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.api_key = api_key

    @classmethod
    def from_config(cls, config: dict) -> LayaDecisionAdapter | None:
        if not config.get("laya_shadow_enabled", False):
            return None
        base_url = config.get("laya_base_url")
        if not base_url:
            raise ValueError("Set TRADINGAGENTS_LAYA_BASE_URL to enable Laya shadow assessments")
        return cls(
            base_url=base_url,
            model=config["laya_model"],
            timeout=config["laya_timeout"],
            api_key=os.environ.get("OLLAYA_API_KEY"),
        )

    def assess(self, phase: str, state: dict) -> dict:
        phase_spec = _PHASES[phase]
        original_snapshot = {key: state.get(key) for key in phase_spec["fields"] if key in state}
        snapshot, original_size = _compact_snapshot(original_snapshot)
        input_size = _serialized_size(snapshot)
        input_compacted = input_size < original_size
        serialized_state = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
        input_digest = hashlib.sha256(serialized_state.encode("utf-8")).hexdigest()
        payload = {
            "model": self.model,
            "state": snapshot,
            "questions": {
                phase_spec["question"]: {
                    "type": "choice",
                    "instructions": phase_spec["instructions"],
                    "criteria": phase_spec["criteria"],
                }
            },
            "extras": ["laya"],
            "keep_alive": "10m",
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None

        try:
            response = requests.post(
                f"{self.base_url}/api/decide",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            error_code = None
            if exc.response is not None:
                with suppress(ValueError, AttributeError):
                    error_code = exc.response.json().get("code")
            logger.warning("Laya %s assessment unavailable: %s", phase, error_code or type(exc).__name__)
            return {
                "status": "error",
                "error_code": error_code,
                "input_fields": list(snapshot),
                "input_sha256": input_digest,
                "input_compacted": input_compacted,
                "input_bytes": input_size,
                "original_input_bytes": original_size,
            }
        except ValueError:
            logger.warning("Laya %s assessment returned invalid JSON", phase)
            return {
                "status": "invalid_response",
                "input_fields": list(snapshot),
                "input_sha256": input_digest,
                "input_compacted": input_compacted,
                "input_bytes": input_size,
                "original_input_bytes": original_size,
            }

        truncated = bool(result.get("state_truncated", False))
        question_id = phase_spec["question"]
        answer = result.get("answers", {}).get(question_id)
        status = "truncated" if truncated else "ok" if answer else "invalid_response"
        return {
            "status": status,
            "model": result.get("model"),
            "answer": answer,
            "routing": result.get("routing"),
            "state_truncated": truncated,
            "input_fields": list(snapshot),
            "input_snapshot": snapshot,
            "input_sha256": input_digest,
            "input_compacted": input_compacted,
            "input_bytes": input_size,
            "original_input_bytes": original_size,
            "request_id": response.headers.get("X-Request-Id"),
            "created_at": result.get("created_at"),
            "total_duration": result.get("total_duration"),
            "usage": result.get("usage"),
        }


def create_laya_assessment_node(adapter: LayaDecisionAdapter | None, phase: str):
    """Create a graph node that records an optional phase assessment."""

    def assess_node(state: dict) -> dict:
        if adapter is None:
            return {}
        return {"laya_assessments": {phase: adapter.assess(phase, state)}}

    return assess_node
