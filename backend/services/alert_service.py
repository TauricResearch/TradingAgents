"""Price alert checker — runs every 15 minutes via APScheduler."""
import logging
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)


async def check_price_alerts() -> None:
    """Check all enabled, un-triggered alerts against current prices."""
    from sqlalchemy import select
    from backend.core.database import AsyncSessionLocal
    from backend.models.alert import PriceAlert
    from backend.models.settings import AppSettings
    from backend.services.notification_service import notify_alert_triggered

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PriceAlert).where(PriceAlert.enabled == True, PriceAlert.triggered_at.is_(None))
        )
        alerts = result.scalars().all()
        if not alerts:
            return

        settings_res = await db.execute(select(AppSettings).where(AppSettings.id == 1))
        settings = settings_res.scalar_one_or_none()

        import asyncio
        prices = await asyncio.to_thread(_fetch_prices, [a.ticker for a in alerts])

        for alert in alerts:
            price = prices.get(alert.ticker)
            if price is None:
                continue
            hit = (alert.condition == "above" and price >= alert.target_price) or \
                  (alert.condition == "below" and price <= alert.target_price)
            if not hit:
                continue

            alert.triggered_at = datetime.now(timezone.utc)
            _logger.info("Alert triggered: %s %s $%.2f (current: $%.2f)",
                         alert.ticker, alert.condition, alert.target_price, price)

            if settings:
                await notify_alert_triggered(alert.ticker, alert.condition, alert.target_price, settings)

            if alert.auto_analyze:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                asyncio.create_task(_auto_analyze(alert.ticker, today, settings, db))

        await db.commit()


def _fetch_prices(tickers: list[str]) -> dict[str, float]:
    import yfinance as yf
    prices = {}
    unique = list(set(tickers))
    try:
        data = yf.download(unique, period="1d", progress=False, auto_adjust=True)
        if "Close" in data.columns:
            close = data["Close"].iloc[-1]
            for t in unique:
                try:
                    prices[t] = float(close[t])
                except Exception:
                    pass
        else:
            for t in unique:
                try:
                    prices[t] = float(yf.Ticker(t).fast_info.last_price or 0)
                except Exception:
                    pass
    except Exception as exc:
        _logger.debug("Batch price fetch failed: %s", exc)
        for t in unique:
            try:
                prices[t] = float(yf.Ticker(t).fast_info.last_price or 0)
            except Exception:
                pass
    return prices


async def _auto_analyze(ticker: str, trade_date: str, settings, db) -> None:
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.services.analysis_service import run_analysis
        import uuid
        async with AsyncSessionLocal() as new_db:
            task_id = str(uuid.uuid4())
            await run_analysis(ticker, trade_date, "stock", settings, new_db,
                               triggered_by="alert", task_id=task_id)
            await new_db.commit()
    except Exception as exc:
        _logger.error("Auto-analyze from alert failed %s: %s", ticker, exc)
