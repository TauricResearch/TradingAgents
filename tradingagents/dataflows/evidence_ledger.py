"""Structured, non-reasoning evidence ledgers for the Evidence Steward.

The ledger deliberately records only reviewable research facts: the claim
being tested, the deterministic criterion, and source metadata.  It must not
contain hidden model reasoning, prompt scratchpads, or chain-of-thought.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from tradingagents.observability.context import current_observation_context
from tradingagents.observability.events import RunEventDraft
from tradingagents.observability.provenance import current_provenance_observer
from tradingagents.observability.redaction import redact_recursive

EVIDENCE_LEDGER_VERSION = 1


def build_evidence_ledger(
    *,
    profile: Mapping[str, Any],
    assessment: Mapping[str, Any],
    trade_date: str,
    enrichment_rounds: int,
    direction_scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Build a deterministic research ledger from already-assessed news.

    ``assessment`` is the existing rule/LLM-assisted coverage result.  This
    function does not ask a model to infer claims; it records the objective
    gate being checked and the source records used for that verdict.
    ``direction_scores`` optionally maps a source item's id or url to a
    normalized direction in [-1, 1] (for example from the Layer 1 sentiment
    pass); records without a score are stored without one rather than
    inferring a direction.
    """
    ticker = str(profile.get("ticker") or profile.get("ts_code") or "unknown")
    status = _ledger_status(assessment.get("status"))
    evidence = [
        _evidence_record(
            item,
            trade_date=trade_date,
            status=status,
            direction_scores=direction_scores,
        )
        for item in assessment.get("items") or []
        if isinstance(item, Mapping)
    ]
    evidence_ids = [entry["evidence_id"] for entry in evidence]
    criteria = _criteria(profile, assessment)
    criterion_ids = [criterion["criterion_id"] for criterion in criteria]
    claim = {
        "claim_id": _stable_id("claim", {"ticker": ticker, "as_of": trade_date}),
        "statement": f"Research evidence for {ticker} satisfies the configured identity and coverage gate.",
        "criterion_ids": criterion_ids,
        "evidence_ids": evidence_ids,
        "verification_status": status,
        "contradicts": _contradictions(assessment),
    }
    ledger = {
        "ledger_version": EVIDENCE_LEDGER_VERSION,
        "subject": {
            "ticker": ticker,
            "name": str(profile.get("name") or ""),
        },
        "data_as_of": str(trade_date or ""),
        "enrichment_rounds": max(0, int(enrichment_rounds)),
        "claims": [claim],
        "criteria": criteria,
        "evidence": evidence,
        "verification_status": status,
    }
    ledger["ledger_id"] = _stable_id("ledger", ledger)
    return ledger


def persist_evidence_ledger(ledger: Mapping[str, Any]) -> str | None:
    """Persist a redacted ledger artifact and emit its typed audit event.

    Standalone CLI and unit calls have no durable observer; they still receive
    the state ledger, while web/observed graph runs additionally receive a
    durable artifact and event linked to the active role turn.
    """
    observer = current_provenance_observer()
    context = current_observation_context()
    if observer is None or context is None:
        return None

    redacted = redact_recursive(dict(ledger))
    artifact = observer.store_artifact("evidence-ledger", redacted.value)
    observer.emit(
        RunEventDraft(
            context.run_id,
            "evidence.ledger_written",
            {
                "turn_id": context.turn_id,
                "graph_task_id": context.graph_task_id,
                "ledger_id": str(ledger["ledger_id"]),
                "artifact_id": artifact.artifact_id,
                "content_sha256": artifact.content_sha256,
                "data_as_of": str(ledger.get("data_as_of") or ""),
                "claim_count": len(ledger.get("claims") or []),
                "evidence_count": len(ledger.get("evidence") or []),
                "verification_status": str(ledger.get("verification_status") or "unknown"),
                "redaction_manifest": [record.path for record in redacted.manifest],
            },
            actor_id=context.actor_id,
            node_id=context.node_id,
            status="completed",
        )
    )
    return artifact.artifact_id


def _criteria(profile: Mapping[str, Any], assessment: Mapping[str, Any]) -> list[dict[str, Any]]:
    ticker = str(profile.get("ticker") or profile.get("ts_code") or "unknown")
    status = _ledger_status(assessment.get("status"))
    return [
        _criterion(
            "identity_match",
            "No contradictory company identity is present in the evidence set.",
            status="contradicted" if _contradictions(assessment) else "verified",
        ),
        _criterion(
            "company_coverage",
            f"Company-relevant evidence meets the configured threshold for {ticker}.",
            observed=assessment.get("company_count", 0),
            status=status,
        ),
        _criterion(
            "mixed_coverage",
            "Company, official, or industry evidence meets the configured mixed threshold.",
            observed=assessment.get("mixed_count", 0),
            status=status,
        ),
    ]


def _criterion(
    name: str, description: str, *, status: str, observed: Any | None = None
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "criterion_id": _stable_id("criterion", {"name": name}),
        "name": name,
        "description": description,
        "verification_status": status,
    }
    if observed is not None:
        record["observed_count"] = int(observed)
    return record


def _evidence_record(
    item: Mapping[str, Any],
    *,
    trade_date: str,
    status: str,
    direction_scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    uri = str(item.get("url") or "")
    source_provider = _source_provider(item, uri)
    source_record = {
        "title": str(item.get("title") or "Untitled"),
        "uri": uri,
        "publisher": str(item.get("publisher") or ""),
        "published": str(item.get("published") or ""),
        # Keep a fingerprint of the source excerpt, not its full prose.
        "excerpt_sha256": _stable_hash(str(item.get("content") or "")),
    }
    artifact_hash = _stable_hash(source_record)
    record = {
        "evidence_id": _stable_id("evidence", source_record),
        "source_provider": source_provider,
        "uri": uri,
        "method": _source_method(item),
        "artifact_hash": artifact_hash,
        "source_artifact_ids": _string_list(item.get("provenance_artifact_ids")),
        "data_as_of": str(item.get("published") or trade_date or ""),
        "verification_status": _item_status(item, default=status),
        "contradicts": [],
        "title": source_record["title"],
        "publisher": source_record["publisher"],
        "credibility": str(item.get("credibility") or "unknown"),
        "direction_score": _direction_score(item, direction_scores),
    }
    return record


def _direction_score(
    item: Mapping[str, Any],
    direction_scores: Mapping[str, float] | None,
) -> float | None:
    """Return a precomputed direction for this source, or None.

    The key is the item's id or url, matching the Layer 1 sentiment item_id.
    No direction is ever inferred here: the ledger stays deterministic and
    non-reasoning, and downstream alignment simply skips records without one.
    """
    if not direction_scores:
        return None
    key = str(item.get("id") or item.get("url") or "").strip()
    if not key:
        return None
    score = direction_scores.get(key)
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return float(score)


def _source_provider(item: Mapping[str, Any], uri: str) -> str:
    source = str(item.get("source") or "").strip()
    if source.startswith("tavily"):
        return "tavily"
    domain = urlparse(uri).netloc.lower()
    return source or domain or "report"


def _source_method(item: Mapping[str, Any]) -> str:
    source = str(item.get("source") or "").strip()
    return "evidence_tavily_enrichment" if source.startswith("tavily") else "report_extraction"


def _item_status(item: Mapping[str, Any], *, default: str) -> str:
    if item.get("cross_source_tag") == "confirmed":
        return "verified"
    return "verified" if default == "verified" else "unverified"


def _contradictions(assessment: Mapping[str, Any]) -> list[str]:
    return [
        str(reason)
        for reason in assessment.get("reasons") or []
        if "身份冲突" in str(reason) or "contradict" in str(reason).lower()
    ]


def _ledger_status(value: Any) -> str:
    raw = str(getattr(value, "value", value) or "").upper()
    if raw == "PASS":
        return "verified"
    if raw == "FAIL_STOP":
        return "contradicted"
    return "insufficient"


def _stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{_stable_hash(value)[:20]}"


def _stable_hash(value: Any) -> str:
    """Hash compact ledger metadata without importing graph-state projections."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if isinstance(item, str)]
