"""Async helper for writing SystemLog rows from anywhere in the app."""
import json
import logging
import traceback
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.log import SystemLog

_logger = logging.getLogger(__name__)


async def _write(db: AsyncSession, level: str, source: str, message: str, details: str | None):
    row = SystemLog(level=level, source=source, message=message, details=details)
    db.add(row)
    try:
        await db.flush()
    except Exception as e:
        _logger.error("Failed to persist system log: %s", e)


async def info(db: AsyncSession, source: str, message: str):
    await _write(db, "INFO", source, message, None)


async def warning(db: AsyncSession, source: str, message: str, exc: Exception | None = None):
    details = traceback.format_exc() if exc else None
    await _write(db, "WARNING", source, message, details)


async def error(db: AsyncSession, source: str, message: str, exc: Exception | None = None):
    details = traceback.format_exc() if exc else None
    await _write(db, "ERROR", source, message, details)
