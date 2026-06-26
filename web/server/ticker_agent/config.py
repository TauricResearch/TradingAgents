"""Agent configuration — persisted settings for the ticker accuracy agent."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_AGENT_ENV_PREFIX = "TRADINGAGENTS_AGENT_"


@dataclass
class AgentConfig:
    min_samples: int = 3
    schedule_interval_h: int = 1
    max_tickers_per_cycle: int = 4
    sp500_enabled: bool = True
    yahoo_sectors_enabled: bool = True
    custom_universe_path: str | None = None


def _default_path() -> str:
    from web.server import storage

    return str(storage.ticker_agent_path("config.json"))


def _read_env() -> dict[str, str]:
    """Read .env at project root."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return {}
    out: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, _, v = s.partition("=")
            out[k.strip()] = v.strip()
    return out


def _get_env_int(key: str, default: int) -> int:
    val = os.environ.get(key) or _read_env().get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def load_config(file_path: str | None = None) -> AgentConfig:
    """Load agent config from disk, returning defaults if file missing.

    ``schedule_interval_h`` is sourced from ``TRADINGAGENTS_AGENT_SCHEDULE_INTERVAL_H``
    env var / .env first so changing the env var takes effect on the next cycle
    without needing a config save.
    """
    path = Path(file_path or _default_path())
    if not path.exists():
        cfg = AgentConfig()
        # Apply env overrides on top of defaults
        cfg.schedule_interval_h = _get_env_int(
            f"{_AGENT_ENV_PREFIX}SCHEDULE_INTERVAL_H", cfg.schedule_interval_h
        )
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cfg = AgentConfig(
            **{k: v for k, v in data.items() if k in AgentConfig.__dataclass_fields__}
        )
        # Env vars win over saved config
        cfg.schedule_interval_h = _get_env_int(
            f"{_AGENT_ENV_PREFIX}SCHEDULE_INTERVAL_H", cfg.schedule_interval_h
        )
        return cfg
    except (json.JSONDecodeError, OSError, TypeError) as e:
        log.warning("Failed to load agent config: %s", e)
        return AgentConfig()


def save_config(cfg: AgentConfig, file_path: str | None = None) -> None:
    """Save agent config to disk and sync key values to .env for durability."""
    path = Path(file_path or _default_path())
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("Failed to save agent config: %s", e)

    # Sync schedule to .env so it survives data-dir wipes
    env_path = Path(__file__).resolve().parents[2] / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    out_lines: list[str] = []
    env_key = f"{_AGENT_ENV_PREFIX}SCHEDULE_INTERVAL_H"
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.partition("=")[0].strip()
            seen.add(k)
            if k == env_key:
                out_lines.append(f"{k}={cfg.schedule_interval_h}")
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    if env_key not in seen:
        out_lines.append(f"{env_key}={cfg.schedule_interval_h}")
    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def config_to_dict(cfg: AgentConfig) -> dict:
    return asdict(cfg)
