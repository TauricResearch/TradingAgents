"""Persona system-prompt overlay helper."""

from __future__ import annotations

from typing import Optional

from tradingagents.personas.loader import Persona


def apply_fragment(base_prompt: str, persona: Optional[Persona]) -> str:
    """Append the active persona fragment to a native TradingAgents prompt."""
    if persona is None:
        return base_prompt
    fragment = (persona.system_prompt_fragment or "").strip()
    if not fragment:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{fragment}".rstrip()
