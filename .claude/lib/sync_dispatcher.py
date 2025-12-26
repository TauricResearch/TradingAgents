#!/usr/bin/env python3
"""
Sync Dispatcher - Backward Compatibility Shim

This module maintains backward compatibility by re-exporting all symbols
from the sync_dispatcher package. Existing code importing from this module
will continue to work unchanged.

DEPRECATED: This module is kept for backward compatibility only.
New code should import from the sync_dispatcher package directly:

    # Old way (still works)
    from sync_dispatcher import SyncResult, SyncDispatcher

    # New way (preferred)
    from sync_dispatcher.models import SyncResult
    from sync_dispatcher.dispatcher import SyncDispatcher

Date: 2025-12-25
Issue: GitHub #TBD - Refactor sync_dispatcher into package
"""

# Re-export all public symbols from the package
from sync_dispatcher import (
    SyncResult,
    SyncDispatcherError,
    SyncError,
    SyncDispatcher,
    dispatch_sync,
    sync_marketplace,
    main,
    AgentInvoker,
    SyncMode,
)

# Define __all__ for explicit exports
__all__ = [
    "SyncResult",
    "SyncDispatcherError",
    "SyncError",
    "SyncDispatcher",
    "dispatch_sync",
    "sync_marketplace",
    "main",
    "AgentInvoker",
    "SyncMode",
]

# CLI entry point
if __name__ == "__main__":
    import sys
    sys.exit(main())
