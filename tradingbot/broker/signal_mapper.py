"""Maps 5-tier agent signals to concrete order instructions."""

from dataclasses import dataclass
from typing import Optional

from .base import OrderSide


@dataclass
class OrderInstruction:
    should_trade: bool
    side: Optional[OrderSide]
    # Fraction of available portfolio cash to allocate (0.0–1.0).
    # For SELL signals this is the fraction of the existing position to exit.
    # 1.0 on a SELL means close the entire position.
    allocation_fraction: float
    reason: str


class SignalMapper:
    """
    Translates the Portfolio Manager's 5-tier rating into OrderInstruction.

    Position sizing is intentionally conservative by default:
      - BUY       → allocate full_pct of portfolio cash (default 5 %)
      - OVERWEIGHT→ allocate partial_pct of portfolio cash (default 3 %)
      - HOLD      → no action
      - UNDERWEIGHT → sell partial_pct of existing position (default 50 %)
      - SELL      → close 100 % of existing position

    These defaults keep individual positions small and let the risk gate
    enforce portfolio-level caps on top.
    """

    VALID_SIGNALS = {"BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL"}

    def __init__(
        self,
        full_position_pct: float = 0.05,
        partial_position_pct: float = 0.03,
        partial_exit_pct: float = 0.50,
    ):
        """
        Args:
            full_position_pct:    Cash fraction for a full BUY (0–1).
            partial_position_pct: Cash fraction for an OVERWEIGHT BUY (0–1).
            partial_exit_pct:     Position fraction to sell on UNDERWEIGHT (0–1).
        """
        self.full_position_pct = full_position_pct
        self.partial_position_pct = partial_position_pct
        self.partial_exit_pct = partial_exit_pct

    def map(self, signal: str) -> OrderInstruction:
        """
        Convert a raw signal string to an OrderInstruction.

        Accepts any casing; strips surrounding whitespace.
        Unknown signals are treated as HOLD to fail safe.
        """
        normalized = signal.strip().upper()

        if normalized == "BUY":
            return OrderInstruction(
                should_trade=True,
                side=OrderSide.BUY,
                allocation_fraction=self.full_position_pct,
                reason="Strong buy — allocating full position",
            )
        if normalized == "OVERWEIGHT":
            return OrderInstruction(
                should_trade=True,
                side=OrderSide.BUY,
                allocation_fraction=self.partial_position_pct,
                reason="Moderate buy — allocating partial position",
            )
        if normalized == "HOLD":
            return OrderInstruction(
                should_trade=False,
                side=None,
                allocation_fraction=0.0,
                reason="Hold — no action taken",
            )
        if normalized == "UNDERWEIGHT":
            return OrderInstruction(
                should_trade=True,
                side=OrderSide.SELL,
                allocation_fraction=self.partial_exit_pct,
                reason=f"Reduce position — selling {self.partial_exit_pct:.0%} of holding",
            )
        if normalized == "SELL":
            return OrderInstruction(
                should_trade=True,
                side=OrderSide.SELL,
                allocation_fraction=1.0,
                reason="Strong sell — closing entire position",
            )

        # Unknown signal: fail safe, no trade
        return OrderInstruction(
            should_trade=False,
            side=None,
            allocation_fraction=0.0,
            reason=f"Unrecognised signal '{signal}' — skipping",
        )

    def compute_buy_qty(
        self,
        instruction: OrderInstruction,
        available_cash: float,
        price: float,
    ) -> float:
        """
        Calculate how many shares to buy given available cash and current price.

        Returns 0.0 if the instruction is not a BUY or price <= 0.
        """
        if not instruction.should_trade or instruction.side != OrderSide.BUY:
            return 0.0
        if price <= 0:
            return 0.0
        dollar_amount = available_cash * instruction.allocation_fraction
        return dollar_amount / price

    def compute_sell_qty(
        self,
        instruction: OrderInstruction,
        held_qty: float,
    ) -> float:
        """
        Calculate how many shares to sell from an existing position.

        Returns 0.0 if the instruction is not a SELL.
        """
        if not instruction.should_trade or instruction.side != OrderSide.SELL:
            return 0.0
        return held_qty * instruction.allocation_fraction
