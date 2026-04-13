from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from fastapi import Request


CONTRACT_VERSION = "v1alpha1"
DEFAULT_EXECUTOR_TYPE = "legacy_subprocess"


@dataclass(frozen=True)
class RequestContext:
    """Minimal request-scoped metadata passed into application services."""

    request_id: str
    contract_version: str = CONTRACT_VERSION
    executor_type: str = DEFAULT_EXECUTOR_TYPE
    api_key: Optional[str] = None
    client_host: Optional[str] = None
    is_local: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


def build_request_context(
    request: Optional[Request] = None,
    *,
    api_key: Optional[str] = None,
    request_id: Optional[str] = None,
    contract_version: str = CONTRACT_VERSION,
    executor_type: str = DEFAULT_EXECUTOR_TYPE,
    metadata: Optional[dict[str, str]] = None,
) -> RequestContext:
    """Create a stable request context without leaking FastAPI internals into services."""
    client_host = request.client.host if request and request.client else None
    is_local = client_host in {"127.0.0.1", "::1", "localhost", "testclient"}
    return RequestContext(
        request_id=request_id or uuid4().hex,
        contract_version=contract_version,
        executor_type=executor_type,
        api_key=api_key,
        client_host=client_host,
        is_local=is_local,
        metadata=dict(metadata or {}),
    )
