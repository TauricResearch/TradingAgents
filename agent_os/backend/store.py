import asyncio
from typing import Any

# In-memory store for demo (should be replaced by Redis/DB for persistence).
# All mutations MUST be performed while holding `runs_lock` to prevent
# concurrent read-modify-write races in the asyncio event loop.
runs: dict[str, dict[str, Any]] = {}
runs_lock: asyncio.Lock = asyncio.Lock()
