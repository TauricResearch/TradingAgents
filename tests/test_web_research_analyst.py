import pytest
from unittest.mock import AsyncMock, patch
from tradingagents.agents.analysts.web_research_analyst import (
    WebResearchAnalyst,
    ResearchReport,
)
from tradingagents.dataflows.google_search_tools import (
    GoogleSearchClient,
    QuotaExceededError,
    SearchResult,
)


def _make_client(daily_limit=95) -> GoogleSearchClient:
    return GoogleSearchClient(api_key="test_key", cx="test_cx", daily_limit=daily_limit)


@pytest.mark.asyncio
async def test_research_token_returns_report():
    """Deve retornar um ResearchReport com todas as categorias preenchidas."""
    client = _make_client()
    analyst = WebResearchAnalyst(search_client=client)

    mock_results = [
        SearchResult(title="Test", link="http://x.com", snippet="A snippet")
    ]

    with patch.object(client, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        report = await analyst.research_token("Solana")

    assert isinstance(report, ResearchReport)
    assert report.token_name == "Solana"
    assert len(report.security_findings) > 0
    assert len(report.news_findings) > 0
    assert mock_search.call_count == 4  # security + news + analytics + sentiment


@pytest.mark.asyncio
async def test_research_token_partial_on_quota_exceeded():
    """Deve retornar resultados parciais quando quota esgota no meio da pesquisa."""
    client = _make_client(daily_limit=2)
    client.quota_manager.usage_today = 1  # 1 query remaining
    analyst = WebResearchAnalyst(search_client=client)

    mock_results = [SearchResult(title="T", link="http://x.com", snippet="s")]

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise QuotaExceededError(2, 2)
        return mock_results

    with patch.object(client, "search", side_effect=side_effect):
        report = await analyst.research_token("BONK")

    # First category (security) succeeds, rest are empty
    assert len(report.security_findings) > 0
    assert len(report.news_findings) == 0
    assert len(report.analytics_findings) == 0


@pytest.mark.asyncio
async def test_research_report_to_text():
    """Deve gerar texto legível por LLM."""
    client = _make_client()
    analyst = WebResearchAnalyst(search_client=client)

    mock_results = [
        SearchResult(
            title="Solana DeFi",
            link="http://defillama.com/solana",
            snippet="TVL rising",
        )
    ]

    with patch.object(client, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        report = await analyst.research_token("Solana")

    text = report.to_text()
    assert "Solana" in text
    assert "Segurança" in text
    assert "Notícias" in text
    assert "Quota Google Search" in text
