"""Secrets access layer (go-live Phase 3).

Resolution order for ``get_secret("NAME")``:

1. ``NAME_FILE`` env var pointing at a file (Docker secrets convention:
   compose/k8s mount the secret at a path and export ``NAME_FILE``).
2. ``NAME`` env var directly.

Plaintext ``.env`` values are acceptable for TESTNET keys only. For
production keys, keep them in an age/SOPS-encrypted file and run the
process under ``sops exec-env secrets.enc.env -- <command>`` (the
decrypted values exist only in the process environment), or use Docker
secrets with the ``_FILE`` convention. Never commit, log, or echo them —
``describe_source`` exists so preflight can REPORT where a secret came
from without revealing it.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


class SecretUnavailable(Exception):
    pass


def get_secret(name: str, required: bool = False) -> str | None:
    file_var = os.environ.get(f"{name}_FILE")
    if file_var:
        try:
            return Path(file_var).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SecretUnavailable(
                f"{name}_FILE points at an unreadable path: {exc}") from exc
    value = os.environ.get(name)
    if value:
        return value
    if required:
        raise SecretUnavailable(
            f"secret {name} not found (checked {name}_FILE and {name})")
    return None


def describe_source(name: str) -> str:
    """Where a secret would come from — for preflight reporting only."""
    if os.environ.get(f"{name}_FILE"):
        return f"file:{os.environ[f'{name}_FILE']}"
    if os.environ.get(name):
        return "env"
    return "absent"


def file_permissions_ok(path: str | Path) -> bool:
    """True when the file is not readable by group/other (0600-style)."""
    mode = stat.S_IMODE(os.stat(path).st_mode)
    return (mode & 0o077) == 0
