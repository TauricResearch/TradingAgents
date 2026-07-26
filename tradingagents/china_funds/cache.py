"""Capability-specific normalized cache for China public-fund providers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from tradingagents.domain import EvidenceField
from tradingagents.persistence import Repository

from .domain import Benchmark, FeeRule, Holding, NavPoint, TransactionStatus
from .providers import CapabilityResult

TTL = {
    "identity": timedelta(days=30),
    "nav": timedelta(hours=6),
    "transaction_status": timedelta(minutes=5),
    "fees": timedelta(days=7),
    "disclosure": timedelta(days=7),
    "benchmark": timedelta(days=30),
}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _encode_value(capability: str, value: Any) -> Any:
    if value is None:
        return None
    if capability in {"nav", "fees"}:
        return [asdict(item) for item in value]
    if capability == "transaction_status":
        return asdict(value)
    if capability == "benchmark":
        return asdict(value)
    if capability == "disclosure":
        encoded = dict(value)
        encoded["holdings"] = [asdict(item) for item in value.get("holdings") or ()]
        return encoded
    return value


def _decode_value(capability: str, value: Any) -> Any:
    if value is None:
        return None
    if capability == "nav":
        return tuple(NavPoint(**item) for item in value)
    if capability == "fees":
        return tuple(FeeRule(**item) for item in value)
    if capability == "transaction_status":
        return TransactionStatus(**value)
    if capability == "benchmark":
        value = dict(value)
        value["components"] = tuple(value.get("components") or ())
        return Benchmark(**value)
    if capability == "disclosure":
        value = dict(value)
        value["holdings"] = tuple(Holding(**item) for item in value.get("holdings") or ())
        return value
    return value


def _decode_evidence(items: list[dict[str, Any]], *, expired: bool) -> tuple[EvidenceField, ...]:
    evidence = []
    for item in items:
        value = dict(item)
        value["normalization_warnings"] = tuple(value.get("normalization_warnings") or ())
        if expired:
            value["freshness_status"] = "stale"
            value["normalization_warnings"] += ("CACHE_EXPIRED",)
        evidence.append(EvidenceField(**value))
    return tuple(evidence)


class CachedChinaFundProvider:
    """Caches normalized capability results and never stores provider payloads."""

    def __init__(self, provider: Any, repository: Repository):
        self.provider = provider
        self.repository = repository
        self.provider_id = str(provider.provider_id)

    def _fetch(
        self,
        capability: str,
        code: str,
        params: dict[str, Any],
        loader: Callable[[], CapabilityResult],
    ) -> CapabilityResult:
        cached = self.repository.get_provider_cache(self.provider_id, code, capability, params)
        now = datetime.now(UTC)
        if cached and _parse_time(cached.expires_at) >= now:
            return self._cached_result(capability, cached.normalized_payload, expired=False)
        try:
            result = loader()
        except Exception:
            if cached:
                return self._cached_result(capability, cached.normalized_payload, expired=True)
            raise
        payload = {
            "value": _encode_value(capability, result.value),
            "evidence": [asdict(item) for item in result.evidence],
            "warnings": list(result.warnings),
        }
        source_reference = next(
            (item.source_reference for item in result.evidence),
            f"provider://{self.provider_id}/{capability}/{code}",
        )
        effective_at = next(
            (item.effective_at for item in reversed(result.evidence) if item.effective_at), None
        )
        retrieved_at = next((item.retrieved_at for item in result.evidence), now.isoformat())
        self.repository.put_provider_cache(
            provider=self.provider_id,
            symbol=code,
            capability=capability,
            request_params=params,
            normalized_payload=payload,
            source_reference=source_reference,
            retrieved_at=retrieved_at,
            effective_at=effective_at,
            expires_at=(now + TTL[capability]).isoformat(),
        )
        return replace(result, cache_status="miss")

    @staticmethod
    def _cached_result(
        capability: str, payload: dict[str, Any], *, expired: bool
    ) -> CapabilityResult:
        warnings = tuple(payload.get("warnings") or ())
        if expired:
            warnings += (f"{capability.upper()}_CACHE_EXPIRED",)
        return CapabilityResult(
            _decode_value(capability, payload.get("value")),
            _decode_evidence(payload.get("evidence") or [], expired=expired),
            tuple(dict.fromkeys(warnings)),
            "expired" if expired else "hit",
        )

    def fetch_identity(self, code: str) -> CapabilityResult:
        return self._fetch("identity", code, {}, lambda: self.provider.fetch_identity(code))

    def fetch_nav(self, code: str, analysis_date: str) -> CapabilityResult:
        params = {"analysis_date": analysis_date}
        return self._fetch(
            "nav", code, params, lambda: self.provider.fetch_nav(code, analysis_date)
        )

    def fetch_transaction_status(self, code: str) -> CapabilityResult:
        return self._fetch(
            "transaction_status",
            code,
            {},
            lambda: self.provider.fetch_transaction_status(code),
        )

    def fetch_fees(self, code: str) -> CapabilityResult:
        return self._fetch("fees", code, {}, lambda: self.provider.fetch_fees(code))

    def fetch_disclosure(self, code: str) -> CapabilityResult:
        return self._fetch("disclosure", code, {}, lambda: self.provider.fetch_disclosure(code))

    def fetch_benchmark(self, code: str) -> CapabilityResult:
        return self._fetch("benchmark", code, {}, lambda: self.provider.fetch_benchmark(code))
