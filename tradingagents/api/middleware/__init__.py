"""Middleware for FastAPI application."""

from tradingagents.api.middleware.error_handler import add_error_handlers

__all__ = ["add_error_handlers"]
