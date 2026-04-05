from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def resolve_codex_binary(codex_binary: str | None) -> str | None:
    requested_candidates = [
        _normalize_explicit_binary(codex_binary),
        _normalize_explicit_binary(os.getenv("CODEX_BINARY")),
    ]
    for candidate in requested_candidates:
        if candidate and _is_usable_codex_binary(candidate):
            return candidate

    discovered_candidates = []
    path_binary = shutil.which("codex")
    if path_binary:
        discovered_candidates.append(path_binary)

    discovered_candidates.extend(str(candidate) for candidate in _windows_codex_candidates())

    first_existing = None
    for candidate in _dedupe_candidates(discovered_candidates):
        if not Path(candidate).is_file():
            continue
        if first_existing is None:
            first_existing = candidate
        if _is_usable_codex_binary(candidate):
            return candidate

    for candidate in requested_candidates:
        if candidate:
            return candidate

    return first_existing


def codex_binary_error_message(codex_binary: str | None) -> str:
    requested = codex_binary or os.getenv("CODEX_BINARY") or "codex"
    message = (
        f"Could not find Codex binary '{requested}'. Install Codex, ensure it is on PATH, "
        "set the `CODEX_BINARY` environment variable, or configure `codex_binary` with the full executable path."
    )
    discovered = [str(path) for path in _windows_codex_candidates() if path.is_file()]
    if discovered:
        message += f" Detected candidate: {discovered[0]}"
    return message


def _normalize_explicit_binary(value: str | None) -> str | None:
    if not value:
        return None

    expanded = str(Path(value).expanduser())
    has_separator = any(sep and sep in expanded for sep in (os.path.sep, os.path.altsep))
    if has_separator:
        return expanded if Path(expanded).is_file() else None

    found = shutil.which(expanded)
    return found or None


def _windows_codex_candidates() -> list[Path]:
    if os.name != "nt":
        return []

    home = Path.home()
    candidates = sorted(
        home.glob(r".vscode/extensions/openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    candidates.extend(
        [
            home / ".codex" / ".sandbox-bin" / "codex.exe",
            home / ".codex" / "bin" / "codex.exe",
            home / "AppData" / "Local" / "Programs" / "Codex" / "codex.exe",
        ]
    )
    return candidates


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    unique = []
    seen = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.normpath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(candidate)
    return unique


def _is_usable_codex_binary(binary: str) -> bool:
    if os.name != "nt":
        return True

    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return completed.returncode == 0
