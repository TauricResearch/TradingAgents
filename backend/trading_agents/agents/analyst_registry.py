"""Analyst Plugin Registry for TradingAgents.

The registry is the single place where analyst metadata, factory functions,
and tool lists live.  Registering a new analyst requires only decorating its
factory function — no changes to graph/setup.py, conditional_logic.py, or
trading_graph.py are needed.

Usage — built-in analysts (applied in each analysts/*.py file)::

    @register_analyst(
        key="market",
        agent_node="Market Analyst",
        clear_node="Msg Clear Market",
        tool_node="tools_market",
        report_key="market_report",
        tools=[get_stock_data, get_indicators],
    )
    def create_market_analyst(llm):
        ...

Usage — third-party / custom analyst::

    from tradingagents.agents.analyst_registry import register_analyst
    from my_package.tools import my_tool

    @register_analyst(
        key="my_analyst",
        agent_node="My Analyst",
        clear_node="Msg Clear MyAnalyst",
        tool_node="tools_my_analyst",
        report_key="my_report",
        tools=[my_tool],
    )
    def create_my_analyst(llm):
        def node(state):
            ...
        return node

    # Then pass "my_analyst" to TradingAgentsGraph(selected_analysts=[..., "my_analyst"])

Public API
----------
register_analyst   : decorator — register a factory function
get_factory(key)   : return the factory callable for key
get_tools(key)     : return the tool list for key
list_analysts()    : return sorted list of registered keys
is_registered(key) : True if key is in registry
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

_logger = logging.getLogger(__name__)


@dataclass
class AnalystRegistration:
    """All metadata for a single registered analyst."""

    key: str
    agent_node: str
    clear_node: str
    tool_node: str
    report_key: str
    factory: Callable       # (llm) → node_function(state) → dict
    tools: list             # LangChain tool objects for ToolNode construction


# Module-level registry dict — populated by @register_analyst decorators
_REGISTRY: dict[str, AnalystRegistration] = {}


def register_analyst(
    key: str,
    agent_node: str,
    clear_node: str,
    tool_node: str,
    report_key: str,
    tools: list,
):
    """Decorator factory that registers an analyst factory function.

    Side effects on decoration
    ~~~~~~~~~~~~~~~~~~~~~~~~~~
    1. Adds an ``AnalystNodeSpec`` entry to ``ANALYST_NODE_SPECS`` (in
       ``graph/analyst_execution.py``) so ``build_analyst_execution_plan``
       continues to work without modification.
    2. Injects a ``should_continue_<key>()`` method into ``ConditionalLogic``
       (in ``graph/conditional_logic.py``) so the graph can route tool-call
       cycles for the new analyst automatically.

    Both side-effects use the ``tool_node`` and ``clear_node`` values passed
    to the decorator, so the routing is always consistent with the spec.
    """

    def decorator(factory_fn: Callable) -> Callable:
        reg = AnalystRegistration(
            key=key,
            agent_node=agent_node,
            clear_node=clear_node,
            tool_node=tool_node,
            report_key=report_key,
            factory=factory_fn,
            tools=list(tools),
        )
        _REGISTRY[key] = reg

        # Note: ANALYST_NODE_SPECS and ConditionalLogic side-effects are applied
        # lazily at graph-setup time (see sync_registry_to_graph() below).
        # Doing them here would cause a circular import:
        #   tradingagents.agents → analyst_registry → tradingagents.graph →
        #   tradingagents.graph.__init__ → trading_graph → tradingagents.agents (partial)
        _logger.debug("Registered analyst: key=%r agent_node=%r", key, agent_node)
        return factory_fn

    return decorator


def sync_registry_to_graph() -> None:
    """Apply registry side-effects to graph components.

    Call this once after all packages are initialized (i.e. inside
    ``GraphSetup.setup_graph()``).  Calling it multiple times is safe.

    Side effects:
    - Adds/updates entries in ``ANALYST_NODE_SPECS`` for registered analysts
      that are not already present (custom plugins).
    - Injects ``should_continue_<key>()`` methods into ``ConditionalLogic``
      for registered analysts that don't yet have one.
    """
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS, AnalystNodeSpec
    from tradingagents.graph.conditional_logic import ConditionalLogic

    for reg in _REGISTRY.values():
        # 1. ANALYST_NODE_SPECS — only add if missing (built-ins are pre-populated)
        if reg.key not in ANALYST_NODE_SPECS:
            ANALYST_NODE_SPECS[reg.key] = AnalystNodeSpec(
                key=reg.key,
                agent_node=reg.agent_node,
                clear_node=reg.clear_node,
                tool_node=reg.tool_node,
                report_key=reg.report_key,
            )

        # 2. ConditionalLogic — inject if missing
        method_name = f"should_continue_{reg.key}"
        if not hasattr(ConditionalLogic, method_name):
            _tn = reg.tool_node
            _cn = reg.clear_node

            def _condition(self, state, _tool_node=_tn, _clear_node=_cn):
                msgs = state["messages"]
                last = msgs[-1]
                return (
                    _tool_node
                    if (hasattr(last, "tool_calls") and last.tool_calls)
                    else _clear_node
                )

            _condition.__name__ = method_name
            _condition.__doc__ = (
                f"Auto-generated router for the {reg.agent_node} node.\n"
                f"Routes to {_tn!r} when tool calls are pending, "
                f"otherwise to {_cn!r}."
            )
            setattr(ConditionalLogic, method_name, _condition)
            _logger.debug("Injected %s into ConditionalLogic", method_name)


# ── Public helpers ─────────────────────────────────────────────────────────────


def get_factory(key: str) -> Callable:
    """Return the factory callable for *key*.

    Raises ``KeyError`` with a helpful message if the key is not registered.
    """
    reg = _REGISTRY.get(key)
    if reg is None:
        available = sorted(_REGISTRY)
        raise KeyError(
            f"Analyst {key!r} is not registered. "
            f"Available keys: {available}. "
            "Did you forget to import the analyst module?"
        )
    return reg.factory


def get_tools(key: str) -> list:
    """Return the tool list for *key* (used to build ``ToolNode`` instances)."""
    reg = _REGISTRY.get(key)
    if reg is None:
        raise KeyError(f"Analyst {key!r} is not registered.")
    return list(reg.tools)


def list_analysts() -> list[str]:
    """Return a sorted list of all registered analyst keys."""
    return sorted(_REGISTRY)


def is_registered(key: str) -> bool:
    """Return ``True`` if *key* is in the registry."""
    return key in _REGISTRY
