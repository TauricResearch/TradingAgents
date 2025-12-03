from dataclasses import dataclass, field
from typing import List, Optional
from pydantic import BaseModel, Field as PydanticField

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.discovery.models import NewsArticle, EventCategory


BATCH_SIZE = 10


@dataclass
class EntityMention:
    company_name: str
    confidence: float
    context_snippet: str
    article_id: str
    event_type: EventCategory
    sentiment: float = field(default=0.0)


class ExtractedEntity(BaseModel):
    company_name: str = PydanticField(description="The name of the publicly traded company mentioned")
    confidence: float = PydanticField(description="Confidence score from 0.0 to 1.0 based on mention clarity")
    context_snippet: str = PydanticField(description="Surrounding context of 50-100 characters around the company mention")
    event_type: str = PydanticField(description="Event category: earnings, merger_acquisition, regulatory, product_launch, executive_change, or other")
    sentiment: float = PydanticField(default=0.0, description="Sentiment score from -1.0 (negative) to 1.0 (positive)")


class ExtractionResponse(BaseModel):
    entities: List[ExtractedEntity] = PydanticField(default_factory=list, description="List of extracted company entities")


def _get_llm(config: Optional[dict] = None):
    cfg = config or DEFAULT_CONFIG
    provider = cfg.get("llm_provider", "openai").lower()
    model = cfg.get("quick_think_llm", "gpt-4o-mini")
    backend_url = cfg.get("backend_url", "https://api.openai.com/v1")

    if provider in ("openai", "ollama", "openrouter"):
        return ChatOpenAI(model=model, base_url=backend_url)
    elif provider == "anthropic":
        return ChatAnthropic(model=model, base_url=backend_url)
    elif provider == "google":
        return ChatGoogleGenerativeAI(model=model)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


EXTRACTION_PROMPT = """You are an expert at identifying publicly traded companies mentioned in news articles.

For each article provided, extract all mentions of publicly traded companies. For each company mention:

1. Extract the company name as it appears (e.g., "Apple Inc.", "Apple", "AAPL", "the iPhone maker")
2. Assign a confidence score from 0.0 to 1.0 based on how clearly the company is mentioned:
   - 0.9-1.0: Direct company name or ticker symbol
   - 0.7-0.9: Clear reference with context (e.g., "the Cupertino tech giant")
   - 0.5-0.7: Indirect reference requiring inference
   - Below 0.5: Uncertain or ambiguous reference
3. Extract 50-100 characters of surrounding context
4. Classify the event type:
   - earnings: Quarterly/annual earnings reports, revenue announcements
   - merger_acquisition: Mergers, acquisitions, buyouts, takeovers
   - regulatory: SEC filings, government investigations, compliance issues
   - product_launch: New products, services, or features
   - executive_change: CEO/CFO changes, board appointments, departures
   - other: Any other business news
5. Assign a sentiment score from -1.0 to 1.0:
   - -1.0: Very negative news (lawsuits, crashes, major failures)
   - -0.5: Moderately negative news
   - 0.0: Neutral news
   - 0.5: Moderately positive news
   - 1.0: Very positive news (breakthroughs, record earnings)

Only extract companies that are publicly traded on major stock exchanges.
Handle name variations by providing the most complete company name found.

Articles to analyze:
{articles_text}

Extract all company mentions from the articles above."""


def _format_articles_for_prompt(articles: List[NewsArticle], start_idx: int) -> str:
    formatted = []
    for i, article in enumerate(articles):
        article_id = f"article_{start_idx + i}"
        formatted.append(
            f"[{article_id}]\n"
            f"Title: {article.title}\n"
            f"Source: {article.source}\n"
            f"Content: {article.content_snippet}\n"
        )
    return "\n---\n".join(formatted)


def _extract_batch(
    articles: List[NewsArticle],
    start_idx: int,
    llm,
) -> List[EntityMention]:
    if not articles:
        return []

    articles_text = _format_articles_for_prompt(articles, start_idx)
    prompt = EXTRACTION_PROMPT.format(articles_text=articles_text)

    structured_llm = llm.with_structured_output(ExtractionResponse)
    response = structured_llm.invoke(prompt)

    mentions = []
    for entity in response.entities:
        event_type_str = entity.event_type.lower().strip()
        valid_event_types = {e.value for e in EventCategory}
        if event_type_str not in valid_event_types:
            event_type_str = "other"

        confidence = max(0.0, min(1.0, entity.confidence))
        sentiment = max(-1.0, min(1.0, entity.sentiment))

        context = entity.context_snippet
        if len(context) > 150:
            context = context[:147] + "..."

        mention = EntityMention(
            company_name=entity.company_name,
            confidence=confidence,
            context_snippet=context,
            article_id=f"article_{start_idx}",
            event_type=EventCategory(event_type_str),
            sentiment=sentiment,
        )
        mentions.append(mention)

    return mentions


def extract_entities(
    articles: List[NewsArticle],
    config: Optional[dict] = None,
) -> List[EntityMention]:
    if not articles:
        return []

    llm = _get_llm(config)
    all_mentions: List[EntityMention] = []

    for batch_start in range(0, len(articles), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(articles))
        batch = articles[batch_start:batch_end]

        batch_mentions = _extract_batch(batch, batch_start, llm)
        all_mentions.extend(batch_mentions)

    return all_mentions
