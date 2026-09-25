"""Execution adapters. Defaults are dry-run and human-confirmed."""

from .binance_executor import BinanceExecutor
from .paper_trading import PaperTradingLedger

__all__ = ["BinanceExecutor", "PaperTradingLedger"]