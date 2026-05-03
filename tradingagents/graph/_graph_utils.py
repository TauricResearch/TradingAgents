"""Shared graph utilities used by TradingAgentsGraph, ScannerGraph, and PortfolioGraph."""

import re
from typing import Any

_REGIME_LABEL_RE = re.compile(r"^(RISK-ON|RISK-OFF|TRANSITION)$", re.IGNORECASE)
_REGIME_LINE_RE = re.compile(r"(?im)^\s*[*-]?\s*\**\s*Macro Regime(?:\s+Alignment)?\**\s*:[^\n]*")
_REGIME_PAIR_RE = re.compile(
    r"\b(RISK-ON|RISK-OFF|TRANSITION)\b"
    r"(?:(?!\b(?:RISK-ON|RISK-OFF|TRANSITION)\b).){0,120}?"
    r"(?:\(\s*(?:Score\s*:?\s*)?([+-]?\d+)\s*/\s*6\s*\)|\bscore\s*:?\s*(?:of\s+)?([+-]?\d+)\s*/\s*6\b)",
    re.IGNORECASE,
)


def get_provider_kwargs(config: dict[str, Any], tier: str) -> dict[str, Any]:
    """Resolve provider-specific LLM kwargs for the given tier.

    Args:
        config: The application configuration dictionary.
        tier: One of "deep_think", "mid_think", "quick_think".

    Returns:
        Dict of extra kwargs to pass to the LLM client constructor.
    """
    kwargs: dict[str, Any] = {}
    prefix = f"{tier}_"
    provider = (config.get(f"{prefix}llm_provider") or config.get("llm_provider", "")).lower()
    timeout = config.get(f"{prefix}llm_timeout")
    if timeout is None:
        timeout = config.get("llm_timeout")
    if timeout is not None:
        kwargs["timeout"] = float(timeout)

    if provider == "google":
        thinking_level = config.get(f"{prefix}google_thinking_level") or config.get(
            "google_thinking_level"
        )
        if thinking_level:
            kwargs["thinking_level"] = thinking_level

    elif provider in ("openai", "xai", "openrouter", "ollama"):
        reasoning_effort = config.get(f"{prefix}openai_reasoning_effort") or config.get(
            "openai_reasoning_effort"
        )
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

    elif provider == "anthropic":
        effort = config.get("anthropic_effort")
        if effort:
            kwargs["effort"] = effort

    return kwargs


def visualize_graph(
    graph: Any, output_path: str | None = None, format: str = "mermaid"
) -> str | bytes | None:
    """Visualize a compiled LangGraph in various formats.

    Args:
        graph: A compiled LangGraph instance (has .get_graph()).
        output_path: If provided, saves the visualization to this file.
        format: "mermaid", "ascii", or "png".

    Returns:
        The visualization as a string (mermaid/ascii) or bytes (png).
    """
    g = graph.get_graph()
    if format == "ascii":
        try:
            res = g.print_ascii()
        except Exception as e:
            res = f"Could not print ASCII: {e}"
            print(res)
        if output_path:
            with open(output_path, "w") as f:
                f.write(res if isinstance(res, str) else "ASCII representation printed to console.")
        return res
    elif format == "png":
        png_data = g.draw_mermaid_png()
        if output_path:
            with open(output_path, "wb") as f:
                f.write(png_data)
        return png_data
    else:
        mermaid_code = g.draw_mermaid()
        if output_path:
            with open(output_path, "w") as f:
                f.write(mermaid_code)
        return mermaid_code


def assert_regime_consistent(analyst_output: str, canonical: dict[str, Any]) -> None:
    """Compare regime label/score in analyst output against the canonical brief.

    Raises ValueError if the analyst output disagrees with the canonical regime.
    Returns None on match.
    """
    text = analyst_output or ""
    if not isinstance(canonical, dict):
        raise ValueError(f"malformed canonical regime: {canonical!r}")
    canonical_label = str(canonical.get("label", "")).upper()
    if not _REGIME_LABEL_RE.fullmatch(canonical_label):
        raise ValueError(f"malformed canonical regime label: {canonical.get('label')!r}")
    canonical_score = canonical.get("score")
    if (
        not isinstance(canonical_score, int)
        or isinstance(canonical_score, bool)
        or not -6 <= canonical_score <= 6
    ):
        raise ValueError(f"malformed canonical regime score: {canonical_score!r}")

    line_match = _REGIME_LINE_RE.search(text)
    statement = line_match.group(0) if line_match else ""
    pair_match = _REGIME_PAIR_RE.search(statement)
    if not pair_match:
        raise ValueError(
            f"could not parse regime from analyst output (first 200 chars): {text[:200]!r}"
        )
    analyst_label = pair_match.group(1).upper()
    analyst_score = int(pair_match.group(2) or pair_match.group(3))
    if analyst_label != canonical_label:
        raise ValueError(
            f"regime drift: canonical label {canonical_label!r} != analyst label {analyst_label!r}"
        )
    if analyst_score != canonical_score:
        raise ValueError(
            f"regime drift: score canonical={canonical_score} != analyst={analyst_score}"
        )
