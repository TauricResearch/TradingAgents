from typing import Any

# In-memory store for demo (should be replaced by Redis/DB for persistence).
#
# Concurrency model: all mutations occur in the single-threaded asyncio event
# loop as synchronous dict operations between await points. Each run_id has at
# most one driving coroutine (_run_and_store / _resume_and_store), so there are
# no concurrent writers to the same run record. This is safe without a lock as
# long as the server remains single-process. If multi-worker deployment is ever
# needed, replace this with Redis or a database.
runs: dict[str, dict[str, Any]] = {}
