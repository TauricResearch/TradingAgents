"""Builds a human-readable run configuration report.

Captures package version, user selections, and effective config so each
analysis report records which parameters produced it. Useful for comparing
runs across LLM providers, research depths, or tradingagents versions.

Issue: https://github.com/TauricResearch/TradingAgents/issues/752
"""

from __future__ import annotations

from typing import Any, Mapping

# Provider-specific reasoning keys: only render when set to avoid noise on
# providers that don't expose the field (e.g. Ollama has no "thinking level").
_PROVIDER_SPECIFIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("openai_reasoning_effort", "OpenAI reasoning effort"),
    ("google_thinking_level", "Google thinking level"),
    ("anthropic_effort", "Anthropic effort"),
)


def _row(label: str, value: Any) -> str:
    """Render a markdown table row, escaping pipes inside the value."""
    if value in (None, ""):
        rendered = "—"
    else:
        rendered = str(value).replace("|", "\\|")
    return f"| {label} | {rendered} |"


def build_run_config_markdown(
    selections: Mapping[str, Any],
    config: Mapping[str, Any],
    version: str,
) -> str:
    """Build a markdown run-configuration report.

    Args:
        selections: dict produced by ``cli.utils.get_user_selections``
            (ticker, analysis_date, analysts, research_depth, llm_provider,
            shallow_thinker, deep_thinker, backend_url, *_effort, etc.).
        config: effective tradingagents config dict (DEFAULT_CONFIG merged
            with overrides applied in ``cli/main.py:run_analysis``).
        version: package version string (e.g. ``"0.2.4"``).

    Returns:
        A markdown string. Caller writes it to disk.
    """
    analyst_names = ", ".join(
        getattr(a, "value", str(a)) for a in selections.get("analysts", []) or []
    ) or "—"

    base_rows = [
        _row("tradingagents version", version),
        _row("Ticker", selections.get("ticker")),
        _row("Analysis date", selections.get("analysis_date")),
        _row("Analysts", analyst_names),
        _row("Research depth", selections.get("research_depth")),
        _row("Output language", selections.get("output_language")),
        _row("LLM provider", selections.get("llm_provider")),
        _row("Quick-thinking model", selections.get("shallow_thinker")),
        _row("Deep-thinking model", selections.get("deep_thinker")),
        _row("Backend URL", selections.get("backend_url")),
        _row("Max debate rounds", config.get("max_debate_rounds")),
        _row("Max risk discuss rounds", config.get("max_risk_discuss_rounds")),
        _row("Checkpoint enabled", config.get("checkpoint_enabled")),
    ]

    provider_rows = []
    for key, label in _PROVIDER_SPECIFIC_FIELDS:
        value = selections.get(key)
        if value not in (None, ""):
            provider_rows.append(_row(label, value))

    lines = [
        "# Run Configuration",
        "",
        (
            "Captures the parameters used to generate this analysis. "
            "Useful for comparing runs across LLM providers, research depths, "
            "or tradingagents versions."
        ),
        "",
        "| Field | Value |",
        "|-------|-------|",
        *base_rows,
    ]

    if provider_rows:
        lines.extend(
            [
                "",
                "## Provider-specific reasoning parameters",
                "",
                "| Field | Value |",
                "|-------|-------|",
                *provider_rows,
            ]
        )

    lines.append("")  # trailing newline
    return "\n".join(lines)
