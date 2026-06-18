"""Agent configuration — persisted settings for the ticker accuracy agent."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    min_samples: int = 3
    schedule_interval_h: int = 6
    max_tickers_per_cycle: int = 20
    sp500_enabled: bool = True
    yahoo_sectors_enabled: bool = True
    custom_universe_path: str | None = None


def _default_path() -> str:
    from web.server import storage

    return str(storage.ticker_agent_path("config.json"))


def load_config(file_path: str | None = None) -> AgentConfig:
    """Load agent config from disk, returning defaults if file missing."""
    path = Path(file_path or _default_path())
    if not path.exists():
        return AgentConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentConfig(
            **{k: v for k, v in data.items() if k in AgentConfig.__dataclass_fields__}
        )
    except (json.JSONDecodeError, OSError, TypeError) as e:
        log.warning("Failed to load agent config: %s", e)
        return AgentConfig()


def save_config(cfg: AgentConfig, file_path: str | None = None) -> None:
    """Save agent config to disk."""
    path = Path(file_path or _default_path())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("Failed to save agent config: %s", e)


def config_to_dict(cfg: AgentConfig) -> dict:
    return asdict(cfg)
