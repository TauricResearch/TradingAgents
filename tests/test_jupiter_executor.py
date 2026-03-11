import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from tradingagents.execution.base_executor import TradeOrder
from tradingagents.execution.jupiter_executor import JupiterExecutor


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
@patch("solders.keypair.Keypair.from_base58_string")
async def test_jupiter_get_quote_returns_valid_route(
    mock_keypair_from_base58, mock_async_client_class
):
    # Arrange
    executor = JupiterExecutor("https://api.mainnet-beta.solana.com", "mock_pk")
    order = TradeOrder(
        action="buy",
        token_in="So11111111111111111111111111111111111111112",  # WSOL
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        amount=0.01,  # 0.01 SOL
        slippage_bps=50,
        chain="solana",
    )

    # Setup mock
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "inputMint": order.token_in,
        "outputMint": order.token_out,
        "outAmount": "1000000",
    }
    mock_client.get.return_value = mock_response
    mock_async_client_class.return_value.__aenter__.return_value = mock_client

    # Act
    quote = await executor.get_quote(order)

    # Assert
    assert quote is not None
    assert "inputMint" in quote
    assert "outputMint" in quote
    assert "outAmount" in quote
    assert quote["inputMint"] == order.token_in
    assert quote["outputMint"] == order.token_out

    # Verify the mock was called with correct math
    mock_client.get.assert_called_once()
    called_url, kwargs = mock_client.get.call_args
    assert kwargs["params"]["amount"] == 10000000  # 0.01 * 1e9


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
@patch("solana.rpc.async_api.AsyncClient.send_transaction")
@patch("solders.keypair.Keypair.from_base58_string")
@patch("tradingagents.execution.jupiter_executor.VersionedTransaction")
@patch("tradingagents.execution.jupiter_executor.to_bytes_versioned")
async def test_jupiter_execute_swap_returns_success(
    mock_to_bytes,
    mock_versioned_tx,
    mock_keypair_from_base58,
    mock_send_tx,
    mock_async_client_class,
):
    # Arrange
    executor = JupiterExecutor("https://api.mainnet-beta.solana.com", "mock_pk")

    # Mock PUBKEY since we cast str(self.keypair.pubkey())
    mock_keypair_instance = MagicMock()
    mock_keypair_instance.pubkey.return_value = "mock_pubkey_123"
    mock_keypair_from_base58.return_value = mock_keypair_instance

    # Mock VersionedTransaction and to_bytes_versioned to bypass parsing
    mock_raw_tx = MagicMock()
    mock_raw_tx.message = "mock_message"
    mock_versioned_tx.from_bytes.return_value = mock_raw_tx
    mock_versioned_tx.populate.return_value = "mock_signed_tx"
    mock_to_bytes.return_value = b"mock_bytes"

    order = TradeOrder(
        action="buy",
        token_in="So11111111111111111111111111111111111111112",
        token_out="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount=0.01,
        slippage_bps=50,
        chain="solana",
    )

    # Setup Jupiter API Mocks
    mock_client = AsyncMock()
    mock_quote_response = MagicMock()
    mock_quote_response.json.return_value = {"outAmount": "1000000"}  # mock quote

    mock_swap_response = MagicMock()
    # A base64 encoded empty compiled transaction (just a placeholder)
    mock_swap_response.json.return_value = {
        "swapTransaction": "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAA=="
    }

    # Side effect to return different responses for /quote and /swap
    async def mock_get(url, **kwargs):
        if "quote" in url:
            return mock_quote_response

    async def mock_post(url, **kwargs):
        if "swap" in url:
            return mock_swap_response

    mock_client.get.side_effect = mock_get
    mock_client.post.side_effect = mock_post
    mock_async_client_class.return_value.__aenter__.return_value = mock_client

    # Setup Solana RPC Mock

    mock_send_tx.return_value = MagicMock(value="mock_sig_123")

    # Act
    # We patch executor._confirm_and_parse since we don't need to test Solana confirmation loop here
    with patch.object(
        executor, "_confirm_and_parse", new_callable=AsyncMock
    ) as mock_confirm:
        from tradingagents.execution.base_executor import TradeResult

        mock_confirm.return_value = TradeResult(
            success=True,
            tx_hash="mock_sig_123",
            amount_in=0.01,
            amount_out=1.0,
            price_impact=0.1,
            gas_cost=0.00001,
            timestamp="2024-01-01",
        )
        result = await executor.execute_swap(order)

    # Assert
    assert result.success is True
    assert result.tx_hash == "mock_sig_123"
    assert result.amount_in == 0.01
    assert result.amount_out == 1.0
    mock_client.post.assert_called_once()  # Called /swap
