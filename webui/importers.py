"""Reading a broker's positions export into a :class:`PortfolioContext`.

Written against Schwab's "Positions" CSV, which is the shape most retail
exports share: a preamble line or two before the real header, dollar amounts
written for a person (``"$1,234.56"``), placeholder dashes for fields that do
not apply, and summary rows mixed in with the holdings. Fidelity's and
Vanguard's exports differ mainly in column names, so the column lookup goes
through a synonym table rather than fixed positions, and those files parse too.

Nothing here guesses at a position it cannot read. A row that does not yield a
symbol and a quantity is skipped and named in the result, so the UI can show
what was dropped instead of silently importing a short book. That matters most
for options and for Schwab's multi-leg rows, which carry a quantity but no
ticker the data layer could price.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from tradingagents.portfolio import PortfolioContext, Position

# Header synonyms, lower-cased. A broker names the same column differently;
# the first one present in the file wins.
_SYMBOL_COLUMNS = ("symbol", "ticker", "instrument", "security id")
_QUANTITY_COLUMNS = ("quantity", "qty", "shares", "quantity owned", "share quantity")
_AVG_PRICE_COLUMNS = (
    "average cost", "average cost basis", "average price", "avg cost", "avg price",
    "cost per share", "average cost per share", "last price",
)
_COST_BASIS_COLUMNS = ("cost basis", "total cost", "cost basis total")
_MARKET_VALUE_COLUMNS = ("market value", "current value", "value", "mkt val (market value)")
_TYPE_COLUMNS = ("security type", "type", "asset class", "security description")

# Rows that summarise rather than hold: Schwab's cash line and account totals,
# Fidelity's pending-activity line, and the disclaimer footers both append.
_CASH_ROW = re.compile(r"cash\s*(&|and)?\s*(cash)?\s*(investments|equivalents|core|sweep)?$|^cash$",
                       re.IGNORECASE)
_TOTAL_ROW = re.compile(r"^(account\s+total|total|grand\s+total|subtotal)", re.IGNORECASE)
_SKIP_ROW = re.compile(r"pending activity|^--$|^$", re.IGNORECASE)

# An options symbol as Schwab and Fidelity write it: an underlying, an
# expiry, a strike and a C/P. The data layer prices equities and crypto, not
# contracts, so these are reported rather than imported.
_OPTION_SYMBOL = re.compile(
    r"^[A-Z.]{1,6}\s+\d{2}/\d{2}/\d{4}\s+[\d.]+\s*[CP]$|"      # AAPL 01/17/2026 200.00 C
    r"^-?[A-Z.]{1,6}\d{6}[CP]\d+$",                             # -AAPL260117C200
    re.IGNORECASE,
)

# A money or quantity cell as a person reads it: "$1,234.56", "(123.00)" for a
# negative, a trailing "%" that means this is not the column we want.
_NUMERIC_JUNK = str.maketrans({",": "", "$": "", "€": "", "£": "", "+": ""})


@dataclass
class ImportResult:
    """What a parse produced: the book, and an account of everything it did not import."""

    portfolio: PortfolioContext
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.portfolio.positions and self.portfolio.cash is None


def _number(cell: str | None) -> float | None:
    """A broker's formatted number as a float, or ``None`` when the cell holds no number.

    Placeholders (``--``, ``N/A``) and percentages read as absent rather than
    zero: a cost basis of zero is a real claim about the book, and reading
    Schwab's ``--`` as zero would put an average price of 0 on every position
    whose cost basis the export withholds.
    """
    if cell is None:
        return None
    text = cell.strip().strip('"').strip()
    if not text or text in {"--", "—", "N/A", "n/a", "NA", "-"} or text.endswith("%"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").translate(_NUMERIC_JUNK).strip()
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def _find_header(rows: list[list[str]]) -> int | None:
    """Index of the header row: the first row naming both a symbol and a quantity column.

    Schwab writes an account line above the header and a disclaimer below the
    last position, so the header is neither the first row nor at a fixed offset.
    """
    for index, row in enumerate(rows):
        cells = {cell.strip().strip('"').lower() for cell in row}
        if cells & set(_SYMBOL_COLUMNS) and cells & set(_QUANTITY_COLUMNS):
            return index
    return None


def _column(header: list[str], names: tuple[str, ...]) -> int | None:
    """Index of the first column in ``names`` present in ``header``."""
    lowered = [cell.strip().strip('"').lower() for cell in header]
    for name in names:
        if name in lowered:
            return lowered.index(name)
    return None


def _cell(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index].strip().strip('"').strip()


def parse_positions_csv(text: str) -> ImportResult:
    """Parse a broker positions export into a portfolio.

    Handles an export covering several accounts: each account repeats the
    header, so positions in the same symbol are summed into one line and their
    cost bases combined into a blended average price, and every account's cash
    row adds to the single cash figure. That matches what the agents are asked
    to reason about — one book — rather than preserving an account split the
    pipeline has nowhere to put.
    """
    rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    if not rows:
        return ImportResult(PortfolioContext(), warnings=["the file is empty"])

    header_index = _find_header(rows)
    if header_index is None:
        return ImportResult(
            PortfolioContext(),
            warnings=[
                "no positions table found: the file needs a header row naming a "
                "symbol column and a quantity column"
            ],
        )

    # quantity and cost are accumulated so a symbol held in two accounts blends.
    quantities: dict[str, float] = {}
    costs: dict[str, float] = {}
    cost_known: dict[str, bool] = {}
    order: list[str] = []
    cash = 0.0
    saw_cash = False
    skipped: list[str] = []
    warnings: list[str] = []
    currency = None

    header = rows[header_index]
    columns = _columns_for(header)

    for row in rows[header_index:]:
        if _find_header([row]) is not None:        # the next account's header
            header = row
            columns = _columns_for(header)
            continue

        # A preamble or disclaimer line is one cell of prose, not a row. It is
        # dropped silently: naming it as a skipped position would put the
        # export's legal footer in a report of what failed to import.
        if sum(1 for cell in row if cell.strip()) < 2:
            continue

        symbol = _cell(row, columns["symbol"])
        if not symbol or _SKIP_ROW.match(symbol):
            continue
        if _TOTAL_ROW.match(symbol):
            continue
        if _CASH_ROW.match(symbol):
            value = _number(_cell(row, columns["market_value"]))
            if value is not None:
                cash += value
                saw_cash = True
            continue

        quantity = _number(_cell(row, columns["quantity"]))
        if quantity is None:
            skipped.append(f"{symbol}: no quantity")
            continue
        if _OPTION_SYMBOL.match(symbol):
            skipped.append(f"{symbol}: options contract, not priced by the data layer")
            continue

        key = symbol.upper()
        if key not in quantities:
            order.append(key)
            quantities[key] = 0.0
            costs[key] = 0.0
            cost_known[key] = True
        quantities[key] += quantity

        # Cost basis is the dependable column: an "average cost" is per share
        # and cannot be blended across accounts without its quantity, while a
        # total divides cleanly at the end.
        basis = _number(_cell(row, columns["cost_basis"]))
        if basis is None:
            per_share = _number(_cell(row, columns["avg_price"]))
            basis = per_share * quantity if per_share is not None else None
        if basis is None:
            cost_known[key] = False
        else:
            costs[key] += basis

    positions = []
    for key in order:
        quantity = quantities[key]
        average = None
        if cost_known[key] and quantity:
            average = abs(costs[key] / quantity)
        positions.append(Position(ticker=key, quantity=quantity, average_price=average))

    if not positions:
        warnings.append("no positions were read; check that this is a positions export")
    missing_cost = [p.ticker for p in positions if p.average_price is None]
    if missing_cost:
        warnings.append(
            "no cost basis in the export for " + ", ".join(missing_cost[:8])
            + ("..." if len(missing_cost) > 8 else "")
            + " — the agents will see the holding without an entry price"
        )
    if not saw_cash:
        warnings.append("no cash row found; set cash yourself if the book holds any")

    return ImportResult(
        PortfolioContext(
            cash=cash if saw_cash else None,
            currency=currency or "USD",
            positions=positions,
        ),
        skipped=skipped,
        warnings=warnings,
    )


def _columns_for(header: list[str]) -> dict[str, int | None]:
    return {
        "symbol": _column(header, _SYMBOL_COLUMNS),
        "quantity": _column(header, _QUANTITY_COLUMNS),
        "avg_price": _column(header, _AVG_PRICE_COLUMNS),
        "cost_basis": _column(header, _COST_BASIS_COLUMNS),
        "market_value": _column(header, _MARKET_VALUE_COLUMNS),
        "type": _column(header, _TYPE_COLUMNS),
    }
