"""Polygon ``PriceSource`` — stub. Replace with a real implementation when
Polygon API access is wired up."""

from __future__ import annotations

from datetime import date
from typing import Set

from tradingagents.backtest.prices import Bars, Resolution


class PolygonSource:
    name = "polygon"
    supports: Set[Resolution] = {Resolution.DAILY}  # advertise; raise on call

    def get_bars(self, ticker: str, start: date, end: date,
                 resolution: Resolution) -> Bars:
        raise NotImplementedError(
            "PolygonSource is a stub in F2. Register a real adapter when "
            "Polygon API access is wired up; see "
            "docs/superpowers/specs/2026-05-26-iic-forge-05-f2-backtest-benchmark-design.md D7."
        )
