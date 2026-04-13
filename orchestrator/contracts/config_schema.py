from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, TypedDict, cast

from tradingagents.default_config import get_default_config


CONTRACT_VERSION = "v1alpha1"


class TradingAgentsConfigPayload(TypedDict, total=False):
    project_dir: str
    results_dir: str
    data_cache_dir: str
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: str
    google_thinking_level: Optional[str]
    openai_reasoning_effort: Optional[str]
    anthropic_effort: Optional[str]
    output_language: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    max_recur_limit: int
    data_vendors: dict[str, str]
    tool_vendors: dict[str, str]
    selected_analysts: list[str]
    llm_timeout: float
    llm_max_retries: int
    timeout: float
    max_retries: int
    use_responses_api: bool


REQUIRED_TRADING_CONFIG_KEYS = (
    "project_dir",
    "results_dir",
    "data_cache_dir",
    "llm_provider",
    "deep_think_llm",
    "quick_think_llm",
)


def _validate_probability(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return float(value)


def _validate_positive_int(name: str, value: Any) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be > 0")
    return value


def _validate_string_map(name: str, value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    normalized = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise TypeError(f"{name} keys and values must be strings")
        normalized[key] = item
    return normalized


def build_trading_agents_config(
    overrides: Optional[Mapping[str, Any]],
) -> TradingAgentsConfigPayload:
    merged: dict[str, Any] = get_default_config()

    if overrides:
        if not isinstance(overrides, Mapping):
            raise TypeError("trading_agents_config must be a mapping")
        for key, value in overrides.items():
            if (
                key in ("data_vendors", "tool_vendors")
                and value is not None
            ):
                merged[key] = _validate_string_map(key, value)
            elif key == "selected_analysts" and value is not None:
                if not isinstance(value, list) or any(
                    not isinstance(item, str) for item in value
                ):
                    raise TypeError("selected_analysts must be a list of strings")
                merged[key] = list(value)
            else:
                merged[key] = value

    for key in REQUIRED_TRADING_CONFIG_KEYS:
        value = merged.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"trading_agents_config.{key} must be a non-empty string")

    merged["data_vendors"] = _validate_string_map("data_vendors", merged["data_vendors"])
    merged["tool_vendors"] = _validate_string_map("tool_vendors", merged["tool_vendors"])

    return cast(TradingAgentsConfigPayload, merged)


@dataclass(frozen=True)
class OrchestratorConfigSchema:
    quant_backtest_path: str = ""
    trading_agents_config: TradingAgentsConfigPayload = field(
        default_factory=lambda: build_trading_agents_config(None)
    )
    quant_weight_cap: float = 0.8
    llm_weight_cap: float = 0.9
    llm_batch_days: int = 7
    cache_dir: str = "orchestrator/cache"
    llm_solo_penalty: float = 0.7
    quant_solo_penalty: float = 0.8
    contract_version: str = CONTRACT_VERSION

    def to_runtime_fields(self) -> dict[str, Any]:
        return {
            "quant_backtest_path": self.quant_backtest_path,
            "trading_agents_config": dict(self.trading_agents_config),
            "quant_weight_cap": self.quant_weight_cap,
            "llm_weight_cap": self.llm_weight_cap,
            "llm_batch_days": self.llm_batch_days,
            "cache_dir": self.cache_dir,
            "llm_solo_penalty": self.llm_solo_penalty,
            "quant_solo_penalty": self.quant_solo_penalty,
        }


def build_orchestrator_schema(raw: Mapping[str, Any]) -> OrchestratorConfigSchema:
    if not isinstance(raw, Mapping):
        raise TypeError("orchestrator config must be a mapping")

    quant_backtest_path = raw.get("quant_backtest_path", "")
    if not isinstance(quant_backtest_path, str):
        raise TypeError("quant_backtest_path must be a string")

    cache_dir = raw.get("cache_dir", "orchestrator/cache")
    if not isinstance(cache_dir, str) or not cache_dir.strip():
        raise ValueError("cache_dir must be a non-empty string")

    return OrchestratorConfigSchema(
        quant_backtest_path=quant_backtest_path,
        trading_agents_config=build_trading_agents_config(
            cast(Optional[Mapping[str, Any]], raw.get("trading_agents_config"))
        ),
        quant_weight_cap=_validate_probability(
            "quant_weight_cap", raw.get("quant_weight_cap", 0.8)
        ),
        llm_weight_cap=_validate_probability(
            "llm_weight_cap", raw.get("llm_weight_cap", 0.9)
        ),
        llm_batch_days=_validate_positive_int(
            "llm_batch_days", raw.get("llm_batch_days", 7)
        ),
        cache_dir=cache_dir,
        llm_solo_penalty=_validate_probability(
            "llm_solo_penalty", raw.get("llm_solo_penalty", 0.7)
        ),
        quant_solo_penalty=_validate_probability(
            "quant_solo_penalty", raw.get("quant_solo_penalty", 0.8)
        ),
    )
