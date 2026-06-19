"""API capabilities inventory for the ticker accuracy agent.

Provides a dynamic list of all backend API endpoints the agent can use,
so the agent knows its capabilities and can detect missing ones.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiCapability:
    path: str
    method: str
    purpose: str
    available: bool = True


_DEFINED_CAPABILITIES: list[ApiCapability] = [
    ApiCapability("/api/runs", "POST", "Start a new analysis run for a ticker"),
    ApiCapability("/api/runs/{run_id}", "GET", "Get run details including events and LLM calls"),
    ApiCapability("/api/runs/{run_id}/cancel", "POST", "Cancel a running run"),
    ApiCapability("/api/runs/{run_id}/resume", "POST", "Resume a failed run"),
    ApiCapability("/api/runs/delete-bulk", "POST", "Delete multiple runs"),
    ApiCapability("/api/watchlist", "GET", "List all watchlist tickers"),
    ApiCapability("/api/watchlist", "POST", "Add a ticker to the watchlist"),
    ApiCapability("/api/watchlist/{ticker}", "DELETE", "Remove a ticker from the watchlist"),
    ApiCapability("/api/tickers/{ticker}/runs", "GET", "List runs for a specific ticker"),
    ApiCapability("/api/tickers/{ticker}/history", "GET", "Get price history + runs for a ticker"),
    ApiCapability("/api/prices", "GET", "Get current prices for all watchlist tickers"),
    ApiCapability("/api/background-runs", "POST", "Schedule historical backtests for a ticker"),
    ApiCapability("/api/background-runs", "GET", "List background run jobs"),
    ApiCapability("/api/background-runs/{job_id}/cancel", "POST", "Cancel a background job"),
    ApiCapability("/api/background-runs/{job_id}/pause", "POST", "Pause a background job"),
    ApiCapability("/api/background-runs/{job_id}/resume", "POST", "Resume a paused background job"),
    ApiCapability("/api/background-runs/{job_id}", "DELETE", "Delete a background run job"),
    ApiCapability("/api/config", "GET", "Get app configuration"),
    ApiCapability("/api/config", "PUT", "Update app configuration"),
    ApiCapability("/api/config/models", "GET", "Get current LLM model configuration"),
    ApiCapability("/api/health", "GET", "Health check endpoint"),
]


def discover_api_capabilities() -> list[ApiCapability]:
    """Return the list of API capabilities available to the agent."""
    return _DEFINED_CAPABILITIES.copy()


def get_capability_by_path(path: str) -> ApiCapability | None:
    """Find a capability by its path pattern."""
    for cap in _DEFINED_CAPABILITIES:
        if cap.path == path:
            return cap
    return None
