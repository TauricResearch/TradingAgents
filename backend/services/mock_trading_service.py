"""Mock trading service — executes paper trades against PostgreSQL portfolio models."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.portfolio import Portfolio, Holding
from backend.models.order import Order

_logger = logging.getLogger(__name__)


async def _get_price(ticker: str) -> Optional[float]:
    """Fetch latest price from yfinance in a thread pool."""
    import yfinance as yf

    def _fetch():
        try:
            info = yf.Ticker(ticker).info
            # Use explicit None checks to avoid treating 0.0 as missing
            price = info.get("currentPrice")
            if price is None:
                price = info.get("regularMarketPrice")
            if price is None:
                hist = yf.Ticker(ticker).history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            return float(price) if price is not None else None
        except Exception as e:
            _logger.warning("Price fetch failed for %s: %s", ticker, e)
            return None

    return await asyncio.to_thread(_fetch)


async def get_or_create_sim_portfolio(db: AsyncSession, initial_capital: float = 100_000.0) -> Portfolio:
    """Return the simulation portfolio, creating one if it doesn't exist."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.mode == "simulation")
        .options(selectinload(Portfolio.holdings))
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        portfolio = Portfolio(
            mode="simulation",
            broker="paper",
            initial_capital=initial_capital,
            current_balance=initial_capital,
            cash_available=initial_capital,
            status="active",
        )
        db.add(portfolio)
        await db.flush()
        await db.refresh(portfolio, ["holdings"])
    return portfolio


async def get_portfolio_with_live_prices(db: AsyncSession) -> dict:
    """Return simulation portfolio enriched with live prices and P&L."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.mode == "simulation")
        .options(selectinload(Portfolio.holdings))
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        portfolio = await get_or_create_sim_portfolio(db)

    # Fetch live prices for all holdings concurrently
    tickers = [h.ticker for h in portfolio.holdings]
    prices = {}
    if tickers:
        raw = await asyncio.gather(*[_get_price(t) for t in tickers], return_exceptions=True)
        prices = {
            t: p for t, p in zip(tickers, raw)
            if p is not None and not isinstance(p, BaseException)
        }

    holdings_data = []
    positions_value = 0.0
    for h in portfolio.holdings:
        fetched = prices.get(h.ticker)
        if fetched is not None:
            price = fetched
        elif h.current_price is not None:
            price = h.current_price
        else:
            price = h.avg_buy_price
        cost_basis = h.avg_buy_price * h.quantity
        market_value = price * h.quantity
        unrealized_pnl = market_value - cost_basis
        pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0

        # Persist updated price & pnl
        h.current_price = price
        h.unrealized_pnl = unrealized_pnl
        positions_value += market_value

        holdings_data.append({
            "ticker": h.ticker,
            "quantity": h.quantity,
            "avg_buy_price": h.avg_buy_price,
            "current_price": price,
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
        })

    total_value = portfolio.cash_available + positions_value
    total_pnl = total_value - portfolio.initial_capital
    total_pnl_pct = (total_pnl / portfolio.initial_capital * 100) if portfolio.initial_capital else 0.0

    portfolio.current_balance = total_value
    await db.flush()

    return {
        "id": portfolio.id,
        "mode": portfolio.mode,
        "initial_capital": portfolio.initial_capital,
        "cash_available": round(portfolio.cash_available, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "holdings": holdings_data,
    }


async def execute_order(
    db: AsyncSession,
    ticker: str,
    action: str,
    quantity: float,
    analysis_id: Optional[int] = None,
) -> dict:
    """Execute a paper BUY or SELL order.

    Returns a result dict with order details or raises ValueError on failure.
    """
    action = action.upper()
    if action not in ("BUY", "SELL"):
        raise ValueError("action must be BUY or SELL")
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    price = await _get_price(ticker)
    if price is None:
        raise ValueError(f"Could not fetch price for {ticker}")

    portfolio = await get_or_create_sim_portfolio(db)
    total_cost = price * quantity
    commission = round(total_cost * 0.001, 4)  # 0.1% commission

    if action == "BUY":
        required = total_cost + commission
        if portfolio.cash_available < required:
            raise ValueError(
                f"Yetersiz bakiye. Gerekli: ${required:.2f}, Mevcut: ${portfolio.cash_available:.2f}"
            )

        portfolio.cash_available -= required

        # Update or create holding
        result = await db.execute(
            select(Holding).where(
                Holding.portfolio_id == portfolio.id,
                Holding.ticker == ticker,
            )
        )
        holding = result.scalar_one_or_none()
        if holding:
            new_qty = holding.quantity + quantity
            holding.avg_buy_price = (
                (holding.avg_buy_price * holding.quantity + price * quantity) / new_qty
            )
            holding.quantity = new_qty
        else:
            db.add(Holding(
                portfolio_id=portfolio.id,
                ticker=ticker,
                quantity=quantity,
                avg_buy_price=price,
                current_price=price,
                unrealized_pnl=0.0,
            ))

    else:  # SELL
        result = await db.execute(
            select(Holding).where(
                Holding.portfolio_id == portfolio.id,
                Holding.ticker == ticker,
            )
        )
        holding = result.scalar_one_or_none()
        if holding is None or holding.quantity < quantity:
            available = holding.quantity if holding else 0
            raise ValueError(f"Yetersiz pozisyon. Mevcut: {available:.4f}, Satılmak istenen: {quantity}")

        portfolio.cash_available += total_cost - commission
        holding.quantity -= quantity
        if holding.quantity < 1e-6:
            await db.delete(holding)

    # Record the order
    order = Order(
        portfolio_id=portfolio.id,
        mode="simulation",
        broker="paper",
        ticker=ticker,
        action=action,
        quantity_requested=quantity,
        quantity_filled=quantity,
        status="FILLED",
        price_per_share=price,
        total_value=total_cost,
        commission=commission,
        analysis_id=analysis_id,
        executed_at=datetime.now(timezone.utc),
    )
    db.add(order)
    await db.flush()

    return {
        "order_id": order.id,
        "ticker": ticker,
        "action": action,
        "quantity": quantity,
        "price": price,
        "total_value": round(total_cost, 2),
        "commission": commission,
        "status": "FILLED",
    }


async def reset_portfolio(db: AsyncSession, initial_capital: float = 100_000.0) -> dict:
    """Reset simulation portfolio to initial state."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.mode == "simulation")
        .options(selectinload(Portfolio.holdings))
    )
    portfolio = result.scalar_one_or_none()

    if portfolio:
        # Bulk delete orders and holdings instead of iterating
        await db.execute(delete(Order).where(Order.portfolio_id == portfolio.id))
        await db.execute(delete(Holding).where(Holding.portfolio_id == portfolio.id))
        portfolio.cash_available = initial_capital
        portfolio.current_balance = initial_capital
        portfolio.initial_capital = initial_capital
    else:
        portfolio = Portfolio(
            mode="simulation",
            broker="paper",
            initial_capital=initial_capital,
            current_balance=initial_capital,
            cash_available=initial_capital,
            status="active",
        )
        db.add(portfolio)

    await db.flush()
    return {"message": "Portföy sıfırlandı", "initial_capital": initial_capital}


async def get_performance(db: AsyncSession) -> dict:
    """Calculate performance metrics vs SPY benchmark."""
    portfolio_data = await get_portfolio_with_live_prices(db)

    # Fetch SPY return over same period as portfolio
    result = await db.execute(
        select(Portfolio).where(Portfolio.mode == "simulation")
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        return portfolio_data

    spy_return_pct = None
    try:
        import yfinance as yf

        def _spy():
            spy = yf.Ticker("SPY").history(period="1y")
            if len(spy) >= 2:
                return float((spy["Close"].iloc[-1] - spy["Close"].iloc[0]) / spy["Close"].iloc[0] * 100)
            return None

        spy_return_pct = await asyncio.to_thread(_spy)
    except Exception:
        pass

    return {
        **portfolio_data,
        "benchmark_ticker": "SPY",
        "benchmark_return_pct": round(spy_return_pct, 2) if spy_return_pct is not None else None,
        "alpha_pct": round(portfolio_data["total_pnl_pct"] - spy_return_pct, 2)
        if spy_return_pct is not None else None,
    }
