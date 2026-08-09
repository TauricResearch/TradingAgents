"""Pure helpers for the structured-output smoke script (issue #1216).

The smoke script calls real LLM providers, so a missing credential or a
provider error must fail fast with a clear, actionable message instead of a
raw traceback.  Keeping the checks here (pure functions) makes them
unit-testable without network access.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Sequence


def require_api_key(env_var: str, provider: str) -> str:
    """Return the API key for *provider* or exit(2) with a clear message.

    A missing or blank env var is a configuration error, not a runtime
    failure: the operator needs to know exactly which variable to set.
    """
    key = os.environ.get(env_var, "")
    if not key:
        print(
            f"ERROR: missing {env_var} for provider '{provider}'.\n"
            f"Set it in your environment (or .env) and re-run, e.g.:\n"
            f"    {env_var}=... python scripts/smoke_structured_output.py {provider}",
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def run_agent_call(label: str, fn: Callable[[], Any]) -> Any:
    """Run *fn* and return its result, or exit(2) on failure.

    Provider timeouts, empty outputs and exceptions are all surfaced as a
    labelled error so a partial run is easy to diagnose.
    """
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - the smoke must not traceback
        print(f"ERROR: {label} call raised: {exc}", file=sys.stderr)
        sys.exit(2)
    if not result:
        print(
            f"ERROR: {label} returned an empty result — check the model and "
            "provider configuration.",
            file=sys.stderr,
        )
        sys.exit(2)
    return result


def check_structure(name: str, text: str, required: Sequence[str]) -> list[str]:
    """Return a list of missing-marker failures for *text*.

    Each failure is a human-readable string naming the section and the
    marker that was absent, so the smoke output tells the operator exactly
    which downstream consumer would break.
    """
    failures: list[str] = []
    for marker in required:
        if marker not in text:
            failures.append(f"{name}: missing {marker!r}")
    return failures
