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


ENTRY_TIMEOUT = 30  # seconds of inactivity before falling back to CLI


def ask_entry_mode(timeout: int = ENTRY_TIMEOUT) -> str:
    """First prompt: full web app or CLI. Env TRADINGAGENTS_INTERFACE wins.

    Falls back to CLI after ``timeout`` seconds without input.
    """
    env = os.environ.get("TRADINGAGENTS_INTERFACE", "").strip().lower()
    if env in ("web", "browser"):
        return "web"
    if env == "cli":
        return "cli"
    if os.name == "nt" and _enable_vt():
        try:
            return _ask_entry_mode_timed(timeout)
        except Exception:
            pass  # non-interactive console: fall through to plain prompt
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


def _enable_vt() -> bool:
    """Enable ANSI escape processing on legacy Windows consoles.

    Windows Terminal handles ANSI natively; plain cmd.exe needs the
    ENABLE_VIRTUAL_TERMINAL_PROCESSING flag or redraws print raw.
    Returns False when it can't be enabled (caller falls back).
    """
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & 0x0004:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _ask_entry_mode_timed(timeout: int) -> str:
    """Windows timed selector: arrows + Enter, auto-CLI on timeout."""
    import msvcrt
    import time as _time

    labels = ["CLI - terminal flow", "Browser - full web app"]
    values = ["cli", "web"]
    idx = 0
    sys.stdout.write("Start in:\n\n\n\n")
    sys.stdout.flush()
    deadline = _time.monotonic() + max(0, timeout)
    last_remaining = -1
    while True:
        remaining = max(0, int(deadline - _time.monotonic() + 0.999))
        if remaining <= 0:
            sys.stdout.write("\x1b[3F\x1b[2K  CLI - terminal flow\n\x1b[2K  Browser - full web app\n"
                             "\x1b[2K\n")
            console.print("[dim]No choice — continuing in CLI.[/dim]")
            return "cli"
        if remaining != last_remaining:
            last_remaining = remaining
            out = "\x1b[3F"
            for i, label in enumerate(labels):
                marker = "\x1b[32m>\x1b[0m" if i == idx else " "
                out += f"\x1b[2K{marker} [{i + 1}] {label}\n"
            out += (f"\x1b[2KAuto-selects CLI in {remaining:2d}s — "
                    "Up/Down or 1/2, Enter to confirm\n")
            sys.stdout.write(out)
            sys.stdout.flush()
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                code = msvcrt.getch()
                if code in (b"H", b"P"):  # up / down
                    idx = (idx + 1) % len(labels) if code == b"P" else (idx - 1) % len(labels)
                    last_remaining = -1  # force redraw
            elif ch == b"\r":
                sys.stdout.write("\n")
                return values[idx]
            elif ch == b"\x1b":
                sys.stdout.write("\n")
                return "cli"
            elif ch in (b"1", b"2"):
                sys.stdout.write("\n")
                return values[int(ch) - 1]
        _time.sleep(0.05)


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
