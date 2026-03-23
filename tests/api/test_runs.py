import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_create_run_returns_run_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/runs", json={
            "ticker": "NVDA", "date": "2024-05-10"
        })
    assert response.status_code == 200
    assert "id" in response.json()

@pytest.mark.asyncio
async def test_list_runs_empty_initially():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
