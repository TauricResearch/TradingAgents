"""Tool-layer guard that prevents silent cross-ticker data mixing.

Analysis agents sometimes query a ticker other than the run's target - for
example, to contrast a peer or an index. That is legitimate, but the result
must not be confused with the target ticker's data in downstream reports.
This guard compares each tool call's ticker argument against the run's
target (stored in :mod:`target_context`) and, on mismatch, prepends a
visible ``COMPARISON_TICKER_NOTICE`` to the result and emits a lightweight
audit event.

The guard never blocks the call: comparison analysis stays possible, but
every cross-ticker query is visible to the LLM (as a notice that re-anchors
the target ticker) and to the workbench (as an audit event that inherits
run_id/turn_id from the active observation context).
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from tradingagents.dataflows.target_context import get_target_ticker
from tradingagents.dataflows.ticker_utils import normalize_ticker_symbol
from tradingagents.observability.context import current_observation_context
from tradingagents.observability.events import RunEventDraft
from tradingagents.observability.provenance import current_provenance_observer

logger = logging.getLogger(__name__)

_NOTICE_TEMPLATE = (
    "⚠️ COMPARISON_TICKER_NOTICE:\n"
    "You requested data for '{requested}', but the primary analysis target is "
    "'{target}'. This is only appropriate for explicit comparison/contrast. "
    "If unintentional, re-check the ticker. Do not mix '{requested}' data into "
    "'{target}' analysis without clearly labeling it as comparison data.\n"
    "---\n"
)


def guard_target_ticker(param_name: str = "ticker"):
    """Decorate a ``@tool`` function to guard against silent cross-ticker mixing.

    ``param_name`` is the tool parameter holding the requested ticker (tools
    use either ``ticker`` or ``symbol``). Apply below ``@tool`` so LangChain
    sees the original annotated signature::

        @tool
        @guard_target_ticker("symbol")
        def get_stock_data(symbol, ...): ...

    The guard is a no-op when no target ticker is set (bare programmatic
    states, tests), preserving backward compatibility.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = get_target_ticker()
            if target is None:
                return func(*args, **kwargs)
            requested = _resolve_requested_ticker(param_name, args, kwargs, func)
            if requested is None or _tickers_match(requested, target.ticker):
                return func(*args, **kwargs)
            result = func(*args, **kwargs)
            _emit_cross_ticker_audit(
                requested=requested,
                target=target.ticker,
                tool_name=getattr(func, "__name__", "tool"),
            )
            return _inject_notice(result, requested, target.ticker)

        return wrapper

    return decorator


def _resolve_requested_ticker(
    param_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    func: Callable[..., Any],
) -> str | None:
    """Extract the ticker argument by name, handling positional and keyword forms."""
    if param_name in kwargs:
        value = kwargs[param_name]
    else:
        try:
            params = list(inspect.signature(func).parameters.keys())
        except (ValueError, TypeError):
            return None
        if param_name in params:
            idx = params.index(param_name)
            if idx < len(args):
                value = args[idx]
            else:
                return None
        else:
            return None
    if value is None:
        return None
    return str(value)


def _tickers_match(requested: str, target: str) -> bool:
    """Return True when requested and target refer to the same instrument.

    Normalizes both sides (A-share suffix folding, case) so ``600519.SH``,
    ``600519.SS`` and bare ``600519`` all match. Falls back to a conservative
    case-insensitive comparison if normalization raises, so a matching ticker
    is never falsely flagged as a cross-ticker query.
    """
    try:
        if normalize_ticker_symbol(requested) == normalize_ticker_symbol(target):
            return True
    except Exception:
        pass
    return requested.strip().upper() == target.strip().upper()


def _inject_notice(result: Any, requested: str, target: str) -> Any:
    """Prepend the notice to the tool result so the LLM sees it next turn."""
    notice = _NOTICE_TEMPLATE.format(requested=requested, target=target)
    if isinstance(result, str):
        return notice + result
    try:
        return notice + str(result)
    except Exception:
        return notice


def _emit_cross_ticker_audit(*, requested: str, target: str, tool_name: str) -> None:
    """Emit a formal audit event for cross-ticker tool calls.

    When running under the web workbench (observation context active), emits a
    persisted ``tool.cross_ticker_query`` event via the observer so the query
    is traceable to its turn and tool call. In CLI runs (no observer), falls
    back to a logger.warning so the query is still visible in logs. The
    notice injected into the tool result is independent of this event and
    always reaches the LLM.
    """
    message = (
        f"cross-ticker query: requested='{requested}' target='{target}' tool={tool_name}"
    )
    logger.warning(message)
    observer = current_provenance_observer()
    context = current_observation_context()
    if (
        observer is not None
        and context is not None
        and context.tool_call_id
    ):
        observer.emit(
            RunEventDraft(
                observer.run_id,
                "tool.cross_ticker_query",
                {
                    "turn_id": context.turn_id,
                    "graph_task_id": context.graph_task_id,
                    "tool_call_id": context.tool_call_id,
                    "tool_name": tool_name,
                    "requested_ticker": requested,
                    "target_ticker": target,
                },
            )
        )
