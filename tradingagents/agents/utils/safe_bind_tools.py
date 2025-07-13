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
    Return True iff `ollama show <model_name>` contains tools capability.
    If the command fails (e.g. Windows, sandbox), fall back to False.
    """
    try:
        output = subprocess.check_output(
            shlex.split(f"ollama show {model_name}"), text=True
        )
        # Check for multiple possible tools indicators
        tools_indicators = [
            '"tools": true',  # Old format
            'tools         ',  # New format in Capabilities section
            'tools\n',        # Alternative new format
            'tools\t',        # Tab-separated format
        ]
        
        # Also check if we're in the Capabilities section
        lines = output.split('\n')
        in_capabilities = False
        for line in lines:
            line_stripped = line.strip().lower()
            if 'capabilities' in line_stripped:
                in_capabilities = True
            elif in_capabilities and line_stripped and not line.startswith(' '):
                # We've left the capabilities section
                in_capabilities = False
            elif in_capabilities and 'tools' in line_stripped:
                log.debug("Found tools capability for model %s", model_name)
                return True
        
        # Fallback to checking for any tools indicator
        for indicator in tools_indicators:
            if indicator in output:
                log.debug("Found tools indicator '%s' for model %s", indicator, model_name)
                return True
                
        log.debug("No tools capability found for model %s", model_name)
        return False
    except (NotImplementedError, AttributeError, subprocess.CalledProcessError) as e:
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

    # Special-case ChatOllama: check for tools capability
    if llm.__class__.__name__ == 'ChatOllama':
        # Get model name from different possible attributes
        model_name = getattr(llm, 'model', None) or getattr(llm, 'model_name', None)
        
        if model_name and not _ollama_has_tools_flag(model_name):
            log.info(
                "[safe_bind_tools] Model %s lacks tools support -- skipping.",
                model_name,
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
