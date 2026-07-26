"""Capability-based provider contracts and failure-isolating registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from tradingagents.domain import EvidenceField

CAPABILITIES = (
    "identity",
    "nav",
    "transaction_status",
    "fees",
    "disclosure",
    "benchmark",
)


@dataclass(frozen=True)
class CapabilityResult:
    value: Any
    evidence: tuple[EvidenceField, ...] = ()
    warnings: tuple[str, ...] = ()
    cache_status: str = "miss"


class FundCapabilityProvider(Protocol):
    provider_id: str

    def fetch_identity(self, code: str) -> CapabilityResult: ...

    def fetch_nav(self, code: str, analysis_date: str) -> CapabilityResult: ...

    def fetch_transaction_status(self, code: str) -> CapabilityResult: ...

    def fetch_fees(self, code: str) -> CapabilityResult: ...

    def fetch_disclosure(self, code: str) -> CapabilityResult: ...

    def fetch_benchmark(self, code: str) -> CapabilityResult: ...


@dataclass
class ProviderRegistry:
    providers: dict[str, list[FundCapabilityProvider]] = field(default_factory=dict)

    def register(self, capability: str, provider: FundCapabilityProvider) -> None:
        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown fund capability: {capability}")
        self.providers.setdefault(capability, []).append(provider)

    def fetch(
        self, capability: str, call: Callable[[FundCapabilityProvider], CapabilityResult]
    ) -> CapabilityResult:
        errors: list[str] = []
        for provider in self.providers.get(capability, []):
            try:
                result = call(provider)
                if result.value is not None:
                    return result
            except Exception as exc:  # noqa: BLE001 - capability failures are isolated
                errors.append(f"{provider.provider_id}:{type(exc).__name__}")
        return CapabilityResult(None, warnings=(f"{capability.upper()}_UNAVAILABLE", *errors))
