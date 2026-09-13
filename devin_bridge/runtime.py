"""Runtime workspace setup for isolated Devin invocations.

Creates a disposable directory outside the TradingAgents checkout, initializes
it as a Devin project root (``git init``), and writes the restrictive
``.devin/config.json`` that denies native coding/runtime tools.

The default runtime directory is created under the OS temp location (e.g.
``/tmp/tradingagents-devin-bridge-<unique>/``), NEVER inside the checkout.
User-supplied ``--runtime-dir`` paths are checked with real-path resolution
to reject paths inside the checkout even via ``..`` or symlinks.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

from .config import RUNTIME_CONFIG


class RuntimeSetupError(Exception):
    """Raised when the runtime workspace cannot be prepared."""


def find_checkout_root(start: str | None = None) -> str:
    """Find the TradingAgents checkout root by walking up for pyproject.toml.

    Returns the real (resolved) absolute path. Falls back to the parent
    of the ``devin_bridge`` package directory.
    """
    p = Path(start).resolve() if start else Path(__file__).resolve().parent.parent
    for candidate in [p, *p.parents]:
        if (candidate / "pyproject.toml").exists() and \
           (candidate / "tradingagents").is_dir():
            return str(candidate)
    return str(p)


def _is_inside_checkout(runtime_dir: str, checkout_dir: str) -> bool:
    """Return True if runtime_dir resolves to inside checkout_dir.

    Uses ``Path.resolve()`` to handle ``..`` and symlinks. Both paths are
    fully resolved before comparison.
    """
    rdir = Path(runtime_dir).resolve()
    cdir = Path(checkout_dir).resolve()
    # Exact match (runtime IS the checkout) or underneath it.
    if rdir == cdir:
        return True
    try:
        rdir.relative_to(cdir)
        return True
    except ValueError:
        return False


def verify_outside_checkout(runtime_dir: str, checkout_dir: str) -> None:
    """Verify the runtime workspace is NOT inside the TradingAgents checkout.

    Uses real-path resolution to handle ``..`` and symlinks.
    Raises RuntimeSetupError if the runtime is inside or equal to the checkout.
    """
    if _is_inside_checkout(runtime_dir, checkout_dir):
        raise RuntimeSetupError(
            f"Runtime workspace {runtime_dir} (resolved to "
            f"{Path(runtime_dir).resolve()}) is inside the TradingAgents "
            f"checkout {checkout_dir} (resolved to "
            f"{Path(checkout_dir).resolve()}). It must be outside."
        )


def prepare_runtime(runtime_dir: str) -> str:
    """Prepare the isolated Devin runtime workspace.

    - Creates the directory if missing (with private permissions).
    - Writes ``.devin/config.json`` with restrictive deny rules.
    - Runs ``git init`` (no commit) so Devin recognizes the project root.
    - Does NOT modify global Devin configuration.

    Returns the absolute path to the runtime directory.
    """
    rdir = Path(runtime_dir).resolve()
    rdir.mkdir(parents=True, exist_ok=True)

    # Set private permissions on the runtime directory (0700).
    with contextlib.suppress(OSError):
        os.chmod(str(rdir), stat.S_IRWXU)

    devin_dir = rdir / ".devin"
    devin_dir.mkdir(exist_ok=True)
    config_path = devin_dir / "config.json"

    config_json = json.dumps(RUNTIME_CONFIG, indent=2)
    config_path.write_text(config_json, encoding="utf-8")
    # Private permissions on config file.
    with contextlib.suppress(OSError):
        os.chmod(str(config_path), stat.S_IRUSR | stat.S_IWUSR)

    # Create .prompts directory with private permissions for prompt files.
    prompts_dir = rdir / ".prompts"
    prompts_dir.mkdir(exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(str(prompts_dir), stat.S_IRWXU)

    # git init for project-root detection (no commit needed).
    git_dir = rdir / ".git"
    if not git_dir.exists():
        result = subprocess.run(
            ["git", "init"],
            cwd=str(rdir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeSetupError(
                f"git init failed in {rdir}: {result.stderr.strip()}"
            )

    return str(rdir)


def cleanup_runtime(runtime_dir: str) -> None:
    """Remove an automatically-created runtime directory.

    Only removes the directory if it exists. This is called on graceful
    shutdown for auto-created temp directories. For user-supplied
    ``--runtime-dir``, this is NOT called (the user owns that directory).
    """
    rdir = Path(runtime_dir).resolve()
    if rdir.exists() and rdir.is_dir():
        shutil.rmtree(str(rdir), ignore_errors=True)
