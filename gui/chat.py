"""Chat with a finished run.

Uses the user's configured *quick-think* provider/model and feeds the full
analysis (analyst reports + debates + decision + tool trace) as the system
prompt so the LLM can answer questions like "why did the trader plan X
but the risk judge override to Y?" or "what did the bear miss?".

Why quick-think and not deep-think:
- Q&A is cheap and fast; the heavy lifting was already done in the analysis.
- The analysis's *voice* (Sonnet/GPT-5/etc.) doesn't need to match — the
  chat model is just summarising and answering on top of recorded text.
- Quick-think models on every supported provider have ample (>100K)
  context for the full state.

Streaming: LangChain's ``.stream()`` yields chunks; we surface them via a
generator so Streamlit's ``st.write_stream`` can render token-by-token.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Generator, Iterable, List, Optional

from gui.config import PROVIDER_KEYS, load as load_config


def bootstrap_env() -> None:
    """Copy GUI-stored API keys into ``os.environ`` if not already set.

    The Run page already does this for the worker subprocess via
    ``export_env``. Chat happens *inside* the Streamlit process, so it
    needs the keys in its own env. Idempotent and safe to call from any
    page that's about to make an LLM call.
    """
    cfg = load_config()
    for env_name, value in cfg.get("api_keys", {}).items():
        if value and not os.environ.get(env_name):
            os.environ[env_name] = value


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _meta_summary(meta: Dict[str, Any]) -> str:
    parts = [
        f"Ticker: {meta.get('ticker', '?')}",
        f"Trade date: {meta.get('trade_date', '?')}",
        f"Decision: {meta.get('decision') or '—'}",
        f"Provider/models: {meta.get('provider') or '—'} (deep: {meta.get('deep_model') or '—'}, quick: {meta.get('quick_model') or '—'})",
    ]
    if meta.get("started_at"):
        parts.append(f"Started: {meta['started_at']}")
    if meta.get("completed_at"):
        parts.append(f"Completed: {meta['completed_at']}")
    return "\n".join(parts)


def _state_as_text(state: Dict[str, Any]) -> str:
    """Render the run state as a structured text block for the system prompt."""
    sections: List[str] = []

    def _add(label: str, body: Optional[str]) -> None:
        if body:
            sections.append(f"## {label}\n\n{body}\n")

    _add("Market analysis", state.get("market_report"))
    _add("Sentiment analysis", state.get("sentiment_report"))
    _add("News analysis", state.get("news_report"))
    _add("Fundamentals analysis", state.get("fundamentals_report"))

    debate = state.get("investment_debate_state") or {}
    _add("Bull case", debate.get("bull_history"))
    _add("Bear case", debate.get("bear_history"))
    _add("Research manager verdict", debate.get("judge_decision"))

    _add("Trader plan",
         state.get("trader_investment_decision")
         or state.get("trader_investment_plan")
         or state.get("investment_plan"))

    risk = state.get("risk_debate_state") or {}
    _add("Aggressive risk perspective", risk.get("aggressive_history"))
    _add("Conservative risk perspective", risk.get("conservative_history"))
    _add("Neutral risk perspective", risk.get("neutral_history"))
    _add("Risk judge", risk.get("judge_decision"))
    _add("FINAL DECISION", state.get("final_trade_decision"))

    return "\n".join(sections)


def _tool_trace_summary(trace: List[Dict[str, Any]]) -> str:
    """Compact one-liner per tool call. Skipped if trace is empty (legacy archive)."""
    if not trace:
        return ""
    lines: List[str] = []
    for entry in trace:
        tool = entry.get("tool", "?")
        inp = (entry.get("input") or "").replace("\n", " ")[:160]
        out_preview = (entry.get("output") or "").replace("\n", " ")[:200]
        lines.append(f"- `{tool}` <- {inp}  ->  {out_preview}")
    return "## Tool calls (data the agents pulled in)\n\n" + "\n".join(lines) + "\n"


def system_prompt(state: Dict[str, Any], meta: Dict[str, Any],
                  tool_trace: Optional[List[Dict[str, Any]]] = None) -> str:
    pieces = [
        "You are a financial research assistant answering questions about a "
        "completed multi-agent stock analysis. Your context below contains the "
        "full analyst output, the bull/bear debate, the trader plan, the "
        "risk-management debate, and the final decision. Answer based ONLY "
        "on this context. If the user asks about something not covered in "
        "the analysis, say so explicitly rather than speculating. Cite the "
        "specific section name when quoting (e.g. 'per the Bear case…').\n",
        "## Run summary\n\n" + _meta_summary(meta) + "\n",
        "## Analysis\n\n" + _state_as_text(state),
    ]
    trace_text = _tool_trace_summary(tool_trace or [])
    if trace_text:
        pieces.append(trace_text)
    return "\n".join(pieces)


# ---------------------------------------------------------------------------
# LLM client + streaming
# ---------------------------------------------------------------------------

def _build_llm() -> Any:
    """Create the quick-think LLM the user has configured.

    Reads provider + quick_think_llm from the GUI config defaults; falls
    back to OpenAI gpt-4o-mini if neither is set. Uses the framework's
    factory so we get the same provider-specific kwargs (anthropic effort,
    google thinking_level, etc.) as a real run.
    """
    bootstrap_env()
    cfg = load_config()
    defaults = cfg.get("defaults", {})
    provider = defaults.get("llm_provider") or "openai"
    model = defaults.get("quick_think_llm") or "gpt-4o-mini"

    from tradingagents.llm_clients import create_llm_client  # type: ignore

    client = create_llm_client(provider=provider, model=model)
    return client.get_llm()


def stream_response(state: Dict[str, Any], meta: Dict[str, Any],
                    history: Iterable[Dict[str, str]], question: str,
                    tool_trace: Optional[List[Dict[str, Any]]] = None,
                    ) -> Generator[str, None, str]:
    """Stream the assistant's reply token-by-token.

    Yields incremental text chunks. The accumulated full text is also
    returned via the generator's ``StopIteration.value`` so callers using
    ``yield from`` can capture it without re-joining manually.
    """
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # type: ignore

    llm = _build_llm()
    msgs: List[Any] = [SystemMessage(content=system_prompt(state, meta, tool_trace))]
    for h in history:
        role = h.get("role")
        content = h.get("content") or ""
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    msgs.append(HumanMessage(content=question))

    full = ""
    try:
        for chunk in llm.stream(msgs):
            text = getattr(chunk, "content", None)
            if isinstance(text, list):
                # Anthropic returns content as a list of blocks; flatten text bits.
                parts = []
                for p in text:
                    if isinstance(p, dict):
                        parts.append(p.get("text", "") or p.get("content", "") or "")
                    else:
                        parts.append(str(p))
                text = "".join(parts)
            if text:
                full += text
                yield text
    except Exception as e:
        err = f"\n\n_(error from chat model: {e})_"
        full += err
        yield err
    return full


def quick_think_label() -> str:
    """Human-readable label for the model that will answer."""
    cfg = load_config()
    defaults = cfg.get("defaults", {})
    provider = defaults.get("llm_provider") or "openai"
    model = defaults.get("quick_think_llm") or "gpt-4o-mini"
    return f"{provider} · {model}"
