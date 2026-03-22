import pytest
from tradingagents.dataflows.dex.coingecko_provider import get_coin_ohlcv, get_coin_info


@pytest.mark.asyncio
async def test_get_coin_ohlcv_returns_data():
    """Test that get_coin_ohlcv returns OHLCV data for SOL."""
    result = await get_coin_ohlcv("solana", "usd", 7)
    assert " timestamp " in result.lower() or "open" in result.lower()
    assert len(result) > 100


@pytest.mark.asyncio
async def test_get_coin_info_returns_metadata():
    """Test that get_coin_info returns token metadata."""
    result = await get_coin_info("solana")
    assert "solana" in result.lower()
    assert "market_cap" in result.lower() or "$" in result