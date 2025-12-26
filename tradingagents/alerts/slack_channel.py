"""Slack Channel for alert notifications.

This module provides Slack integration for alerts including:
- Webhook-based message delivery
- Rich message formatting with blocks
- Priority-based styling
- Rate limiting and retry logic

Issue #40: [ALERT-39] Slack channel - webhooks

Design Principles:
    - Non-blocking async delivery
    - Rich Slack Block Kit formatting
    - Configurable webhook endpoints
    - Graceful error handling
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import json
import logging
import urllib.request
import urllib.error

from .alert_manager import (
    Alert,
    AlertPriority,
    AlertCategory,
    ChannelType,
)


# ============================================================================
# Logging Setup
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class SlackMessageStyle(str, Enum):
    """Slack message styling options."""
    SIMPLE = "simple"      # Plain text message
    BLOCKS = "blocks"      # Rich Block Kit formatting
    ATTACHMENT = "attachment"  # Legacy attachment format


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SlackConfig:
    """Configuration for Slack channel.

    Attributes:
        webhook_url: Slack incoming webhook URL
        channel: Override channel (optional)
        username: Bot username (optional)
        icon_emoji: Bot icon emoji (optional)
        icon_url: Bot icon URL (optional)
        style: Message formatting style
        include_timestamp: Include timestamp in messages
        include_source: Include alert source
        mention_on_critical: Mention users for critical alerts
        mention_users: Users to mention for critical alerts
        retry_count: Number of retries on failure
        retry_delay_seconds: Delay between retries
        timeout_seconds: Request timeout
    """
    webhook_url: str = ""
    channel: Optional[str] = None
    username: str = "TradingAgents Alert"
    icon_emoji: str = ":chart_with_upwards_trend:"
    icon_url: Optional[str] = None
    style: SlackMessageStyle = SlackMessageStyle.BLOCKS
    include_timestamp: bool = True
    include_source: bool = True
    mention_on_critical: bool = True
    mention_users: List[str] = field(default_factory=list)
    retry_count: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: int = 30


@dataclass
class SlackMessageResult:
    """Result of Slack message send.

    Attributes:
        success: Whether message was sent
        status_code: HTTP status code
        response_body: Response body
        error_message: Error message if failed
        attempts: Number of attempts made
        latency_ms: Total latency in milliseconds
    """
    success: bool = False
    status_code: int = 0
    response_body: str = ""
    error_message: str = ""
    attempts: int = 0
    latency_ms: float = 0.0


# ============================================================================
# Slack Message Formatter
# ============================================================================

class SlackMessageFormatter:
    """Formats alerts for Slack messages."""

    # Priority to color mapping
    PRIORITY_COLORS = {
        AlertPriority.LOW: "#36a64f",       # Green
        AlertPriority.MEDIUM: "#ffcc00",    # Yellow
        AlertPriority.HIGH: "#ff9900",      # Orange
        AlertPriority.CRITICAL: "#ff0000",  # Red
    }

    # Priority to emoji mapping
    PRIORITY_EMOJIS = {
        AlertPriority.LOW: ":information_source:",
        AlertPriority.MEDIUM: ":warning:",
        AlertPriority.HIGH: ":exclamation:",
        AlertPriority.CRITICAL: ":rotating_light:",
    }

    # Category to emoji mapping
    CATEGORY_EMOJIS = {
        AlertCategory.TRADE: ":chart_with_upwards_trend:",
        AlertCategory.RISK: ":shield:",
        AlertCategory.SYSTEM: ":gear:",
        AlertCategory.MARKET: ":bar_chart:",
        AlertCategory.PORTFOLIO: ":moneybag:",
        AlertCategory.EXECUTION: ":zap:",
        AlertCategory.COMPLIANCE: ":memo:",
    }

    @classmethod
    def format_simple(cls, alert: Alert, config: SlackConfig) -> Dict[str, Any]:
        """Format alert as simple text message.

        Args:
            alert: Alert to format
            config: Slack configuration

        Returns:
            Slack message payload
        """
        emoji = cls.PRIORITY_EMOJIS.get(alert.priority, ":bell:")
        category_emoji = cls.CATEGORY_EMOJIS.get(alert.category, ":bell:")

        text_parts = [
            f"{emoji} *{alert.title}*",
            "",
            alert.message,
        ]

        if config.include_source and alert.source:
            text_parts.append(f"_Source: {alert.source}_")

        if config.include_timestamp:
            text_parts.append(f"_Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}_")

        # Add mention for critical alerts
        if config.mention_on_critical and alert.priority == AlertPriority.CRITICAL:
            mentions = " ".join(f"<@{user}>" for user in config.mention_users)
            if mentions:
                text_parts.insert(0, mentions)

        payload: Dict[str, Any] = {
            "text": "\n".join(text_parts),
        }

        if config.username:
            payload["username"] = config.username

        if config.icon_emoji:
            payload["icon_emoji"] = config.icon_emoji
        elif config.icon_url:
            payload["icon_url"] = config.icon_url

        if config.channel:
            payload["channel"] = config.channel

        return payload

    @classmethod
    def format_blocks(cls, alert: Alert, config: SlackConfig) -> Dict[str, Any]:
        """Format alert with Slack Block Kit.

        Args:
            alert: Alert to format
            config: Slack configuration

        Returns:
            Slack message payload with blocks
        """
        emoji = cls.PRIORITY_EMOJIS.get(alert.priority, ":bell:")
        color = cls.PRIORITY_COLORS.get(alert.priority, "#808080")
        category_emoji = cls.CATEGORY_EMOJIS.get(alert.category, ":bell:")

        blocks = []

        # Header section with critical mention
        header_text = f"{emoji} *{alert.title}*"
        if config.mention_on_critical and alert.priority == AlertPriority.CRITICAL:
            mentions = " ".join(f"<@{user}>" for user in config.mention_users)
            if mentions:
                header_text = f"{mentions}\n{header_text}"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": header_text,
            },
        })

        # Message body
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": alert.message,
            },
        })

        # Context fields
        context_elements = []

        # Category badge
        context_elements.append({
            "type": "mrkdwn",
            "text": f"{category_emoji} *{alert.category.value.upper()}*",
        })

        # Priority badge
        priority_text = {
            AlertPriority.LOW: "LOW",
            AlertPriority.MEDIUM: "MEDIUM",
            AlertPriority.HIGH: "HIGH",
            AlertPriority.CRITICAL: ":fire: CRITICAL :fire:",
        }.get(alert.priority, "UNKNOWN")

        context_elements.append({
            "type": "mrkdwn",
            "text": f"*Priority:* {priority_text}",
        })

        if config.include_source and alert.source:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Source:* {alert.source}",
            })

        if config.include_timestamp:
            context_elements.append({
                "type": "mrkdwn",
                "text": f"*Time:* {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            })

        if context_elements:
            blocks.append({
                "type": "context",
                "elements": context_elements,
            })

        # Add divider
        blocks.append({"type": "divider"})

        # Add data fields if present
        if alert.data:
            fields_text = []
            for key, value in list(alert.data.items())[:10]:  # Limit to 10 fields
                fields_text.append(f"*{key}:* {value}")

            if fields_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(fields_text),
                    },
                })

        payload: Dict[str, Any] = {
            "blocks": blocks,
            "text": f"{emoji} {alert.title}",  # Fallback text
        }

        # Add attachment for color
        payload["attachments"] = [{
            "color": color,
            "blocks": blocks,
        }]
        # Remove blocks from top level when using attachments
        del payload["blocks"]

        if config.username:
            payload["username"] = config.username

        if config.icon_emoji:
            payload["icon_emoji"] = config.icon_emoji
        elif config.icon_url:
            payload["icon_url"] = config.icon_url

        if config.channel:
            payload["channel"] = config.channel

        return payload

    @classmethod
    def format_attachment(cls, alert: Alert, config: SlackConfig) -> Dict[str, Any]:
        """Format alert with legacy attachment format.

        Args:
            alert: Alert to format
            config: Slack configuration

        Returns:
            Slack message payload with attachments
        """
        emoji = cls.PRIORITY_EMOJIS.get(alert.priority, ":bell:")
        color = cls.PRIORITY_COLORS.get(alert.priority, "#808080")

        fields = []

        fields.append({
            "title": "Category",
            "value": alert.category.value.upper(),
            "short": True,
        })

        fields.append({
            "title": "Priority",
            "value": alert.priority.value.upper(),
            "short": True,
        })

        if config.include_source and alert.source:
            fields.append({
                "title": "Source",
                "value": alert.source,
                "short": True,
            })

        if alert.tags:
            fields.append({
                "title": "Tags",
                "value": ", ".join(alert.tags),
                "short": True,
            })

        # Add data fields
        for key, value in list(alert.data.items())[:6]:
            fields.append({
                "title": key,
                "value": str(value),
                "short": True,
            })

        attachment = {
            "color": color,
            "pretext": f"{emoji} *{alert.title}*",
            "text": alert.message,
            "fields": fields,
            "footer": "TradingAgents Alert System",
            "ts": int(alert.timestamp.timestamp()),
        }

        # Add mention for critical alerts
        if config.mention_on_critical and alert.priority == AlertPriority.CRITICAL:
            mentions = " ".join(f"<@{user}>" for user in config.mention_users)
            if mentions:
                attachment["pretext"] = f"{mentions}\n{attachment['pretext']}"

        payload: Dict[str, Any] = {
            "attachments": [attachment],
            "text": f"{emoji} {alert.title}",  # Fallback text
        }

        if config.username:
            payload["username"] = config.username

        if config.icon_emoji:
            payload["icon_emoji"] = config.icon_emoji
        elif config.icon_url:
            payload["icon_url"] = config.icon_url

        if config.channel:
            payload["channel"] = config.channel

        return payload

    @classmethod
    def format(cls, alert: Alert, config: SlackConfig) -> Dict[str, Any]:
        """Format alert based on configured style.

        Args:
            alert: Alert to format
            config: Slack configuration

        Returns:
            Slack message payload
        """
        if config.style == SlackMessageStyle.SIMPLE:
            return cls.format_simple(alert, config)
        elif config.style == SlackMessageStyle.BLOCKS:
            return cls.format_blocks(alert, config)
        elif config.style == SlackMessageStyle.ATTACHMENT:
            return cls.format_attachment(alert, config)
        else:
            return cls.format_simple(alert, config)


# ============================================================================
# SlackChannel Class
# ============================================================================

class SlackChannel:
    """Slack channel for alert delivery.

    Implements the AlertChannel protocol for integration
    with AlertManager.

    Attributes:
        config: Slack channel configuration
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        config: Optional[SlackConfig] = None,
    ):
        """Initialize Slack channel.

        Args:
            webhook_url: Slack webhook URL (overrides config)
            config: Full configuration (optional)
        """
        self.config = config or SlackConfig()

        if webhook_url:
            self.config.webhook_url = webhook_url

        self._formatter = SlackMessageFormatter()

    @property
    def channel_type(self) -> ChannelType:
        """Get channel type."""
        return ChannelType.SLACK

    @property
    def is_available(self) -> bool:
        """Check if channel is available."""
        return bool(self.config.webhook_url)

    def validate_config(self) -> tuple[bool, str]:
        """Validate configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.config.webhook_url:
            return False, "Webhook URL is required"

        if not self.config.webhook_url.startswith("https://hooks.slack.com/"):
            return False, "Invalid Slack webhook URL format"

        return True, ""

    async def send(self, alert: Alert) -> bool:
        """Send alert to Slack.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully
        """
        result = await self.send_with_result(alert)
        return result.success

    async def send_with_result(self, alert: Alert) -> SlackMessageResult:
        """Send alert and return detailed result.

        Args:
            alert: Alert to send

        Returns:
            Detailed send result
        """
        result = SlackMessageResult()
        start_time = datetime.now()

        if not self.is_available:
            result.error_message = "Slack channel not configured"
            return result

        # Format message
        payload = self._formatter.format(alert, self.config)

        # Send with retries
        for attempt in range(self.config.retry_count):
            result.attempts = attempt + 1

            try:
                send_result = await self._send_webhook(payload)
                result.success = send_result.get("success", False)
                result.status_code = send_result.get("status_code", 0)
                result.response_body = send_result.get("body", "")

                if result.success:
                    break

                # Check if retryable
                if result.status_code >= 500:
                    # Server error - retry
                    if attempt < self.config.retry_count - 1:
                        await asyncio.sleep(self.config.retry_delay_seconds)
                    continue
                elif result.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = send_result.get("retry_after", 5)
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    # Client error - don't retry
                    result.error_message = f"HTTP {result.status_code}: {result.response_body}"
                    break

            except Exception as e:
                result.error_message = str(e)
                if attempt < self.config.retry_count - 1:
                    await asyncio.sleep(self.config.retry_delay_seconds)

        result.latency_ms = (datetime.now() - start_time).total_seconds() * 1000
        return result

    async def _send_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send payload to webhook.

        Args:
            payload: Message payload

        Returns:
            Result dict with success, status_code, body
        """
        # Run synchronous HTTP call in executor for async compatibility
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._send_webhook_sync,
            payload,
        )

    def _send_webhook_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send payload to webhook synchronously.

        Args:
            payload: Message payload

        Returns:
            Result dict with success, status_code, body
        """
        try:
            data = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                self.config.webhook_url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                },
            )

            with urllib.request.urlopen(
                req,
                timeout=self.config.timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
                return {
                    "success": response.status == 200,
                    "status_code": response.status,
                    "body": body,
                }

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            retry_after = e.headers.get("Retry-After", 5) if e.headers else 5
            return {
                "success": False,
                "status_code": e.code,
                "body": body,
                "retry_after": int(retry_after),
            }

        except urllib.error.URLError as e:
            return {
                "success": False,
                "status_code": 0,
                "body": str(e.reason),
            }

        except Exception as e:
            return {
                "success": False,
                "status_code": 0,
                "body": str(e),
            }

    def send_sync(self, alert: Alert) -> SlackMessageResult:
        """Send alert synchronously.

        Args:
            alert: Alert to send

        Returns:
            Send result
        """
        return asyncio.run(self.send_with_result(alert))

    def test_webhook(self) -> SlackMessageResult:
        """Send test message to verify webhook.

        Returns:
            Send result
        """
        test_alert = Alert(
            title="Test Alert",
            message="This is a test message from TradingAgents Alert System.",
            priority=AlertPriority.LOW,
            category=AlertCategory.SYSTEM,
            source="slack_channel_test",
            data={"test": True},
        )

        return self.send_sync(test_alert)


# ============================================================================
# Factory Functions
# ============================================================================

def create_slack_channel(
    webhook_url: str,
    channel: Optional[str] = None,
    username: str = "TradingAgents Alert",
    style: SlackMessageStyle = SlackMessageStyle.BLOCKS,
    mention_users: Optional[List[str]] = None,
) -> SlackChannel:
    """Create a configured Slack channel.

    Args:
        webhook_url: Slack webhook URL
        channel: Override channel name
        username: Bot username
        style: Message formatting style
        mention_users: Users to mention for critical alerts

    Returns:
        Configured SlackChannel
    """
    config = SlackConfig(
        webhook_url=webhook_url,
        channel=channel,
        username=username,
        style=style,
        mention_users=mention_users or [],
    )
    return SlackChannel(config=config)
