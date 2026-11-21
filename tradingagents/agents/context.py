"""Prompt context shared by the agents: instrument identity, output language and portfolio."""

import functools
import json
import logging
import re
from collections.abc import Mapping
from math import ceil
from typing import Any

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.vendors.yahoo.fundamentals import get_company_profile

logger = logging.getLogger(__name__)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    # The labelled lines are read by the program, so they keep their English
    # label and value: a translated rating line leaves the reader prose to
    # search, where a negated rating ("not a Sell") reads as the call (#1435).
    return (
        f" Write your entire response in {lang}, except the labelled lines the format"
        f" asks for (the \"**Rating**:\" line, \"FINAL TRANSACTION PROPOSAL:\"):"
        f" keep their label and value in English, exactly as specified."
    )


def opponent_argument_or_opening(text: str, opponent: str) -> str:
    """Opponent's latest argument, or an explicit opening marker when empty.

    The first speaker in each debate round receives an empty opponent response;
    interpolating it into a "refute the opponent" prompt makes the model
    fabricate the other side's position. Returning a clear "has not spoken yet"
    marker instead lets it open with its own case (#1176).
    """
    text = (text or "").strip()
    if text:
        return text
    return f"(The {opponent} has not spoken yet — open the debate with your own case.)"


def _clean_identity_value(value: Any) -> str | None:
    """Return a trimmed string, or None for empty / placeholder-ish values."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "nan", "null"}:
        return None
    return cleaned


def resolve_instrument_identity(ticker: str) -> dict:
    """Resolve deterministic identity metadata (company name, sector, …) for a ticker.

    This exists to stop the pipeline from hallucinating a *different* company
    when a chart pattern suggests a different industry than the real one
    (#814): without a ground-truth name, the market analyst would pattern-match
    the price action to a narrative and invent an identity that then cascaded
    through every downstream agent.

    Best-effort by design: if yfinance is unavailable, rate-limited, or doesn't
    recognise the ticker, we return ``{}`` and the caller falls back to
    ticker-only context rather than failing before analysis starts. An answer
    is cached for the process; a failed lookup is asked again next time.

    Identity resolves for the same instrument the price path fetches
    (``XAUUSD`` -> ``GC=F``, #983).
    """
    try:
        return _identity(ticker)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the run
        logger.debug("Could not resolve instrument identity for %s: %s", ticker, exc)
        return {}


@functools.lru_cache(maxsize=256)
def _identity(ticker: str) -> dict:
    """The vendor's identity fields for ``ticker``; raises if the lookup fails."""
    info = get_company_profile(ticker)
    identity: dict[str, str] = {}
    company_name = _clean_identity_value(info.get("longName")) or _clean_identity_value(
        info.get("shortName")
    )
    if company_name:
        identity["company_name"] = company_name
    for source_key, target_key in (
        ("sector", "sector"),
        ("industry", "industry"),
        ("exchange", "exchange"),
        ("quoteType", "quote_type"),
    ):
        value = _clean_identity_value(info.get(source_key))
        if value:
            identity[target_key] = value
    return identity


def build_instrument_context(
    ticker: str,
    asset_type: str = "stock",
    identity: Mapping[str, str] | None = None,
    trade_date: str | None = None,
) -> str:
    """Describe the exact instrument so agents preserve identity and ticker.

    When ``identity`` is provided (resolved deterministically via
    :func:`resolve_instrument_identity`), the company name and business
    classification are injected so agents anchor to the real company rather
    than pattern-matching the price chart to a wrong one (#814).

    That profile carries no historical vintage: it describes the company today.
    A run dated earlier gets the current name alone, as a way to tell the
    company apart from others rather than as what it was called then; a sector,
    industry or exchange it holds today is not given, since it may not have held
    on the analysis date.
    """
    is_crypto = asset_type == "crypto"
    instrument_label = "asset" if is_crypto else "instrument"
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "The tools serve this instrument; refer to it by this exact ticker in every report and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    identity = identity or {}
    name = identity.get("company_name") or identity.get("name")
    label = "Name" if is_crypto else "Company"
    details = []
    if is_historical(trade_date):
        if name:
            details.append(
                f"{label}: {name} (its current name, given only to identify it; "
                f"on {trade_date} it may have been named differently)"
            )
    else:
        if name:
            details.append(f"{label}: {name}")
        sector, industry = identity.get("sector"), identity.get("industry")
        if sector and industry:
            details.append(f"Business classification: {sector} / {industry}")
        elif sector:
            details.append(f"Sector: {sector}")
        elif industry:
            details.append(f"Industry: {industry}")
        if identity.get("exchange"):
            details.append(f"Exchange: {identity['exchange']}")

    if details:
        context += (
            f" Resolved identity: {'; '.join(details)}. "
            "Do not substitute a different company or ticker unless a tool "
            "result explicitly disproves this resolved identity."
        )

    if is_crypto:
        context += (
            " Treat it as a crypto asset rather than a company, and do not "
            "assume company fundamentals are available."
        )
    return context


def get_instrument_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the instrument context for the current run.

    Prefers the identity-resolved context computed once at run start and
    stored on the state (see ``TradingAgentsGraph.resolve_instrument_context``).
    Falls back to a ticker-only context — with no network lookup — when the
    state was constructed without it (bare programmatic states, tests), so a
    consumer is never forced to make a yfinance call mid-graph.
    """
    context = state.get("instrument_context")
    if isinstance(context, str) and context.strip():
        return context
    return build_instrument_context(
        str(state["company_of_interest"]),
        state.get("asset_type", "stock"),
    )


def report_or_absent(text: str, source: str) -> str:
    """An analyst's report, or a marker saying it was never produced.

    A report is empty when its analyst was not selected, refused, or returned
    nothing. Interpolating that into a labelled section presents an absence as a
    blank finding, and the reading agent fills it in from nothing, the same way
    an empty opponent argument used to invite an invented rebuttal (#1176).
    """
    text = (text or "").strip()
    if text:
        return text
    return f"(No {source} report in this run: it is not available, not an empty finding.)"


def get_portfolio_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the caller's portfolio block, or a notice that none was given.

    A run without portfolio context must not read as a flat book: the agents
    would otherwise size as if the caller held nothing, which is a claim about
    an account we were never told about.
    """
    context = state.get("portfolio_context")
    if isinstance(context, str) and context.strip():
        return context
    return (
        "Holdings and cash were not provided; no account ownership is assumed.\n"
        "Portfolio context: not provided. You do not know the caller's current "
        "holdings or cash. Do not imply that the caller owns, must trim, retain or exit a position. "
        "Do not assume a flat book; give only explicitly conditional direction and "
        "sizing guidance in terms the caller can apply to their own position."
    )

# Application-level context guard. Estimates are deliberately provider-neutral;
# they bound assembled characters/4 and are not billing or aggregate run budgets.
class ContextBudgetError(RuntimeError):
    """Protected context cannot fit within the application estimate cap."""


def estimate_context_tokens(text: str) -> int:
    return ceil(len(text) / 4)


def _message_role(message) -> str:
    if isinstance(message, Mapping):
        return str(message.get("role", "user")).casefold()
    return str(getattr(message, "type", "user")).casefold()


def _message_content(message):
    if isinstance(message, Mapping):
        return message.get("content")
    return getattr(message, "content", None)


def _with_message_content(message, content):
    if isinstance(message, Mapping):
        return {**message, "content": content}
    if hasattr(message, "model_copy"):
        return message.model_copy(update={"content": content})
    return message.copy(update={"content": content}) if hasattr(message, "copy") else message


def _trim_narrative(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    marker = "\n[… older context compacted …]\n"
    if budget <= len(marker):
        return text[-budget:] if budget > 0 else ""
    return marker + text[-(budget - len(marker)):]


def protect_context(text: str) -> str:
    """Mark trusted instructions that compaction must preserve verbatim."""
    return "<protected_context>\n" + text + "\n</protected_context>"


def _protected_ranges(text: str):
    spans = [(m.start(), m.end()) for m in re.finditer(
        r"<protected_context>.*?</protected_context>", text, re.DOTALL)]
    edge = min(512, len(text) // 3)
    spans += [(0, edge), (len(text) - edge, len(text))]
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _compact_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    ranges = _protected_ranges(text)
    protected = sum(end - start for start, end in ranges)
    if protected > limit:
        raise ContextBudgetError("Protected task context exceeds the configured context cap.")
    remaining = limit - protected
    narrative = len(text) - protected
    parts, cursor = [], 0
    for start, end in ranges + [(len(text), len(text))]:
        fragment = text[cursor:start]
        share = remaining * len(fragment) // narrative if narrative else 0
        parts.extend((_trim_narrative(fragment, share), text[start:end]))
        cursor = end
    return "".join(parts)


def bound_agent_prompt(prompt, context_cap_tokens: int | None = None,
                       compaction_threshold_tokens: int | None = None):
    """Bound fully assembled input using the current run config, preserving trusted blocks.

    This is a character based estimate, not a provider tokenizer or total run budget.
    Explicit arguments remain supported for callers and tests.
    """
    from tradingagents.dataflows.config import get_config
    config = get_config()
    cap_tokens = int(config.get("context_cap_tokens", 24000) if context_cap_tokens is None else context_cap_tokens)
    threshold = int(config.get("compaction_threshold_tokens", 19200) if compaction_threshold_tokens is None else compaction_threshold_tokens)
    if cap_tokens <= 0 or threshold <= 0:
        raise ContextBudgetError("Context budget values must be positive.")
    cap = cap_tokens * 4
    target = min(threshold * 4, cap)
    if isinstance(prompt, str):
        protected = sum(b-a for a,b in _protected_ranges(prompt))
        return _compact_text(prompt, min(cap, max(target, protected)))
    if not isinstance(prompt, (list, tuple)):
        return prompt
    messages = list(prompt)
    originals = [_message_content(m) for m in messages]
    # Preserve provider content blocks unchanged, charging their serialized size.
    # Dropping or flattening an image/tool block would change message semantics.
    contents = [c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                for c in originals]
    if sum(map(len, contents)) <= target:
        return prompt
    minima = [len(c) if _message_role(m) in {"system", "developer"} or not isinstance(original, str)
              else sum(b-a for a,b in _protected_ranges(c))
              for m,c,original in zip(messages, contents, originals, strict=True)]
    protected = sum(minima)
    if protected > cap:
        raise ContextBudgetError("Protected task context exceeds the configured context cap.")
    budget = max(target, protected) - protected
    narrative = sum(len(c)-minimum for c,minimum in zip(contents,minima, strict=True))
    for i,(message,content,minimum) in enumerate(zip(messages,contents,minima, strict=True)):
        share = budget * (len(content)-minimum) // narrative if narrative else 0
        if isinstance(originals[i], str):
            messages[i] = _with_message_content(message, _compact_text(content, minimum + share))
    return tuple(messages) if isinstance(prompt, tuple) else messages
