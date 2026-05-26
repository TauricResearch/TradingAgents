"""Secretary service.

F1 ships only ``compose_deep_dive`` end-to-end. The other compose methods
(morning_digest, event_alert) are stubs raising NotImplementedError —
they land in later phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",)),
    keep_trailing_newline=True,
)


def render_deep_dive(
    *,
    ticker: str,
    trade_date: str,
    synthesis: Dict[str, str],
    persona_runs: List[Dict[str, Any]],
) -> str:
    return _env.get_template("deep_dive.j2").render(
        ticker=ticker,
        trade_date=trade_date,
        synthesis=synthesis,
        persona_runs=persona_runs,
    )
