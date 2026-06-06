"""Resolve configured IIC personas without importing the full graph stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from tradingagents.personas.loader import Persona, load_persona_from_file


def personas_dir() -> Path:
    return Path(__file__).resolve().parent


def load_persona_from_config(config: Mapping[str, Any]) -> Optional[Persona]:
    persona_id = config.get("persona_id")
    if not persona_id:
        return None
    yaml_path = personas_dir() / f"{persona_id}.yaml"
    if not yaml_path.exists():
        return None
    return load_persona_from_file(str(yaml_path))
