"""Canonical JSON and SHA-256 helpers for FR-04 identities.

The canonical form is the proposed shared form: sorted object keys, compact
separators, UTF-8, Decimal as a fixed-point string, aware datetimes normalized to
UTC, tuples as arrays, and SHA-256 lowercase hex.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def hash_is_valid(value: Any) -> bool:
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value) is not None


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.isoformat()
        return value.astimezone(UTC).isoformat()
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(item) for item in value)
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {str(key): _normalize(item) for key, item in items}
    if hasattr(value, "to_canonical_dict"):
        return _normalize(value.to_canonical_dict())
    raise TypeError(f"cannot canonicalize {type(value)!r}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _claim_dict(claim: Any) -> dict[str, Any]:
    if isinstance(claim, Mapping):
        return {
            "claim_id": claim.get("claim_id"),
            "text": claim.get("text"),
            "evidence_ids": claim.get("evidence_ids", ()),
            "stance": claim.get("stance"),
            "counterargument": claim.get("counterargument"),
            "unresolved": claim.get("unresolved"),
        }
    return {
        "claim_id": getattr(claim, "claim_id", None),
        "text": getattr(claim, "text", None),
        "evidence_ids": getattr(claim, "evidence_ids", ()),
        "stance": getattr(claim, "stance", None),
        "counterargument": getattr(claim, "counterargument", None),
        "unresolved": getattr(claim, "unresolved", None),
    }


def _item_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return {
            "evidence_id": item.get("evidence_id"),
            "source_uri": item.get("source_uri"),
            "published_at": item.get("published_at"),
            "fetched_at": item.get("fetched_at"),
            "content_hash": item.get("content_hash"),
            "excerpt": item.get("excerpt"),
            "availability": item.get("availability"),
            "trust_label": item.get("trust_label"),
        }
    return {
        "evidence_id": getattr(item, "evidence_id", None),
        "source_uri": getattr(item, "source_uri", None),
        "published_at": getattr(item, "published_at", None),
        "fetched_at": getattr(item, "fetched_at", None),
        "content_hash": getattr(item, "content_hash", None),
        "excerpt": getattr(item, "excerpt", None),
        "availability": getattr(item, "availability", None),
        "trust_label": getattr(item, "trust_label", None),
    }


def proposal_fields(proposal: Any) -> dict[str, Any]:
    claims = getattr(proposal, "claims", ()) or ()
    return {
        "proposal_id": getattr(proposal, "proposal_id", None),
        "run_id": getattr(proposal, "run_id", None),
        "ticker": getattr(proposal, "ticker", None),
        "action": getattr(proposal, "action", None),
        "quantity": getattr(proposal, "quantity", None),
        "currency": getattr(proposal, "currency", None),
        "reference_price": getattr(proposal, "reference_price", None),
        "price_time": getattr(proposal, "price_time", None),
        "claims": tuple(_claim_dict(claim) for claim in claims),
        "evidence_pack_hash": getattr(proposal, "evidence_pack_hash", None),
        "portfolio_version": getattr(proposal, "portfolio_version", None),
        "policy_hash": getattr(proposal, "policy_hash", None),
        "expires_at": getattr(proposal, "expires_at", None),
    }


def policy_fields(policy: Any) -> dict[str, Any]:
    return {
        "version": getattr(policy, "version", None),
        "base_currency": getattr(policy, "base_currency", None),
        "max_position_pct": getattr(policy, "max_position_pct", None),
        "max_order_pct": getattr(policy, "max_order_pct", None),
        "price_freshness_seconds": getattr(policy, "price_freshness_seconds", None),
        "fee_bps": getattr(policy, "fee_bps", None),
        "slippage_bps": getattr(policy, "slippage_bps", None),
        "allowed_actions": getattr(policy, "allowed_actions", frozenset()),
        "long_only": getattr(policy, "long_only", None),
        "paper_only": getattr(policy, "paper_only", None),
        "effective_from": getattr(policy, "effective_from", None),
        "expires_at": getattr(policy, "expires_at", None),
        "quantization": getattr(policy, "quantization", None),
    }


def evidence_fields(pack: Any) -> dict[str, Any]:
    items = getattr(pack, "items", ()) or ()
    excluded = getattr(pack, "excluded_items", ()) or ()
    return {
        "run_id": getattr(pack, "run_id", None),
        "snapshot_id": getattr(pack, "snapshot_id", None),
        "items": tuple(_item_dict(item) for item in items),
        "excluded_items": tuple(_item_dict(item) for item in excluded),
        "cutoff": getattr(pack, "cutoff", None),
    }


def recompute_proposal_hash(proposal: Any) -> str:
    return sha256_hex(proposal_fields(proposal))


def recompute_policy_hash(policy: Any) -> str:
    return sha256_hex(policy_fields(policy))


def recompute_evidence_hash(pack: Any) -> str:
    return sha256_hex(evidence_fields(pack))


def payload_hash(payload: Mapping[str, Any]) -> str:
    return sha256_hex(payload)
