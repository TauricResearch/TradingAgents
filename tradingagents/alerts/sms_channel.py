"""SMS Channel for alert delivery via Twilio.

Issue #41: [ALERT-40] SMS channel - Twilio

This module provides SMS alert delivery using Twilio's API.

Classes:
    SMSConfig: Configuration for SMS channel
    SMSMessageResult: Result of SMS delivery
    SMSChannel: SMS channel implementing AlertChannel protocol

Functions:
    create_sms_channel: Factory function for creating SMS channels

Example:
    >>> from tradingagents.alerts import SMSChannel, Alert, AlertPriority
    >>>
    >>> # Create channel with credentials
    >>> sms = SMSChannel(
    ...     account_sid="ACxxxxx",
    ...     auth_token="your_token",
    ...     from_number="+15551234567",
    ...     to_numbers=["+15559876543"],
    ... )
    >>>
    >>> # Send alert
    >>> alert = Alert(
    ...     title="Trade Alert",
    ...     message="AAPL buy signal",
    ...     priority=AlertPriority.HIGH,
    ... )
    >>> await sms.send(alert)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Protocol
import asyncio
import base64
import json
import logging
import re
import time
import urllib.parse
import urllib.request

from .alert_manager import Alert, AlertPriority, AlertCategory, ChannelType


logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Standard SMS character limit
SMS_STANDARD_LIMIT = 160

# Unicode SMS limit (70 chars)
SMS_UNICODE_LIMIT = 70

# Max concatenated SMS segments
MAX_SMS_SEGMENTS = 4

# Twilio API base URL
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# E.164 phone number pattern
E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


# ============================================================================
# Enums
# ============================================================================

class SMSFormat(Enum):
    """SMS message format options."""

    PLAIN = "plain"  # Plain text
    COMPACT = "compact"  # Minimal format
    DETAILED = "detailed"  # Full details


class SMSStatus(Enum):
    """Twilio message status codes."""

    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    FAILED = "failed"
    CANCELED = "canceled"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SMSConfig:
    """Configuration for SMS channel.

    Attributes:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        from_number: Sender phone number (E.164 format)
        to_numbers: Recipient phone numbers (E.164 format)
        messaging_service_sid: Optional messaging service SID
        format: Message format style
        include_priority: Whether to include priority indicator
        include_timestamp: Whether to include timestamp
        max_length: Maximum message length (0 = no limit)
        retry_count: Number of retry attempts
        retry_delay_seconds: Delay between retries
        status_callback_url: URL for status webhooks
        priority_filter: Minimum priority to send (None = all)
    """

    account_sid: str = ""
    auth_token: str = ""
    from_number: str = ""
    to_numbers: list[str] = field(default_factory=list)
    messaging_service_sid: str = ""
    format: SMSFormat = SMSFormat.COMPACT
    include_priority: bool = True
    include_timestamp: bool = False
    max_length: int = 0  # 0 = no limit (allow multi-segment)
    retry_count: int = 2
    retry_delay_seconds: float = 1.0
    status_callback_url: str = ""
    priority_filter: Optional[AlertPriority] = None


@dataclass
class SMSMessageResult:
    """Result of SMS message send operation.

    Attributes:
        success: Whether the send was successful
        message_sid: Twilio message SID
        status: Message status
        to_number: Recipient number
        segments: Number of SMS segments used
        price: Message price (if available)
        error_code: Twilio error code (if failed)
        error_message: Error description
        attempts: Number of send attempts
        latency_ms: Total latency in milliseconds
        timestamp: When the result was created
    """

    success: bool = False
    message_sid: str = ""
    status: str = ""
    to_number: str = ""
    segments: int = 1
    price: Optional[str] = None
    error_code: Optional[int] = None
    error_message: str = ""
    attempts: int = 0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SMSBatchResult:
    """Result of batch SMS send operation.

    Attributes:
        success: Whether all sends were successful
        total_sent: Number of messages sent
        total_failed: Number of failed messages
        results: Individual results per recipient
        latency_ms: Total batch latency
    """

    success: bool = False
    total_sent: int = 0
    total_failed: int = 0
    results: list[SMSMessageResult] = field(default_factory=list)
    latency_ms: float = 0.0


# ============================================================================
# Message Formatter
# ============================================================================

class SMSMessageFormatter:
    """Formats alerts for SMS delivery."""

    # Priority indicators
    PRIORITY_INDICATORS: dict[AlertPriority, str] = {
        AlertPriority.LOW: "",
        AlertPriority.MEDIUM: "",
        AlertPriority.HIGH: "[!]",
        AlertPriority.CRITICAL: "[!!!]",
    }

    # Category prefixes (short for SMS)
    CATEGORY_PREFIXES: dict[AlertCategory, str] = {
        AlertCategory.TRADE: "TRD",
        AlertCategory.RISK: "RSK",
        AlertCategory.SYSTEM: "SYS",
        AlertCategory.MARKET: "MKT",
        AlertCategory.PORTFOLIO: "PRT",
        AlertCategory.EXECUTION: "EXE",
        AlertCategory.COMPLIANCE: "CMP",
    }

    @classmethod
    def format(cls, alert: Alert, config: SMSConfig) -> str:
        """Format alert for SMS.

        Args:
            alert: Alert to format
            config: SMS configuration

        Returns:
            Formatted message string
        """
        if config.format == SMSFormat.PLAIN:
            return cls.format_plain(alert, config)
        elif config.format == SMSFormat.COMPACT:
            return cls.format_compact(alert, config)
        else:
            return cls.format_detailed(alert, config)

    @classmethod
    def format_plain(cls, alert: Alert, config: SMSConfig) -> str:
        """Format as plain text.

        Args:
            alert: Alert to format
            config: SMS configuration

        Returns:
            Plain text message
        """
        parts = []

        # Priority indicator
        if config.include_priority:
            indicator = cls.PRIORITY_INDICATORS.get(alert.priority, "")
            if indicator:
                parts.append(indicator)

        # Title and message
        if alert.title:
            parts.append(alert.title)
        if alert.message:
            parts.append(alert.message)

        # Timestamp
        if config.include_timestamp:
            parts.append(f"({alert.timestamp.strftime('%H:%M')})")

        message = " ".join(parts)

        # Apply max length if set
        if config.max_length > 0 and len(message) > config.max_length:
            message = message[: config.max_length - 3] + "..."

        return message

    @classmethod
    def format_compact(cls, alert: Alert, config: SMSConfig) -> str:
        """Format as compact message (optimized for SMS).

        Args:
            alert: Alert to format
            config: SMS configuration

        Returns:
            Compact message string
        """
        parts = []

        # Priority + Category prefix
        priority_ind = cls.PRIORITY_INDICATORS.get(alert.priority, "")
        category_pre = cls.CATEGORY_PREFIXES.get(alert.category, "")

        prefix_parts = [p for p in [priority_ind, category_pre] if p]
        if prefix_parts:
            parts.append(" ".join(prefix_parts))

        # Title (shortened)
        if alert.title:
            title = alert.title
            if len(title) > 30:
                title = title[:27] + "..."
            parts.append(title)

        # Message (shortened)
        if alert.message:
            msg = alert.message
            # Leave room for other parts
            max_msg_len = SMS_STANDARD_LIMIT - sum(len(p) for p in parts) - len(parts) - 10
            if max_msg_len > 0 and len(msg) > max_msg_len:
                msg = msg[: max_msg_len - 3] + "..."
            parts.append(msg)

        # Key data fields (if space allows)
        if alert.data:
            remaining = SMS_STANDARD_LIMIT - sum(len(p) for p in parts) - len(parts)
            if remaining > 20:
                data_parts = []
                for key, value in list(alert.data.items())[:2]:
                    data_str = f"{key}:{value}"
                    if len(data_str) <= remaining:
                        data_parts.append(data_str)
                        remaining -= len(data_str) + 1
                if data_parts:
                    parts.append(" ".join(data_parts))

        message = " - ".join(parts)

        # Apply max length if set
        if config.max_length > 0 and len(message) > config.max_length:
            message = message[: config.max_length - 3] + "..."

        return message

    @classmethod
    def format_detailed(cls, alert: Alert, config: SMSConfig) -> str:
        """Format with full details (may use multiple segments).

        Args:
            alert: Alert to format
            config: SMS configuration

        Returns:
            Detailed message string
        """
        lines = []

        # Priority indicator
        if config.include_priority:
            indicator = cls.PRIORITY_INDICATORS.get(alert.priority, "")
            priority_name = alert.priority.name.upper()
            if indicator:
                lines.append(f"{indicator} {priority_name}")
            else:
                lines.append(priority_name)

        # Category
        lines.append(f"[{alert.category.name}]")

        # Title
        if alert.title:
            lines.append(alert.title)

        # Message
        if alert.message:
            lines.append(alert.message)

        # Data fields
        if alert.data:
            for key, value in alert.data.items():
                lines.append(f"{key}: {value}")

        # Source
        if alert.source:
            lines.append(f"Source: {alert.source}")

        # Timestamp
        if config.include_timestamp:
            lines.append(f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        message = "\n".join(lines)

        # Apply max length if set (with segment consideration)
        max_len = config.max_length if config.max_length > 0 else SMS_STANDARD_LIMIT * MAX_SMS_SEGMENTS
        if len(message) > max_len:
            message = message[: max_len - 3] + "..."

        return message

    @classmethod
    def count_segments(cls, message: str) -> int:
        """Count SMS segments needed for message.

        Args:
            message: Message text

        Returns:
            Number of SMS segments
        """
        # Check for non-GSM characters (requires Unicode encoding)
        gsm_chars = set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )

        is_unicode = not all(c in gsm_chars for c in message)

        if is_unicode:
            # Unicode: 70 chars per segment, 67 for concatenated
            if len(message) <= SMS_UNICODE_LIMIT:
                return 1
            return (len(message) + 66) // 67
        else:
            # GSM-7: 160 chars per segment, 153 for concatenated
            if len(message) <= SMS_STANDARD_LIMIT:
                return 1
            return (len(message) + 152) // 153


# ============================================================================
# SMS Channel
# ============================================================================

class SMSChannel:
    """SMS alert channel using Twilio.

    Implements the AlertChannel protocol for SMS delivery.

    Attributes:
        config: SMS channel configuration
        channel_type: Always ChannelType.SMS
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
        to_numbers: Optional[list[str]] = None,
        *,
        config: Optional[SMSConfig] = None,
    ):
        """Initialize SMS channel.

        Args:
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
            from_number: Sender phone number
            to_numbers: List of recipient numbers
            config: Optional full configuration (overrides other args)
        """
        if config is not None:
            self.config = config
        else:
            self.config = SMSConfig(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                to_numbers=to_numbers or [],
            )

    @property
    def channel_type(self) -> ChannelType:
        """Get channel type."""
        return ChannelType.SMS

    @property
    def is_available(self) -> bool:
        """Check if channel is available."""
        return bool(
            self.config.account_sid
            and self.config.auth_token
            and (self.config.from_number or self.config.messaging_service_sid)
            and self.config.to_numbers
        )

    def validate_config(self) -> tuple[bool, str]:
        """Validate channel configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.config.account_sid:
            return False, "Account SID is required"

        if not self.config.auth_token:
            return False, "Auth token is required"

        if not self.config.from_number and not self.config.messaging_service_sid:
            return False, "From number or messaging service SID is required"

        if self.config.from_number and not E164_PATTERN.match(self.config.from_number):
            return False, f"Invalid from number format: {self.config.from_number}. Use E.164 format (+15551234567)"

        if not self.config.to_numbers:
            return False, "At least one recipient number is required"

        for number in self.config.to_numbers:
            if not E164_PATTERN.match(number):
                return False, f"Invalid phone number format: {number}. Use E.164 format (+15551234567)"

        return True, ""

    def _should_send(self, alert: Alert) -> bool:
        """Check if alert should be sent based on priority filter.

        Args:
            alert: Alert to check

        Returns:
            True if alert should be sent
        """
        if self.config.priority_filter is None:
            return True

        priority_order = [
            AlertPriority.LOW,
            AlertPriority.MEDIUM,
            AlertPriority.HIGH,
            AlertPriority.CRITICAL,
        ]

        alert_idx = priority_order.index(alert.priority)
        filter_idx = priority_order.index(self.config.priority_filter)

        return alert_idx >= filter_idx

    async def send(self, alert: Alert) -> bool:
        """Send alert via SMS.

        Args:
            alert: Alert to send

        Returns:
            True if all messages sent successfully
        """
        result = await self.send_batch(alert)
        return result.success

    async def send_with_result(self, alert: Alert, to_number: Optional[str] = None) -> SMSMessageResult:
        """Send alert to a single number with detailed result.

        Args:
            alert: Alert to send
            to_number: Recipient number (uses first configured if not specified)

        Returns:
            SMSMessageResult with delivery details
        """
        start_time = time.time()

        if not self.is_available:
            return SMSMessageResult(
                success=False,
                error_message="SMS channel not configured",
                latency_ms=(time.time() - start_time) * 1000,
            )

        if not self._should_send(alert):
            return SMSMessageResult(
                success=False,
                error_message=f"Alert priority {alert.priority.name} below filter threshold",
                latency_ms=(time.time() - start_time) * 1000,
            )

        target_number = to_number or self.config.to_numbers[0]
        message = SMSMessageFormatter.format(alert, self.config)

        attempt = 0
        last_error = ""

        while attempt < self.config.retry_count + 1:
            attempt += 1

            try:
                result = await self._send_twilio_message(target_number, message)

                if result.get("success"):
                    return SMSMessageResult(
                        success=True,
                        message_sid=result.get("sid", ""),
                        status=result.get("status", ""),
                        to_number=target_number,
                        segments=SMSMessageFormatter.count_segments(message),
                        price=result.get("price"),
                        attempts=attempt,
                        latency_ms=(time.time() - start_time) * 1000,
                    )

                error_code = result.get("error_code")
                last_error = result.get("error_message", "Unknown error")

                # Don't retry on client errors (4xx)
                if error_code and 400 <= error_code < 500:
                    break

                # Retry on server errors
                if attempt < self.config.retry_count + 1:
                    await asyncio.sleep(self.config.retry_delay_seconds * attempt)

            except Exception as e:
                last_error = str(e)
                logger.warning(f"SMS send attempt {attempt} failed: {e}")

                if attempt < self.config.retry_count + 1:
                    await asyncio.sleep(self.config.retry_delay_seconds * attempt)

        return SMSMessageResult(
            success=False,
            to_number=target_number,
            error_message=last_error,
            attempts=attempt,
            latency_ms=(time.time() - start_time) * 1000,
        )

    async def send_batch(self, alert: Alert) -> SMSBatchResult:
        """Send alert to all configured recipients.

        Args:
            alert: Alert to send

        Returns:
            SMSBatchResult with all delivery results
        """
        start_time = time.time()

        if not self.is_available:
            return SMSBatchResult(
                success=False,
                results=[
                    SMSMessageResult(
                        success=False,
                        error_message="SMS channel not configured",
                    )
                ],
            )

        if not self._should_send(alert):
            return SMSBatchResult(
                success=False,
                results=[
                    SMSMessageResult(
                        success=False,
                        error_message=f"Alert priority below filter threshold",
                    )
                ],
            )

        # Send to all recipients concurrently
        tasks = [
            self.send_with_result(alert, to_number=number)
            for number in self.config.to_numbers
        ]

        results = await asyncio.gather(*tasks)

        total_sent = sum(1 for r in results if r.success)
        total_failed = sum(1 for r in results if not r.success)

        return SMSBatchResult(
            success=total_failed == 0,
            total_sent=total_sent,
            total_failed=total_failed,
            results=list(results),
            latency_ms=(time.time() - start_time) * 1000,
        )

    async def _send_twilio_message(self, to_number: str, message: str) -> dict[str, Any]:
        """Send message via Twilio API.

        Args:
            to_number: Recipient phone number
            message: Message text

        Returns:
            API response dict
        """
        # Build request
        url = f"{TWILIO_API_BASE}/Accounts/{self.config.account_sid}/Messages.json"

        data = {
            "To": to_number,
            "Body": message,
        }

        if self.config.messaging_service_sid:
            data["MessagingServiceSid"] = self.config.messaging_service_sid
        else:
            data["From"] = self.config.from_number

        if self.config.status_callback_url:
            data["StatusCallback"] = self.config.status_callback_url

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_request, url, data)

    def _send_request(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        """Send HTTP request to Twilio (sync).

        Args:
            url: Request URL
            data: Form data

        Returns:
            Response dict
        """
        try:
            # Encode credentials
            credentials = f"{self.config.account_sid}:{self.config.auth_token}"
            encoded_creds = base64.b64encode(credentials.encode()).decode()

            # Build request
            encoded_data = urllib.parse.urlencode(data).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=encoded_data,
                method="POST",
                headers={
                    "Authorization": f"Basic {encoded_creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            # Send request
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body)

                return {
                    "success": True,
                    "sid": result.get("sid"),
                    "status": result.get("status"),
                    "price": result.get("price"),
                    "num_segments": result.get("num_segments"),
                }

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                error_data = json.loads(body)
                return {
                    "success": False,
                    "error_code": e.code,
                    "error_message": error_data.get("message", str(e)),
                    "twilio_code": error_data.get("code"),
                }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error_code": e.code,
                    "error_message": str(e),
                }

        except urllib.error.URLError as e:
            return {
                "success": False,
                "error_code": 0,
                "error_message": f"Network error: {e.reason}",
            }

        except Exception as e:
            return {
                "success": False,
                "error_code": 0,
                "error_message": str(e),
            }

    def _send_request_sync(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        """Alias for sync request (for testing)."""
        return self._send_request(url, data)

    def test_connection(self) -> SMSMessageResult:
        """Test Twilio connection by fetching account info.

        Returns:
            SMSMessageResult indicating success/failure
        """
        start_time = time.time()

        if not self.config.account_sid or not self.config.auth_token:
            return SMSMessageResult(
                success=False,
                error_message="Account SID and Auth Token required",
                latency_ms=(time.time() - start_time) * 1000,
            )

        try:
            url = f"{TWILIO_API_BASE}/Accounts/{self.config.account_sid}.json"

            credentials = f"{self.config.account_sid}:{self.config.auth_token}"
            encoded_creds = base64.b64encode(credentials.encode()).decode()

            request = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "Authorization": f"Basic {encoded_creds}",
                },
            )

            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8")
                result = json.loads(body)

                return SMSMessageResult(
                    success=True,
                    status=result.get("status", "active"),
                    latency_ms=(time.time() - start_time) * 1000,
                )

        except urllib.error.HTTPError as e:
            return SMSMessageResult(
                success=False,
                error_code=e.code,
                error_message=f"Authentication failed: {e.code}",
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return SMSMessageResult(
                success=False,
                error_message=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )


# ============================================================================
# Factory Functions
# ============================================================================

def create_sms_channel(
    account_sid: str,
    auth_token: str,
    from_number: str = "",
    to_numbers: Optional[list[str]] = None,
    *,
    messaging_service_sid: str = "",
    format: SMSFormat = SMSFormat.COMPACT,
    include_priority: bool = True,
    include_timestamp: bool = False,
    max_length: int = 0,
    retry_count: int = 2,
    priority_filter: Optional[AlertPriority] = None,
    status_callback_url: str = "",
) -> SMSChannel:
    """Create an SMS channel with configuration.

    Args:
        account_sid: Twilio Account SID
        auth_token: Twilio Auth Token
        from_number: Sender phone number (E.164 format)
        to_numbers: List of recipient numbers
        messaging_service_sid: Optional messaging service SID
        format: Message format style
        include_priority: Include priority in message
        include_timestamp: Include timestamp in message
        max_length: Maximum message length
        retry_count: Number of retry attempts
        priority_filter: Minimum priority to send
        status_callback_url: URL for status webhooks

    Returns:
        Configured SMSChannel instance
    """
    config = SMSConfig(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        to_numbers=to_numbers or [],
        messaging_service_sid=messaging_service_sid,
        format=format,
        include_priority=include_priority,
        include_timestamp=include_timestamp,
        max_length=max_length,
        retry_count=retry_count,
        priority_filter=priority_filter,
        status_callback_url=status_callback_url,
    )

    return SMSChannel(config=config)
