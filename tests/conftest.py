"""conftest.py — mock out heavy third-party dependencies AND the internal
package __init__ modules that create deep import chains.  This lets tests
import specific leaf modules (risk_manager.py, propagation.py, setup.py)
without triggering the full dependency tree, which requires Python 3.10+
and numerous third-party packages.
"""

import os
import sys
from unittest.mock import MagicMock

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG_ROOT = os.path.join(_PROJECT_ROOT, "tradingagents")

# ---------------------------------------------------------------------------
# External third-party packages to mock
# ---------------------------------------------------------------------------
_EXTERNAL_PACKAGES = [
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.tools",
    "langchain_core.utils",
    "langchain_core.utils.function_calling",
    "langchain_openai",
    "langchain_anthropic",
    "langchain_google_genai",
    "langchain_experimental",
    "langchain_experimental.utilities",
    "langgraph",
    "langgraph.graph",
    "langgraph.prebuilt",
    "yfinance",
    "pandas",
    "backtrader",
    "stockstats",
    "rank_bm25",
    "requests",
    "parsel",
    "redis",
    "chainlit",
    "questionary",
    "typer",
    "rich",
    "rich.console",
    "rich.panel",
    "rich.table",
    "rich.progress",
    "tqdm",
    "pytz",
    "setuptools",
]


def _make_mock(name, path=None):
    """Create a MagicMock that behaves like a module/package."""
    mock_mod = MagicMock()
    mock_mod.__name__ = name
    mock_mod.__file__ = f"<mocked {name}>"
    mock_mod.__path__ = [path] if path else []
    mock_mod.__all__ = []
    mock_mod.__spec__ = None
    mock_mod.__package__ = name
    return mock_mod


# Install external mocks
for _pkg in _EXTERNAL_PACKAGES:
    if _pkg not in sys.modules:
        sys.modules[_pkg] = _make_mock(_pkg)

# ---------------------------------------------------------------------------
# Internal packages: replace __init__.py-level imports with stubs that have
# real __path__ entries so importlib can still find submodule .py files.
# ---------------------------------------------------------------------------
_INTERNAL_PKG_DIRS = {
    "tradingagents.graph": os.path.join(_PKG_ROOT, "graph"),
    "tradingagents.graph.conditional_logic": None,  # leaf, no subdir
    "tradingagents.agents": os.path.join(_PKG_ROOT, "agents"),
    "tradingagents.agents.utils": os.path.join(_PKG_ROOT, "agents", "utils"),
    "tradingagents.agents.utils.agent_utils": None,
    "tradingagents.agents.utils.memory": None,
    "tradingagents.agents.managers": os.path.join(_PKG_ROOT, "agents", "managers"),
    "tradingagents.dataflows": os.path.join(_PKG_ROOT, "dataflows"),
    "tradingagents.dataflows.interface": None,
}

for _pkg, _dir in _INTERNAL_PKG_DIRS.items():
    if _pkg not in sys.modules:
        sys.modules[_pkg] = _make_mock(_pkg, _dir)

# ---------------------------------------------------------------------------
# Now import the real leaf modules we want to test.
# ---------------------------------------------------------------------------
import importlib

# agent_states — pure TypedDict definitions, needs typing_extensions + mocked langgraph
_agent_states = importlib.import_module("tradingagents.agents.utils.agent_states")
sys.modules["tradingagents.agents.utils.agent_states"] = _agent_states

# propagation.py — imports agent_states (now real)
_propagation = importlib.import_module("tradingagents.graph.propagation")
sys.modules["tradingagents.graph.propagation"] = _propagation

# risk_manager.py — standalone, only uses llm.invoke and memory
_risk_manager = importlib.import_module("tradingagents.agents.managers.risk_manager")
sys.modules["tradingagents.agents.managers.risk_manager"] = _risk_manager

# setup.py — defines ChatModel type alias; imports langchain_* (mocked) and .conditional_logic (mocked)
_setup = importlib.import_module("tradingagents.graph.setup")
sys.modules["tradingagents.graph.setup"] = _setup
