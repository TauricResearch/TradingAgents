from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AutomationSettings:
    watchlist: tuple[str, ...]
    batch_size: int
    analysis_interval_minutes: int
    position_interval_minutes: int
    max_cash_allocation: float
    decision_max_age_minutes: int
    rebalance_threshold_usd: float
    state_path: Path
    auto_execute: bool
    alpaca_mode: str
    live_trading_ack: str

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "AutomationSettings":
        symbols = tuple(symbol.strip().upper() for symbol in str(config["watchlist"]).split(","))
        if not all(symbols) or len(symbols) != 7 or len(set(symbols)) != 7:
            raise ValueError("watchlist must contain exactly 7 unique symbols")

        batch_size = config["batch_size"]
        if batch_size not in (2, 3):
            raise ValueError("batch_size must be 2 or 3")

        alpaca_mode = config["alpaca_mode"]
        if alpaca_mode not in ("paper", "live"):
            raise ValueError("alpaca_mode must be paper or live")

        analysis_interval_minutes = config["analysis_interval_minutes"]
        position_interval_minutes = config["position_interval_minutes"]
        decision_max_age_minutes = config["decision_max_age_minutes"]
        if any(value <= 0 for value in (
            analysis_interval_minutes,
            position_interval_minutes,
            decision_max_age_minutes,
        )):
            raise ValueError("intervals and decision age must be positive")

        max_cash_allocation = config["max_cash_allocation"]
        if not 0 < max_cash_allocation <= 0.30:
            raise ValueError("max_cash_allocation must be greater than 0 and no greater than 0.30")

        rebalance_threshold_usd = config["rebalance_threshold_usd"]
        if rebalance_threshold_usd < 0:
            raise ValueError("rebalance_threshold_usd must be non-negative")

        return cls(
            watchlist=symbols,
            batch_size=batch_size,
            analysis_interval_minutes=analysis_interval_minutes,
            position_interval_minutes=position_interval_minutes,
            max_cash_allocation=max_cash_allocation,
            decision_max_age_minutes=decision_max_age_minutes,
            rebalance_threshold_usd=rebalance_threshold_usd,
            state_path=Path(config["automation_state_path"]),
            auto_execute=config["auto_execute"],
            alpaca_mode=alpaca_mode,
            live_trading_ack=config["live_trading_ack"],
        )


def partition_watchlist(
    symbols: tuple[str, ...], preferred_size: int
) -> tuple[tuple[str, ...], ...]:
    if len(symbols) != 7 or preferred_size not in (2, 3):
        raise ValueError("seven symbols and a preferred batch size of 2 or 3 are required")
    cut_points = (2, 4) if preferred_size == 2 else (3, 5)
    first, second = cut_points
    return (symbols[:first], symbols[first:second], symbols[second:])
