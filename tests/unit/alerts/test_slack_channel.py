"""Tests for Slack Channel.

Issue #40: [ALERT-39] Slack channel - webhooks
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from tradingagents.alerts.slack_channel import (
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
from tradingagents.alerts.alert_manager import (
    Alert,
    AlertPriority,
    AlertCategory,
    ChannelType,
)


# ============================================================================
# Enum Tests
# ============================================================================

class TestSlackMessageStyle:
    """Tests for SlackMessageStyle enum."""

    def test_all_styles_defined(self):
        """Verify all styles exist."""
        assert SlackMessageStyle.SIMPLE
        assert SlackMessageStyle.BLOCKS
        assert SlackMessageStyle.ATTACHMENT

    def test_style_values(self):
        """Verify style values."""
        assert SlackMessageStyle.SIMPLE.value == "simple"
        assert SlackMessageStyle.BLOCKS.value == "blocks"


# ============================================================================
# Data Class Tests
# ============================================================================

class TestSlackConfig:
    """Tests for SlackConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = SlackConfig()
        assert config.webhook_url == ""
        assert config.username == "TradingAgents Alert"
        assert config.icon_emoji == ":chart_with_upwards_trend:"
        assert config.style == SlackMessageStyle.BLOCKS

    def test_custom_config(self):
        """Test creating custom config."""
        config = SlackConfig(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
            username="CustomBot",
        )
        assert config.webhook_url == "https://hooks.slack.com/test"
        assert config.channel == "#alerts"
        assert config.username == "CustomBot"


class TestSlackMessageResult:
    """Tests for SlackMessageResult dataclass."""

    def test_default_creation(self):
        """Test creating result with defaults."""
        result = SlackMessageResult()
        assert result.success is False
        assert result.status_code == 0
        assert result.attempts == 0


# ============================================================================
# Formatter Tests
# ============================================================================

class TestSlackMessageFormatter:
    """Tests for SlackMessageFormatter."""

    @pytest.fixture
    def alert(self):
        """Create test alert."""
        return Alert(
            title="Test Alert",
            message="This is a test message",
            priority=AlertPriority.MEDIUM,
            category=AlertCategory.TRADE,
            source="test",
            data={"symbol": "AAPL", "price": "150.00"},
        )

    @pytest.fixture
    def config(self):
        """Create test config."""
        return SlackConfig(
            webhook_url="https://hooks.slack.com/test",
            username="TestBot",
        )

    def test_format_simple(self, alert, config):
        """Test simple format."""
        config.style = SlackMessageStyle.SIMPLE
        payload = SlackMessageFormatter.format_simple(alert, config)

        assert "text" in payload
        assert "Test Alert" in payload["text"]
        assert "This is a test message" in payload["text"]
        assert payload.get("username") == "TestBot"

    def test_format_blocks(self, alert, config):
        """Test blocks format."""
        config.style = SlackMessageStyle.BLOCKS
        payload = SlackMessageFormatter.format_blocks(alert, config)

        assert "attachments" in payload
        assert len(payload["attachments"]) > 0
        assert "blocks" in payload["attachments"][0]

    def test_format_attachment(self, alert, config):
        """Test attachment format."""
        config.style = SlackMessageStyle.ATTACHMENT
        payload = SlackMessageFormatter.format_attachment(alert, config)

        assert "attachments" in payload
        assert len(payload["attachments"]) > 0
        assert "fields" in payload["attachments"][0]

    def test_format_dispatcher(self, alert, config):
        """Test format dispatcher."""
        config.style = SlackMessageStyle.SIMPLE
        payload_simple = SlackMessageFormatter.format(alert, config)
        assert "text" in payload_simple
        assert "attachments" not in payload_simple

        config.style = SlackMessageStyle.BLOCKS
        payload_blocks = SlackMessageFormatter.format(alert, config)
        assert "attachments" in payload_blocks

    def test_priority_colors(self, config):
        """Test priority color mapping."""
        for priority in AlertPriority:
            alert = Alert(
                title="Test",
                message="Test",
                priority=priority,
            )
            config.style = SlackMessageStyle.BLOCKS
            payload = SlackMessageFormatter.format_blocks(alert, config)

            # Check attachment has color
            assert "color" in payload["attachments"][0]

    def test_priority_emojis(self, config):
        """Test priority emoji mapping."""
        for priority in AlertPriority:
            alert = Alert(
                title="Test",
                message="Test",
                priority=priority,
            )
            config.style = SlackMessageStyle.SIMPLE
            payload = SlackMessageFormatter.format_simple(alert, config)

            # Should have some emoji
            assert ":" in payload["text"]

    def test_category_emojis(self, config):
        """Test category emoji mapping."""
        for category in AlertCategory:
            alert = Alert(
                title="Test",
                message="Test",
                category=category,
            )
            config.style = SlackMessageStyle.BLOCKS
            payload = SlackMessageFormatter.format_blocks(alert, config)

            # Blocks should contain category
            blocks = payload["attachments"][0]["blocks"]
            assert any("elements" in block for block in blocks)

    def test_critical_mention(self, config):
        """Test critical alert mentions."""
        config.mention_on_critical = True
        config.mention_users = ["U12345", "U67890"]

        alert = Alert(
            title="Critical Alert",
            message="Critical issue",
            priority=AlertPriority.CRITICAL,
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        assert "<@U12345>" in payload["text"]
        assert "<@U67890>" in payload["text"]

    def test_include_timestamp(self, config):
        """Test timestamp inclusion."""
        config.include_timestamp = True

        alert = Alert(
            title="Test",
            message="Test",
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        assert "Time:" in payload["text"]

    def test_include_source(self, config):
        """Test source inclusion."""
        config.include_source = True

        alert = Alert(
            title="Test",
            message="Test",
            source="test_source",
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        assert "Source:" in payload["text"]

    def test_data_fields(self, alert, config):
        """Test data fields in attachment format."""
        config.style = SlackMessageStyle.ATTACHMENT
        payload = SlackMessageFormatter.format_attachment(alert, config)

        fields = payload["attachments"][0]["fields"]
        field_titles = [f["title"] for f in fields]

        assert "Category" in field_titles
        assert "Priority" in field_titles

    def test_channel_override(self, alert, config):
        """Test channel override."""
        config.channel = "#custom-channel"
        payload = SlackMessageFormatter.format_simple(alert, config)

        assert payload.get("channel") == "#custom-channel"


# ============================================================================
# SlackChannel Tests
# ============================================================================

class TestSlackChannel:
    """Tests for SlackChannel class."""

    @pytest.fixture
    def channel(self):
        """Create test channel."""
        return SlackChannel("https://hooks.slack.com/test")

    @pytest.fixture
    def alert(self):
        """Create test alert."""
        return Alert(
            title="Test Alert",
            message="Test message",
            priority=AlertPriority.MEDIUM,
            category=AlertCategory.TRADE,
        )

    def test_initialization_with_url(self):
        """Test initialization with URL."""
        channel = SlackChannel("https://hooks.slack.com/test")
        assert channel.config.webhook_url == "https://hooks.slack.com/test"

    def test_initialization_with_config(self):
        """Test initialization with config."""
        config = SlackConfig(
            webhook_url="https://hooks.slack.com/test",
            username="CustomBot",
        )
        channel = SlackChannel(config=config)
        assert channel.config.username == "CustomBot"

    def test_channel_type(self, channel):
        """Test channel type."""
        assert channel.channel_type == ChannelType.SLACK

    def test_is_available_with_url(self, channel):
        """Test availability with URL."""
        assert channel.is_available is True

    def test_is_available_without_url(self):
        """Test availability without URL."""
        channel = SlackChannel("")
        assert channel.is_available is False

    def test_validate_config_valid(self, channel):
        """Test config validation with valid config."""
        is_valid, error = channel.validate_config()
        assert is_valid is True
        assert error == ""

    def test_validate_config_no_url(self):
        """Test config validation with no URL."""
        channel = SlackChannel("")
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "required" in error.lower()

    def test_validate_config_invalid_url(self):
        """Test config validation with invalid URL."""
        channel = SlackChannel("https://example.com/webhook")
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "invalid" in error.lower()

    @pytest.mark.asyncio
    async def test_send_not_available(self, alert):
        """Test send when not available."""
        channel = SlackChannel("")
        result = await channel.send_with_result(alert)

        assert result.success is False
        assert "not configured" in result.error_message

    @pytest.mark.asyncio
    async def test_send_success(self, channel, alert):
        """Test successful send."""
        with patch.object(
            channel,
            "_send_webhook",
            return_value={"success": True, "status_code": 200, "body": "ok"},
        ):
            result = await channel.send_with_result(alert)

            assert result.success is True
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_send_failure(self, channel, alert):
        """Test failed send."""
        with patch.object(
            channel,
            "_send_webhook",
            return_value={"success": False, "status_code": 400, "body": "error"},
        ):
            result = await channel.send_with_result(alert)

            assert result.success is False
            assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_send_retry_on_server_error(self, channel, alert):
        """Test retry on server error."""
        channel.config.retry_count = 3
        channel.config.retry_delay_seconds = 0.01

        call_count = 0

        async def mock_send(payload):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"success": False, "status_code": 500, "body": "error"}
            return {"success": True, "status_code": 200, "body": "ok"}

        with patch.object(channel, "_send_webhook", side_effect=mock_send):
            result = await channel.send_with_result(alert)

            assert result.success is True
            assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_send_no_retry_on_client_error(self, channel, alert):
        """Test no retry on client error."""
        channel.config.retry_count = 3

        with patch.object(
            channel,
            "_send_webhook",
            return_value={"success": False, "status_code": 400, "body": "bad request"},
        ):
            result = await channel.send_with_result(alert)

            assert result.success is False
            assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_send_rate_limited(self, channel, alert):
        """Test rate limit handling."""
        channel.config.retry_count = 2
        channel.config.retry_delay_seconds = 0.01

        call_count = 0

        async def mock_send(payload):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": False, "status_code": 429, "body": "rate limited", "retry_after": 0.01}
            return {"success": True, "status_code": 200, "body": "ok"}

        with patch.object(channel, "_send_webhook", side_effect=mock_send):
            result = await channel.send_with_result(alert)

            assert result.success is True
            assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_send_latency_tracked(self, channel, alert):
        """Test latency tracking."""
        with patch.object(
            channel,
            "_send_webhook",
            return_value={"success": True, "status_code": 200, "body": "ok"},
        ):
            result = await channel.send_with_result(alert)

            assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_send_bool_return(self, channel, alert):
        """Test send returns bool."""
        with patch.object(
            channel,
            "_send_webhook",
            return_value={"success": True, "status_code": 200, "body": "ok"},
        ):
            result = await channel.send(alert)

            assert result is True


class TestSlackChannelIntegration:
    """Integration tests for Slack channel."""

    def test_with_alert_manager(self):
        """Test integration with AlertManager."""
        from tradingagents.alerts.alert_manager import AlertManager, RoutingRule

        manager = AlertManager()

        # Create and register Slack channel
        slack = SlackChannel("https://hooks.slack.com/test")
        manager.register_channel(slack)

        # Add routing rule
        manager.add_routing_rule(RoutingRule(
            name="slack_alerts",
            priority=AlertPriority.HIGH,
            channels=[ChannelType.SLACK],
        ))

        assert ChannelType.SLACK in manager.channels

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.alerts import (
            SlackMessageStyle,
            SlackConfig,
            SlackMessageResult,
            SlackMessageFormatter,
            SlackChannel,
            create_slack_channel,
        )

        # All imports successful
        assert SlackMessageStyle.BLOCKS is not None
        assert SlackChannel is not None

    def test_create_slack_channel_factory(self):
        """Test factory function."""
        channel = create_slack_channel(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
            username="CustomBot",
            style=SlackMessageStyle.SIMPLE,
            mention_users=["U12345"],
        )

        assert channel.config.webhook_url == "https://hooks.slack.com/test"
        assert channel.config.channel == "#alerts"
        assert channel.config.username == "CustomBot"
        assert channel.config.style == SlackMessageStyle.SIMPLE
        assert "U12345" in channel.config.mention_users

    def test_test_webhook_method(self):
        """Test the test_webhook method."""
        channel = SlackChannel("https://hooks.slack.com/test")

        with patch.object(
            channel,
            "_send_webhook_sync",
            return_value={"success": True, "status_code": 200, "body": "ok"},
        ):
            result = channel.test_webhook()

            assert result.success is True

    def test_message_formatting_all_styles(self):
        """Test all message formatting styles."""
        alert = Alert(
            title="Test",
            message="Test message",
            priority=AlertPriority.HIGH,
            category=AlertCategory.RISK,
            data={"key": "value"},
        )

        for style in SlackMessageStyle:
            config = SlackConfig(
                webhook_url="https://hooks.slack.com/test",
                style=style,
            )
            channel = SlackChannel(config=config)

            # Should not raise
            payload = SlackMessageFormatter.format(alert, config)
            assert payload is not None
            assert "text" in payload or "attachments" in payload


class TestSlackChannelFormatting:
    """Tests for Slack message formatting edge cases."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return SlackConfig(webhook_url="https://hooks.slack.com/test")

    def test_empty_message(self, config):
        """Test formatting empty message."""
        alert = Alert(
            title="",
            message="",
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        assert "text" in payload

    def test_long_message(self, config):
        """Test formatting long message."""
        alert = Alert(
            title="Long Alert",
            message="x" * 5000,
        )

        payload = SlackMessageFormatter.format_blocks(alert, config)
        # Should not truncate
        assert "x" * 100 in str(payload)

    def test_special_characters(self, config):
        """Test formatting with special characters."""
        alert = Alert(
            title="Alert <test> & \"quotes\"",
            message="Message with `code` and *markdown*",
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        assert "<test>" in payload["text"]

    def test_unicode_characters(self, config):
        """Test formatting with unicode."""
        alert = Alert(
            title="Alert with emoji",
            message="Price target reached",
        )

        payload = SlackMessageFormatter.format_blocks(alert, config)
        assert payload is not None

    def test_many_data_fields(self, config):
        """Test formatting with many data fields."""
        data = {f"field_{i}": f"value_{i}" for i in range(20)}

        alert = Alert(
            title="Data Alert",
            message="Many fields",
            data=data,
        )

        # Blocks format limits fields
        payload = SlackMessageFormatter.format_blocks(alert, config)
        blocks = payload["attachments"][0]["blocks"]

        # Should have some data fields
        assert any("field_" in str(block) for block in blocks)

    def test_no_mention_without_users(self, config):
        """Test critical alert without mention users."""
        config.mention_on_critical = True
        config.mention_users = []

        alert = Alert(
            title="Critical",
            message="Critical issue",
            priority=AlertPriority.CRITICAL,
        )

        payload = SlackMessageFormatter.format_simple(alert, config)
        # Should not have @mentions
        assert "<@" not in payload["text"]
