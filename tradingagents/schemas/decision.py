from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from json import JSONDecodeError
from typing import Any, Mapping


class StructuredDecisionValidationError(ValueError):
    """Raised when a decision payload does not match the required schema."""


class DecisionRating(str, Enum):
    BUY = "BUY"
    OVERWEIGHT = "OVERWEIGHT"
    HOLD = "HOLD"
    UNDERWEIGHT = "UNDERWEIGHT"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class TimeHorizon(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


@dataclass(frozen=True)
class StructuredDecision:
    rating: DecisionRating
    confidence: float
    time_horizon: TimeHorizon
    entry_logic: str
    exit_logic: str
    position_sizing: str
    risk_limits: str
    catalysts: tuple[str, ...]
    invalidators: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rating": self.rating.value,
            "confidence": self.confidence,
            "time_horizon": self.time_horizon.value,
            "entry_logic": self.entry_logic,
            "exit_logic": self.exit_logic,
            "position_sizing": self.position_sizing,
            "risk_limits": self.risk_limits,
            "catalysts": list(self.catalysts),
            "invalidators": list(self.invalidators),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def build_decision_output_instructions(context: str) -> str:
    return (
        f"Return only one valid JSON object for the {context}. "
        "Do not wrap it in markdown fences. "
        "The schema is: "
        '{"rating":"BUY | OVERWEIGHT | HOLD | UNDERWEIGHT | SELL | NO_TRADE",'
        '"confidence":0.0,'
        '"time_horizon":"short | medium | long",'
        '"entry_logic":"...",'
        '"exit_logic":"...",'
        '"position_sizing":"...",'
        '"risk_limits":"...",'
        '"catalysts":["..."],'
        '"invalidators":["..."]}. '
        "Use an uppercase rating, confidence between 0 and 1 inclusive, and concise but specific strings."
    )


def _extract_json_object(payload: str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload

    if not isinstance(payload, str) or not payload.strip():
        raise StructuredDecisionValidationError("Decision payload must be a non-empty JSON string or mapping.")

    text = payload.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, Mapping):
            return parsed
    except JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return parsed

    raise StructuredDecisionValidationError("Could not locate a valid JSON object in the decision payload.")


def _require_string(data: Mapping[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise StructuredDecisionValidationError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _require_string_list(data: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise StructuredDecisionValidationError(f"Field '{field_name}' must be a list of strings.")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise StructuredDecisionValidationError(
                f"Field '{field_name}' must contain only non-empty strings."
            )
        normalized.append(item.strip())
    return tuple(normalized)


def parse_structured_decision(payload: str | Mapping[str, Any]) -> StructuredDecision:
    data = _extract_json_object(payload)
    missing_fields = {
        "rating",
        "confidence",
        "time_horizon",
        "entry_logic",
        "exit_logic",
        "position_sizing",
        "risk_limits",
        "catalysts",
        "invalidators",
    } - set(data.keys())
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise StructuredDecisionValidationError(f"Decision payload is missing required fields: {missing}.")

    try:
        rating = DecisionRating(str(data["rating"]).strip().upper())
    except ValueError as exc:
        raise StructuredDecisionValidationError(f"Unsupported rating: {data.get('rating')!r}.") from exc

    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError) as exc:
        raise StructuredDecisionValidationError("Field 'confidence' must be numeric.") from exc
    if not 0.0 <= confidence <= 1.0:
        raise StructuredDecisionValidationError("Field 'confidence' must be between 0 and 1 inclusive.")

    try:
        time_horizon = TimeHorizon(str(data["time_horizon"]).strip().lower())
    except ValueError as exc:
        raise StructuredDecisionValidationError(
            f"Unsupported time horizon: {data.get('time_horizon')!r}."
        ) from exc

    return StructuredDecision(
        rating=rating,
        confidence=confidence,
        time_horizon=time_horizon,
        entry_logic=_require_string(data, "entry_logic"),
        exit_logic=_require_string(data, "exit_logic"),
        position_sizing=_require_string(data, "position_sizing"),
        risk_limits=_require_string(data, "risk_limits"),
        catalysts=_require_string_list(data, "catalysts"),
        invalidators=_require_string_list(data, "invalidators"),
    )


def ensure_structured_decision_json(payload: str | Mapping[str, Any]) -> str:
    return parse_structured_decision(payload).to_json()
