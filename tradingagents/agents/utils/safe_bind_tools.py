"""
safe_bind_tools.py
────────────────────────────────────────────────────────
Attach tool schemas only when the underlying LLM truly
supports OpenAI-style function calling.

• OpenAI / Anthropic / Google models  →  always attach
• ChatOllama models                  →  attach **only**
  if the Ollama tag contains `"tools": true`
• All other cases                    →  silently fall
  back to plain text reasoning
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel


log = logging.getLogger(__name__)

def _ollama_has_tools_flag(model_name: str) -> bool:
    """
    Return True iff `ollama show <model_name>` contains `"tools": true`.
    If the command fails (e.g. Windows, sandbox), fall back to False.
    """
    try:
        output = subprocess.check_output(
            shlex.split(f"ollama show {model_name}"), text=True
        )
        return '"tools": true' in output
    except (NotImplementedError, AttributeError) as e:
        log.debug("Could not inspect model %s: %s", model_name, e)
        return False

def safe_bind_tools(
    llm: BaseChatModel, tools: Sequence[dict[str, Any]]
) -> BaseChatModel:
    """
    Attach `tools` to an LLM **only** if the model can actually handle them.
    Otherwise, return the original LLM unchanged.

    Parameters
    ----------
    llm
        Any LangChain chat model instance.
    tools
        List of tool schemas compatible with OpenAI function calling.

    Returns
    -------
    BaseChatModel
        Either the bound LLM (when tool calling is available) or the
        original LLM (fallback).
    """
    # LLM has no bind_tools method at all → nothing to do
    if not hasattr(llm, "bind_tools"):
        return llm

    # Special-case ChatOllama: check the `"tools": true` tag first
    if isinstance(llm, BaseChatModel) and not _ollama_has_tools_flag(llm.model):
        log.info(
            "[safe_bind_tools] Model %s lacks tools support -- skipping.",
            llm.model,
        )
        return llm

    # Generic path: try to bind; fall back gracefully on failure
    try:
        return llm.bind_tools(tools)
    except (NotImplementedError, AttributeError) as e:
        log.debug(
            "[safe_bind_tools] bind_tools failed for %s: %s – "
            "falling back to plain reasoning.",
            llm.__class__.__name__,
            e,
        )
        return llm
