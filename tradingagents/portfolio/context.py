"""Portfolio context generator for LLM prompts.

Converts portfolio data into structured Markdown text that can be
embedded into analyst/trader agent prompts.
"""

from typing import List

from .models import PositionRecord, Transaction
from .store import PortfolioStore


def build_portfolio_context(ticker: str, store: PortfolioStore) -> str:
    """Build a Markdown portfolio context string for the given ticker.

    Args:
        ticker: The stock ticker being analyzed (e.g., "NVDA", "000404.SH").
        store: A PortfolioStore instance to read data from.

    Returns:
        A Markdown string with portfolio context, or empty string if no data
        or if an error occurs.
    """
    try:
        positions = store.list_positions()
        ticker_positions = store.get_position(ticker)
        transactions = store.list_transactions(ticker=ticker, limit=10)
    except Exception:
        return ""

    # If there's absolutely no data related to this context, return empty
    if not positions and not transactions:
        return ""

    sections: List[str] = []
    sections.append("## Your Current Portfolio Context")

    # ─── Overall Position Summary ─────────────────────────────────────
    sections.append(_build_overall_summary(ticker, positions, ticker_positions))

    # ─── Position Detail ──────────────────────────────────────────────
    if ticker_positions:
        sections.append(_build_position_detail(ticker, ticker_positions))

    # ─── Recent Transactions ──────────────────────────────────────────
    if transactions:
        sections.append(_build_recent_transactions(ticker, transactions))

    # ─── Portfolio Concentration ──────────────────────────────────────
    if positions:
        sections.append(_build_concentration(ticker, positions))

    return "\n\n".join(sections)


def _build_overall_summary(
    ticker: str,
    all_positions: List[PositionRecord],
    ticker_positions: List[PositionRecord],
) -> str:
    """Build the Overall Position Summary section."""
    total = len(set(p.ticker.upper() for p in all_positions))
    lines = ["### Overall Position Summary"]
    lines.append(f"- Total positions: {total} stocks")

    display_ticker = ticker.upper()
    if ticker_positions:
        total_qty = sum(p.quantity for p in ticker_positions)
        total_cost = sum(p.entry_price * p.quantity for p in ticker_positions)
        avg_cost = total_cost / total_qty if total_qty else 0
        lines.append(
            f"- This ticker ({display_ticker}): HOLDING {_fmt_qty(total_qty)} shares "
            f"@ avg cost ${avg_cost:,.2f}"
        )
    else:
        lines.append(f"- This ticker ({display_ticker}): NOT IN PORTFOLIO")

    return "\n".join(lines)


def _build_position_detail(
    ticker: str, ticker_positions: List[PositionRecord]
) -> str:
    """Build the Position Detail section for the ticker."""
    display_ticker = ticker.upper()

    # Aggregate across multiple lots
    total_qty = sum(p.quantity for p in ticker_positions)
    total_cost = sum(p.entry_price * p.quantity for p in ticker_positions)
    avg_cost = total_cost / total_qty if total_qty else 0

    # Use earliest entry date
    earliest_date = min(p.entry_date for p in ticker_positions)
    # Use the side of the first position (should be consistent)
    side = ticker_positions[0].side.capitalize()
    # Combine notes
    notes = [p.note for p in ticker_positions if p.note]
    note_str = "; ".join(notes) if notes else ""

    lines = [f"### Position Detail for {display_ticker}"]
    lines.append(f"- Entry Date: {earliest_date}")
    lines.append(f"- Average Cost: ${avg_cost:,.2f}")
    lines.append(f"- Quantity: {_fmt_qty(total_qty)} shares")
    lines.append(f"- Side: {side}")
    if note_str:
        lines.append(f"- Note: {note_str}")

    return "\n".join(lines)


def _build_recent_transactions(
    ticker: str, transactions: List[Transaction]
) -> str:
    """Build the Recent Transactions section."""
    display_ticker = ticker.upper()
    lines = [f"### Recent Transactions for {display_ticker}"]

    # Already sorted by date descending from store
    for tx in transactions:
        action = tx.action.upper()
        lines.append(f"- {tx.date}: {action} {_fmt_qty(tx.quantity)} shares @ ${tx.price:,.2f}")

    return "\n".join(lines)


def _build_concentration(
    ticker: str, all_positions: List[PositionRecord]
) -> str:
    """Build the Portfolio Concentration section."""
    display_ticker = ticker.upper()

    # Calculate cost basis for each ticker
    ticker_costs: dict = {}
    for p in all_positions:
        key = p.ticker.upper()
        ticker_costs[key] = ticker_costs.get(key, 0) + p.entry_price * p.quantity

    total_cost_basis = sum(ticker_costs.values())
    if total_cost_basis == 0:
        return ""

    # Current ticker weight
    current_weight = ticker_costs.get(display_ticker, 0) / total_cost_basis * 100

    # Top holdings sorted by cost basis descending
    sorted_holdings = sorted(ticker_costs.items(), key=lambda x: x[1], reverse=True)
    top_5 = sorted_holdings[:5]
    top_str = ", ".join(
        f"{t} ({v / total_cost_basis * 100:.1f}%)" for t, v in top_5
    )

    lines = ["### Portfolio Concentration"]
    lines.append(f"- {display_ticker} weight: ~{current_weight:.1f}% of portfolio (by cost basis)")
    lines.append(f"- Top holdings: {top_str}")

    return "\n".join(lines)


def _fmt_qty(qty: float) -> str:
    """Format quantity: show as int if whole number, else 2 decimal places."""
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.2f}"
