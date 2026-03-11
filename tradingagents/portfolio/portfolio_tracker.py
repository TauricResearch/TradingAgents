from dataclasses import dataclass


@dataclass
class PositionInfo:
    token_address: str
    symbol: str
    balance: float
    avg_entry_price: float
    current_price: float
    value_usd: float
    pnl_percent: float


@dataclass
class Portfolio:
    positions: dict[str, PositionInfo]
    total_value_usd: float
    unrealized_pnl: float
    realized_pnl: float


class PortfolioTracker:
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

    async def get_portfolio_state(self, wallet: str, chain: str) -> Portfolio:
        balances = await self._fetch_token_balances(wallet, chain)
        prices = await self._fetch_token_prices(list(balances.keys()), chain)

        positions = {}
        total_usd = 0.0

        for token, bal in balances.items():
            price = prices.get(token, 0.0)
            value = bal * price
            total_usd += value

            positions[token] = PositionInfo(
                token_address=token,
                symbol="UNKNOWN",  # Requires metadata fetcher for real symbols
                balance=bal,
                avg_entry_price=price,  # Placeholder for real execution tracker
                current_price=price,
                value_usd=value,
                pnl_percent=0.0,
            )

        return Portfolio(
            positions=positions,
            total_value_usd=total_usd,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
        )

    async def _fetch_token_balances(self, wallet: str, chain: str) -> dict[str, float]:
        # Real implementation would call Solana RPC / Web3
        return {}

    async def _fetch_token_prices(
        self, tokens: list[str], chain: str
    ) -> dict[str, float]:
        # Real implementation would call Pyth / Birdeye / CoinGecko
        return {}
