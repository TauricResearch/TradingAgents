"""TradingAgents — multi-agent LLM financial trading framework."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("tradingagents")
except PackageNotFoundError:  # pragma: no cover - fallback when not installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
