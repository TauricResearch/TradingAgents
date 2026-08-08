"""Project-local environment-file boundaries."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def secure_environment_file(path: Path, *, create: bool = False) -> bool:
    """Reject links/non-files and enforce owner-only access on a secrets file."""
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if path.is_symlink() or not stat.S_ISREG(mode):
            raise ValueError(f"{path.name} must be a regular file")
        os.chmod(path, 0o600)
        return True
    if not create:
        return False
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    return True
