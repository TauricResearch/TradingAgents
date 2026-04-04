from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .codex_app_server import (
    CodexAppServerAuthError,
    CodexAppServerBinaryError,
    CodexAppServerSession,
)
from .codex_binary import codex_binary_error_message, resolve_codex_binary


@dataclass(slots=True)
class CodexPreflightResult:
    account: dict
    models: list[str]


def run_codex_preflight(
    *,
    codex_binary: str | None,
    model: str,
    request_timeout: float,
    workspace_dir: str,
    cleanup_threads: bool,
    session_factory: Callable[..., CodexAppServerSession] = CodexAppServerSession,
) -> CodexPreflightResult:
    binary = resolve_codex_binary(codex_binary)
    if not binary:
        raise CodexAppServerBinaryError(codex_binary_error_message(codex_binary))

    session = session_factory(
        codex_binary=binary,
        request_timeout=request_timeout,
        workspace_dir=workspace_dir,
        cleanup_threads=cleanup_threads,
    )

    try:
        session.start()
        account_payload = session.account_read()
        account = account_payload.get("account")
        if not account:
            raise CodexAppServerAuthError(
                "Codex authentication is not available for TradingAgents. "
                "Run `codex login` or `codex login --device-auth`, then retry."
            )

        models_payload = session.model_list(include_hidden=True)
        models = _collect_model_names(models_payload)
        if model not in models:
            preview = ", ".join(models[:8]) if models else "no models reported"
            raise CodexAppServerBinaryError(
                f"Codex model '{model}' is not available from `model/list`. Available models: {preview}"
            )

        return CodexPreflightResult(account=account, models=models)
    finally:
        session.close()


def _collect_model_names(payload: dict) -> list[str]:
    names: list[str] = []
    for entry in payload.get("data", []) or []:
        if not isinstance(entry, dict):
            continue
        for key in ("model", "id"):
            value = entry.get(key)
            if isinstance(value, str) and value not in names:
                names.append(value)
    return names
