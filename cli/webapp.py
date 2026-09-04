"""Launcher for the full Next.js web app (optional CLI alternative).

Three ways to use TradingAgents, picked by prompts:
1. Full web app — chosen FIRST, before any CLI selections. Boots the API +
   Next.js production servers (detached, per-session ports) and the CLI
   exits; the whole flow then happens in the browser.
2. CLI panels — the classic terminal flow with Rich panels.
3. Scroll webpage — the always-on :8765 dashboard mirroring the run, with a
   prompt bar; runs side-by-side with the CLI flow.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import questionary
from rich.console import Console

from cli.dashboard import find_free_port

console = Console()

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
REPO_ROOT = Path(__file__).resolve().parent.parent
NEXT_BASE_PORT = 3000
API_BASE_PORT = 8787

_STYLE = questionary.Style(
    [
        ("selected", "fg:magenta noinherit"),
        ("highlighted", "fg:magenta noinherit"),
        ("pointer", "fg:magenta noinherit"),
        ("dropdown", "bg:black fg:white"),
        ("dropdown.border", "fg:magenta"),
        ("dropdown.item", "fg:white"),
        ("dropdown.item.selected", "bg:magenta fg:black"),
    ]
)


def ask_entry_mode() -> str:
    """First prompt: full web app or CLI. Env TRADINGAGENTS_INTERFACE wins."""
    env = os.environ.get("TRADINGAGENTS_INTERFACE", "").strip().lower()
    if env in ("web", "browser"):
        return "web"
    if env == "cli":
        return "cli"
    choice = questionary.select(
        "Start in:",
        choices=[
            questionary.Choice("CLI — terminal flow", value="cli"),
            questionary.Choice("Browser — full web app", value="web"),
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=_STYLE,
    ).ask()
    return choice if choice in ("web", "cli") else "cli"


def ask_watch_mode() -> str:
    """At research start (CLI mode): watch in terminal panels or scroll page."""
    if os.environ.get("TRADINGAGENTS_WEB", "1") == "0":
        return "cli"
    choice = questionary.select(
        "Watch this run in:",
        choices=[
            questionary.Choice("CLI — terminal panels", value="cli"),
            questionary.Choice("Browser — scroll webpage (same run, live)", value="browser"),
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=_STYLE,
    ).ask()
    return choice if choice in ("browser", "cli") else "cli"


def _run_npm(args: list[str]) -> int:
    """Run an npm command inside web/. Returns the exit code."""
    if os.name == "nt":
        cmd = ["cmd", "/c", "npm", *args]
    else:
        cmd = ["npm", *args]
    proc = subprocess.run(cmd, cwd=str(WEB_DIR))
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
        console.print("[red]Web build failed.[/red]")
        return False
    return True


def _spawn_detached(cmd: list[str], cwd: Path, log_path: Path):
    log_file = open(log_path, "a", encoding="utf-8")
    if os.name == "nt":
        full = ["cmd", "/c", *cmd] if cmd[0] == "npm" else cmd
        return subprocess.Popen(
            full,
            cwd=str(cwd),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.DETACHED_PROCESS,
        )
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def start_api_detached(host: str = "127.0.0.1", port: int = API_BASE_PORT):
    """Start ``tradingagents web`` detached. Returns ``(proc, url)``."""
    try:
        port = int(os.environ.get("TRADINGAGENTS_API_PORT", port))
    except ValueError:
        port = API_BASE_PORT
    port = find_free_port(host, port)
    if port is None:
        console.print("[red]No free port for the web API.[/red]")
        return None, None
    try:
        proc = _spawn_detached(
            [sys.executable, "-m", "cli.main", "web", "--port", str(port)],
            REPO_ROOT,
            REPO_ROOT / "web-api-out.log",
        )
    except Exception as exc:
        console.print(f"[red]Could not start the web API: {exc}[/red]")
        return None, None
    url = f"http://{host}:{port}"
    # Wait for warmup (heavy imports take ~20s) so the printed URL is live.
    for _ in range(90):
        try:
            urllib.request.urlopen(url + "/api/runs", timeout=5)
            break
        except Exception:
            time.sleep(2)
    else:
        console.print("[yellow]API starting slowly — the URL may need a moment.[/yellow]")
    return proc, url


def start_webapp(host: str = "127.0.0.1", port: int = NEXT_BASE_PORT):
    """Start the Next.js production server on a free port.

    Returns ``(process, url)`` or ``(None, None)``. Detached: keeps running
    after the CLI exits; output goes to ``web/.next-out.log``.
    """
    try:
        port = int(os.environ.get("TRADINGAGENTS_NEXT_PORT", port))
    except ValueError:
        port = NEXT_BASE_PORT
    port = find_free_port(host, port)
    if port is None:
        console.print("[red]No free port for the web app.[/red]")
        return None, None

    log_path = WEB_DIR / ".next-out.log"
    try:
        proc = _spawn_detached(
            ["npm", "run", "start", "--", "-p", str(port)], WEB_DIR, log_path
        )
    except Exception as exc:
        console.print(f"[red]Could not start the web app: {exc}[/red]")
        return None, None
    url = f"http://{host}:{port}"
    console.print(f"\n[bold cyan]Web app (PID {proc.pid}):[/bold cyan] {url}")
    console.print(f"[dim]Server log: {log_path} (kill PID {proc.pid} to stop it)[/dim]\n")
    return proc, url


def launch_full_web() -> str | None:
    """Boot API + Next.js (build first if missing). Returns app URL or None."""
    if not ensure_webapp_build():
        return None
    api_proc, api_url = start_api_detached()
    if api_url is None:
        return None
    console.print(f"[bold cyan]Web API (PID {api_proc.pid}):[/bold cyan] {api_url}")
    _, url = start_webapp()
    if url is None:
        return None
    # The app's baked-in API URL may differ from this session's port; the
    # ?api= variant pins it (stored in browser storage on first load).
    console.print(f"[dim]If the app can't reach the API, open: {url}/dashboard?api={api_url}[/dim]")
    return url


if __name__ == "__main__":
    url = launch_full_web()
    print(url or "FAILED")
    sys.exit(0 if url else 1)
