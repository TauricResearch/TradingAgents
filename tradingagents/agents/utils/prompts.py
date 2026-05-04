"""Helpers for rendering file-backed agent prompt templates."""

from __future__ import annotations

from importlib.resources import files
from string import Formatter
from typing import Mapping


def load_prompt_template(template_name: str) -> str:
    """Load a prompt template without formatting it."""
    return (
        files("tradingagents.agents.prompts")
        .joinpath(template_name)
        .read_text(encoding="utf-8")
    )


def render_prompt_template(template_name: str, values: Mapping[str, object]) -> str:
    """Render a prompt template from ``tradingagents.agents.prompts``.

    Templates use Python's standard ``str.format`` placeholders. Missing
    placeholders intentionally raise ``KeyError`` so prompt drift is caught in
    tests instead of being sent to an LLM.
    """
    template = load_prompt_template(template_name)
    required_names = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None and field_name != ""
    }
    missing_names = required_names.difference(values)
    if missing_names:
        raise KeyError(sorted(missing_names)[0])
    return template.format(**values)
