"""Alerts module for trading alerts and notifications.

This module provides alert management including:
- Alert orchestration and routing
- Multiple alert channels (email, slack, sms, webhook)
- Alert priorities and severity levels
- Rate limiting to prevent alert storms
- Alert history tracking

Issue #38: [ALERT-37] Alert manager - orchestration and routing
Issue #40: [ALERT-39] Slack channel - webhooks

Submodules:
    alert_manager: Core alert management functionality
    slack_channel: Slack webhook integration

Classes:
    Enums:
    - AlertPriority: Alert priority levels (low, medium, high, critical)
    - AlertCategory: Alert categories (trade, risk, system, market, etc.)
    - AlertStatus: Alert delivery status
    - ChannelType: Alert channel types
    - SlackMessageStyle: Slack message formatting styles

    Data Classes:
    - AlertTemplate: Template for formatting alerts
    - RateLimitConfig: Rate limiting configuration
    - RoutingRule: Rule for routing alerts to channels
    - AlertConfig: Alert manager configuration
    - Alert: An alert to be sent
    - DeliveryResult: Result of alert delivery
    - AlertStats: Statistics about alerts
    - SlackConfig: Slack channel configuration
    - SlackMessageResult: Result of Slack message send

    Channel Classes:
    - LogChannel: Channel that logs to Python logging
    - WebhookChannel: Channel that sends to webhooks
    - SlackChannel: Channel that sends to Slack via webhooks

    Main Classes:
    - AlertManager: Orchestrates alert routing and delivery

Example:
    >>> from tradingagents.alerts import (
    ...     AlertManager,
    ...     AlertPriority,
    ...     AlertCategory,
    ...     SlackChannel,
    ... )
    >>> from decimal import Decimal
    >>>
    >>> manager = AlertManager()
    >>>
    >>> # Add Slack channel
    >>> slack = SlackChannel("https://hooks.slack.com/...")
    >>> manager.register_channel(slack)
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

from .slack_channel import (
    # Enums
    SlackMessageStyle,
    # Data Classes
    SlackConfig,
    SlackMessageResult,
    # Classes
    SlackMessageFormatter,
    SlackChannel,
    # Factory Functions
    create_slack_channel,
)

__all__ = [
    # Enums
    "AlertPriority",
    "AlertCategory",
    "AlertStatus",
    "ChannelType",
    "SlackMessageStyle",
    # Data Classes
    "AlertTemplate",
    "RateLimitConfig",
    "RoutingRule",
    "AlertConfig",
    "Alert",
    "DeliveryResult",
    "AlertStats",
    "SlackConfig",
    "SlackMessageResult",
    # Channel Classes
    "LogChannel",
    "WebhookChannel",
    "SlackChannel",
    # Main Classes
    "AlertManager",
    "SlackMessageFormatter",
    # Factory Functions
    "create_slack_channel",
]
