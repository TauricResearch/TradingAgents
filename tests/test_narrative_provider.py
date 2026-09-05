from datetime import date, datetime, timezone

import pytest

from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.narrative_provider import (
    GeneratedNarrative,
    NarrativeProviderUnavailableError,
    OpenAIResearchNarrativeProvider,
    ResearchNarrativeContext,
    build_narrative_evidence,
)


class FakeStructuredLlm:
    def __init__(self):
        self.schema = None
        self.prompt = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        return GeneratedNarrative(
            headline="Fixture narrative",
            summary="Structured commentary based on fixture data.",
            supporting_points=["Price and news inputs were available."],
            risks=["Fixture risk."],
            confidence="medium",
        )


def _context() -> ResearchNarrativeContext:
    as_of_date = date(2026, 1, 5)
    provenance = DataProvenance(
        provider="fixture",
        as_of_date=as_of_date,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )
    prices = [
        PriceBar(
            symbol="NVDA",
            date=date(2026, 1, 5),
            open=100,
            high=105,
            low=99,
            close=103,
            volume=100,
            currency="USD",
            provenance=provenance,
        )
    ]
    fundamentals = [
        FundamentalSnapshot(
            symbol="NVDA",
            period_end=as_of_date,
            metrics={"market_cap": 1_000_000},
            provenance=provenance,
        )
    ]
    news = [
        NewsItem(
            symbol="NVDA",
            title="Fixture headline",
            published_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            as_of_date=as_of_date,
            provider="fixture-news",
            source_id="fixture-news-1",
        )
    ]
    return ResearchNarrativeContext(
        symbol="NVDA",
        as_of_date=as_of_date,
        price_bars=prices,
        fundamentals=fundamentals,
        news=news,
        evidence=build_narrative_evidence(
            symbol="NVDA",
            as_of_date=as_of_date,
            price_bars=prices,
            fundamentals=fundamentals,
            news=news,
        ),
    )


def test_openai_narrative_provider_converts_structured_response_to_envelope():
    llm = FakeStructuredLlm()
    provider = OpenAIResearchNarrativeProvider(model="fixture-model", llm=llm)

    outputs = provider.generate(_context())

    assert llm.schema is GeneratedNarrative
    assert "Do not recommend a position size or trade direction." in llm.prompt
    assert len(outputs) == 1
    assert outputs[0].agent_id == "openai-research-narrative"
    assert outputs[0].headline == "Fixture narrative"
    assert outputs[0].evidence[0].source_id.startswith("price:NVDA:")
    assert outputs[0].metadata["model"] == "fixture-model"


def test_openai_narrative_provider_requires_explicit_environment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RESEARCH_OPENAI_MODEL", raising=False)

    with pytest.raises(NarrativeProviderUnavailableError, match="OPENAI_API_KEY"):
        OpenAIResearchNarrativeProvider.from_environment()
