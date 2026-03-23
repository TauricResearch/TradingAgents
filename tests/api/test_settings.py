import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_get_settings_returns_defaults():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/settings")
    assert response.status_code == 200
    data = response.json()
    assert "deep_think_llm" in data
    assert "max_debate_rounds" in data

@pytest.mark.asyncio
async def test_put_settings_updates_values():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put("/settings", json={
            "deep_think_llm": "claude-opus-4-6",
            "quick_think_llm": "claude-haiku-4-5-20251001",
            "llm_provider": "anthropic",
            "max_debate_rounds": 2,
            "max_risk_discuss_rounds": 2,
        })
    assert response.status_code == 200
    assert response.json()["deep_think_llm"] == "claude-opus-4-6"
