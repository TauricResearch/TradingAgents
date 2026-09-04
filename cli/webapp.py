"""Launcher for the full Next.js web app (the CLI replacement).

Behavior (per user spec):
- ``tradingagents`` always starts the CLI; just before research begins the
  user picks Browser or CLI from a dropdown.
- Browser: ensure the production build exists (``npm run build`` when the
  ``.next`` output is missing), then start it (``npm run start``) on a free
  port — every session gets its own port — and print the URL.
- CLI: continue with the terminal flow unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import questionary
from rich.console import Console

from cli.dashboard import find_free_port

console = Console()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
NEXT_BASE_PORT = 3000


def ask_interface() -> str:
    """Ask whether this run is watched in the browser or the terminal."""
    choice = questionary.select(
        "Watch this run in:",
        choices=[
            questionary.Choice("CLI — terminal panels", value="cli"),
            questionary.Choice("Browser — full web dashboard", value="browser"),
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
                ("dropdown", "bg:black fg:white"),
                ("dropdown.border", "fg:magenta"),
                ("dropdown.item", "fg:white"),
                ("dropdown.item.selected", "bg:magenta fg:black"),
            ]
        ),
    ).ask()
    # Cancel (Esc/Ctrl-C) falls back to the terminal flow, never strands a run.
    return choice if choice in ("browser", "cli") else "cli"


def _run_npm(args: list[str]) -> int:
    """Run an npm command inside web/. Returns the exit code."""
    if os.name == "nt":
        cmd: list[str] | str = ["cmd", "/c", "npm", *args]
        shell = False
    else:
        cmd = ["npm", *args]
        shell = False
    proc = subprocess.run(cmd, cwd=str(WEB_DIR), shell=shell)
    return proc.returncode


def ensure_webapp_build() -> bool:
    """Build the Next.js production bundle if it is missing."""
    if not WEB_DIR.is_dir():
        console.print("[red]Web app directory not found (expected web/ next to cli/).[/red]")
        return False
    if (WEB_DIR / ".next" / "BUILD_ID").is_file():
        return True
    console.print("[yellow]No production build found — running `npm run build`...[/yellow]")
    if _run_npm(["run", "build"]) != 0:
        console.print("[red]Web build failed. Continuing in CLI mode.[/red]")
        return False
    return True


def start_webapp(host: str = "127.0.0.1", port: int = NEXT_BASE_PORT):
    """Start the Next.js production server on a free port.

    Returns ``(process, url)`` or ``(None, None)``. The server is detached
    so it keeps running after the CLI exits; its output goes to
    ``web/.next-out.log``.
    """
    try:
        port = int(os.environ.get("TRADINGAGENTS_NEXT_PORT", port))
    except ValueError:
        port = NEXT_BASE_PORT
    port = find_free_port(host, port)
    if port is None:
        console.print("[red]No free port for the web app. Continuing in CLI mode.[/red]")
        return None, None

    log_path = WEB_DIR / ".next-out.log"
    try:
        log_file = open(log_path, "a", encoding="utf-8")
        if os.name == "nt":
            proc = subprocess.Popen(
                ["cmd", "/c", "npm", "run", "start", "--", "-p", str(port)],
                cwd=str(WEB_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.DETACHED_PROCESS,
            )
        else:
            proc = subprocess.Popen(
                ["npm", "run", "start", "--", "-p", str(port)],
                cwd=str(WEB_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception as exc:
        console.print(f"[red]Could not start the web app: {exc}[/red]")
        return None, None
    url = f"http://{host}:{port}"
    console.print(f"\n[bold cyan]Web app (PID {proc.pid}):[/bold cyan] {url}")
    console.print(f"[dim]Server log: {log_path} (kill PID {proc.pid} to stop it)[/dim]\n")
    return proc, url


def launch_browser_mode() -> str | None:
    """Ensure build + start server. Returns the URL or None on failure."""
    if not ensure_webapp_build():
        return None
    _, url = start_webapp()
    return url


if __name__ == "__main__":
    url = launch_browser_mode()
    print(url or "FAILED")
    sys.exit(0 if url else 1)
