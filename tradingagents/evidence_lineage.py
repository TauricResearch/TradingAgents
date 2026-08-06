"""Canonical, content-bound identifiers for collected evidence.

The collector, store, selector, and independent verifier use these helpers to
name both a provider identity and the exact point-in-time snapshot received for
that identity without copying full payload text into a fetch receipt.
"""

from __future__ import annotations

import hashlib

from tradingagents.research_protocol import content_id


def _text_sha256(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def evidence_id(row: dict) -> str:
    """Identify a provider item independently of mutable capture metadata."""
    return content_id(
        {"source": row.get("source"), "external_id": row.get("external_id")},
        prefix="evidence_",
    )


def raw_content_id(row: dict) -> str:
    """Identify the exact candidate snapshot observed by one fetch."""
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return content_id(
        {
            "source": row.get("source"),
            "external_id": row.get("external_id"),
            "published_utc": row.get("created_utc"),
            "publisher_or_author": row.get("author") or row.get("publisher_or_author"),
            "publisher_domain": metadata.get("publisher_domain")
            or row.get("publisher_domain"),
            "article_url": metadata.get("article_url") or row.get("article_url"),
            "title_sha256": _text_sha256(row.get("title") or ""),
            "text_sha256": _text_sha256(row.get("body") or row.get("text") or ""),
            "verified_type": metadata.get("verified_type"),
            "evidence_role": metadata.get("evidence_role"),
            "author_id": metadata.get("author_id"),
            "account_created_utc": metadata.get("account_created_utc"),
            "automation_signals_complete": metadata.get(
                "automation_signals_complete"
            ),
            "automation_risk": metadata.get("automation_risk"),
            "engagement": metadata.get("engagement"),
            "author_metrics": metadata.get("author_metrics"),
        },
        prefix="raw_",
    )


__all__ = ["evidence_id", "raw_content_id"]
