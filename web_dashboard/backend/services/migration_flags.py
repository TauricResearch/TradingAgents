from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MigrationFlags:
    """Migration modes for contract-first backend rollout."""

    executor_mode: str = "legacy"
    response_mode: str = "contract_first"
    write_mode: str = "dual_write"
    read_mode: str = "dual_read"
    request_context_enabled: bool = True

    @property
    def use_application_services(self) -> bool:
        return self.executor_mode in {"legacy", "direct", "auto"}

    @property
    def use_result_store(self) -> bool:
        return self.read_mode in {"dual_read", "contract_only"}

    @property
    def use_request_context(self) -> bool:
        return self.request_context_enabled


def load_migration_flags() -> MigrationFlags:
    """Load service migration modes from the environment with boolean compatibility."""
    executor_mode = os.environ.get("TRADINGAGENTS_EXECUTOR_MODE")
    if executor_mode is None:
        executor_mode = "legacy" if _env_flag("TRADINGAGENTS_USE_APPLICATION_SERVICES", default=False) else "legacy"

    response_mode = os.environ.get("TRADINGAGENTS_RESPONSE_MODE", "contract_first")
    write_mode = os.environ.get("TRADINGAGENTS_WRITE_MODE")
    if write_mode is None:
        write_mode = "dual_write" if _env_flag("TRADINGAGENTS_USE_RESULT_STORE", default=False) else "dual_write"

    read_mode = os.environ.get("TRADINGAGENTS_READ_MODE")
    if read_mode is None:
        read_mode = "dual_read" if _env_flag("TRADINGAGENTS_USE_RESULT_STORE", default=False) else "legacy_only"

    return MigrationFlags(
        executor_mode=executor_mode,
        response_mode=response_mode,
        write_mode=write_mode,
        read_mode=read_mode,
        request_context_enabled=_env_flag("TRADINGAGENTS_USE_REQUEST_CONTEXT", default=True),
    )
