from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tradingagents_service.db.repository import PrecedentCreate, ShadowRunRepository


@pytest.mark.unit
def test_deterministic_precedent_embedding_and_similarity_ranking() -> None:
    bullish_source = "NVDA data center revenue accelerated with stronger gross margin."
    unrelated_source = "Bank credit losses widened after deposit costs increased."

    query_embedding = ShadowRunRepository.build_precedent_embedding(
        "NVDA gross margin and data center revenue strength"
    )
    repeat_embedding = ShadowRunRepository.build_precedent_embedding(
        "NVDA gross margin and data center revenue strength"
    )

    assert query_embedding == repeat_embedding
    assert len(query_embedding) == ShadowRunRepository.PRECEDENT_EMBEDDING_DIMENSIONS

    ranked = ShadowRunRepository.rank_precedents_by_similarity(
        [
            SimpleNamespace(
                run_id=uuid4(),
                id=uuid4(),
                ticker="JPM",
                trade_date=date(2026, 1, 10),
                content_text=unrelated_source,
                content_hash=ShadowRunRepository.build_content_hash(unrelated_source),
                embedding_json={"vector": ShadowRunRepository.build_precedent_embedding(unrelated_source)},
                embedding_model="hashed-bow-v1",
                metadata_json={},
            ),
            SimpleNamespace(
                run_id=uuid4(),
                id=uuid4(),
                ticker="NVDA",
                trade_date=date(2026, 1, 15),
                content_text=bullish_source,
                content_hash=ShadowRunRepository.build_content_hash(bullish_source),
                embedding_json={"vector": ShadowRunRepository.build_precedent_embedding(bullish_source)},
                embedding_model="hashed-bow-v1",
                metadata_json={},
            ),
        ],
        query_embedding=query_embedding,
        metric="cosine",
        limit=1,
    )

    assert ranked[0].ticker == "NVDA"
    assert ranked[0].similarity > 0


@pytest.mark.unit
def test_precedent_create_normalizes_metadata_and_hash() -> None:
    payload = PrecedentCreate(
        run_id=uuid4(),
        ticker="nvda",
        trade_date=date(2026, 1, 15),
        selected_analysts=["news", "market", "news"],
        source_text="Final decision: Buy NVDA on margin strength.",
        provider="ollama",
        model="llama3:latest",
    )

    assert payload.ticker == "NVDA"
    assert payload.selected_analysts == ["market", "news"]
    assert payload.content_hash == ShadowRunRepository.build_content_hash(payload.source_text)
    assert payload.embedding == ShadowRunRepository.build_precedent_embedding(payload.source_text)
