from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShadowRunRequest:
    ticker: str
    trade_date: str
    selected_analysts: list[str]
    provider: str
    deep_model: str
    quick_model: str
    shadow_run_id: str | None = None
    target_profile: dict[str, Any] | None = None
    checkpoint_enabled: bool = False
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
    debug: bool = False
    repo_root: Path = Path.cwd()
    env_file: Path | None = None


@dataclass(frozen=True)
class ShadowRunResult:
    ticker: str
    trade_date: str
    decision: str
    final_trade_decision: str | None
    state_log_dir: str
    memory_log_path: str
    provider: str
    deep_model: str
    quick_model: str
    shadow_run_id: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
