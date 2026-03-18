"""
Auto-discovery and registration of market providers.

Each market subdirectory (vn/, th/, etc.) should export a `provider` instance
that is a subclass of MarketProvider. This module auto-discovers and registers them.
"""

import importlib
import pkgutil
from pathlib import Path

from ..market_registry import registry


def _discover_and_register():
    """Discover all market provider modules and register them."""
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if not module_info.ispkg:
            continue

        try:
            module = importlib.import_module(f".{module_info.name}", package=__name__)
            provider = getattr(module, "provider", None)
            if provider is not None:
                registry.register(provider)
        except Exception as e:
            print(f"Warning: Could not load market provider '{module_info.name}': {e}")


_discover_and_register()
