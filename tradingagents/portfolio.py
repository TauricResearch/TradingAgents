"""The caller's book, as the decision agents see it.

Optional input to a run: what is held, at what average price, and how much cash
is free. Without it the agents cannot tell adding to a full position from
opening a new one. Three states are distinct and must stay so: a position, a
flat book, and no context at all, since treating "not provided" as "flat" would
invent a fact about the caller's account.

Broker-neutral by construction: quantities are generic units and the currency is
whatever label the caller passes, so nothing here implies a venue or an
execution path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ValidationError


class Position(BaseModel):
    ticker: str = Field(description="Instrument symbol, e.g. AAPL")
    quantity: float = Field(description="Signed units held; negative is short")
    average_price: float | None = Field(default=None, description="Average entry price per unit")


class OptionPosition(BaseModel):
    underlying: str = Field(description="Underlying symbol, e.g. SPY")
    option_type: Literal["call", "put"]
    strike: float
    expiry: date = Field(description="Expiration date, YYYY-MM-DD")
    quantity: float = Field(description="Signed contracts held; negative is written")
    average_price: float | None = Field(default=None, description="Average premium paid per share")
    multiplier: float = Field(default=100, description="Shares per contract")
    mark: float | None = Field(default=None, description="Broker's price per share on mark_date")
    mark_date: date | None = Field(default=None, description="Date the mark was taken")

    def label(self) -> str:
        return (f"{self.underlying.upper()} {self.expiry.isoformat()} "
                f"{self.strike:g} {self.option_type[0].upper()}")


class PortfolioContext(BaseModel):
    cash: float | None = Field(default=None, description="Free cash available")
    currency: str | None = Field(default=None, description="Currency label for cash and prices")
    positions: list[Position] = Field(default_factory=list)
    options: list[OptionPosition] = Field(default_factory=list)

    def position_in(self, ticker: str) -> Position | None:
        return next((p for p in self.positions if p.ticker.upper() == ticker.strip().upper()), None)

    def options_on(self, ticker: str) -> list[OptionPosition]:
        return [o for o in self.options if o.underlying.upper() == ticker.strip().upper()]

    def underlyings(self) -> list[str]:
        """Every instrument the book is exposed to, shares first, in book order."""
        names = [p.ticker.strip().upper() for p in self.positions]
        names += [o.underlying.strip().upper() for o in self.options]
        return list(dict.fromkeys(names))

    def render(self, ticker: str) -> str:
        """The portfolio block for the decision agents, led by the analyzed instrument."""
        symbol = ticker.strip().upper()
        held = self.position_in(symbol)
        if held is None:
            lines = [f"- No current position in {symbol}"]
        else:
            price = f", average price {held.average_price:,.2f}" if held.average_price is not None else ""
            lines = [f"- Current position in {symbol}: {held.quantity:,.4g} units{price}"]
        if self.cash is not None:
            lines.append(f"- Cash available: {self.cash:,.2f}{' ' + self.currency if self.currency else ''}")
        for o in self.options_on(symbol):
            paid = f", paid {o.average_price:,.2f}" if o.average_price is not None else ""
            lines.append(f"- Option on {symbol}: {o.quantity:,.4g} x {o.label()}"
                         f" ({o.multiplier:g} shares each{paid})")
        others = [p for p in self.positions if p is not held]
        if others:
            lines.append("- Other positions: " + ", ".join(f"{p.ticker.upper()} {p.quantity:,.4g}" for p in others))
        other_options = [o for o in self.options if o.underlying.upper() != symbol]
        if other_options:
            lines.append("- Other options: " + ", ".join(f"{o.quantity:,.4g} x {o.label()}" for o in other_options))
        return "Portfolio at the analysis date:\n" + "\n".join(lines)

    def fingerprint(self) -> str:
        """Stable digest of the book, so a changed one cannot resume a stale run."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]


def load_portfolio(path: str | Path) -> PortfolioContext:
    """Read a portfolio JSON file, failing before the run rather than mid-graph."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return PortfolioContext.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"portfolio file {path} is not usable: {exc}") from exc
