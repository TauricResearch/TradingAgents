"""Global configuration — one file to tune the whole system.

Edit ``config.toml`` (repo root) to retune every parameter; secrets stay in
``.env``. ``load_settings()`` starts from the code defaults below, overlays the
TOML file if present, and returns a typed ``Settings`` object the entry points
read from. Anything not in the TOML keeps its default, so the file can be partial.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    provider: str = "openrouter"
    deep_model: str = "deepseek/deepseek-v4-flash:free"
    quick_model: str = "deepseek/deepseek-v4-flash:free"
    backend_url: str | None = None


class RiskSettings(BaseModel):
    base_risk_pct: float = 0.01      # risk budget per trade (× conviction)
    heat_max_pct: float = 0.06       # max aggregate open risk (portfolio heat)
    max_position_pct: float = 0.10   # max weight per single position
    atr_period: int = 14
    k_entry: float = 0.5             # entry distance in ATR (PM may override)
    k_stop: float = 2.0
    k_tp: float = 3.0
    min_risk_reward: float = 1.5


class CharterSettings(BaseModel):
    cash_reserve_pct: float = 0.10   # strategic cash reserve (Statute)
    max_portfolio_var: float = 0.10
    max_sector_pct: float = 0.30


class ScreeningSettings(BaseModel):
    lookback: int = 60
    top_k: int = 5                   # how many tickers per cycle reach the deep dive


class CycleSettings(BaseModel):
    max_revisions: int = 1           # "when in doubt, ask" loop cap
    interval_seconds: float = 3600.0  # autonomous loop period
    price_alert_atr: float = 1.5     # anomalous-move trigger threshold


class DataSettings(BaseModel):
    history_start: str = "2024-01-01"


class CostSettings(BaseModel):
    token_cost_per_cycle: float = 0.0
    commission_per_trade: float = 0.0  # 0 = ZeroCommission (e.g. Alpaca equity)


class Settings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    charter: CharterSettings = Field(default_factory=CharterSettings)
    screening: ScreeningSettings = Field(default_factory=ScreeningSettings)
    cycle: CycleSettings = Field(default_factory=CycleSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    costs: CostSettings = Field(default_factory=CostSettings)

    # -- convenience views -------------------------------------------------
    def llm_config(self) -> dict[str, Any]:
        """Shape expected by ForkStructuredLLM / default_config."""
        return {
            "llm_provider": self.llm.provider,
            "deep_think_llm": self.llm.deep_model,
            "quick_think_llm": self.llm.quick_model,
            "backend_url": self.llm.backend_url,
        }

    def charter_dict(self) -> dict[str, float]:
        return {
            "cash_reserve_pct": self.charter.cash_reserve_pct,
            "max_portfolio_var": self.charter.max_portfolio_var,
            "max_sector_pct": self.charter.max_sector_pct,
            "min_risk_reward": self.risk.min_risk_reward,
            "max_position_pct": self.risk.max_position_pct,
            "base_risk_pct": self.risk.base_risk_pct,
            "heat_max_pct": self.risk.heat_max_pct,
        }


def _deep_update(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _default_path() -> Path:
    return Path(os.environ.get("TRADINGAGENTS_CONFIG", "config.toml"))


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    """Load Settings: code defaults overlaid with the TOML file when present."""
    p = Path(path) if path is not None else _default_path()
    data = Settings().model_dump()
    if p.exists():
        import tomllib

        with open(p, "rb") as fh:
            _deep_update(data, tomllib.load(fh))
    return Settings(**data)
