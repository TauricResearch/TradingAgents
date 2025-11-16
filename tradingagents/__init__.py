"""
TradingAgents - Multi-Agents LLM Financial Trading Framework.

This package provides the main functionality for the TradingAgents system,
including workflows, agents, and domain services.
"""

# Expose Dagster workspace definition
from tradingagents.workflows.definitions import define_tradingagents_workspace

__all__ = ["define_tradingagents_workspace"]
