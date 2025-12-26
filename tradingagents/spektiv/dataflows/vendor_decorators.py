"""
Vendor Decorators for Auto-Registration and Rate Limiting (Issue #11).

This module provides:
1. @register_vendor - Auto-register vendor class with registry
2. @vendor_method - Map implementation method to standard method name
3. @rate_limited - Enforce rate limiting on vendor methods

Decorators can be stacked for complete vendor implementation.
"""

import time
import threading
from functools import wraps
from typing import List, Callable, Optional

from spektiv.dataflows.vendor_registry import VendorRegistry, VendorMetadata


def register_vendor(
    name: str,
    capabilities: List[str],
    priority: int = 0,
    rate_limit: Optional[int] = None,
    requires_auth: bool = False
) -> Callable:
    """
    Decorator to auto-register vendor class with VendorRegistry.

    Adds vendor metadata to the class and registers it with the global
    VendorRegistry singleton on class definition.

    Args:
        name: Vendor identifier (e.g., "alpha_vantage")
        capabilities: List of capability strings
        priority: Vendor priority for routing (higher = preferred)
        rate_limit: Maximum calls per minute (optional)
        requires_auth: Whether vendor requires authentication

    Returns:
        Class decorator function

    Usage:
        @register_vendor(
            name="alpha_vantage",
            capabilities=["stock_data", "fundamentals"],
            priority=100,
            rate_limit=5
        )
        class AlphaVantageVendor(BaseVendor):
            pass
    """
    def decorator(cls):
        # Collect method mappings from @vendor_method decorators
        methods = {}
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if hasattr(attr, '_vendor_method'):
                methods[attr._vendor_method] = attr_name

        # Create metadata
        metadata = VendorMetadata(
            name=name,
            capabilities=capabilities,
            methods=methods,
            priority=priority,
            rate_limit=rate_limit
        )

        # Register with singleton registry
        registry = VendorRegistry()
        registry.register_vendor(cls, metadata)

        # Add metadata to class for introspection
        cls._vendor_name = name
        cls._vendor_capabilities = capabilities
        cls._vendor_priority = priority
        cls._vendor_rate_limit = rate_limit
        cls._vendor_requires_auth = requires_auth

        return cls

    return decorator


def vendor_method(method_name: str) -> Callable:
    """
    Decorator to map vendor implementation method to standard method name.

    Marks a method as implementing a standard interface method.
    The @register_vendor decorator collects these mappings.

    Args:
        method_name: Standard method name (e.g., "get_stock_data")

    Returns:
        Method decorator function

    Usage:
        class MyVendor(BaseVendor):
            @vendor_method("get_stock_data")
            def fetch_stock_data(self, ticker):
                return self._api_call(ticker)
    """
    def decorator(func):
        # Add metadata to function
        func._vendor_method = method_name

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Preserve metadata on wrapper
        wrapper._vendor_method = method_name
        return wrapper

    return decorator


def rate_limited(
    calls_per_minute: int,
    burst: Optional[int] = None
) -> Callable:
    """
    Decorator to enforce rate limiting on vendor methods.

    Uses a sliding window algorithm with thread-safe access.
    Raises exception if rate limit or burst limit exceeded.

    Args:
        calls_per_minute: Maximum calls per minute
        burst: Maximum burst size (optional, defaults to calls_per_minute)

    Returns:
        Method decorator function

    Raises:
        Exception: If rate limit or burst limit exceeded

    Usage:
        class MyVendor(BaseVendor):
            @rate_limited(calls_per_minute=5, burst=10)
            def fetch_data(self):
                return self._api_call()
    """
    def decorator(func):
        # Create rate limit state per decorated function
        state = {
            'calls': [],
            'calls_per_minute': calls_per_minute,
            'burst': burst if burst is not None else calls_per_minute,
            'lock': threading.Lock()
        }

        @wraps(func)
        def wrapper(*args, **kwargs):
            with state['lock']:
                now = time.time()
                minute_ago = now - 60.0

                # Remove calls older than 1 minute (sliding window)
                state['calls'] = [t for t in state['calls'] if t > minute_ago]

                # Check rate limit (calls per minute)
                if len(state['calls']) >= state['calls_per_minute']:
                    raise Exception(
                        f"Rate limit exceeded: {state['calls_per_minute']} calls/minute"
                    )

                # Check burst limit (simultaneous calls)
                if state['burst'] and len(state['calls']) >= state['burst']:
                    raise Exception(
                        f"Burst limit exceeded: {state['burst']} calls"
                    )

                # Record this call
                state['calls'].append(now)

            # Execute function outside lock
            return func(*args, **kwargs)

        # Add rate limit metadata for introspection
        wrapper._rate_limit = calls_per_minute
        wrapper._rate_limit_burst = burst

        return wrapper

    return decorator
