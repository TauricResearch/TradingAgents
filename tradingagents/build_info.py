"""Build identification for the running service (§2 of the P1 task).

The data lineage audit established that a process started before a merge
executes the code it loaded at start, whatever the files on disk say. Start time
alone was not enough to prove which code was live, so this module makes the
question answerable from the service itself.

Two identifiers, both derived at import time and both non-sensitive:

``commit``
    The short SHA the working tree reports, or ``unknown`` when it cannot be
    read (no git binary, a source distribution). Never raises.
``loaded_at``
    When *this process* imported the module — the moment the running code began
    to exist, which is what distinguishes a live process from a stale one.

The combination is the point: a commit from months ago paired with a
``loaded_at`` from minutes ago tells an operator the service did not restart
after a deployment. Nothing here reads configuration values, paths outside the
repository, or anything an operator would not publish in a health response.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

# Captured at import: the instant this process began running this code.
LOADED_AT = datetime.now(UTC).isoformat(timespec="seconds")

# ``build_info.py`` lives in ``<repo>/tradingagents/``, so the repository root is
# its parent's parent — not three levels up, which would escape the repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def commit_sha(short: bool = True) -> str:
    """The commit this code came from, or ``unknown``.

    Cached because a health endpoint may be polled; the value cannot change for
    a running process. Deliberately forgiving: a deployment without git, or a
    read-only filesystem, must not make the service report itself unhealthy.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse",
             "--short" if short else "--verify", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def build_info() -> dict:
    """What the service is running, for a health response.

    Reports no environment values and no filesystem paths: a health endpoint is
    often reachable by anyone who can reach the service, so the payload stays to
    what identifies the build and nothing more.

    §3 of P4 widened this from "which commit" to "which code, in which process,
    with which validators loaded". The three questions an operator actually asks
    after a deployment are answered here: is the running code the merged code
    (``commit``), did the process restart since the merge (``service_started_at``
    against the commit time), and are the deterministic checks actually wired
    (``validators``) — the last one being the failure the lineage audit could
    not detect from outside.
    """
    from tradingagents.dataflows import run_record

    return {
        "commit": commit_sha(),
        "build_id": run_record.build_id(),
        "loaded_at": LOADED_AT,
        "service_started_at": LOADED_AT,
        "python": run_record.runtime_fingerprint()["python"],
        "validators": run_record.validator_status(),
        "math_engine": {
            "loaded": run_record.validator_status().get(
                "metric_registry", {}).get("loaded", False),
            "module": "tradingagents.dataflows.math",
        },
    }
