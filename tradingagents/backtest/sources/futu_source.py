"""Futu OpenD ``PriceSource`` — stub."""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, Resolution


class FutuSource:
    name = "futu"
    supports: Set[Resolution] = {Resolution.DAILY}

    def get_bars(self, ticker: str, start: date, end: date,
                 resolution: Resolution) -> Bars:
        raise NotImplementedError(
            "FutuSource is a stub in F2."
        )
