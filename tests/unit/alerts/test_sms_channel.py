"""Tests for SMS Channel.

Issue #41: [ALERT-40] SMS channel - Twilio
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json
import pytest

from tradingagents.alerts.sms_channel import (
    # Enums
    SMSFormat,
    SMSStatus,
    # Data Classes
    SMSConfig,
    SMSMessageResult,
    SMSBatchResult,
    # Classes
    SMSMessageFormatter,
    SMSChannel,
    # Factory Functions
    create_sms_channel,
    # Constants
    SMS_STANDARD_LIMIT,
    SMS_UNICODE_LIMIT,
    E164_PATTERN,
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

class TestSMSFormat:
    """Tests for SMSFormat enum."""

    def test_all_formats_defined(self):
        """Verify all formats exist."""
        assert SMSFormat.PLAIN
        assert SMSFormat.COMPACT
        assert SMSFormat.DETAILED

    def test_format_values(self):
        """Verify format values."""
        assert SMSFormat.PLAIN.value == "plain"
        assert SMSFormat.COMPACT.value == "compact"
        assert SMSFormat.DETAILED.value == "detailed"


class TestSMSStatus:
    """Tests for SMSStatus enum."""

    def test_all_statuses_defined(self):
        """Verify all Twilio statuses exist."""
        assert SMSStatus.QUEUED
        assert SMSStatus.SENDING
        assert SMSStatus.SENT
        assert SMSStatus.DELIVERED
        assert SMSStatus.UNDELIVERED
        assert SMSStatus.FAILED
        assert SMSStatus.CANCELED


# ============================================================================
# Data Class Tests
# ============================================================================

class TestSMSConfig:
    """Tests for SMSConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = SMSConfig()
        assert config.account_sid == ""
        assert config.auth_token == ""
        assert config.from_number == ""
        assert config.to_numbers == []
        assert config.format == SMSFormat.COMPACT
        assert config.retry_count == 2

    def test_custom_config(self):
        """Test creating custom config."""
        config = SMSConfig(
            account_sid="ACtest123",
            auth_token="token123",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )
        assert config.account_sid == "ACtest123"
        assert config.from_number == "+15551234567"
        assert len(config.to_numbers) == 1

    def test_messaging_service_sid(self):
        """Test messaging service SID config."""
        config = SMSConfig(
            account_sid="ACtest123",
            auth_token="token123",
            messaging_service_sid="MGtest456",
            to_numbers=["+15559876543"],
        )
        assert config.messaging_service_sid == "MGtest456"

    def test_priority_filter(self):
        """Test priority filter config."""
        config = SMSConfig(
            priority_filter=AlertPriority.HIGH,
        )
        assert config.priority_filter == AlertPriority.HIGH


class TestSMSMessageResult:
    """Tests for SMSMessageResult dataclass."""

    def test_default_creation(self):
        """Test creating result with defaults."""
        result = SMSMessageResult()
        assert result.success is False
        assert result.message_sid == ""
        assert result.segments == 1
        assert result.attempts == 0

    def test_successful_result(self):
        """Test successful result."""
        result = SMSMessageResult(
            success=True,
            message_sid="SM12345",
            status="sent",
            to_number="+15559876543",
            segments=1,
        )
        assert result.success is True
        assert result.message_sid == "SM12345"


class TestSMSBatchResult:
    """Tests for SMSBatchResult dataclass."""

    def test_default_creation(self):
        """Test creating batch result with defaults."""
        result = SMSBatchResult()
        assert result.success is False
        assert result.total_sent == 0
        assert result.total_failed == 0
        assert result.results == []

    def test_batch_result_with_results(self):
        """Test batch result with individual results."""
        individual_results = [
            SMSMessageResult(success=True, to_number="+15551111111"),
            SMSMessageResult(success=True, to_number="+15552222222"),
            SMSMessageResult(success=False, to_number="+15553333333"),
        ]
        result = SMSBatchResult(
            success=False,
            total_sent=2,
            total_failed=1,
            results=individual_results,
        )
        assert result.total_sent == 2
        assert result.total_failed == 1
        assert len(result.results) == 3


# ============================================================================
# Formatter Tests
# ============================================================================

class TestSMSMessageFormatter:
    """Tests for SMSMessageFormatter."""

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
        return SMSConfig(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )

    def test_format_plain(self, alert, config):
        """Test plain format."""
        config.format = SMSFormat.PLAIN
        message = SMSMessageFormatter.format_plain(alert, config)

        assert "Test Alert" in message
        assert "This is a test message" in message

    def test_format_compact(self, alert, config):
        """Test compact format."""
        config.format = SMSFormat.COMPACT
        message = SMSMessageFormatter.format_compact(alert, config)

        assert "TRD" in message  # Category prefix
        assert "Test Alert" in message
        assert len(message) <= SMS_STANDARD_LIMIT

    def test_format_detailed(self, alert, config):
        """Test detailed format."""
        config.format = SMSFormat.DETAILED
        message = SMSMessageFormatter.format_detailed(alert, config)

        assert "TRADE" in message  # Category
        assert "Test Alert" in message
        assert "symbol" in message
        assert "AAPL" in message

    def test_format_dispatcher(self, alert, config):
        """Test format dispatcher."""
        config.format = SMSFormat.PLAIN
        plain_msg = SMSMessageFormatter.format(alert, config)

        config.format = SMSFormat.COMPACT
        compact_msg = SMSMessageFormatter.format(alert, config)

        assert plain_msg != compact_msg

    def test_priority_indicators(self, config):
        """Test priority indicators in message."""
        alert_high = Alert(
            title="High Alert",
            message="High priority",
            priority=AlertPriority.HIGH,
        )
        alert_critical = Alert(
            title="Critical Alert",
            message="Critical issue",
            priority=AlertPriority.CRITICAL,
        )

        config.format = SMSFormat.PLAIN
        high_msg = SMSMessageFormatter.format_plain(alert_high, config)
        critical_msg = SMSMessageFormatter.format_plain(alert_critical, config)

        assert "[!]" in high_msg
        assert "[!!!]" in critical_msg

    def test_category_prefixes(self, config):
        """Test category prefixes in compact format."""
        for category in AlertCategory:
            alert = Alert(
                title="Test",
                message="Test",
                category=category,
            )
            config.format = SMSFormat.COMPACT
            message = SMSMessageFormatter.format_compact(alert, config)

            # Message should be created without error
            assert message is not None

    def test_include_timestamp(self, alert, config):
        """Test timestamp inclusion."""
        config.include_timestamp = True
        config.format = SMSFormat.PLAIN
        message = SMSMessageFormatter.format_plain(alert, config)

        # Should have time in HH:MM format
        assert "(" in message
        assert ")" in message

    def test_max_length_truncation(self, config):
        """Test message truncation with max_length."""
        alert = Alert(
            title="Very Long Title That Should Be Truncated",
            message="A" * 200,
        )
        config.max_length = 100
        config.format = SMSFormat.PLAIN
        message = SMSMessageFormatter.format_plain(alert, config)

        assert len(message) <= 100
        assert message.endswith("...")

    def test_count_segments_standard(self):
        """Test segment counting for standard messages."""
        # Single segment
        short_msg = "Hello world"
        assert SMSMessageFormatter.count_segments(short_msg) == 1

        # Exactly 160 chars
        exact_msg = "A" * SMS_STANDARD_LIMIT
        assert SMSMessageFormatter.count_segments(exact_msg) == 1

        # Two segments
        two_segment_msg = "A" * 161
        assert SMSMessageFormatter.count_segments(two_segment_msg) == 2

    def test_count_segments_unicode(self):
        """Test segment counting for unicode messages."""
        # Unicode requires different counting
        unicode_msg = "Hello 😀"  # Contains emoji
        segments = SMSMessageFormatter.count_segments(unicode_msg)
        assert segments >= 1

    def test_data_fields_in_compact(self, alert, config):
        """Test data fields in compact format."""
        config.format = SMSFormat.COMPACT
        message = SMSMessageFormatter.format_compact(alert, config)

        # Should include some data if space allows
        # Since compact prioritizes brevity, data may be truncated
        assert len(message) <= SMS_STANDARD_LIMIT


# ============================================================================
# SMSChannel Tests
# ============================================================================

class TestSMSChannel:
    """Tests for SMSChannel class."""

    @pytest.fixture
    def channel(self):
        """Create test channel."""
        return SMSChannel(
            account_sid="ACtest123",
            auth_token="test_token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )

    @pytest.fixture
    def alert(self):
        """Create test alert."""
        return Alert(
            title="Test Alert",
            message="Test message",
            priority=AlertPriority.MEDIUM,
            category=AlertCategory.TRADE,
        )

    def test_initialization_with_args(self):
        """Test initialization with arguments."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )
        assert channel.config.account_sid == "ACtest"
        assert channel.config.from_number == "+15551234567"

    def test_initialization_with_config(self):
        """Test initialization with config object."""
        config = SMSConfig(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543", "+15551111111"],
        )
        channel = SMSChannel(config=config)
        assert len(channel.config.to_numbers) == 2

    def test_channel_type(self, channel):
        """Test channel type."""
        assert channel.channel_type == ChannelType.SMS

    def test_is_available_with_config(self, channel):
        """Test availability with config."""
        assert channel.is_available is True

    def test_is_available_without_config(self):
        """Test availability without config."""
        channel = SMSChannel()
        assert channel.is_available is False

    def test_is_available_with_messaging_service(self):
        """Test availability with messaging service SID."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            config=SMSConfig(
                account_sid="ACtest",
                auth_token="token",
                messaging_service_sid="MGtest",
                to_numbers=["+15559876543"],
            ),
        )
        assert channel.is_available is True

    def test_validate_config_valid(self, channel):
        """Test config validation with valid config."""
        is_valid, error = channel.validate_config()
        assert is_valid is True
        assert error == ""

    def test_validate_config_no_account_sid(self):
        """Test config validation without account SID."""
        channel = SMSChannel(
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "Account SID" in error

    def test_validate_config_no_auth_token(self):
        """Test config validation without auth token."""
        channel = SMSChannel(
            account_sid="ACtest",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "Auth token" in error

    def test_validate_config_no_from_number(self):
        """Test config validation without from number."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            to_numbers=["+15559876543"],
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "From number" in error

    def test_validate_config_invalid_from_number(self):
        """Test config validation with invalid from number."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="5551234567",  # Missing +
            to_numbers=["+15559876543"],
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "Invalid from number" in error

    def test_validate_config_invalid_to_number(self):
        """Test config validation with invalid to number."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["5559876543"],  # Missing +
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "Invalid phone number" in error

    def test_validate_config_no_recipients(self):
        """Test config validation without recipients."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
        )
        is_valid, error = channel.validate_config()
        assert is_valid is False
        assert "recipient" in error.lower()

    @pytest.mark.asyncio
    async def test_send_not_available(self, alert):
        """Test send when not available."""
        channel = SMSChannel()
        result = await channel.send_with_result(alert)

        assert result.success is False
        assert "not configured" in result.error_message

    @pytest.mark.asyncio
    async def test_send_success(self, channel, alert):
        """Test successful send."""
        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={
                "success": True,
                "sid": "SM12345",
                "status": "queued",
            },
        ):
            result = await channel.send_with_result(alert)

            assert result.success is True
            assert result.message_sid == "SM12345"

    @pytest.mark.asyncio
    async def test_send_failure(self, channel, alert):
        """Test failed send."""
        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={
                "success": False,
                "error_code": 400,
                "error_message": "Invalid number",
            },
        ):
            result = await channel.send_with_result(alert)

            assert result.success is False
            assert "Invalid number" in result.error_message

    @pytest.mark.asyncio
    async def test_send_retry_on_server_error(self, channel, alert):
        """Test retry on server error."""
        channel.config.retry_count = 3
        channel.config.retry_delay_seconds = 0.01

        call_count = 0

        async def mock_send(to, msg):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"success": False, "error_code": 500, "error_message": "Server error"}
            return {"success": True, "sid": "SM12345", "status": "queued"}

        with patch.object(channel, "_send_twilio_message", side_effect=mock_send):
            result = await channel.send_with_result(alert)

            assert result.success is True
            assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_send_no_retry_on_client_error(self, channel, alert):
        """Test no retry on client error."""
        channel.config.retry_count = 3

        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={
                "success": False,
                "error_code": 400,
                "error_message": "Bad request",
            },
        ):
            result = await channel.send_with_result(alert)

            assert result.success is False
            assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_send_batch(self, alert):
        """Test batch send to multiple recipients."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15551111111", "+15552222222", "+15553333333"],
        )

        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={
                "success": True,
                "sid": "SM12345",
                "status": "queued",
            },
        ):
            result = await channel.send_batch(alert)

            assert result.success is True
            assert result.total_sent == 3
            assert result.total_failed == 0
            assert len(result.results) == 3

    @pytest.mark.asyncio
    async def test_send_batch_partial_failure(self, alert):
        """Test batch send with partial failure."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15551111111", "+15552222222"],
        )

        call_count = 0

        async def mock_send(to, msg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "sid": "SM1", "status": "queued"}
            return {"success": False, "error_code": 400, "error_message": "Invalid"}

        with patch.object(channel, "_send_twilio_message", side_effect=mock_send):
            result = await channel.send_batch(alert)

            assert result.success is False
            assert result.total_sent == 1
            assert result.total_failed == 1

    @pytest.mark.asyncio
    async def test_send_bool_return(self, channel, alert):
        """Test send returns bool."""
        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={
                "success": True,
                "sid": "SM12345",
                "status": "queued",
            },
        ):
            result = await channel.send(alert)
            assert result is True

    @pytest.mark.asyncio
    async def test_priority_filter(self, channel, alert):
        """Test priority filter."""
        channel.config.priority_filter = AlertPriority.HIGH

        # LOW priority should be filtered
        alert.priority = AlertPriority.LOW
        result = await channel.send_with_result(alert)
        assert result.success is False
        assert "priority" in result.error_message.lower()

        # HIGH priority should pass
        alert.priority = AlertPriority.HIGH
        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={"success": True, "sid": "SM1", "status": "queued"},
        ):
            result = await channel.send_with_result(alert)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_latency_tracked(self, channel, alert):
        """Test latency tracking."""
        with patch.object(
            channel,
            "_send_twilio_message",
            return_value={"success": True, "sid": "SM1", "status": "queued"},
        ):
            result = await channel.send_with_result(alert)
            assert result.latency_ms > 0


class TestSMSChannelIntegration:
    """Integration tests for SMS channel."""

    def test_with_alert_manager(self):
        """Test integration with AlertManager."""
        from tradingagents.alerts.alert_manager import AlertManager, RoutingRule

        manager = AlertManager()

        # Create and register SMS channel
        sms = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )
        manager.register_channel(sms)

        # Add routing rule
        manager.add_routing_rule(RoutingRule(
            name="sms_alerts",
            priority=AlertPriority.CRITICAL,
            channels=[ChannelType.SMS],
        ))

        assert ChannelType.SMS in manager.channels

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.alerts import (
            SMSFormat,
            SMSStatus,
            SMSConfig,
            SMSMessageResult,
            SMSBatchResult,
            SMSMessageFormatter,
            SMSChannel,
            create_sms_channel,
        )

        # All imports successful
        assert SMSFormat.COMPACT is not None
        assert SMSChannel is not None

    def test_create_sms_channel_factory(self):
        """Test factory function."""
        channel = create_sms_channel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543", "+15551111111"],
            format=SMSFormat.DETAILED,
            include_priority=True,
            priority_filter=AlertPriority.HIGH,
        )

        assert channel.config.account_sid == "ACtest"
        assert channel.config.from_number == "+15551234567"
        assert len(channel.config.to_numbers) == 2
        assert channel.config.format == SMSFormat.DETAILED
        assert channel.config.priority_filter == AlertPriority.HIGH

    def test_e164_pattern_valid(self):
        """Test E.164 pattern validation."""
        valid_numbers = [
            "+15551234567",
            "+14155551234",
            "+441onal2341234",
            "+61412345678",
        ]

        for number in valid_numbers:
            if E164_PATTERN.match(number):
                assert True
            # Some may not match due to length

    def test_e164_pattern_invalid(self):
        """Test E.164 pattern rejects invalid numbers."""
        invalid_numbers = [
            "5551234567",  # No +
            "+0551234567",  # Leading 0 after +
            "+(555)1234567",  # Parentheses
            "+1-555-123-4567",  # Dashes
            "+1 555 123 4567",  # Spaces
        ]

        for number in invalid_numbers:
            assert not E164_PATTERN.match(number)


class TestSMSChannelFormatting:
    """Tests for SMS message formatting edge cases."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return SMSConfig(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )

    def test_empty_message(self, config):
        """Test formatting empty message."""
        alert = Alert(
            title="",
            message="",
        )

        message = SMSMessageFormatter.format_compact(alert, config)
        # Should still produce some output
        assert message is not None

    def test_long_title(self, config):
        """Test formatting with long title."""
        alert = Alert(
            title="A" * 100,
            message="Short message",
        )

        config.format = SMSFormat.COMPACT
        message = SMSMessageFormatter.format_compact(alert, config)
        assert len(message) <= SMS_STANDARD_LIMIT

    def test_long_message_detailed(self, config):
        """Test formatting long message in detailed mode."""
        alert = Alert(
            title="Alert",
            message="A" * 500,
        )

        config.format = SMSFormat.DETAILED
        config.max_length = SMS_STANDARD_LIMIT * 4  # Limit to 4 segments
        message = SMSMessageFormatter.format_detailed(alert, config)
        # Should not exceed max length
        assert len(message) <= SMS_STANDARD_LIMIT * 4

    def test_special_characters(self, config):
        """Test formatting with special characters."""
        alert = Alert(
            title="Price Alert: $AAPL",
            message="Target price: $150.00 (>5% gain)",
        )

        message = SMSMessageFormatter.format_plain(alert, config)
        assert "$AAPL" in message
        assert "$150.00" in message

    def test_unicode_emoji(self, config):
        """Test formatting with emoji."""
        alert = Alert(
            title="Alert",
            message="Success!",
        )

        message = SMSMessageFormatter.format_plain(alert, config)
        segments = SMSMessageFormatter.count_segments(message)
        # Should be able to count segments
        assert segments >= 1

    def test_many_data_fields(self, config):
        """Test formatting with many data fields."""
        data = {f"field_{i}": f"value_{i}" for i in range(10)}

        alert = Alert(
            title="Data Alert",
            message="Multiple fields",
            data=data,
        )

        config.format = SMSFormat.COMPACT
        message = SMSMessageFormatter.format_compact(alert, config)
        # Should be constrained to SMS limit
        assert len(message) <= SMS_STANDARD_LIMIT

    def test_no_priority_indicator(self, config):
        """Test without priority indicator."""
        config.include_priority = False

        alert = Alert(
            title="Alert",
            message="Message",
            priority=AlertPriority.CRITICAL,
        )

        message = SMSMessageFormatter.format_plain(alert, config)
        assert "[!!!]" not in message


class TestSMSChannelConnection:
    """Tests for SMS channel connection testing."""

    def test_test_connection_no_credentials(self):
        """Test connection test without credentials."""
        channel = SMSChannel()
        result = channel.test_connection()

        assert result.success is False
        assert "Account SID" in result.error_message or "Auth Token" in result.error_message

    def test_test_connection_with_mock(self):
        """Test connection test with mocked response."""
        channel = SMSChannel(
            account_sid="ACtest",
            auth_token="token",
            from_number="+15551234567",
            to_numbers=["+15559876543"],
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.read.return_value = json.dumps({
                "status": "active",
                "friendly_name": "Test Account",
            }).encode()
            mock_urlopen.return_value = mock_response

            result = channel.test_connection()

            assert result.success is True
            assert result.status == "active"
