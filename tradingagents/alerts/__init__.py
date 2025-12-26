"""Alerts module for trading alerts and notifications.

This module provides alert management including:
- Alert orchestration and routing
- Multiple alert channels (email, slack, sms, webhook)
- Alert priorities and severity levels
- Rate limiting to prevent alert storms
- Alert history tracking

Issue #38: [ALERT-37] Alert manager - orchestration and routing

Submodules:
    alert_manager: Core alert management functionality

Classes:
    Enums:
    - AlertPriority: Alert priority levels (low, medium, high, critical)
    - AlertCategory: Alert categories (trade, risk, system, market, etc.)
    - AlertStatus: Alert delivery status
    - ChannelType: Alert channel types

    Data Classes:
    - AlertTemplate: Template for formatting alerts
    - RateLimitConfig: Rate limiting configuration
    - RoutingRule: Rule for routing alerts to channels
    - AlertConfig: Alert manager configuration
    - Alert: An alert to be sent
    - DeliveryResult: Result of alert delivery
    - AlertStats: Statistics about alerts

    Channel Classes:
    - LogChannel: Channel that logs to Python logging
    - WebhookChannel: Channel that sends to webhooks

    Main Classes:
    - AlertManager: Orchestrates alert routing and delivery

Example:
    >>> from tradingagents.alerts import (
    ...     AlertManager,
    ...     AlertPriority,
    ...     AlertCategory,
    ... )
    >>> from decimal import Decimal
    >>>
    >>> manager = AlertManager()
    >>>
    >>> # Create and send alert
    >>> alert = manager.create_alert(
    ...     title="Buy Signal",
    ...     message="AAPL buy signal detected",
    ...     priority=AlertPriority.MEDIUM,
    ...     category=AlertCategory.TRADE,
    ... )
    >>> manager.send(alert)
    >>>
    >>> # Convenience methods
    >>> manager.alert_trade("AAPL", "BUY", Decimal("150.00"))
    >>> manager.alert_risk("DrawdownLimit", "15%", "10%")
"""

from .alert_manager import (
    # Enums
    AlertPriority,
    AlertCategory,
    AlertStatus,
    ChannelType,
    # Data Classes
    AlertTemplate,
    RateLimitConfig,
    RoutingRule,
    AlertConfig,
    Alert,
    DeliveryResult,
    AlertStats,
    # Channel Classes
    LogChannel,
    WebhookChannel,
    # Main Class
    AlertManager,
)

__all__ = [
    # Enums
    "AlertPriority",
    "AlertCategory",
    "AlertStatus",
    "ChannelType",
    # Data Classes
    "AlertTemplate",
    "RateLimitConfig",
    "RoutingRule",
    "AlertConfig",
    "Alert",
    "DeliveryResult",
    "AlertStats",
    # Channel Classes
    "LogChannel",
    "WebhookChannel",
    # Main Class
    "AlertManager",
]
