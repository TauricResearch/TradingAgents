"""Prompt context shared by the agents: instrument identity, output language and portfolio."""

import functools
import logging
from collections.abc import Mapping
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


_INSTRUMENT_LABELS = {"crypto": "asset", "commodity": "commodity"}


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

    ``asset_type="commodity"`` (trading-workspace#68) covers a global futures
    benchmark (e.g. ``CL=F``/``GC=F``, resolved from an MCX mini-contract
    name via symbol_utils.py) -- there is no "company" to anchor to, same
    structural gap as crypto, so it gets the same no-fundamentals framing
    below plus its own commodity-specific driver language.

    That profile carries no historical vintage: it describes the company today.
    A run dated earlier gets the current name alone, as a way to tell the
    company apart from others rather than as what it was called then; a sector,
    industry or exchange it holds today is not given, since it may not have held
    on the analysis date.
    """
    is_crypto = asset_type == "crypto"
    is_commodity = asset_type == "commodity"
    instrument_label = _INSTRUMENT_LABELS.get(asset_type, "instrument")
    context = (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "The tools serve this instrument; refer to it by this exact ticker in every report and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
    )

    identity = identity or {}
    name = identity.get("company_name") or identity.get("name")
    label = "Name" if is_crypto or is_commodity else "Company"
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
    elif is_commodity:
        context += (
            " Treat it as a commodity futures contract rather than a company, "
            "and do not assume company fundamentals (earnings, balance sheet, "
            "insider activity) are available -- reason from supply/demand "
            "balance, inventories, OPEC+/central-bank policy, and geopolitical "
            "developments instead."
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


def get_external_signal_context_from_state(state: Mapping[str, Any]) -> str:
    """Return the external-scanner signal context for the current run, or ""
    when none was injected (trading-workspace#37 — most callers never set
    this; only news-gap-ml's technical-trigger leg does). No fallback
    construction here, unlike get_instrument_context_from_state — there's no
    deterministic way to derive this lazily if it wasn't provided at run
    start, so an absent value just means "no prior signal to consider"."""
    context = state.get("external_signal_context")
    return context if isinstance(context, str) and context.strip() else ""


def get_external_signal_direction_from_state(state: Mapping[str, Any]) -> str:
    """"up" / "down" when the external signal carried an explicit direction
    (trading-workspace TradingAgents#30), else "". Set at run start from
    decide.py's --context (a technical scanner's side, or news-gap-ml's
    sector_direction); never derived inside the graph."""
    direction = state.get("external_signal_direction")
    return direction if direction in ("up", "down") else ""


def external_signal_prompt_block(state: Mapping[str, Any], require_justification: bool = False) -> str:
    """Prompt passage every reasoning agent appends when an external signal was
    injected (TradingAgents#30), or "" when there is none.

    Background: news-gap-ml's sector leg passed "GST rate cuts boost FMCG /
    sector_direction=up" as context and 93 such decisions came back 43 Hold /
    11 Underweight / 0 bullish -- the debate simply never engaged with the
    upstream direction. The block states the signal and its direction in one
    place; with ``require_justification`` (Trader, Portfolio Manager) it also
    obliges the agent to say explicitly what evidence overrides the signal
    whenever its call goes the other way or abstains. The signal stays a prior
    the agent can reject -- but no longer one it can silently ignore."""
    context = get_external_signal_context_from_state(state)
    if not context:
        return ""
    direction = get_external_signal_direction_from_state(state)
    lines = ["**External signal (prior from the upstream scanner, not authoritative):** " + context]
    if direction:
        stance = "BULLISH (up)" if direction == "up" else "BEARISH (down)"
        lines.append(f"Upstream direction for this instrument: {stance}.")
        if require_justification:
            lines.append(
                "Treat this direction as your prior. You may reject it, but if your call "
                "points the other way, or is Hold, you must state explicitly which specific "
                "evidence from the reports overrides it -- 'no company-specific catalyst "
                "found' is not sufficient when the upstream signal itself is a dated, "
                "sector-wide catalyst for this session."
            )
    return "\n".join(lines)


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
        "Portfolio context: not provided. You do not know the caller's current "
        "holdings or cash, so do not assume a flat book; give direction and "
        "sizing guidance in terms the caller can apply to their own position."
    )
