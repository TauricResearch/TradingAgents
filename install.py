#!/usr/bin/env python3
"""Single cross-OS installer for TradingAgents (Windows / Linux / macOS).

Run from the repo root. Does everything, then tells you to open a NEW
terminal and type ``tradingagents``:
  1. Creates ``.venv`` here if missing.
  2. Installs the package (editable) + dependencies via pip.
  3. Writes ``tradingagents`` launchers (``.bat`` for cmd, ``.ps1`` for
     PowerShell, ``~/.local/bin`` symlink on POSIX).
  4. Adds this folder to the user PATH (setx on Windows, shell-rc export
     lines on POSIX).
  5. Runs ``npm install`` in ``web/`` when node is available (Browser mode).

Stdlib only. Idempotent — safe to re-run. Use ``--dry-run`` to preview.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
WEB_DIR = HERE / "web"


def shlex_join(args):
    try:
        import shlex

        return shlex.join(args)
    except Exception:
        return " ".join(args)


def run(args, **kwargs):
    print("+", shlex_join(str(a) for a in args))
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv(dry: bool):
    py = venv_python()
    if py.exists():
        print(f"venv exists: {py}")
        return py
    print("Creating virtual environment...")
    if not dry:
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    return py


def pip_install(py: Path, dry: bool):
    print("Upgrading pip...")
    if not dry:
        run([py, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    print("Installing TradingAgents (editable)...")
    if not dry:
        run([py, "-m", "pip", "install", "-e", "."], cwd=str(HERE))


BAT = """@echo off
title TradingAgents CLI
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\\Scripts\\python.exe"
if not exist "%PY%" (
    echo TradingAgents venv not found at %PY%
    echo Re-run install.py
    exit /b 1
)
"%PY%" -m cli.main %*
"""

PS1 = """#!/usr/bin/env pwsh
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$pyPath = Join-Path $scriptDir ".venv/Scripts/python.exe"
if ($IsWindows -and -not (Test-Path $pyPath)) {
    $pyPath = Join-Path $scriptDir ".venv/Scripts/python.exe"
}
if ((-not $IsWindows) -or (-not (Test-Path $pyPath))) {
    # POSIX layout fallback (pwsh on Linux/macOS)
    $pyPath = Join-Path $scriptDir ".venv/bin/python"
}
if (-not (Test-Path $pyPath)) { Write-Error "TradingAgents venv not found; re-run install.py"; exit 1 }
& $pyPath -m cli.main @args
"""


def write_wrappers(dry: bool):
    import tempfile

    # NOTE: no extension-less `tradingagents` file here — on a
    # case-insensitive filesystem it would collide with nothing here, but
    # pip already installs a `tradingagents` entry point in the venv, so
    # POSIX just symlinks that into ~/.local/bin (below).
    for name, content in (("tradingagents.bat", BAT), ("tradingagents.ps1", PS1)):
        path = HERE / name
        print(f"Writing {name} ...")
        if dry:
            continue
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="", delete=False, dir=str(HERE)
            ) as tmp:
                tmp.write(content)
            os.replace(tmp.name, path)
        except OSError as exc:
            print(f"WARNING: could not write {name}: {exc}")
            continue
    if os.name != "nt" and not dry:
        link_dir = Path.home() / ".local" / "bin"
        try:
            link_dir.mkdir(parents=True, exist_ok=True)
            src = VENV / "bin" / "tradingagents"
            link = link_dir / "tradingagents"
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(src)
            print(f"Linked {link} -> {src}")
        except OSError as exc:
            print(f"WARNING: could not link launcher: {exc}")


def ensure_path(dry: bool):
    if os.name == "nt":
        import ctypes

        try:
            buf = ctypes.create_unicode_buffer(32767)
            ctypes.windll.kernel32.GetEnvironmentVariableW("Path", buf, 32767)
            user_path = buf.value
        except Exception:
            user_path = os.environ.get("Path", "")
        if str(HERE).lower() in user_path.lower():
            print("PATH already contains repo dir.")
            return
        print("Adding repo dir to User PATH (setx)...")
        if not dry:
            subprocess.run(
                ["setx", "Path", f"{user_path};{HERE}"],
                check=True,
                capture_output=True,
            )
        print("NOTE: open a NEW terminal for the new PATH to apply.")
        return
    # POSIX: export line in bashrc/zshrc with a marker (no duplicates).
    line = f'\nexport PATH="{HERE}:$PATH"  # tradingagents-install\n'
    for rc in (Path.home() / ".bashrc", Path.home() / ".zshrc"):
        try:
            text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        except OSError:
            continue
        if "tradingagents-install" in text:
            print(f"PATH already configured in {rc.name}.")
            continue
        print(f"Appending PATH export to {rc} ...")
        if not dry:
            with open(rc, "a", encoding="utf-8") as f:
                f.write(line)
    print("NOTE: open a NEW terminal (or `source ~/.bashrc`) to apply PATH.")


def ensure_web(dry: bool):
    if not WEB_DIR.is_dir():
        return
    npm = shutil.which("npm")
    if npm is None:
        print("WARNING: node/npm not found — Browser mode needs it (https://nodejs.org).")
        return
    if (WEB_DIR / "node_modules").is_dir():
        print("web/node_modules already installed.")
        return
    print("Installing web dependencies (npm install)...")
    if not dry:
        run([npm, "install"], cwd=str(WEB_DIR))


def main() -> int:
    ap = argparse.ArgumentParser(description="Install TradingAgents (all OSes).")
    ap.add_argument("--dry-run", action="store_true", help="print actions without doing them")
    ap.add_argument("--no-web", action="store_true", help="skip web/node setup")
    args = ap.parse_args()

    if not (HERE / "pyproject.toml").is_file():
        print(f"ERROR: run this from the repo root (no pyproject.toml in {HERE}).")
        return 1

    print(f"Repo : {HERE}")
    print(f"OS   : {os.name} ({sys.platform})")
    py = ensure_venv(args.dry_run)
    pip_install(py, args.dry_run)
    write_wrappers(args.dry_run)
    ensure_path(args.dry_run)
    if not args.no_web:
        ensure_web(args.dry_run)

    print("\nInstall complete!")
    print("Open a NEW terminal and type: tradingagents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
