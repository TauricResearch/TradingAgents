"""CronService — APScheduler-backed watchlist scanner."""
import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_logger = logging.getLogger(__name__)
_cron_service: Optional["CronService"] = None


class CronService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

    def start(self):
        if not self._running:
            self.scheduler.start()
            self._running = True
            # Alert price checker — every 15 minutes
            self.scheduler.add_job(
                _run_alert_checker, "interval", minutes=15,
                id="alert_checker", replace_existing=True, misfire_grace_time=120,
            )
            # Performance backfill — every 6 hours
            self.scheduler.add_job(
                _run_performance_backfill, "interval", hours=6,
                id="perf_backfill", replace_existing=True, misfire_grace_time=3600,
            )
            _logger.info("CronService started")

    def stop(self):
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False

    async def apply_settings(self, settings):
        """Re-configure the watchlist scan job from AppSettings."""
        self.scheduler.remove_job("watchlist_scan") if self.scheduler.get_job("watchlist_scan") else None

        if settings.cron_enabled and settings.watchlist:
            try:
                trigger = CronTrigger.from_crontab(settings.cron_schedule, timezone="UTC")
                self.scheduler.add_job(
                    self._run_watchlist_scan,
                    trigger,
                    id="watchlist_scan",
                    replace_existing=True,
                    misfire_grace_time=300,
                )
                _logger.info("Cron job configured: %s", settings.cron_schedule)
            except Exception as e:
                _logger.error("Failed to configure cron job: %s", e)

    async def _run_watchlist_scan(self):
        """Triggered by APScheduler — runs analysis for every ticker in watchlist."""
        from backend.core.database import AsyncSessionLocal
        from backend.models.settings import AppSettings
        from backend.services.analysis_service import run_analysis
        from backend.services.execution.factory import get_trader
        from backend.services.execution.base import OrderRequest
        from sqlalchemy import select

        today = date.today().strftime("%Y-%m-%d")
        _logger.info("Cron watchlist scan started for date=%s", today)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
            settings = result.scalar_one_or_none()
            if not settings:
                return

            trader = get_trader(settings.trading_mode, settings.active_broker)

            for ticker in settings.watchlist:
                try:
                    _logger.info("Cron scanning ticker=%s", ticker)
                    task_id, row = await run_analysis(
                        ticker=ticker,
                        trade_date=today,
                        asset_type="stock",
                        settings=settings,
                        db=db,
                        triggered_by="cron",
                    )
                    await db.commit()

                    # Execute if signal warrants it
                    if row.signal in ("Buy", "Overweight", "Sell", "Underweight"):
                        await _maybe_execute(ticker, row, settings, trader, db)

                except Exception as e:
                    _logger.error("Cron scan failed for %s: %s", ticker, e, exc_info=True)
                    await db.rollback()

        _logger.info("Cron watchlist scan completed")

    def get_status(self) -> dict:
        job = self.scheduler.get_job("watchlist_scan")
        return {
            "running": self._running,
            "job_configured": job is not None,
            "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
        }


async def _maybe_execute(ticker: str, row, settings, trader, db):
    """Execute trade if AI signal warrants and price is within tolerance."""
    from backend.models.order import Order
    from backend.services.execution.base import OrderRequest

    price = trader.get_current_price(ticker)
    if not price or price <= 0:
        _logger.warning("No price available for %s, skipping execution", ticker)
        return

    action = "BUY" if row.signal in ("Buy", "Overweight") else "SELL"
    qty = (settings.max_risk_per_trade_pct / 100 * 100_000) / price

    req = OrderRequest(
        ticker=ticker,
        action=action,
        quantity=qty,
        reference_price=price,
        ai_signal=row.signal or "",
        ai_reasoning=row.final_decision[:500],
    )
    result = trader.place_order(req)

    order_row = Order(
        portfolio_id=1,
        mode=settings.trading_mode,
        broker=settings.active_broker,
        ticker=ticker,
        action=action,
        quantity_requested=qty,
        quantity_filled=result.filled_quantity or 0,
        status=result.status,
        price_per_share=result.filled_price,
        total_value=(result.filled_price or 0) * (result.filled_quantity or 0),
        commission=result.commission,
        analysis_id=row.id,
        ai_signal=row.signal or "",
        ai_reasoning=row.final_decision[:500],
        executed_at=result.executed_at,
    )
    db.add(order_row)
    await db.flush()
    _logger.info("Order placed: %s %s %s → %s", action, qty, ticker, result.status)


async def _run_alert_checker():
    from backend.services.alert_service import check_price_alerts
    try:
        await check_price_alerts()
    except Exception as exc:
        _logger.error("Alert checker error: %s", exc)


async def _run_performance_backfill():
    from backend.core.database import AsyncSessionLocal
    from backend.services.performance_service import backfill_returns
    try:
        async with AsyncSessionLocal() as db:
            await backfill_returns(db)
    except Exception as exc:
        _logger.error("Performance backfill error: %s", exc)


def init_cron_service() -> CronService:
    global _cron_service
    _cron_service = CronService()
    return _cron_service


def get_cron_service() -> Optional[CronService]:
    return _cron_service
