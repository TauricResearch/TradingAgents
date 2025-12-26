"""Tests for Alert Manager.

Issue #38: [ALERT-37] Alert manager - orchestration and routing
"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tradingagents.alerts.alert_manager import (
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


# ============================================================================
# Enum Tests
# ============================================================================

class TestAlertPriority:
    """Tests for AlertPriority enum."""

    def test_all_priorities_defined(self):
        """Verify all priorities exist."""
        assert AlertPriority.LOW
        assert AlertPriority.MEDIUM
        assert AlertPriority.HIGH
        assert AlertPriority.CRITICAL

    def test_priority_values(self):
        """Verify priority values."""
        assert AlertPriority.LOW.value == "low"
        assert AlertPriority.CRITICAL.value == "critical"


class TestAlertCategory:
    """Tests for AlertCategory enum."""

    def test_all_categories_defined(self):
        """Verify all categories exist."""
        assert AlertCategory.TRADE
        assert AlertCategory.RISK
        assert AlertCategory.SYSTEM
        assert AlertCategory.MARKET
        assert AlertCategory.PORTFOLIO
        assert AlertCategory.EXECUTION
        assert AlertCategory.COMPLIANCE


class TestAlertStatus:
    """Tests for AlertStatus enum."""

    def test_all_statuses_defined(self):
        """Verify all statuses exist."""
        assert AlertStatus.PENDING
        assert AlertStatus.SENDING
        assert AlertStatus.DELIVERED
        assert AlertStatus.FAILED
        assert AlertStatus.RATE_LIMITED
        assert AlertStatus.SUPPRESSED


class TestChannelType:
    """Tests for ChannelType enum."""

    def test_all_channels_defined(self):
        """Verify all channels exist."""
        assert ChannelType.EMAIL
        assert ChannelType.SLACK
        assert ChannelType.SMS
        assert ChannelType.WEBHOOK
        assert ChannelType.PUSH
        assert ChannelType.LOG


# ============================================================================
# Data Class Tests
# ============================================================================

class TestAlertTemplate:
    """Tests for AlertTemplate dataclass."""

    def test_default_creation(self):
        """Test creating template with defaults."""
        template = AlertTemplate()
        assert template.template_id is not None
        assert template.title_template == "{category}: {title}"

    def test_render_template(self):
        """Test rendering template."""
        template = AlertTemplate(
            title_template="[{category}] {title}",
            body_template="Message: {message}",
        )
        title, body = template.render({
            "category": "TRADE",
            "title": "Buy Signal",
            "message": "AAPL buy detected",
        })
        assert title == "[TRADE] Buy Signal"
        assert body == "Message: AAPL buy detected"


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = RateLimitConfig()
        assert config.max_alerts_per_minute == 10
        assert config.max_alerts_per_hour == 100
        assert config.enable_deduplication is True


class TestRoutingRule:
    """Tests for RoutingRule dataclass."""

    def test_default_creation(self):
        """Test creating rule with defaults."""
        rule = RoutingRule()
        assert rule.rule_id is not None
        assert rule.enabled is True
        assert rule.priority == AlertPriority.LOW

    def test_matches_priority(self):
        """Test priority matching."""
        rule = RoutingRule(priority=AlertPriority.HIGH)

        low_alert = Alert(priority=AlertPriority.LOW)
        high_alert = Alert(priority=AlertPriority.HIGH)
        critical_alert = Alert(priority=AlertPriority.CRITICAL)

        assert not rule.matches(low_alert)
        assert rule.matches(high_alert)
        assert rule.matches(critical_alert)

    def test_matches_category(self):
        """Test category matching."""
        rule = RoutingRule(
            categories=[AlertCategory.TRADE, AlertCategory.RISK],
        )

        trade_alert = Alert(category=AlertCategory.TRADE)
        system_alert = Alert(category=AlertCategory.SYSTEM)

        assert rule.matches(trade_alert)
        assert not rule.matches(system_alert)

    def test_disabled_rule(self):
        """Test disabled rule never matches."""
        rule = RoutingRule(enabled=False)
        alert = Alert()
        assert not rule.matches(alert)


class TestAlertConfig:
    """Tests for AlertConfig dataclass."""

    def test_default_creation(self):
        """Test creating config with defaults."""
        config = AlertConfig()
        assert config.log_all_alerts is True
        assert config.store_history is True
        assert config.max_history_size == 1000


class TestAlert:
    """Tests for Alert dataclass."""

    def test_default_creation(self):
        """Test creating alert with defaults."""
        alert = Alert()
        assert alert.alert_id is not None
        assert alert.status == AlertStatus.PENDING
        assert alert.timestamp is not None

    def test_content_hash(self):
        """Test content hash generation."""
        alert1 = Alert(
            title="Test",
            message="Message",
            category=AlertCategory.TRADE,
        )
        alert2 = Alert(
            title="Test",
            message="Message",
            category=AlertCategory.TRADE,
        )
        alert3 = Alert(
            title="Different",
            message="Message",
            category=AlertCategory.TRADE,
        )

        assert alert1.content_hash == alert2.content_hash
        assert alert1.content_hash != alert3.content_hash


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_default_creation(self):
        """Test creating result with defaults."""
        result = DeliveryResult()
        assert result.success is False
        assert result.timestamp is not None


class TestAlertStats:
    """Tests for AlertStats dataclass."""

    def test_default_creation(self):
        """Test creating stats with defaults."""
        stats = AlertStats()
        assert stats.total_sent == 0
        assert stats.total_failed == 0


# ============================================================================
# Channel Tests
# ============================================================================

class TestLogChannel:
    """Tests for LogChannel."""

    def test_channel_type(self):
        """Test channel type."""
        channel = LogChannel()
        assert channel.channel_type == ChannelType.LOG

    def test_is_available(self):
        """Test availability."""
        channel = LogChannel()
        assert channel.is_available is True

    @pytest.mark.asyncio
    async def test_send(self):
        """Test sending alert."""
        channel = LogChannel()
        alert = Alert(title="Test", message="Test message")
        result = await channel.send(alert)
        assert result is True


class TestWebhookChannel:
    """Tests for WebhookChannel."""

    def test_channel_type(self):
        """Test channel type."""
        channel = WebhookChannel("https://example.com/webhook")
        assert channel.channel_type == ChannelType.WEBHOOK

    def test_availability_with_url(self):
        """Test availability with URL."""
        channel = WebhookChannel("https://example.com/webhook")
        assert channel.is_available is True

    def test_availability_without_url(self):
        """Test availability without URL."""
        channel = WebhookChannel("")
        assert channel.is_available is False

    @pytest.mark.asyncio
    async def test_send_with_url(self):
        """Test sending with URL."""
        channel = WebhookChannel("https://example.com/webhook")
        alert = Alert(title="Test", message="Test message")
        result = await channel.send(alert)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_without_url(self):
        """Test sending without URL fails."""
        channel = WebhookChannel("")
        alert = Alert(title="Test", message="Test message")
        result = await channel.send(alert)
        assert result is False


# ============================================================================
# AlertManager Tests
# ============================================================================

class TestAlertManager:
    """Tests for AlertManager class."""

    @pytest.fixture
    def manager(self):
        """Create default manager."""
        return AlertManager()

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.config is not None
        assert ChannelType.LOG in manager.channels
        assert len(manager.routing_rules) > 0

    def test_register_channel(self, manager):
        """Test registering a channel."""
        webhook = WebhookChannel("https://example.com")
        manager.register_channel(webhook)
        assert ChannelType.WEBHOOK in manager.channels

    def test_unregister_channel(self, manager):
        """Test unregistering a channel."""
        manager.unregister_channel(ChannelType.LOG)
        assert ChannelType.LOG not in manager.channels

    def test_add_routing_rule(self, manager):
        """Test adding routing rule."""
        initial_count = len(manager.routing_rules)
        rule = RoutingRule(name="test_rule")
        manager.add_routing_rule(rule)
        assert len(manager.routing_rules) == initial_count + 1

    def test_remove_routing_rule(self, manager):
        """Test removing routing rule."""
        rule = RoutingRule(name="test_rule")
        manager.add_routing_rule(rule)
        result = manager.remove_routing_rule(rule.rule_id)
        assert result is True

    def test_remove_nonexistent_rule(self, manager):
        """Test removing nonexistent rule."""
        result = manager.remove_routing_rule("nonexistent")
        assert result is False

    def test_register_template(self, manager):
        """Test registering template."""
        template = AlertTemplate(name="custom_template")
        manager.register_template(template)
        assert "custom_template" in manager.templates

    def test_create_alert(self, manager):
        """Test creating alert."""
        alert = manager.create_alert(
            title="Test Alert",
            message="This is a test",
            priority=AlertPriority.HIGH,
            category=AlertCategory.RISK,
        )
        assert alert.title == "Test Alert"
        assert alert.priority == AlertPriority.HIGH
        assert alert.category == AlertCategory.RISK

    def test_create_alert_from_template(self, manager):
        """Test creating alert from template."""
        alert = manager.create_alert_from_template(
            "trade_signal",
            {
                "symbol": "AAPL",
                "action": "BUY",
                "price": "150.00",
                "reason": "Momentum signal",
            },
        )
        assert alert is not None
        assert "AAPL" in alert.title
        assert "BUY" in alert.title

    def test_create_alert_from_nonexistent_template(self, manager):
        """Test creating alert from nonexistent template."""
        alert = manager.create_alert_from_template(
            "nonexistent",
            {},
        )
        assert alert is None

    def test_send_alert(self, manager):
        """Test sending alert."""
        alert = manager.create_alert(
            title="Test",
            message="Test message",
        )
        results = manager.send(alert)
        assert len(results) > 0
        assert alert.status == AlertStatus.DELIVERED

    @pytest.mark.asyncio
    async def test_send_alert_async(self, manager):
        """Test sending alert asynchronously."""
        alert = manager.create_alert(
            title="Test",
            message="Test message",
        )
        results = await manager.send_async(alert)
        assert len(results) > 0
        assert alert.status == AlertStatus.DELIVERED


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.fixture
    def limited_manager(self):
        """Create manager with tight rate limits."""
        config = AlertConfig(
            rate_limit_config=RateLimitConfig(
                max_alerts_per_minute=2,
                max_alerts_per_hour=5,
            ),
        )
        return AlertManager(config=config)

    def test_rate_limit_per_minute(self, limited_manager):
        """Test rate limit per minute."""
        # Send 2 alerts (should succeed) - each with unique message to avoid dedup
        for i in range(2):
            alert = limited_manager.create_alert(
                title=f"Test {i}",
                message=f"Test message {i}",
                category=AlertCategory.TRADE,
            )
            limited_manager.send(alert)

        # 3rd alert should be rate limited
        alert = limited_manager.create_alert(
            title="Test 3",
            message="Test message 3",
            category=AlertCategory.TRADE,
        )
        limited_manager.send(alert)
        assert alert.status == AlertStatus.RATE_LIMITED


class TestDeduplication:
    """Tests for deduplication."""

    @pytest.fixture
    def manager(self):
        """Create manager with deduplication."""
        config = AlertConfig(
            rate_limit_config=RateLimitConfig(
                enable_deduplication=True,
                dedupe_window_seconds=60,
            ),
        )
        return AlertManager(config=config)

    def test_duplicate_suppressed(self, manager):
        """Test duplicate alerts are suppressed."""
        # First alert should succeed
        alert1 = manager.create_alert(
            title="Same Title",
            message="Same Message",
            category=AlertCategory.TRADE,
        )
        manager.send(alert1)
        assert alert1.status == AlertStatus.DELIVERED

        # Duplicate should be suppressed
        alert2 = manager.create_alert(
            title="Same Title",
            message="Same Message",
            category=AlertCategory.TRADE,
        )
        manager.send(alert2)
        assert alert2.status == AlertStatus.SUPPRESSED

    def test_different_not_suppressed(self, manager):
        """Test different alerts are not suppressed."""
        alert1 = manager.create_alert(
            title="Title 1",
            message="Message 1",
        )
        manager.send(alert1)

        alert2 = manager.create_alert(
            title="Title 2",
            message="Message 2",
        )
        manager.send(alert2)
        assert alert2.status == AlertStatus.DELIVERED


class TestHistory:
    """Tests for alert history."""

    @pytest.fixture
    def manager(self):
        """Create manager with history."""
        return AlertManager()

    def test_history_stored(self, manager):
        """Test alerts are stored in history."""
        alert = manager.create_alert(title="Test", message="Test")
        manager.send(alert)

        history = manager.get_history()
        assert len(history) > 0
        assert history[0].title == "Test"

    def test_history_filter_category(self, manager):
        """Test filtering history by category."""
        alert1 = manager.create_alert(
            title="Trade",
            message="Trade alert",
            category=AlertCategory.TRADE,
        )
        alert2 = manager.create_alert(
            title="Risk",
            message="Risk alert",
            category=AlertCategory.RISK,
        )
        manager.send(alert1)
        manager.send(alert2)

        trade_history = manager.get_history(category=AlertCategory.TRADE)
        assert len(trade_history) == 1
        assert trade_history[0].category == AlertCategory.TRADE

    def test_history_filter_priority(self, manager):
        """Test filtering history by priority."""
        alert1 = manager.create_alert(
            title="Low",
            message="Low priority",
            priority=AlertPriority.LOW,
        )
        alert2 = manager.create_alert(
            title="High",
            message="High priority",
            priority=AlertPriority.HIGH,
        )
        manager.send(alert1)
        manager.send(alert2)

        high_history = manager.get_history(priority=AlertPriority.HIGH)
        assert len(high_history) == 1
        assert high_history[0].priority == AlertPriority.HIGH

    def test_clear_history(self, manager):
        """Test clearing history."""
        alert = manager.create_alert(title="Test", message="Test")
        manager.send(alert)

        count = manager.clear_history()
        assert count > 0
        assert len(manager.get_history()) == 0


class TestAcknowledgement:
    """Tests for alert acknowledgement."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        return AlertManager()

    def test_acknowledge_alert(self, manager):
        """Test acknowledging alert."""
        alert = manager.create_alert(title="Test", message="Test")
        manager.send(alert)

        result = manager.acknowledge_alert(alert.alert_id, "user@example.com")
        assert result is True

        history = manager.get_history()
        assert history[0].acknowledged is True
        assert history[0].acknowledged_by == "user@example.com"

    def test_acknowledge_nonexistent(self, manager):
        """Test acknowledging nonexistent alert."""
        result = manager.acknowledge_alert("nonexistent", "user@example.com")
        assert result is False

    def test_get_unacknowledged(self, manager):
        """Test getting unacknowledged alerts."""
        alert1 = manager.create_alert(title="Test1", message="Test1")
        alert2 = manager.create_alert(title="Test2", message="Test2")
        manager.send(alert1)
        manager.send(alert2)

        manager.acknowledge_alert(alert1.alert_id, "user")

        unacked = manager.get_unacknowledged()
        assert len(unacked) == 1
        assert unacked[0].alert_id == alert2.alert_id


class TestStats:
    """Tests for statistics."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        return AlertManager()

    def test_stats_updated(self, manager):
        """Test stats are updated."""
        alert = manager.create_alert(title="Test", message="Test")
        manager.send(alert)

        stats = manager.get_stats()
        assert stats.total_sent > 0

    def test_reset_stats(self, manager):
        """Test resetting stats."""
        alert = manager.create_alert(title="Test", message="Test")
        manager.send(alert)

        manager.reset_stats()
        stats = manager.get_stats()
        assert stats.total_sent == 0


class TestConvenienceMethods:
    """Tests for convenience methods."""

    @pytest.fixture
    def manager(self):
        """Create manager."""
        return AlertManager()

    def test_alert_trade(self, manager):
        """Test trade alert convenience method."""
        alert = manager.alert_trade(
            symbol="AAPL",
            action="BUY",
            price=Decimal("150.00"),
            reason="Momentum",
        )
        assert alert is not None
        assert alert.category == AlertCategory.TRADE

    def test_alert_risk(self, manager):
        """Test risk alert convenience method."""
        alert = manager.alert_risk(
            risk_type="DrawdownLimit",
            current_value="15%",
            limit_value="10%",
        )
        assert alert is not None
        assert alert.category == AlertCategory.RISK

    def test_alert_execution(self, manager):
        """Test execution alert convenience method."""
        alert = manager.alert_execution(
            order_id="order-123",
            symbol="AAPL",
            status="FILLED",
            quantity=Decimal("100"),
            price=Decimal("150.00"),
        )
        assert alert is not None
        assert alert.category == AlertCategory.EXECUTION


# ============================================================================
# Integration Tests
# ============================================================================

class TestAlertManagerIntegration:
    """Integration tests for alert manager."""

    def test_full_workflow(self):
        """Test complete alert workflow."""
        # Setup manager
        manager = AlertManager()

        # Add custom channel
        webhook = WebhookChannel("https://example.com/webhook")
        manager.register_channel(webhook)

        # Add custom routing rule
        manager.add_routing_rule(RoutingRule(
            name="critical_webhook",
            priority=AlertPriority.CRITICAL,
            channels=[ChannelType.WEBHOOK],
        ))

        # Send alerts of different priorities
        low_alert = manager.create_alert(
            title="Info",
            message="Informational message",
            priority=AlertPriority.LOW,
        )
        manager.send(low_alert)

        critical_alert = manager.create_alert(
            title="Critical Issue",
            message="Immediate attention required",
            priority=AlertPriority.CRITICAL,
        )
        manager.send(critical_alert)

        # Verify stats
        stats = manager.get_stats()
        assert stats.total_sent == 2
        assert stats.by_priority.get("low", 0) >= 1
        assert stats.by_priority.get("critical", 0) >= 1

    def test_module_imports(self):
        """Test that all classes are exported from module."""
        from tradingagents.alerts import (
            AlertPriority,
            AlertCategory,
            AlertStatus,
            ChannelType,
            AlertTemplate,
            RateLimitConfig,
            RoutingRule,
            AlertConfig,
            Alert,
            DeliveryResult,
            AlertStats,
            LogChannel,
            WebhookChannel,
            AlertManager,
        )

        # All imports successful
        assert AlertPriority.CRITICAL is not None
        assert AlertManager is not None

    def test_multi_channel_delivery(self):
        """Test delivery to multiple channels."""
        manager = AlertManager()

        # Register webhook channel
        webhook = WebhookChannel("https://example.com/webhook")
        manager.register_channel(webhook)

        # Add rule for multi-channel delivery
        manager.add_routing_rule(RoutingRule(
            name="all_channels",
            priority=AlertPriority.HIGH,
            channels=[ChannelType.LOG, ChannelType.WEBHOOK],
        ))

        alert = manager.create_alert(
            title="Multi-Channel Test",
            message="Should go to multiple channels",
            priority=AlertPriority.HIGH,
        )
        results = manager.send(alert)

        # Should have results for multiple channels
        assert len(results) >= 2
        assert ChannelType.LOG in alert.channels_sent
        assert ChannelType.WEBHOOK in alert.channels_sent
