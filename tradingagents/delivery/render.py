"""Channel-aware Jinja renderer.

Looks up templates by (channel, mode). Email has no event_alert template;
that combination falls back to cli/event_alert.j2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_ROOT)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)

_KNOWN_CHANNELS = ("telegram", "email", "cli")
_FALLBACK = {("email", "event_alert"): "cli/event_alert.j2"}


def render_for_channel(*, channel: str, mode: str, brief: Dict[str, Any]) -> str:
    if channel not in _KNOWN_CHANNELS:
        raise ValueError(f"unknown channel: {channel}")
    template_path = _FALLBACK.get((channel, mode), f"{channel}/{mode}.j2")
    tmpl = _env.get_template(template_path)
    return tmpl.render(**brief)
