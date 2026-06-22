"""FastAPI server that runs inside the TradingDesk backend Docker container.

Wraps the TradingAgents engine and streams a run's events to the macOS app over
Server-Sent Events. The event objects are exactly the ones produced by
``desk_adapter.diff.SnapshotDiffer`` (the NDJSON payloads), now delivered as SSE
``data:`` frames — so the engine-side derivation logic is shared, not duplicated.
"""
