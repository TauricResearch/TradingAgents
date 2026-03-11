import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from tradingagents.dataflows.google_search_tools import (
    GoogleSearchClient,
    QuotaExceededError,
)


@pytest.mark.asyncio
async def test_quota_manager_allows_within_limit():
    """Deve permitir queries dentro do limite diário."""
    client = GoogleSearchClient(api_key="test_key", cx="test_cx", daily_limit=5)

    with patch("httpx.AsyncClient") as mock_http:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {
                    "title": "Result",
                    "link": "http://example.com",
                    "snippet": "A snippet",
                }
            ]
        }
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )

        result = await client.search("solana price")
        assert result is not None
        assert len(result) > 0
        assert client.quota_manager.usage_today == 1


@pytest.mark.asyncio
async def test_quota_manager_blocks_over_limit():
    """Deve bloquear quando o limite diário é atingido."""
    client = GoogleSearchClient(api_key="test_key", cx="test_cx", daily_limit=2)
    client.quota_manager.usage_today = 2  # Simulate already at limit

    with pytest.raises(QuotaExceededError):
        await client.search("solana price")


@pytest.mark.asyncio
async def test_quota_manager_resets_next_day():
    """Deve resetar o contador no próximo dia."""
    from datetime import date, timedelta

    client = GoogleSearchClient(api_key="test_key", cx="test_cx", daily_limit=5)
    # Simulate yesterday's usage
    client.quota_manager.usage_today = 5
    client.quota_manager.last_reset = date.today() - timedelta(days=1)

    # After reset, should allow new queries
    with patch("httpx.AsyncClient") as mock_http:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"title": "R", "link": "http://x.com", "snippet": "s"}]
        }
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )

        await client.search("bitcoin news")
        assert client.quota_manager.usage_today == 1  # Reset + 1 used


@pytest.mark.asyncio
async def test_quota_manager_warns_near_limit():
    """Deve retornar aviso quando próximo ao limite."""
    client = GoogleSearchClient(
        api_key="test_key", cx="test_cx", daily_limit=10, warn_threshold=0.8
    )
    client.quota_manager.usage_today = 8  # 80% used

    with patch("httpx.AsyncClient") as mock_http:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [{"title": "R", "link": "http://x.com", "snippet": "s"}]
        }
        mock_http.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_resp
        )

        await client.search("ethereum news")
        # Should still work, but usage should be visible
        assert client.quota_manager.is_near_limit() is True
        assert client.quota_manager.usage_today == 9
