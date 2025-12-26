"""Tests for VendorRegistry.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

import pytest
import threading
from unittest.mock import Mock

from tradingagents.dataflows.vendor_registry import (
    VendorCapability,
    VendorMetadata,
    VendorRegistry,
    get_registry,
    register_vendor,
    register_method,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton registry before each test."""
    VendorRegistry.reset_instance()
    yield
    VendorRegistry.reset_instance()


class TestVendorMetadata:
    """Tests for VendorMetadata dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        metadata = VendorMetadata(name="test")
        assert metadata.name == "test"
        assert metadata.priority == 100
        assert metadata.capabilities == set()
        assert metadata.rate_limit_exception is None
        assert metadata.description == ""
        assert metadata.enabled is True

    def test_custom_values(self):
        """Test custom values are preserved."""
        metadata = VendorMetadata(
            name="yfinance",
            priority=10,
            capabilities={VendorCapability.STOCK_DATA},
            description="Yahoo Finance vendor"
        )
        assert metadata.name == "yfinance"
        assert metadata.priority == 10
        assert VendorCapability.STOCK_DATA in metadata.capabilities
        assert metadata.description == "Yahoo Finance vendor"

    def test_hash(self):
        """Test VendorMetadata is hashable by name."""
        m1 = VendorMetadata(name="vendor1")
        m2 = VendorMetadata(name="vendor1", priority=50)
        assert hash(m1) == hash(m2)

    def test_equality(self):
        """Test VendorMetadata equality is by name."""
        m1 = VendorMetadata(name="vendor1", priority=10)
        m2 = VendorMetadata(name="vendor1", priority=50)
        m3 = VendorMetadata(name="vendor2")
        assert m1 == m2
        assert m1 != m3

    def test_equality_with_non_metadata(self):
        """Test equality with non-VendorMetadata objects."""
        metadata = VendorMetadata(name="test")
        assert metadata != "test"
        assert metadata != {"name": "test"}


class TestVendorRegistry:
    """Tests for VendorRegistry singleton."""

    def test_singleton_pattern(self):
        """Test that VendorRegistry is a singleton."""
        r1 = VendorRegistry()
        r2 = VendorRegistry()
        assert r1 is r2

    def test_get_registry_returns_singleton(self):
        """Test get_registry returns same instance."""
        r1 = get_registry()
        r2 = VendorRegistry()
        assert r1 is r2

    def test_reset_instance(self):
        """Test reset_instance creates new singleton."""
        r1 = VendorRegistry()
        VendorRegistry.reset_instance()
        r2 = VendorRegistry()
        assert r1 is not r2

    def test_register_vendor(self):
        """Test registering a vendor."""
        registry = VendorRegistry()
        metadata = VendorMetadata(
            name="yfinance",
            capabilities={VendorCapability.STOCK_DATA}
        )
        registry.register_vendor(metadata)

        result = registry.get_vendor("yfinance")
        assert result is not None
        assert result.name == "yfinance"

    def test_register_vendor_empty_name_raises(self):
        """Test registering vendor with empty name raises ValueError."""
        registry = VendorRegistry()
        with pytest.raises(ValueError, match="cannot be empty"):
            registry.register_vendor(VendorMetadata(name=""))

    def test_unregister_vendor(self):
        """Test unregistering a vendor."""
        registry = VendorRegistry()
        metadata = VendorMetadata(name="test_vendor")
        registry.register_vendor(metadata)

        assert registry.unregister_vendor("test_vendor") is True
        assert registry.get_vendor("test_vendor") is None

    def test_unregister_nonexistent_vendor(self):
        """Test unregistering non-existent vendor returns False."""
        registry = VendorRegistry()
        assert registry.unregister_vendor("nonexistent") is False

    def test_get_all_vendors_sorted_by_priority(self):
        """Test get_all_vendors returns vendors sorted by priority."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="low", priority=100))
        registry.register_vendor(VendorMetadata(name="high", priority=10))
        registry.register_vendor(VendorMetadata(name="medium", priority=50))

        vendors = registry.get_all_vendors()
        assert [v.name for v in vendors] == ["high", "medium", "low"]

    def test_get_vendors_for_capability(self):
        """Test getting vendors by capability."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(
            name="yfinance",
            capabilities={VendorCapability.STOCK_DATA, VendorCapability.FUNDAMENTALS}
        ))
        registry.register_vendor(VendorMetadata(
            name="alpha_vantage",
            capabilities={VendorCapability.STOCK_DATA}
        ))

        stock_vendors = registry.get_vendors_for_capability(VendorCapability.STOCK_DATA)
        assert len(stock_vendors) == 2

        fundamental_vendors = registry.get_vendors_for_capability(VendorCapability.FUNDAMENTALS)
        assert len(fundamental_vendors) == 1
        assert fundamental_vendors[0].name == "yfinance"

    def test_get_vendors_for_capability_only_enabled(self):
        """Test only enabled vendors are returned by default."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(
            name="enabled_vendor",
            capabilities={VendorCapability.STOCK_DATA}
        ))
        registry.register_vendor(VendorMetadata(
            name="disabled_vendor",
            capabilities={VendorCapability.STOCK_DATA},
            enabled=False
        ))

        vendors = registry.get_vendors_for_capability(VendorCapability.STOCK_DATA)
        assert len(vendors) == 1
        assert vendors[0].name == "enabled_vendor"

        all_vendors = registry.get_vendors_for_capability(
            VendorCapability.STOCK_DATA,
            only_enabled=False
        )
        assert len(all_vendors) == 2


class TestVendorRegistryMethods:
    """Tests for method registration in VendorRegistry."""

    def test_register_method(self):
        """Test registering a method for a vendor."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="yfinance"))

        mock_func = Mock()
        registry.register_method("yfinance", "get_stock", mock_func)

        result = registry.get_method("yfinance", "get_stock")
        assert result is mock_func

    def test_register_method_unregistered_vendor_raises(self):
        """Test registering method for unregistered vendor raises."""
        registry = VendorRegistry()
        with pytest.raises(ValueError, match="not registered"):
            registry.register_method("nonexistent", "method", Mock())

    def test_register_method_empty_name_raises(self):
        """Test registering method with empty name raises."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="test"))
        with pytest.raises(ValueError, match="cannot be empty"):
            registry.register_method("test", "", Mock())

    def test_get_method_nonexistent(self):
        """Test getting non-existent method returns None."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="test"))
        assert registry.get_method("test", "nonexistent") is None

    def test_get_methods_for_vendor(self):
        """Test getting all methods for a vendor."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="yfinance"))

        func1 = Mock()
        func2 = Mock()
        registry.register_method("yfinance", "get_stock", func1)
        registry.register_method("yfinance", "get_fundamentals", func2)

        methods = registry.get_methods_for_vendor("yfinance")
        assert len(methods) == 2
        assert methods["get_stock"] is func1
        assert methods["get_fundamentals"] is func2

    def test_get_methods_for_unregistered_vendor(self):
        """Test getting methods for unregistered vendor returns empty dict."""
        registry = VendorRegistry()
        assert registry.get_methods_for_vendor("nonexistent") == {}


class TestVendorRegistryVendorControl:
    """Tests for vendor enable/disable and priority control."""

    def test_set_vendor_enabled(self):
        """Test enabling/disabling a vendor."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="test", enabled=True))

        assert registry.set_vendor_enabled("test", False) is True
        assert registry.get_vendor("test").enabled is False

        assert registry.set_vendor_enabled("test", True) is True
        assert registry.get_vendor("test").enabled is True

    def test_set_vendor_enabled_nonexistent(self):
        """Test setting enabled on non-existent vendor."""
        registry = VendorRegistry()
        assert registry.set_vendor_enabled("nonexistent", True) is False

    def test_set_vendor_priority(self):
        """Test updating vendor priority."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="test", priority=100))

        assert registry.set_vendor_priority("test", 10) is True
        assert registry.get_vendor("test").priority == 10

    def test_set_vendor_priority_nonexistent(self):
        """Test setting priority on non-existent vendor."""
        registry = VendorRegistry()
        assert registry.set_vendor_priority("nonexistent", 10) is False

    def test_clear(self):
        """Test clearing all registrations."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(
            name="test",
            capabilities={VendorCapability.STOCK_DATA}
        ))
        registry.register_method("test", "method", Mock())

        registry.clear()

        assert registry.get_vendor("test") is None
        assert len(registry.get_all_vendors()) == 0


class TestVendorRegistryThreadSafety:
    """Tests for thread safety of VendorRegistry."""

    def test_concurrent_registration(self):
        """Test concurrent vendor registration is thread-safe."""
        registry = VendorRegistry()
        errors = []

        def register_vendor(i):
            try:
                registry.register_vendor(VendorMetadata(
                    name=f"vendor_{i}",
                    capabilities={VendorCapability.STOCK_DATA}
                ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_vendor, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(registry.get_all_vendors()) == 50

    def test_concurrent_method_registration(self):
        """Test concurrent method registration is thread-safe."""
        registry = VendorRegistry()
        registry.register_vendor(VendorMetadata(name="test"))
        errors = []

        def register_method(i):
            try:
                registry.register_method("test", f"method_{i}", Mock())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_method, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(registry.get_methods_for_vendor("test")) == 50


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_register_vendor_function(self):
        """Test module-level register_vendor function."""
        metadata = VendorMetadata(name="module_test")
        register_vendor(metadata)

        registry = get_registry()
        assert registry.get_vendor("module_test") is not None

    def test_register_method_function(self):
        """Test module-level register_method function."""
        metadata = VendorMetadata(name="method_test")
        register_vendor(metadata)

        mock_func = Mock()
        register_method("method_test", "test_method", mock_func)

        registry = get_registry()
        assert registry.get_method("method_test", "test_method") is mock_func
