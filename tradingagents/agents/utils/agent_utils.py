from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, RemoveMessage


def prefetch_tools_parallel(tool_calls: list[dict]) -> dict[str, str]:
    """Pre-fetch multiple LangChain tools in parallel using ThreadPoolExecutor.

    Each entry in *tool_calls* must be a dict with:
    - ``"tool"``: the LangChain tool object (must have an ``.invoke()`` method)
    - ``"args"``: dict of keyword arguments to pass to ``tool.invoke()``
    - ``"label"``: human-readable section header for the injected context block

    Per-tool exceptions are caught so that a failure in one pre-fetch never
    crashes the analyst node.  The failing entry is replaced with an error
    placeholder so the LLM can fall back to calling that tool itself.

    Returns:
        dict mapping ``label`` → result string (or error placeholder)
    """
    results: dict[str, str] = {}

    def _fetch_one(tc: dict) -> tuple[str, str]:
        label: str = tc["label"]
        try:
            result = tc["tool"].invoke(tc["args"])
            return label, str(result)
        except Exception as exc:  # noqa: BLE001
            return label, f"[Error fetching {label}: {exc}]"

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_fetch_one, tc): tc["label"] for tc in tool_calls}
        for future in as_completed(futures):
            label, result = future.result()
            results[label] = result

    return results


def format_prefetched_context(results: dict[str, str]) -> str:
    """Format a prefetched-results dict into a clean Markdown block.

    Each key becomes a ``## <label>`` section header, with the corresponding
    content beneath it.  Sections are separated by a horizontal rule so the
    LLM can locate each dataset quickly.

    Returns:
        A single multi-line string ready for injection into a system prompt.
    """
    sections = [f"## {label}\n\n{content}" for label, content in results.items()]
    return "\n\n---\n\n".join(sections)


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
