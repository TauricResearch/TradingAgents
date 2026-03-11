from tradingagents.execution.base_executor import TradeOrder
from tradingagents.portfolio.portfolio_tracker import Portfolio


class OrderManager:
    """Converte sinais dos agentes em ordens executáveis com base no risco."""

    def __init__(self, risk_params: dict):
        self.risk_params = risk_params
        # Defaults
        self.max_position_size = self.risk_params.get("max_position_size", 1000.0)
        self.default_buy_amount = self.risk_params.get("default_buy_amount", 100.0)

    async def process_signal(
        self, signal: str, token_address: str, portfolio: Portfolio, chain: str
    ) -> TradeOrder | None:
        """
        Processes a string signal (e.g. "BUY", "SELL", "HOLD") and translates
        it into a well-formed TradeOrder, applying limits.
        """
        signal_upper = signal.upper()

        if signal_upper == "HOLD":
            return None

        # Determine stables depending on chain
        # Simple hardcoded stables for the mvp
        stable_address = (
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            if chain == "solana"
            else "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        )

        if signal_upper == "BUY":
            # Check current position size
            current_pos = portfolio.positions.get(token_address)
            current_value = current_pos.value_usd if current_pos else 0.0

            # If already at max, reject
            if current_value >= self.max_position_size:
                return None

            # Calculate how much to buy
            amount_to_buy = self.default_buy_amount
            # Cap by max position
            if current_value + amount_to_buy > self.max_position_size:
                amount_to_buy = self.max_position_size - current_value

            return TradeOrder(
                action="buy",
                token_in=stable_address,
                token_out=token_address,
                amount=amount_to_buy,
                slippage_bps=50,  # 0.5% default
                chain=chain,
            )

        elif signal_upper == "SELL":
            # Check if we have it
            current_pos = portfolio.positions.get(token_address)
            if not current_pos or current_pos.balance <= 0:
                return None

            # Simple sell all
            return TradeOrder(
                action="sell",
                token_in=token_address,
                token_out=stable_address,
                amount=current_pos.balance,
                slippage_bps=50,
                chain=chain,
            )

        return None
