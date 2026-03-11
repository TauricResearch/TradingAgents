from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeOrder:
    action: str  # "buy" | "sell"
    token_in: str  # Contract address of the token being sold
    token_out: str  # Contract address of the token being bought
    amount: float
    slippage_bps: int  # Basis points (e.g., 50 = 0.5%)
    chain: str
    priority_fee: Optional[int] = None  # Lamports (Solana) or Gwei (EVM)


@dataclass
class TradeResult:
    success: bool
    tx_hash: str
    amount_in: float
    amount_out: float
    price_impact: float
    gas_cost: float
    timestamp: str
    error_message: Optional[str] = None


class BaseExecutor(ABC):
    @abstractmethod
    async def execute_swap(self, order: TradeOrder) -> TradeResult:
        pass

    @abstractmethod
    async def get_quote(self, order: TradeOrder) -> dict:
        pass

    @abstractmethod
    async def get_wallet_balance(self, token_address: str) -> float:
        pass
