import pytest
from unittest.mock import patch, AsyncMock
from tradingagents.portfolio.portfolio_tracker import (
    PortfolioTracker,
    Portfolio,
    PositionInfo,
)


@pytest.mark.asyncio
async def test_get_portfolio_state_returns_portfolio():
    # Arrange
    tracker = PortfolioTracker(rpc_url="https://api.mainnet-beta.solana.com")
    wallet = "5MaiiCavjCmn9Hs1o3eznqx5EpG18Z8Z3v3XEQ3B3T8T4xQ3M3M3M3M3M3M3M3M3M3M3M3M3"

    # Act
    # We will mock the internal fetchings to just return a dummy portfolio state
    with patch.object(
        tracker, "_fetch_token_balances", new_callable=AsyncMock
    ) as mock_balances:
        mock_balances.return_value = {
            "So11111111111111111111111111111111111111112": 10.5
        }

        with patch.object(
            tracker, "_fetch_token_prices", new_callable=AsyncMock
        ) as mock_prices:
            mock_prices.return_value = {
                "So11111111111111111111111111111111111111112": 150.0
            }

            portfolio = await tracker.get_portfolio_state(wallet, "solana")

    # Assert
    assert isinstance(portfolio, Portfolio)
    assert portfolio.total_value_usd == 1575.0  # 10.5 * 150.0
    assert "So11111111111111111111111111111111111111112" in portfolio.positions
    pos = portfolio.positions["So11111111111111111111111111111111111111112"]
    assert isinstance(pos, PositionInfo)
    assert pos.balance == 10.5
    assert pos.current_price == 150.0
    assert pos.value_usd == 1575.0
