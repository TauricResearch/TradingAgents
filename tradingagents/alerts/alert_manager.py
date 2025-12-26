"""Alert Manager for orchestration and routing.

This module provides comprehensive alert management including:
- Alert orchestration and routing
- Multiple alert channels (email, slack, sms, webhook)
- Alert priorities and severity levels
- Rate limiting to prevent alert storms
- Alert history tracking
- Template-based formatting

Issue #38: [ALERT-37] Alert manager - orchestration and routing

Design Principles:
    - Flexible channel routing
    - Rate limiting prevents spam
    - Template-based alert formatting
    - Async support for non-blocking delivery
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Set
import asyncio
import hashlib
import logging
import uuid

# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class AlertPriority(str, Enum):
    """Alert priority levels."""
    LOW = "low"              # Informational
    MEDIUM = "medium"        # Important but not urgent
    HIGH = "high"            # Requires attention
    CRITICAL = "critical"    # Immediate action required


class AlertCategory(str, Enum):
    """Alert category types."""
    TRADE = "trade"              # Trade-related alerts
    RISK = "risk"                # Risk management alerts
    SYSTEM = "system"            # System status alerts
    MARKET = "market"            # Market condition alerts
    PORTFOLIO = "portfolio"      # Portfolio alerts
    EXECUTION = "execution"      # Order execution alerts
    COMPLIANCE = "compliance"    # Regulatory/compliance alerts


class AlertStatus(str, Enum):
    """Alert delivery status."""
    PENDING = "pending"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    SUPPRESSED = "suppressed"


class ChannelType(str, Enum):
    """Alert channel types."""
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    WEBHOOK = "webhook"
    PUSH = "push"
    LOG = "log"


# ============================================================================
# Protocols
# ============================================================================

class AlertChannel(Protocol):
    """Protocol for alert channels."""

    @property
    def channel_type(self) -> ChannelType:
        """Get channel type."""
        ...

    @property
    def is_available(self) -> bool:
        """Check if channel is available."""
        ...

    async def send(self, alert: "Alert") -> bool:
        """Send an alert through this channel.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        ...


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AlertTemplate:
    """Template for formatting alerts.

    Attributes:
        template_id: Unique template identifier
        name: Template name
        title_template: Template for alert title
        body_template: Template for alert body
        category: Alert category this applies to
        variables: Required template variables
    """
    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    title_template: str = "{category}: {title}"
    body_template: str = "{message}"
    category: Optional[AlertCategory] = None
    variables: List[str] = field(default_factory=list)

    def render(self, context: Dict[str, Any]) -> tuple[str, str]:
        """Render the template with context.

        Args:
            context: Template variables

        Returns:
            Tuple of (title, body)
        """
        title = self.title_template.format(**context)
        body = self.body_template.format(**context)
        return title, body


@dataclass
class RateLimitConfig:
    """Rate limiting configuration.

    Attributes:
        max_alerts_per_minute: Maximum alerts per minute per category
        max_alerts_per_hour: Maximum alerts per hour per category
        cooldown_seconds: Cooldown after rate limit hit
        dedupe_window_seconds: Window for deduplication
        enable_deduplication: Enable duplicate detection
    """
    max_alerts_per_minute: int = 10
    max_alerts_per_hour: int = 100
    cooldown_seconds: int = 60
    dedupe_window_seconds: int = 300
    enable_deduplication: bool = True


@dataclass
class RoutingRule:
    """Rule for routing alerts to channels.

    Attributes:
        rule_id: Unique rule identifier
        name: Rule name
        priority: Minimum priority for this rule
        categories: Categories this rule applies to
        channels: Channels to route to
        enabled: Whether rule is enabled
        conditions: Additional conditions as callable
    """
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    priority: AlertPriority = AlertPriority.LOW
    categories: List[AlertCategory] = field(default_factory=list)
    channels: List[ChannelType] = field(default_factory=list)
    enabled: bool = True
    conditions: Optional[Callable[["Alert"], bool]] = None

    def matches(self, alert: "Alert") -> bool:
        """Check if alert matches this rule.

        Args:
            alert: Alert to check

        Returns:
            True if alert matches
        """
        if not self.enabled:
            return False

        # Check priority
        priority_order = [
            AlertPriority.LOW,
            AlertPriority.MEDIUM,
            AlertPriority.HIGH,
            AlertPriority.CRITICAL,
        ]
        if priority_order.index(alert.priority) < priority_order.index(self.priority):
            return False

        # Check category
        if self.categories and alert.category not in self.categories:
            return False

        # Check custom conditions
        if self.conditions and not self.conditions(alert):
            return False

        return True


@dataclass
class AlertConfig:
    """Alert manager configuration.

    Attributes:
        rate_limit_config: Rate limiting configuration
        default_channels: Default channels for alerts
        log_all_alerts: Log all alerts to file
        store_history: Store alert history
        max_history_size: Maximum history entries
        retry_failed: Retry failed deliveries
        max_retries: Maximum retry attempts
        async_delivery: Use async delivery
    """
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)
    default_channels: List[ChannelType] = field(
        default_factory=lambda: [ChannelType.LOG]
    )
    log_all_alerts: bool = True
    store_history: bool = True
    max_history_size: int = 1000
    retry_failed: bool = True
    max_retries: int = 3
    async_delivery: bool = True


@dataclass
class Alert:
    """An alert to be sent.

    Attributes:
        alert_id: Unique alert identifier
        title: Alert title
        message: Alert message body
        priority: Alert priority
        category: Alert category
        source: Source of the alert
        timestamp: When alert was created
        data: Additional alert data
        tags: Alert tags for filtering
        status: Current delivery status
        channels_sent: Channels that received alert
        delivery_attempts: Number of delivery attempts
        last_error: Last delivery error
        acknowledged: Whether alert was acknowledged
        acknowledged_by: Who acknowledged
        acknowledged_at: When acknowledged
    """
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    message: str = ""
    priority: AlertPriority = AlertPriority.MEDIUM
    category: AlertCategory = AlertCategory.SYSTEM
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    status: AlertStatus = AlertStatus.PENDING
    channels_sent: List[ChannelType] = field(default_factory=list)
    delivery_attempts: int = 0
    last_error: str = ""
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

    @property
    def content_hash(self) -> str:
        """Get hash of alert content for deduplication."""
        content = f"{self.title}:{self.message}:{self.category.value}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class DeliveryResult:
    """Result of alert delivery attempt.

    Attributes:
        alert_id: Alert that was delivered
        channel: Channel used
        success: Whether delivery succeeded
        timestamp: When delivery occurred
        error_message: Error if failed
        response_data: Channel response data
    """
    alert_id: str = ""
    channel: ChannelType = ChannelType.LOG
    success: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: str = ""
    response_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertStats:
    """Statistics about alerts.

    Attributes:
        total_sent: Total alerts sent
        total_failed: Total failed deliveries
        total_rate_limited: Total rate-limited alerts
        total_suppressed: Total suppressed (dedupe)
        by_priority: Count by priority
        by_category: Count by category
        by_channel: Count by channel
        avg_delivery_time_ms: Average delivery time
    """
    total_sent: int = 0
    total_failed: int = 0
    total_rate_limited: int = 0
    total_suppressed: int = 0
    by_priority: Dict[str, int] = field(default_factory=dict)
    by_category: Dict[str, int] = field(default_factory=dict)
    by_channel: Dict[str, int] = field(default_factory=dict)
    avg_delivery_time_ms: float = 0.0


# ============================================================================
# Channel Implementations
# ============================================================================

class LogChannel:
    """Channel that logs alerts to Python logging."""

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.LOG

    @property
    def is_available(self) -> bool:
        return True

    async def send(self, alert: Alert) -> bool:
        """Log the alert."""
        log_level = {
            AlertPriority.LOW: logging.INFO,
            AlertPriority.MEDIUM: logging.WARNING,
            AlertPriority.HIGH: logging.ERROR,
            AlertPriority.CRITICAL: logging.CRITICAL,
        }.get(alert.priority, logging.INFO)

        logger.log(
            log_level,
            f"[{alert.category.value.upper()}] {alert.title}: {alert.message}",
        )
        return True


class WebhookChannel:
    """Channel that sends alerts to webhooks."""

    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None):
        """Initialize webhook channel.

        Args:
            webhook_url: URL to send webhooks to
            headers: Optional HTTP headers
        """
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self._available = bool(webhook_url)

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WEBHOOK

    @property
    def is_available(self) -> bool:
        return self._available

    async def send(self, alert: Alert) -> bool:
        """Send alert to webhook.

        Note: Actual HTTP call would be implemented here.
        For now, returns success if URL is configured.
        """
        if not self.webhook_url:
            return False

        payload = {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "message": alert.message,
            "priority": alert.priority.value,
            "category": alert.category.value,
            "timestamp": alert.timestamp.isoformat(),
            "data": alert.data,
        }

        # In production, would use aiohttp or similar
        logger.info(f"Webhook payload: {payload}")
        return True


# ============================================================================
# AlertManager Class
# ============================================================================

class AlertManager:
    """Orchestrates alert routing and delivery.

    Manages alert channels, routing rules, rate limiting,
    and delivery tracking.

    Attributes:
        config: Alert configuration
        channels: Registered alert channels
        routing_rules: Alert routing rules
        templates: Alert templates
    """

    def __init__(
        self,
        config: Optional[AlertConfig] = None,
    ):
        """Initialize alert manager.

        Args:
            config: Alert configuration
        """
        self.config = config or AlertConfig()

        # Channels
        self.channels: Dict[ChannelType, AlertChannel] = {}
        self._register_default_channels()

        # Routing
        self.routing_rules: List[RoutingRule] = []
        self._setup_default_rules()

        # Templates
        self.templates: Dict[str, AlertTemplate] = {}
        self._setup_default_templates()

        # Rate limiting
        self._rate_limit_state: Dict[str, List[datetime]] = {}
        self._seen_hashes: Dict[str, datetime] = {}

        # History
        self._history: List[Alert] = []
        self._delivery_results: List[DeliveryResult] = []

        # Stats
        self._stats = AlertStats()

    def _register_default_channels(self) -> None:
        """Register default channels."""
        self.register_channel(LogChannel())

    def _setup_default_rules(self) -> None:
        """Setup default routing rules."""
        # Critical alerts go to all channels
        self.add_routing_rule(RoutingRule(
            name="critical_all_channels",
            priority=AlertPriority.CRITICAL,
            categories=[],  # All categories
            channels=[ChannelType.LOG],
            enabled=True,
        ))

        # Trade alerts go to log
        self.add_routing_rule(RoutingRule(
            name="trade_alerts",
            priority=AlertPriority.MEDIUM,
            categories=[AlertCategory.TRADE, AlertCategory.EXECUTION],
            channels=[ChannelType.LOG],
            enabled=True,
        ))

        # Risk alerts go to log
        self.add_routing_rule(RoutingRule(
            name="risk_alerts",
            priority=AlertPriority.HIGH,
            categories=[AlertCategory.RISK],
            channels=[ChannelType.LOG],
            enabled=True,
        ))

    def _setup_default_templates(self) -> None:
        """Setup default alert templates."""
        self.register_template(AlertTemplate(
            name="trade_signal",
            title_template="[TRADE] {symbol} - {action}",
            body_template="Signal: {action} {symbol}\nPrice: {price}\nReason: {reason}",
            category=AlertCategory.TRADE,
            variables=["symbol", "action", "price", "reason"],
        ))

        self.register_template(AlertTemplate(
            name="risk_breach",
            title_template="[RISK] {risk_type} threshold breached",
            body_template="Risk breach detected:\nType: {risk_type}\nCurrent: {current_value}\nLimit: {limit_value}",
            category=AlertCategory.RISK,
            variables=["risk_type", "current_value", "limit_value"],
        ))

        self.register_template(AlertTemplate(
            name="order_executed",
            title_template="[EXECUTION] Order {order_id} {status}",
            body_template="Order {order_id} for {symbol} has been {status}.\nQuantity: {quantity}\nPrice: {price}",
            category=AlertCategory.EXECUTION,
            variables=["order_id", "symbol", "status", "quantity", "price"],
        ))

    def register_channel(self, channel: AlertChannel) -> None:
        """Register an alert channel.

        Args:
            channel: Channel to register
        """
        self.channels[channel.channel_type] = channel
        logger.info(f"Registered alert channel: {channel.channel_type.value}")

    def unregister_channel(self, channel_type: ChannelType) -> None:
        """Unregister an alert channel.

        Args:
            channel_type: Type of channel to remove
        """
        if channel_type in self.channels:
            del self.channels[channel_type]
            logger.info(f"Unregistered alert channel: {channel_type.value}")

    def add_routing_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule.

        Args:
            rule: Routing rule to add
        """
        self.routing_rules.append(rule)
        logger.debug(f"Added routing rule: {rule.name}")

    def remove_routing_rule(self, rule_id: str) -> bool:
        """Remove a routing rule.

        Args:
            rule_id: ID of rule to remove

        Returns:
            True if removed
        """
        for i, rule in enumerate(self.routing_rules):
            if rule.rule_id == rule_id:
                del self.routing_rules[i]
                return True
        return False

    def register_template(self, template: AlertTemplate) -> None:
        """Register an alert template.

        Args:
            template: Template to register
        """
        self.templates[template.name] = template

    def create_alert(
        self,
        title: str,
        message: str,
        priority: AlertPriority = AlertPriority.MEDIUM,
        category: AlertCategory = AlertCategory.SYSTEM,
        source: str = "",
        data: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Alert:
        """Create a new alert.

        Args:
            title: Alert title
            message: Alert message
            priority: Alert priority
            category: Alert category
            source: Alert source
            data: Additional data
            tags: Alert tags

        Returns:
            Created alert
        """
        return Alert(
            title=title,
            message=message,
            priority=priority,
            category=category,
            source=source,
            data=data or {},
            tags=tags or [],
        )

    def create_alert_from_template(
        self,
        template_name: str,
        context: Dict[str, Any],
        priority: Optional[AlertPriority] = None,
        source: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[Alert]:
        """Create an alert from a template.

        Args:
            template_name: Name of template to use
            context: Template variables
            priority: Override priority
            source: Alert source
            tags: Alert tags

        Returns:
            Created alert or None if template not found
        """
        template = self.templates.get(template_name)
        if not template:
            logger.warning(f"Template not found: {template_name}")
            return None

        # Add category and title to context for default template
        context.setdefault("category", template.category.value if template.category else "SYSTEM")
        context.setdefault("title", template_name)

        title, body = template.render(context)

        return Alert(
            title=title,
            message=body,
            priority=priority or AlertPriority.MEDIUM,
            category=template.category or AlertCategory.SYSTEM,
            source=source,
            data=context,
            tags=tags or [],
        )

    def _check_rate_limit(self, alert: Alert) -> bool:
        """Check if alert is rate-limited.

        Args:
            alert: Alert to check

        Returns:
            True if rate-limited
        """
        config = self.config.rate_limit_config
        key = alert.category.value

        now = datetime.now()

        # Initialize if needed
        if key not in self._rate_limit_state:
            self._rate_limit_state[key] = []

        # Clean old entries
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        self._rate_limit_state[key] = [
            ts for ts in self._rate_limit_state[key]
            if ts > hour_ago
        ]

        # Count recent alerts
        minute_count = sum(1 for ts in self._rate_limit_state[key] if ts > minute_ago)
        hour_count = len(self._rate_limit_state[key])

        if minute_count >= config.max_alerts_per_minute:
            return True
        if hour_count >= config.max_alerts_per_hour:
            return True

        return False

    def _check_duplicate(self, alert: Alert) -> bool:
        """Check if alert is a duplicate.

        Args:
            alert: Alert to check

        Returns:
            True if duplicate
        """
        if not self.config.rate_limit_config.enable_deduplication:
            return False

        content_hash = alert.content_hash
        now = datetime.now()
        window = timedelta(
            seconds=self.config.rate_limit_config.dedupe_window_seconds
        )

        # Clean old hashes
        self._seen_hashes = {
            h: ts for h, ts in self._seen_hashes.items()
            if now - ts < window
        }

        if content_hash in self._seen_hashes:
            return True

        self._seen_hashes[content_hash] = now
        return False

    def _get_target_channels(self, alert: Alert) -> Set[ChannelType]:
        """Get channels to route alert to.

        Args:
            alert: Alert to route

        Returns:
            Set of channel types
        """
        channels: Set[ChannelType] = set()

        # Check routing rules
        for rule in self.routing_rules:
            if rule.matches(alert):
                channels.update(rule.channels)

        # Add default channels if no rules matched
        if not channels:
            channels.update(self.config.default_channels)

        return channels

    def send(self, alert: Alert) -> List[DeliveryResult]:
        """Send an alert synchronously.

        Args:
            alert: Alert to send

        Returns:
            List of delivery results
        """
        return asyncio.run(self.send_async(alert))

    async def send_async(self, alert: Alert) -> List[DeliveryResult]:
        """Send an alert asynchronously.

        Args:
            alert: Alert to send

        Returns:
            List of delivery results
        """
        results: List[DeliveryResult] = []

        # Check rate limit
        if self._check_rate_limit(alert):
            alert.status = AlertStatus.RATE_LIMITED
            self._stats.total_rate_limited += 1
            logger.warning(f"Alert rate-limited: {alert.title}")
            return results

        # Check duplicate
        if self._check_duplicate(alert):
            alert.status = AlertStatus.SUPPRESSED
            self._stats.total_suppressed += 1
            logger.debug(f"Duplicate alert suppressed: {alert.title}")
            return results

        # Get target channels
        target_channels = self._get_target_channels(alert)

        # Record for rate limiting
        self._rate_limit_state.setdefault(alert.category.value, []).append(
            datetime.now()
        )

        # Update status
        alert.status = AlertStatus.SENDING

        # Send to each channel
        for channel_type in target_channels:
            channel = self.channels.get(channel_type)
            if not channel or not channel.is_available:
                continue

            result = await self._deliver_to_channel(alert, channel)
            results.append(result)

            if result.success:
                alert.channels_sent.append(channel_type)
                self._stats.by_channel[channel_type.value] = (
                    self._stats.by_channel.get(channel_type.value, 0) + 1
                )

        # Update final status
        if any(r.success for r in results):
            alert.status = AlertStatus.DELIVERED
            self._stats.total_sent += 1
        elif results:
            alert.status = AlertStatus.FAILED
            self._stats.total_failed += 1
            alert.last_error = results[-1].error_message

        # Update stats
        self._stats.by_priority[alert.priority.value] = (
            self._stats.by_priority.get(alert.priority.value, 0) + 1
        )
        self._stats.by_category[alert.category.value] = (
            self._stats.by_category.get(alert.category.value, 0) + 1
        )

        # Store history
        if self.config.store_history:
            self._add_to_history(alert)

        # Store results
        self._delivery_results.extend(results)

        return results

    async def _deliver_to_channel(
        self,
        alert: Alert,
        channel: AlertChannel,
    ) -> DeliveryResult:
        """Deliver alert to a specific channel.

        Args:
            alert: Alert to deliver
            channel: Channel to use

        Returns:
            Delivery result
        """
        result = DeliveryResult(
            alert_id=alert.alert_id,
            channel=channel.channel_type,
        )

        try:
            alert.delivery_attempts += 1
            success = await channel.send(alert)
            result.success = success

            if not success:
                result.error_message = "Channel returned failure"

        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error(f"Error delivering to {channel.channel_type.value}: {e}")

        return result

    def _add_to_history(self, alert: Alert) -> None:
        """Add alert to history.

        Args:
            alert: Alert to add
        """
        self._history.append(alert)

        # Trim history if needed
        max_size = self.config.max_history_size
        if len(self._history) > max_size:
            self._history = self._history[-max_size:]

    def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: ID of alert to acknowledge
            acknowledged_by: Who is acknowledging

        Returns:
            True if acknowledged
        """
        for alert in self._history:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_by = acknowledged_by
                alert.acknowledged_at = datetime.now()
                return True
        return False

    def get_history(
        self,
        category: Optional[AlertCategory] = None,
        priority: Optional[AlertPriority] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Get alert history.

        Args:
            category: Filter by category
            priority: Filter by priority
            since: Filter by timestamp
            limit: Maximum results

        Returns:
            List of alerts
        """
        alerts = self._history

        if category:
            alerts = [a for a in alerts if a.category == category]

        if priority:
            alerts = [a for a in alerts if a.priority == priority]

        if since:
            alerts = [a for a in alerts if a.timestamp >= since]

        # Return most recent first
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_unacknowledged(
        self,
        priority: Optional[AlertPriority] = None,
    ) -> List[Alert]:
        """Get unacknowledged alerts.

        Args:
            priority: Filter by priority

        Returns:
            List of unacknowledged alerts
        """
        alerts = [a for a in self._history if not a.acknowledged]

        if priority:
            alerts = [a for a in alerts if a.priority == priority]

        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_stats(self) -> AlertStats:
        """Get alert statistics.

        Returns:
            Current statistics
        """
        return self._stats

    def clear_history(self) -> int:
        """Clear alert history.

        Returns:
            Number of alerts cleared
        """
        count = len(self._history)
        self._history.clear()
        self._delivery_results.clear()
        return count

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = AlertStats()

    # ========================================================================
    # Convenience Methods
    # ========================================================================

    def alert_trade(
        self,
        symbol: str,
        action: str,
        price: Decimal,
        reason: str = "",
        priority: AlertPriority = AlertPriority.MEDIUM,
    ) -> Alert:
        """Send a trade alert.

        Args:
            symbol: Trading symbol
            action: Action (buy/sell)
            price: Trade price
            reason: Reason for trade
            priority: Alert priority

        Returns:
            Sent alert
        """
        alert = self.create_alert_from_template(
            "trade_signal",
            {
                "symbol": symbol,
                "action": action,
                "price": str(price),
                "reason": reason,
            },
            priority=priority,
            source="trade_alert",
        )

        if alert:
            self.send(alert)
            return alert

        # Fallback if template not found
        return self.create_alert(
            title=f"Trade Signal: {action} {symbol}",
            message=f"Price: {price}, Reason: {reason}",
            priority=priority,
            category=AlertCategory.TRADE,
        )

    def alert_risk(
        self,
        risk_type: str,
        current_value: Any,
        limit_value: Any,
        priority: AlertPriority = AlertPriority.HIGH,
    ) -> Alert:
        """Send a risk alert.

        Args:
            risk_type: Type of risk
            current_value: Current risk value
            limit_value: Limit value
            priority: Alert priority

        Returns:
            Sent alert
        """
        alert = self.create_alert_from_template(
            "risk_breach",
            {
                "risk_type": risk_type,
                "current_value": str(current_value),
                "limit_value": str(limit_value),
            },
            priority=priority,
            source="risk_alert",
        )

        if alert:
            self.send(alert)
            return alert

        return self.create_alert(
            title=f"Risk Breach: {risk_type}",
            message=f"Current: {current_value}, Limit: {limit_value}",
            priority=priority,
            category=AlertCategory.RISK,
        )

    def alert_execution(
        self,
        order_id: str,
        symbol: str,
        status: str,
        quantity: Decimal,
        price: Decimal,
        priority: AlertPriority = AlertPriority.MEDIUM,
    ) -> Alert:
        """Send an execution alert.

        Args:
            order_id: Order ID
            symbol: Trading symbol
            status: Order status
            quantity: Order quantity
            price: Execution price
            priority: Alert priority

        Returns:
            Sent alert
        """
        alert = self.create_alert_from_template(
            "order_executed",
            {
                "order_id": order_id,
                "symbol": symbol,
                "status": status,
                "quantity": str(quantity),
                "price": str(price),
            },
            priority=priority,
            source="execution_alert",
        )

        if alert:
            self.send(alert)
            return alert

        return self.create_alert(
            title=f"Order {status}: {order_id}",
            message=f"Symbol: {symbol}, Qty: {quantity}, Price: {price}",
            priority=priority,
            category=AlertCategory.EXECUTION,
        )
