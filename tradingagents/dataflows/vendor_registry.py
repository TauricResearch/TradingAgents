"""Vendor Registry for extensible data vendor management.

This module provides a thread-safe registry pattern for managing data vendors,
enabling easy addition of new vendors without modifying core interface code.

Issue #11: [DATA-10] Interface routing - add new data vendors
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Set, Any, Type
import threading
import logging

logger = logging.getLogger(__name__)


class VendorCapability(Enum):
    """Capabilities that vendors can provide."""
    STOCK_DATA = auto()
    TECHNICAL_INDICATORS = auto()
    FUNDAMENTALS = auto()
    BALANCE_SHEET = auto()
    CASHFLOW = auto()
    INCOME_STATEMENT = auto()
    NEWS = auto()
    GLOBAL_NEWS = auto()
    INSIDER_SENTIMENT = auto()
    INSIDER_TRANSACTIONS = auto()
    MACROECONOMIC = auto()
    BENCHMARK = auto()


@dataclass
class VendorMetadata:
    """Metadata about a registered vendor."""
    name: str
    priority: int = 100  # Lower = higher priority
    capabilities: Set[VendorCapability] = field(default_factory=set)
    rate_limit_exception: Optional[Type[Exception]] = None
    description: str = ""
    enabled: bool = True

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, VendorMetadata):
            return False
        return self.name == other.name


class VendorRegistry:
    """Thread-safe singleton registry for data vendors.

    Provides centralized vendor registration, lookup, and routing.
    Uses double-checked locking for thread-safe singleton pattern.

    Example:
        # Register a vendor
        registry = VendorRegistry()
        registry.register_vendor(
            VendorMetadata(
                name="yfinance",
                priority=10,
                capabilities={VendorCapability.STOCK_DATA, VendorCapability.FUNDAMENTALS}
            )
        )

        # Register a method
        registry.register_method("yfinance", "get_stock_data", get_yfinance_stock)

        # Get vendors for a capability
        vendors = registry.get_vendors_for_capability(VendorCapability.STOCK_DATA)
    """

    _instance: Optional["VendorRegistry"] = None
    _lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> "VendorRegistry":
        """Thread-safe singleton instantiation with double-checked locking."""
        # Fast path: instance exists
        if cls._instance is not None:
            return cls._instance

        # Slow path: acquire lock and create instance
        with cls._lock:
            # Double-check inside lock
            if cls._instance is None:
                instance = super().__new__(cls)
                # Initialize instance attributes before publishing
                instance._vendors: Dict[str, VendorMetadata] = {}
                instance._methods: Dict[str, Dict[str, Callable]] = {}
                instance._capability_index: Dict[VendorCapability, Set[str]] = {}
                instance._vendor_lock = threading.RLock()
                # Publish instance only after fully initialized
                cls._instance = instance
            return cls._instance

    def __init__(self):
        """Initialize registry (only runs once due to singleton)."""
        # Skip if already initialized
        if VendorRegistry._initialized:
            return
        VendorRegistry._initialized = True

    def register_vendor(self, metadata: VendorMetadata) -> None:
        """Register a new vendor with its metadata.

        Args:
            metadata: VendorMetadata containing vendor info and capabilities

        Raises:
            ValueError: If vendor name is empty
        """
        if not metadata.name:
            raise ValueError("Vendor name cannot be empty")

        with self._vendor_lock:
            self._vendors[metadata.name] = metadata

            # Update capability index
            for capability in metadata.capabilities:
                if capability not in self._capability_index:
                    self._capability_index[capability] = set()
                self._capability_index[capability].add(metadata.name)

            logger.debug(f"Registered vendor: {metadata.name} with capabilities: {metadata.capabilities}")

    def unregister_vendor(self, name: str) -> bool:
        """Unregister a vendor.

        Args:
            name: Name of vendor to unregister

        Returns:
            True if vendor was unregistered, False if not found
        """
        with self._vendor_lock:
            if name not in self._vendors:
                return False

            metadata = self._vendors.pop(name)

            # Remove from capability index
            for capability in metadata.capabilities:
                if capability in self._capability_index:
                    self._capability_index[capability].discard(name)

            # Remove all registered methods
            if name in self._methods:
                del self._methods[name]

            logger.debug(f"Unregistered vendor: {name}")
            return True

    def register_method(
        self,
        vendor_name: str,
        method_name: str,
        implementation: Callable
    ) -> None:
        """Register a method implementation for a vendor.

        Args:
            vendor_name: Name of the vendor
            method_name: Name of the method
            implementation: Callable implementation

        Raises:
            ValueError: If vendor is not registered or method name is empty
        """
        if not method_name:
            raise ValueError("Method name cannot be empty")

        with self._vendor_lock:
            if vendor_name not in self._vendors:
                raise ValueError(f"Vendor '{vendor_name}' not registered")

            if vendor_name not in self._methods:
                self._methods[vendor_name] = {}

            self._methods[vendor_name][method_name] = implementation
            logger.debug(f"Registered method '{method_name}' for vendor '{vendor_name}'")

    def get_vendor(self, name: str) -> Optional[VendorMetadata]:
        """Get vendor metadata by name.

        Args:
            name: Vendor name

        Returns:
            VendorMetadata if found, None otherwise
        """
        with self._vendor_lock:
            return self._vendors.get(name)

    def get_all_vendors(self) -> List[VendorMetadata]:
        """Get all registered vendors sorted by priority.

        Returns:
            List of VendorMetadata sorted by priority (lower = higher)
        """
        with self._vendor_lock:
            return sorted(
                self._vendors.values(),
                key=lambda v: v.priority
            )

    def get_vendors_for_capability(
        self,
        capability: VendorCapability,
        only_enabled: bool = True
    ) -> List[VendorMetadata]:
        """Get all vendors that support a specific capability.

        Args:
            capability: The capability to find vendors for
            only_enabled: If True, only return enabled vendors

        Returns:
            List of VendorMetadata sorted by priority
        """
        with self._vendor_lock:
            vendor_names = self._capability_index.get(capability, set())
            vendors = [
                self._vendors[name]
                for name in vendor_names
                if name in self._vendors
            ]

            if only_enabled:
                vendors = [v for v in vendors if v.enabled]

            return sorted(vendors, key=lambda v: v.priority)

    def get_method(
        self,
        vendor_name: str,
        method_name: str
    ) -> Optional[Callable]:
        """Get a method implementation for a vendor.

        Args:
            vendor_name: Name of the vendor
            method_name: Name of the method

        Returns:
            Callable if found, None otherwise
        """
        with self._vendor_lock:
            vendor_methods = self._methods.get(vendor_name, {})
            return vendor_methods.get(method_name)

    def get_methods_for_vendor(self, vendor_name: str) -> Dict[str, Callable]:
        """Get all methods registered for a vendor.

        Args:
            vendor_name: Name of the vendor

        Returns:
            Dictionary mapping method names to implementations
        """
        with self._vendor_lock:
            return dict(self._methods.get(vendor_name, {}))

    def set_vendor_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a vendor.

        Args:
            name: Vendor name
            enabled: Whether vendor should be enabled

        Returns:
            True if vendor was found and updated, False otherwise
        """
        with self._vendor_lock:
            if name not in self._vendors:
                return False
            self._vendors[name].enabled = enabled
            return True

    def set_vendor_priority(self, name: str, priority: int) -> bool:
        """Update a vendor's priority.

        Args:
            name: Vendor name
            priority: New priority (lower = higher priority)

        Returns:
            True if vendor was found and updated, False otherwise
        """
        with self._vendor_lock:
            if name not in self._vendors:
                return False
            self._vendors[name].priority = priority
            return True

    def clear(self) -> None:
        """Clear all registrations. Primarily for testing."""
        with self._vendor_lock:
            self._vendors.clear()
            self._methods.clear()
            self._capability_index.clear()
            logger.debug("Cleared all vendor registrations")

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance. For testing only."""
        with cls._lock:
            cls._instance = None
            cls._initialized = False


# Module-level convenience functions
def get_registry() -> VendorRegistry:
    """Get the global vendor registry instance."""
    return VendorRegistry()


def register_vendor(metadata: VendorMetadata) -> None:
    """Register a vendor in the global registry."""
    get_registry().register_vendor(metadata)


def register_method(vendor_name: str, method_name: str, implementation: Callable) -> None:
    """Register a method in the global registry."""
    get_registry().register_method(vendor_name, method_name, implementation)
