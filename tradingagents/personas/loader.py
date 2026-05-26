"""Persona YAML loader with Pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


# Keep this list in sync with tradingagents.cli.models.AnalystType.
_VALID_ANALYSTS = {"market", "news", "sentiment", "fundamentals", "derivatives", "social"}


class LLMSettings(BaseModel):
    deep_think_llm: str
    quick_think_llm: str
    deepseek_reasoning_effort: str | None = None  # "high" | "max" | None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None


class AnalystSettings(BaseModel):
    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "AnalystSettings":
        unknown_in = set(self.include) - _VALID_ANALYSTS
        unknown_ex = set(self.exclude) - _VALID_ANALYSTS
        if unknown_in:
            raise ValueError(f"unknown analyst names in include: {sorted(unknown_in)}")
        if unknown_ex:
            raise ValueError(f"unknown analyst names in exclude: {sorted(unknown_ex)}")
        overlap = set(self.include) & set(self.exclude)
        if overlap:
            raise ValueError(f"include/exclude overlap: {sorted(overlap)}")
        return self


class RiskDebateSettings(BaseModel):
    weights: Dict[str, float] = Field(default_factory=lambda: {
        "aggressive": 1.0, "conservative": 1.0, "neutral": 1.0
    })


class Persona(BaseModel):
    id: str
    name: str
    description: str
    system_prompt_fragment: str
    llm: LLMSettings
    analysts: AnalystSettings
    risk_debate: RiskDebateSettings
    memory_scope: Literal["isolated", "shared", "hybrid"] = "hybrid"


def load_persona_from_string(yaml_text: str) -> Persona:
    raw = yaml.safe_load(yaml_text)
    return Persona.model_validate(raw)


def load_persona_from_file(path: str | Path) -> Persona:
    return load_persona_from_string(Path(path).read_text(encoding="utf-8"))


def load_all_personas(dir_path: str | Path) -> List[Persona]:
    out: List[Persona] = []
    for f in sorted(Path(dir_path).glob("*.yaml")):
        out.append(load_persona_from_file(f))
    return out
