"""
Vendor Registry System for Interface Routing (Issue #11).

This module provides:
1. VendorCapability - Enum for vendor capabilities
2. VendorMetadata - Dataclass for vendor information
3. VendorRegistry - Thread-safe singleton for vendor registration and lookup
4. VendorRegistrationError - Custom exception for registration errors

The registry enables centralized vendor management with priority-based
routing, capability tracking, and thread-safe access patterns.
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class VendorCapability(str, Enum):
    """
    Enum for vendor capabilities.

    Defines standard data provider capabilities for routing requests
    to appropriate vendors.
    """

    STOCK_DATA = "stock_data"
    FUNDAMENTALS = "fundamentals"
    TECHNICAL_INDICATORS = "technical_indicators"
    NEWS = "news"
    MACROECONOMIC = "macroeconomic"
    INSIDER_DATA = "insider_data"


@dataclass
class VendorMetadata:
    """
    Metadata for a registered vendor.

    Attributes:
        name: Vendor identifier (e.g., "alpha_vantage")
        capabilities: List of VendorCapability values
        methods: Dict mapping method names to implementation names
        priority: Vendor priority for routing (higher = preferred)
        rate_limit: Maximum calls per minute (None = unlimited)
    """

    name: str
    capabilities: List[str]
    methods: Dict[str, str]
    priority: int = 0
    rate_limit: Optional[int] = None


class VendorRegistrationError(Exception):
    """Exception raised for vendor registration errors."""
    pass


class VendorRegistry:
    """
    Thread-safe singleton registry for vendor management.

    Provides centralized registration, lookup, and routing for data vendors.
    Uses double-checked locking for thread-safe singleton pattern.

    Thread Safety:
        All public methods use internal locking to ensure thread-safe access.
        Registry state is protected by _lock during mutations.

    Usage:
        registry = VendorRegistry()
        registry.register_vendor(vendor_class, metadata)
        vendors = registry.get_vendor_for_method("get_stock_data")
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """
        Create or return singleton instance with double-checked locking.

        Returns:
            VendorRegistry: Singleton instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize registry storage (only once for singleton)."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            self._vendors: Dict[str, Dict[str, Any]] = {}
            self._method_map: Dict[str, List[Dict[str, Any]]] = {}
            self._initialized = True

    def register_vendor(self, vendor_class: type, metadata: VendorMetadata) -> None:
        """
        Register a vendor with its metadata.

        Args:
            vendor_class: Vendor class to register
            metadata: VendorMetadata describing vendor capabilities

        Thread Safety:
            Uses lock to ensure atomic registration
        """
        with self._lock:
            # Store vendor and metadata
            self._vendors[metadata.name] = {
                'class': vendor_class,
                'metadata': metadata
            }

            # Update method map for each method
            for method_name, impl_name in metadata.methods.items():
                if method_name not in self._method_map:
                    self._method_map[method_name] = []

                # Remove existing entry for this vendor if present
                self._method_map[method_name] = [
                    entry for entry in self._method_map[method_name]
                    if entry['vendor'] != metadata.name
                ]

                # Add new entry
                self._method_map[method_name].append({
                    'vendor': metadata.name,
                    'priority': metadata.priority,
                    'implementation': impl_name
                })

                # Sort by priority (highest first)
                self._method_map[method_name].sort(
                    key=lambda x: x['priority'],
                    reverse=True
                )

    def get_vendor_for_method(self, method_name: str) -> List[str]:
        """
        Get list of vendors supporting a method, ordered by priority.

        Args:
            method_name: Method name to lookup (e.g., "get_stock_data")

        Returns:
            List of vendor names ordered by priority (highest first)
            Empty list if no vendors support the method

        Thread Safety:
            Read-only operation, no locking needed for immutable view
        """
        if method_name not in self._method_map:
            return []

        return [entry['vendor'] for entry in self._method_map[method_name]]

    def get_vendor_metadata(self, vendor_name: str) -> VendorMetadata:
        """
        Get metadata for a specific vendor.

        Args:
            vendor_name: Name of vendor to lookup

        Returns:
            VendorMetadata for the vendor

        Raises:
            ValueError: If vendor not found

        Thread Safety:
            Read-only operation, no locking needed for immutable view
        """
        if vendor_name not in self._vendors:
            raise ValueError(f"Vendor '{vendor_name}' not found")

        return self._vendors[vendor_name]['metadata']

    def list_all_vendors(self) -> List[str]:
        """
        List all registered vendor names.

        Returns:
            List of registered vendor names

        Thread Safety:
            Read-only operation, no locking needed for immutable view
        """
        return list(self._vendors.keys())

    def get_methods_by_capability(self, capability: str) -> List[str]:
        """
        Get all methods provided by vendors with a specific capability.

        Args:
            capability: Capability to search for (e.g., "stock_data")

        Returns:
            List of method names provided by vendors with this capability

        Thread Safety:
            Read-only operation, no locking needed for immutable view
        """
        methods = set()

        for vendor_name, vendor_data in self._vendors.items():
            metadata = vendor_data['metadata']
            if capability in metadata.capabilities:
                methods.update(metadata.methods.keys())

        return list(methods)

    def get_vendor_implementation(self, vendor_name: str, method_name: str) -> Optional[str]:
        """
        Get the implementation name for a specific vendor and method.

        Args:
            vendor_name: Name of vendor
            method_name: Name of method

        Returns:
            Implementation method name, or None if not found

        Thread Safety:
            Read-only operation, no locking needed for immutable view
        """
        if vendor_name not in self._vendors:
            return None

        metadata = self._vendors[vendor_name]['metadata']
        return metadata.methods.get(method_name)

    def clear_registry(self) -> None:
        """
        Clear all registered vendors (primarily for testing).

        Thread Safety:
            Uses lock to ensure atomic clear operation
        """
        with self._lock:
            self._vendors.clear()
            self._method_map.clear()
