import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from tradingagents.execution.base_executor import TradeOrder
from tradingagents.execution.oneinch_executor import OneInchExecutor


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
async def test_oneinch_get_quote_returns_valid_route(mock_async_client_class):
    # Arrange
    executor = OneInchExecutor(
        "https://ethereum-rpc.publicnode.com",
        "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        1,
    )
    order = TradeOrder(
        action="buy",
        token_in="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        token_out="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        amount=100.0,  # 100 USDC
        slippage_bps=50,
        chain="ethereum",
    )

    # Setup mock
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"dstAmount": "50000000000000000"}  # 0.05 WETH
    mock_client.get.return_value = mock_response
    mock_async_client_class.return_value.__aenter__.return_value = mock_client

    # Act
    quote = await executor.get_quote(order)

    # Assert
    assert quote is not None
    assert "dstAmount" in quote

    # Verify the mock was called with correct parameters
    mock_client.get.assert_called_once()
    called_url, kwargs = mock_client.get.call_args
    assert "https://api.1inch.dev/swap/v6.0/1/quote" in called_url[0]
    assert kwargs["params"]["src"] == order.token_in
    assert kwargs["params"]["dst"] == order.token_out


@pytest.mark.asyncio
@patch("httpx.AsyncClient")
@patch("web3.eth.async_eth.AsyncEth.send_raw_transaction")
async def test_oneinch_execute_swap_returns_success(
    mock_send_raw, mock_async_client_class
):
    # Arrange
    executor = OneInchExecutor(
        "https://ethereum-rpc.publicnode.com",
        "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        1,
    )
    order = TradeOrder(
        action="buy",
        token_in="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        token_out="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
        amount=100.0,  # 100 USDC
        slippage_bps=50,
        chain="ethereum",
    )

    # Setup API Mocks
    mock_client = AsyncMock()
    mock_quote_response = MagicMock()
    mock_quote_response.json.return_value = {
        "dstAmount": "50000000000000000"
    }  # mock quote

    mock_swap_response = MagicMock()
    # 1inch V6 API returns 'tx' with transaction data
    mock_swap_response.json.return_value = {
        "tx": {
            "from": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
            "to": "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3 router example
            "data": "0xabcdef",
            "value": "0",
            "gas": 100000,
            "gasPrice": "20000000000",
        }
    }

    # Side effect to return different responses for /quote and /swap
    async def mock_get(url, **kwargs):
        if "quote" in url:
            return mock_quote_response
        if "swap" in url:
            return mock_swap_response

    mock_client.get.side_effect = mock_get
    mock_async_client_class.return_value.__aenter__.return_value = mock_client

    # Setup Web3 RPC Mock
    mock_send_raw.return_value = b"mock_tx_hash_123"

    # Act
    # We patch executor._confirm_and_parse since we don't need to test EVM confirmation loop here
    with patch.object(
        executor, "_confirm_and_parse", new_callable=AsyncMock
    ) as mock_confirm:
        from tradingagents.execution.base_executor import TradeResult

        mock_confirm.return_value = TradeResult(
            success=True,
            tx_hash="0xmock_tx_hash_123",
            amount_in=100.0,
            amount_out=0.05,
            price_impact=0.1,
            gas_cost=0.005,
            timestamp="2024-01-01",
        )
        # Mock web3 transaction count & signing
        with patch.object(
            executor.w3.eth, "get_transaction_count", new_callable=AsyncMock
        ) as mock_tc:
            mock_tc.return_value = 1
            with patch.object(executor.account, "sign_transaction") as mock_sign:
                mock_sign.return_value = MagicMock(raw_transaction=b"mock_raw_bytes")
                result = await executor.execute_swap(order)

    # Assert
    assert result.success is True
    assert result.tx_hash == "0xmock_tx_hash_123"
    assert result.amount_in == 100.0
    assert result.amount_out == 0.05
    # 1 call for swap directly builds the tx
    assert mock_client.get.call_count == 1
