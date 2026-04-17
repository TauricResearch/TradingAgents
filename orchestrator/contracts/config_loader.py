from __future__ import annotations

from typing import Any, Mapping, Optional

from orchestrator.contracts.config_schema import (
    build_orchestrator_schema,
    build_trading_agents_config,
)


def normalize_trading_agents_config(
    config: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    return dict(build_trading_agents_config(config))


def normalize_orchestrator_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    return build_orchestrator_schema(raw).to_runtime_fields()
