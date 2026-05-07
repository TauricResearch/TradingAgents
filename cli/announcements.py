import getpass
from typing import cast

import requests
from rich.console import Console
from rich.panel import Panel

from cli.config import CLI_CONFIG


def fetch_announcements(url: str | None = None, timeout: float | None = None) -> dict:
    """Fetch announcements from endpoint. Returns dict with announcements and settings."""
    endpoint = url or str(CLI_CONFIG["announcements_url"])
    configured_timeout = cast(float | int | str, CLI_CONFIG["announcements_timeout"])
    request_timeout = timeout or float(configured_timeout)
    fallback = CLI_CONFIG["announcements_fallback"]

    try:
        response = requests.get(endpoint, timeout=request_timeout)
        response.raise_for_status()
        data = response.json()
        return {
            "announcements": data.get("announcements", [fallback]),
            "require_attention": data.get("require_attention", False),
        }
    except Exception:
        return {
            "announcements": [fallback],
            "require_attention": False,
        }


def display_announcements(console: Console, data: dict) -> None:
    """Display announcements panel. Prompts for Enter if require_attention is True."""
    announcements = data.get("announcements", [])
    require_attention = data.get("require_attention", False)

    if not announcements:
        return

    content = "\n".join(announcements)

    panel = Panel(
        content,
        border_style="cyan",
        padding=(1, 2),
        title="Announcements",
    )
    console.print(panel)

    if require_attention:
        getpass.getpass("Press Enter to continue...")
    else:
        console.print()
