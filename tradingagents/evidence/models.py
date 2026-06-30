"""Pydantic models for runtime evidence tracking."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    source: str
    title: str
    as_of_date: str
    payload: Any
    aliases: list[str] = Field(default_factory=list)
    created_by: str = "deterministic_tool"


class ClaimRecord(BaseModel):
    text: str
    evidence_refs: list[str] = Field(default_factory=list)
    claim_type: str = "generic"


class CitationVerificationResult(BaseModel):
    passed: bool
    cited_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    missing_required: bool = False
    warnings: list[str] = Field(default_factory=list)
