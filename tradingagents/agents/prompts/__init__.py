"""Analyst prompt loader.

Prompts are stored as YAML files in this directory, one file per analyst
type.  Each file must have a ``system`` key whose value is the analyst's
instruction text.

Externalising prompts here means they can be edited, versioned, or A/B
tested without touching Python source files.  The ``get_language_instruction()``
suffix is appended at runtime by the analyst factory, not stored in YAML,
so a single file covers all configured output languages.

Usage::

    from tradingagents.agents.prompts import load_prompt

    system_text = load_prompt("market_analyst")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_PROMPT_DIR = Path(__file__).parent


def load_prompt(analyst_type: str) -> str:
    """Return the ``system`` prompt string for *analyst_type*.

    Args:
        analyst_type: File stem of the YAML file, e.g. ``"market_analyst"``.

    Raises:
        FileNotFoundError: If no YAML file exists for the given analyst type.
        KeyError: If the YAML file exists but has no ``system`` key.
    """
    path = _PROMPT_DIR / f"{analyst_type}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No prompt file found for analyst type {analyst_type!r}. "
            f"Expected: {path}"
        )
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["system"]
