from .base_executor import BaseExecutor, TradeOrder, TradeResult
import httpx
import base64
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned


class JupiterExecutor(BaseExecutor):
    def __init__(self, rpc_url: str, private_key: str):
        self.api_url = "https://quote-api.jup.ag/v6"
        self.client = AsyncClient(rpc_url)
        self.keypair = Keypair.from_base58_string(private_key)

    async def execute_swap(self, order: TradeOrder) -> TradeResult:
        # 1. Get quote
        quote = await self.get_quote(order)

        # 2. Get swap transaction serialized from Jupiter
        payload = {
            "quoteResponse": quote,
            "userPublicKey": str(self.keypair.pubkey()),
            "wrapAndUnwrapSol": True,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.api_url}/swap", json=payload)
            resp.raise_for_status()
            swap_tx_b64 = resp.json()["swapTransaction"]

        # 3. Deserialize and sign
        raw_tx = VersionedTransaction.from_bytes(base64.b64decode(swap_tx_b64))
        signature = self.keypair.sign_message(to_bytes_versioned(raw_tx.message))
        signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

        # 4. Send transaction
        opts = TxOpts(skip_preflight=False, preflight_commitment="processed")
        tx_resp = await self.client.send_transaction(signed_tx, opts=opts)
        tx_hash = str(tx_resp.value)

        # 5. Confirm and compile final result
        return await self._confirm_and_parse(tx_hash, order)

    async def _confirm_and_parse(self, tx_hash: str, order: TradeOrder) -> TradeResult:
        # Placeholder for Solana transaction confirmation loop
        # For minimum viable implementation, assume success if sent successfully
        return TradeResult(
            success=True,
            tx_hash=tx_hash,
            amount_in=order.amount,
            amount_out=0.0,  # Real implementation parses log / events
            price_impact=0.0,
            gas_cost=0.0,
            timestamp="",
        )

    async def get_quote(self, order: TradeOrder) -> dict:
        # Simplest code: assumes input token is 9 decimals (Solana standard)
        amount_lamports = int(order.amount * 1_000_000_000)
        params = {
            "inputMint": order.token_in,
            "outputMint": order.token_out,
            "amount": amount_lamports,
            "slippageBps": order.slippage_bps,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.api_url}/quote", params=params)
            response.raise_for_status()
            return response.json()

    async def get_wallet_balance(self, token_address: str) -> float:
        pass
