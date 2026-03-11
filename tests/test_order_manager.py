import pytest
from tradingagents.execution.order_manager import OrderManager
from tradingagents.portfolio.portfolio_tracker import Portfolio


@pytest.mark.asyncio
async def test_order_manager_process_signal_buy():
    # Arrange
    manager = OrderManager(
        risk_params={
            "max_position_size": 1000.0,  # USD max per position
            "default_buy_amount": 100.0,  # USD to spend
        }
    )
    portfolio = Portfolio(
        positions={}, total_value_usd=10000.0, unrealized_pnl=0.0, realized_pnl=0.0
    )

    # Act
    # We want to buy SOL with $100.
    # Suppose WSOL token is So11... and USDC token is EPjFW...
    # The signal must convert $100 USDC to SOL.
    # Let's say the signal says "BUY"
    order = await manager.process_signal(
        signal="BUY",
        token_address="So11111111111111111111111111111111111111112",
        portfolio=portfolio,
        chain="solana",
    )

    # Assert
    assert order is not None
    assert order.action == "buy"
    assert order.token_out == "So11111111111111111111111111111111111111112"
    # EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v is USDC on Solana
    assert order.token_in == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    assert order.amount == 100.0
    assert order.chain == "solana"
