"""Append-only snapshot store for news / sentiment fetches (T0.3).

Every call into a news vendor (yfinance, alpha_vantage, etc.) persists both
the raw upstream response and the formatted string that was returned to
the LLM. On subsequent calls for the same (source, scope, date) tuple,
the cached ``formatted_output`` is replayed verbatim so that a re-run of
``propagate(ticker, date)`` sees byte-identical news context.

Why both raw + formatted: raw lets a future audit re-format or re-filter
the same articles under different rules; formatted is what the LLM
actually saw and must match on replay.

Why date-scoped rather than fetch-time-scoped: the trade_date is what's
deterministic about a run. Two fetches on the same trade_date for the
same ticker should be interchangeable from the model's POV, even if
upstream news moves around between them. The most recent snapshot wins,
older ones stay on disk as evidence of when the data changed.

This is the Phase 0 ancestor of the full provenance ledger (T1.3 / T1.5):
the on-disk format is forward-compatible with the hash-chained record so
later phases can migrate without re-fetching history.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import get_config

logger = logging.getLogger(__name__)

# Reserved scope label for vendor calls that are not tied to a single ticker
# (e.g. global macro news, ``get_global_news_*``). Underscore prefix keeps
# it from colliding with real tickers since exchanges don't issue symbols
# beginning with ``_``.
GLOBAL_SCOPE = "_global"

# Filenames are ``{kind}_{source}_{utc_iso}.json``; the timestamp is the
# fetched_at field encoded for filesystem sorting. Microsecond precision
# so two writes in the same second produce distinct files (e.g. when a
# force_refresh follows the original snapshot inside the same test or
# the same propagate() call).
_FN_PATTERN = re.compile(
    r"^(?P<kind>[a-z0-9]+)_(?P<source>[a-z0-9_]+)_(?P<ts>\d{8}T\d{12}Z)\.json$"
)


def _safe_component(value: str) -> str:
    """Strip path separators / wildcards from a component used in a snapshot path.

    Matches the convention used elsewhere in the repo
    (``dataflows.utils.safe_ticker_component``) but kept inline here so the
    snapshot module doesn't depend on the ticker-specific helper.

    The regex converts every character outside ``[A-Za-z0-9._-]`` to ``_``,
    which neutralises path separators on every platform. The only escape
    primitive that survives is a component composed purely of dots (``.``,
    ``..``, etc.) — those resolve to parent or current directory at
    ``Path`` join time and would let snapshots escape the configured root.
    We swap such components for a placeholder.

    Leading underscores are preserved on purpose so the reserved
    :data:`GLOBAL_SCOPE` value (``"_global"``) round-trips intact.
    """
    if value is None:
        return "_unknown"
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", str(value))
    if not cleaned or set(cleaned) <= {"."}:
        return "_unknown"
    return cleaned[:64]


def _snapshot_root() -> Path:
    """Resolve the snapshot root directory from active config, expanding ``~``."""
    cfg = get_config()
    root = cfg.get("news_snapshot_dir") or "~/.tradingagents/snapshots"
    return Path(root).expanduser()


def _snapshot_dir(scope: str, date: str) -> Path:
    """Return the directory containing snapshots for one (scope, date) tuple."""
    return _snapshot_root() / _safe_component(scope) / _safe_component(date)


def is_enabled() -> bool:
    """Whether news snapshotting is on for the current process."""
    return bool(get_config().get("news_snapshot_enabled", True))


def force_refresh() -> bool:
    """Whether the caller has explicitly asked to bypass cached snapshots."""
    return bool(get_config().get("news_force_refresh", False))


def _utc_now_iso_compact() -> str:
    """UTC ``YYYYMMDDTHHMMSSffffffZ`` — sortable, filesystem-safe, microsecond precision."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_snapshot(
    *,
    kind: str,
    source: str,
    scope: str,
    date: str,
    params: Dict[str, Any],
    raw_response: Any,
    formatted_output: str,
) -> Optional[Path]:
    """Persist one fetch to ``snapshot_dir/{kind}_{source}_{ts}.json``.

    Returns the file path written, or None if snapshotting is disabled or
    the write fails. We never raise here — a snapshot failure must not
    break the user's run; it only weakens future replay, which is logged.

    Filename format note: ``kind`` is required to be alphanumeric only.
    Underscores in ``kind`` would collide with the ``_`` separator used
    between ``kind`` / ``source`` / ``ts``, making the load-side regex
    ambiguous (e.g. ``balance_sheet_yfinance_<ts>.json`` would parse as
    ``kind=balance, source=sheet_yfinance``). Renaming to camel-style
    (``balancesheet``) avoids the ambiguity without changing the file
    format. Underscores in ``source`` are fine because the regex anchors
    the timestamp at the end.
    """
    if not is_enabled():
        return None
    if "_" in kind:
        raise ValueError(
            f"snapshot kind must not contain underscore (got {kind!r}); "
            f"the filename separator would become ambiguous. Use "
            f"camelCase (e.g. 'balanceSheet') or omit the underscore."
        )

    fetched_at = _utc_now_iso_compact()
    payload = {
        "fetched_at": fetched_at,
        "kind": kind,
        "source": source,
        "scope": scope,
        "date": date,
        "params": params,
        "raw_response": raw_response,
        "formatted_output": formatted_output,
    }

    target_dir = _snapshot_dir(scope, date)
    fname = f"{_safe_component(kind)}_{_safe_component(source)}_{fetched_at}.json"
    target_path = target_dir / fname

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        # ``default=str`` covers datetimes and other JSON-foreign types that
        # vendor responses occasionally contain (yfinance pubDate datetimes).
        target_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info(
            "snapshot written: kind=%s source=%s scope=%s date=%s path=%s",
            kind, source, scope, date, target_path,
        )
        return target_path
    except Exception as e:
        logger.warning(
            "snapshot write failed: kind=%s source=%s scope=%s date=%s err=%s",
            kind, source, scope, date, e,
        )
        return None


def load_latest_snapshot(
    *,
    kind: str,
    source: str,
    scope: str,
    date: str,
) -> Optional[Dict[str, Any]]:
    """Return the most recent matching snapshot's parsed payload, or None.

    "Most recent" = greatest ``fetched_at`` in filename. Files that don't
    match the naming pattern are skipped (they may belong to a future
    schema version). Read errors return None and emit a warning rather
    than raising — same philosophy as ``write_snapshot``.
    """
    if not is_enabled() or force_refresh():
        return None

    target_dir = _snapshot_dir(scope, date)
    if not target_dir.is_dir():
        return None

    candidates = []
    for child in target_dir.iterdir():
        m = _FN_PATTERN.match(child.name)
        if not m:
            continue
        if m.group("kind") != _safe_component(kind):
            continue
        if m.group("source") != _safe_component(source):
            continue
        candidates.append((m.group("ts"), child))

    if not candidates:
        return None

    candidates.sort()
    _, latest = candidates[-1]

    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("snapshot read failed: path=%s err=%s", latest, e)
        return None


def replay_formatted(
    *,
    kind: str,
    source: str,
    scope: str,
    date: str,
) -> Tuple[Optional[str], bool]:
    """Return ``(formatted_output, hit)``.

    ``hit=True`` means the caller may skip the live fetch entirely; the
    string returned is what the LLM saw on the original run. ``hit=False``
    means no cached entry — caller must fetch live and call
    :func:`write_snapshot` with the result.
    """
    snap = load_latest_snapshot(kind=kind, source=source, scope=scope, date=date)
    if snap is None:
        return None, False
    formatted = snap.get("formatted_output")
    if not isinstance(formatted, str):
        # Snapshot exists but is malformed — treat as miss so the caller
        # fetches fresh data rather than serving garbage to the LLM.
        logger.warning(
            "snapshot missing formatted_output: source=%s scope=%s date=%s",
            source, scope, date,
        )
        return None, False
    logger.info(
        "snapshot cache hit: kind=%s source=%s scope=%s date=%s",
        kind, source, scope, date,
    )
    return formatted, True


def replay_raw(
    *,
    kind: str,
    source: str,
    scope: str,
    date: str,
) -> Tuple[Any, bool]:
    """Return ``(raw_response, hit)``.

    Companion to :func:`replay_formatted` for sources whose return type
    is a structured object (dict / list) rather than a pre-formatted
    string. The cached value is whatever was originally stored as the
    snapshot's ``raw_response`` — JSON round-tripped, so dicts come
    back as dicts and lists as lists.
    """
    snap = load_latest_snapshot(kind=kind, source=source, scope=scope, date=date)
    if snap is None:
        return None, False
    if "raw_response" not in snap:
        return None, False
    logger.info(
        "snapshot cache hit (raw): kind=%s source=%s scope=%s date=%s",
        kind, source, scope, date,
    )
    return snap["raw_response"], True


def snapshot(
    *,
    kind: str,
    source: str,
    scope_arg: Optional[str] = None,
    scope_literal: Optional[str] = None,
    date_arg: str,
    serialize: str = "str",
):
    """Decorator: cache a data-fetch function's I/O under the snapshot store.

    Behavior (T1.5 generalisation of the T0.3 pattern):

    1. **Cache check** before invocation. Cache key is
       ``(kind, source, scope_value, date_value)`` where the values come
       from the wrapped function's bound arguments. On hit, the wrapped
       function is NOT called — we return the cached value directly.
    2. **Cache miss**: call the wrapped function. If it raises or returns
       a known "error sentinel" string (currently ``"Error..."``-prefixed
       strings from this codebase's convention), we do NOT cache —
       re-running an error case should re-attempt the fetch.
    3. **Persistence**: write a snapshot containing the bound argument
       dict, the raw return, and (for ``serialize="str"``) the same
       value as ``formatted_output``.

    ``serialize`` controls how the return value flows through:

    - ``"str"`` (default): function returns a string. Stored as
      ``formatted_output`` and replayed via :func:`replay_formatted`.
      Matches every yfinance helper in this codebase (they all
      ``df.to_csv()`` before return).
    - ``"json"``: function returns a JSON-serializable object (dict /
      list / etc.). Stored as ``raw_response`` and replayed via
      :func:`replay_raw`. Used by alpha_vantage helpers which return
      the API's raw JSON dict.

    Either ``scope_arg`` (name of a function parameter holding the
    scope, typically a ticker) or ``scope_literal`` (constant string,
    e.g. :data:`GLOBAL_SCOPE` for market-wide fetches that aren't
    ticker-specific) must be supplied. ``date_arg`` names the parameter
    holding the temporal anchor; both are resolved via
    ``inspect.signature.bind`` so the decorator works regardless of
    positional vs keyword invocation. If ``date_arg`` resolves to None,
    we use the sentinel ``"_latest"``; this is acceptable for endpoints
    that return real-time data and the resulting cache won't
    invalidate, which is fine for the per-run audit-replay use case.
    """
    import functools
    import inspect

    if scope_arg is None and scope_literal is None:
        raise ValueError("snapshot decorator requires scope_arg or scope_literal")

    def decorator(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Resolve arguments deterministically — works for both
            # positional and keyword calls.
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
            except TypeError:
                # Bad signature match — bail out and let the wrapped
                # function produce its native error.
                return fn(*args, **kwargs)

            if scope_literal is not None:
                scope = scope_literal
            else:
                scope_value = bound.arguments.get(scope_arg)
                scope = str(scope_value) if scope_value is not None else "_unknown"

            date_value = bound.arguments.get(date_arg) or "_latest"
            date = str(date_value)

            # Make params JSON-safe — drop non-serializable arguments
            # rather than blowing up the snapshot.
            params = {}
            for k, v in bound.arguments.items():
                try:
                    json.dumps(v, default=str)
                    params[k] = v
                except (TypeError, ValueError):
                    params[k] = repr(v)

            # Cache check
            if serialize == "str":
                cached, hit = replay_formatted(
                    kind=kind, source=source, scope=scope, date=date,
                )
                if hit:
                    return cached
            else:  # "json"
                cached, hit = replay_raw(
                    kind=kind, source=source, scope=scope, date=date,
                )
                if hit:
                    return cached

            # Cache miss — call wrapped function
            result = fn(*args, **kwargs)

            # Don't cache error-sentinel strings. Convention in this
            # codebase: error returns start with "Error" or "No data
            # found"; both are short-lived states a replay must re-attempt.
            if isinstance(result, str) and (
                result.startswith("Error")
                or "No data found" in result
                or "No fundamentals data found" in result
                or "No balance sheet data found" in result
                or "No cashflow data found" in result
                or "No income statement data found" in result
                or "No news found" in result
            ):
                return result

            # Persist
            if serialize == "str":
                if not isinstance(result, str):
                    logger.warning(
                        "snapshot decorator: %s.%s returned %s, expected str",
                        source, fn.__name__, type(result).__name__,
                    )
                    return result
                write_snapshot(
                    kind=kind, source=source, scope=scope, date=date,
                    params=params,
                    raw_response=None,
                    formatted_output=result,
                )
            else:  # "json"
                try:
                    formatted = json.dumps(result, ensure_ascii=False, default=str)
                except Exception as e:
                    logger.warning(
                        "snapshot decorator: %s.%s result not JSON-serializable: %s",
                        source, fn.__name__, e,
                    )
                    return result
                write_snapshot(
                    kind=kind, source=source, scope=scope, date=date,
                    params=params,
                    raw_response=result,
                    formatted_output=formatted,
                )

            return result

        # Expose the original function for tests that need to bypass
        # the decorator (e.g. when patching upstream API calls and
        # expecting a fresh fetch each time).
        wrapper.__wrapped__ = fn
        return wrapper

    return decorator
