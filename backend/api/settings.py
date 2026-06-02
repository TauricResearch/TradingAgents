from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.settings import SettingsRead, SettingsUpdate
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/llm-catalog")
async def get_llm_catalog(_: User = Depends(get_current_user)):
    """Return all providers and their available models from the model catalog."""
    from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
    catalog = {}
    for provider, modes in MODEL_OPTIONS.items():
        catalog[provider] = {
            mode: [{"label": label, "value": value} for label, value in opts]
            for mode, opts in modes.items()
        }
    return catalog


async def _get_or_create_settings(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings(id=1)
        db.add(settings)
        await db.flush()
    return settings


@router.get("", response_model=SettingsRead)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await _get_or_create_settings(db)
    return SettingsRead(
        trading_mode=settings.trading_mode,
        active_broker=settings.active_broker,
        active_data_vendor=settings.active_data_vendor,
        cron_enabled=settings.cron_enabled,
        cron_schedule=settings.cron_schedule,
        price_tolerance_pct=settings.price_tolerance_pct,
        watchlist=settings.watchlist,
        selected_analysts=settings.selected_analysts,
        llm_provider=settings.llm_provider,
        deep_think_llm=settings.deep_think_llm,
        quick_think_llm=settings.quick_think_llm,
        backend_url=settings.backend_url,
        openai_reasoning_effort=settings.openai_reasoning_effort,
        anthropic_effort=settings.anthropic_effort,
        google_thinking_level=settings.google_thinking_level,
        output_language=settings.output_language or "English",
        analyst_concurrency_limit=settings.analyst_concurrency_limit or 1,
        checkpoint_enabled=getattr(settings, "checkpoint_enabled", False) or False,
        max_recur_limit=getattr(settings, "max_recur_limit", 1000) or 1000,
        news_article_limit=getattr(settings, "news_article_limit", 20) or 20,
        global_news_article_limit=getattr(settings, "global_news_article_limit", 10) or 10,
        global_news_lookback_days=getattr(settings, "global_news_lookback_days", 7) or 7,
        benchmark_ticker=getattr(settings, "benchmark_ticker", None),
        azure_deployment=getattr(settings, "azure_deployment", None),
        data_vendor_core_stock=getattr(settings, "data_vendor_core_stock", None) or "yfinance",
        data_vendor_technicals=getattr(settings, "data_vendor_technicals", None) or "yfinance",
        data_vendor_fundamentals=getattr(settings, "data_vendor_fundamentals", None) or "yfinance",
        data_vendor_news=getattr(settings, "data_vendor_news", None) or "yfinance",
        max_debate_rounds=settings.max_debate_rounds,
        max_risk_rounds=settings.max_risk_rounds,
        max_position_size_pct=settings.max_position_size_pct,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        updated_at=settings.updated_at,
    )


@router.put("", response_model=SettingsRead)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    settings = await _get_or_create_settings(db)

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "watchlist":
            settings.watchlist = value
        elif field == "selected_analysts":
            settings.selected_analysts = value
        else:
            setattr(settings, field, value)
    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Notify cron service to reconfigure if cron settings changed
    from backend.services.cron_service import get_cron_service
    cron = get_cron_service()
    if cron:
        await cron.apply_settings(settings)

    return await get_settings(db=db, _=_)
