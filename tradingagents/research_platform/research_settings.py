"""Persistent, user-editable research universe and data-period settings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SectorRule(BaseModel):
    """One configurable concept group used to discover watchlist members."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    enabled: bool = True
    keywords: list[str] = Field(default_factory=list)
    explicit_includes: list[str] = Field(default_factory=list)
    explicit_excludes: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _normalize_id(cls, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-")
        if not normalized:
            raise ValueError("sector id must contain a letter or number")
        return normalized

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, values: list[str]) -> list[str]:
        return _unique(value.strip() for value in values if value.strip())

    @field_validator("explicit_includes", "explicit_excludes")
    @classmethod
    def _normalize_symbols(cls, values: list[str]) -> list[str]:
        return _unique(value.strip().upper() for value in values if value.strip())


class DataPeriodPreset(BaseModel):
    """A named research lookback that can be extended from the settings page."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    days: int = Field(ge=1, le=3650)

    @field_validator("id", "name")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("period id and name are required")
        return normalized


def default_sector_rules() -> list[SectorRule]:
    return [
        SectorRule(
            id="game",
            name="游戏",
            keywords=["游戏", "网络游戏", "手机游戏", "云游戏", "电子竞技", "电竞"],
            explicit_includes=["002602", "002624"],
        ),
        SectorRule(
            id="ai",
            name="人工智能",
            keywords=[
                "人工智能",
                "AIGC",
                "ChatGPT",
                "大模型",
                "生成式AI",
                "算力",
                "机器学习",
                "机器视觉",
                "AI应用",
            ],
        ),
    ]


def default_period_presets() -> list[DataPeriodPreset]:
    return [
        DataPeriodPreset(id="3m", name="近 3 个月", days=90),
        DataPeriodPreset(id="6m", name="近 6 个月", days=180),
        DataPeriodPreset(id="1y", name="近 1 年", days=365),
        DataPeriodPreset(id="2y", name="近 2 年", days=730),
        DataPeriodPreset(id="5y", name="近 5 年", days=1825),
    ]


class ResearchSettings(BaseModel):
    """Server-side settings; credentials are deliberately not represented."""

    model_config = ConfigDict(frozen=True)

    version: int = 1
    preferred_data_provider: str = "auto"
    default_period_id: str = "1y"
    sector_rules: list[SectorRule] = Field(default_factory=default_sector_rules)
    period_presets: list[DataPeriodPreset] = Field(default_factory=default_period_presets)

    @field_validator("preferred_data_provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"auto", "tushare", "yfinance"}:
            raise ValueError("preferred_data_provider must be auto, tushare, or yfinance")
        return normalized

    @model_validator(mode="after")
    def _validate_unique_ids(self) -> ResearchSettings:
        sector_ids = [item.id for item in self.sector_rules]
        period_ids = [item.id for item in self.period_presets]
        if len(sector_ids) != len(set(sector_ids)):
            raise ValueError("sector ids must be unique")
        if not period_ids or len(period_ids) != len(set(period_ids)):
            raise ValueError("period ids must be non-empty and unique")
        if self.default_period_id not in set(period_ids):
            raise ValueError("default_period_id must reference a period preset")
        return self

    @property
    def default_lookback_days(self) -> int:
        return next(item.days for item in self.period_presets if item.id == self.default_period_id)


class JsonResearchSettingsStore:
    """Keep cockpit settings beside local research artifacts."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @property
    def path(self) -> Path:
        return self.root / "research_settings.json"

    def load(self) -> ResearchSettings:
        if not self.path.exists():
            return ResearchSettings()
        try:
            return ResearchSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ResearchSettings()

    def save(self, settings: ResearchSettings) -> ResearchSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2)
        self.path.write_text(payload + "\n", encoding="utf-8")
        return settings


def _unique(values) -> list[str]:
    return list(dict.fromkeys(values))
