from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_codex_binary(codex_binary: str | None) -> str | None:
    explicit = _normalize_explicit_binary(codex_binary)
    if explicit:
        return explicit

    env_value = _normalize_explicit_binary(os.getenv("CODEX_BINARY"))
    if env_value:
        return env_value

    path_binary = shutil.which("codex")
    if path_binary:
        return path_binary

    for candidate in _windows_codex_candidates():
        if candidate.is_file():
            return str(candidate)

    return None


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
            home / ".codex" / "bin" / "codex.exe",
            home / "AppData" / "Local" / "Programs" / "Codex" / "codex.exe",
        ]
    )
    return candidates
