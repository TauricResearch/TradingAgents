"""LangChain BaseChatModel backed by the ``claude -p`` CLI subprocess.

Each ``invoke()`` call spawns a fresh ``claude -p`` process, pipes the
formatted prompt via stdin, and parses the JSON response. This lets
users with a Claude Max subscription run the full TradingAgents pipeline
at $0 additional API cost.

Design notes
------------
- **No tool-call support.** ``supports_tool_calls`` is ``False`` so
  analyst nodes can branch to the pre-fetch path instead of ``bind_tools``.
- **Subprocess-per-call.** No persistent daemon; auth is handled by the
  user's existing ``claude auth login`` session.
- **JSON output.** ``--output-format json`` gives structured
  ``{"result": "..."}`` output, eliminating ANSI-escape parsing.
- **stdin pipe.** Prompts are piped via stdin to avoid shell arg-length
  limits (debate histories can be 10-20 K tokens).

See also: PLAN.md Phase 1, Task 1.1.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger(__name__)

# Defaults -----------------------------------------------------------------

_DEFAULT_TIMEOUT_S = 300  # Opus reasoning can be slow
_DEFAULT_MAX_RETRIES = 3
_RETRY_BASE_DELAY_S = 2.0
_CLAUDE_BIN = "claude"


def _find_claude_binary() -> str:
    """Return the absolute path to the ``claude`` binary, or raise."""
    path = shutil.which(_CLAUDE_BIN)
    if path is None:
        raise FileNotFoundError(
            f"'{_CLAUDE_BIN}' not found on PATH. Install Claude Code CLI "
            "and run 'claude auth login' first."
        )
    return path


# Environment --------------------------------------------------------------

def _minimal_env() -> dict[str, str]:
    """Build a minimal environment for the claude subprocess.

    Only forward variables the CLI actually needs — PATH, HOME, auth
    config dirs. This avoids leaking unrelated API keys (OPENAI_API_KEY,
    etc.) into the subprocess as a defense-in-depth measure.
    """
    env: dict[str, str] = {}
    for key in (
        "PATH", "HOME", "USER", "TERM", "LANG", "SHELL",
        # Claude CLI config / auth directories
        "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
        # macOS keychain access
        "TMPDIR",
    ):
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    return env


# Message formatting -------------------------------------------------------

def _extract_text(content: Any) -> str:
    """Extract plain text from LangChain message content.

    Content can be a string, a list of typed blocks (e.g.
    ``[{"type": "text", "text": "..."}]``), or something else.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _format_messages(messages: Sequence[BaseMessage]) -> tuple[str, str]:
    """Convert LangChain messages to (system_prompt, user_prompt) strings.

    Returns a 2-tuple so the system message can be passed via
    ``--system-prompt`` and the rest via stdin. If there is no explicit
    system message, the system prompt is empty and everything goes to
    stdin.
    """
    system_parts: list[str] = []
    conversation_parts: list[str] = []

    for msg in messages:
        text = _extract_text(msg.content)
        if isinstance(msg, SystemMessage):
            system_parts.append(text)
        elif isinstance(msg, HumanMessage):
            conversation_parts.append(f"[Human]\n{text}")
        elif isinstance(msg, AIMessage):
            conversation_parts.append(f"[Assistant]\n{text}")
        else:
            # ToolMessage, FunctionMessage, etc. — stringify generically
            role = getattr(msg, "type", "unknown")
            conversation_parts.append(f"[{role}]\n{text}")

    system_prompt = "\n\n".join(system_parts)
    user_prompt = "\n\n".join(conversation_parts)
    return system_prompt, user_prompt


# Subprocess call ----------------------------------------------------------

def _call_cli(
    user_prompt: str,
    *,
    system_prompt: str = "",
    model: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT_S,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    claude_bin: str | None = None,
) -> str:
    """Run ``claude -p`` and return the response text.

    Retries with exponential back-off on transient errors (timeout,
    non-zero exit). Raises on permanent failures after exhausting retries.
    """
    bin_path = claude_bin or _find_claude_binary()

    cmd: list[str] = [bin_path, "-p", "--output-format", "json"]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if model:
        cmd += ["--model", model]

    env = _minimal_env()
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                "claude -p attempt %d/%d  prompt=%d chars  system=%d chars",
                attempt,
                max_retries,
                len(user_prompt),
                len(system_prompt),
            )
            proc = subprocess.run(
                cmd,
                input=user_prompt.encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
            )

            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                error_detail = stderr or stdout or f"exit code {proc.returncode}"
                # Check for rate limiting keywords
                combined = (stderr + stdout).lower()
                if any(kw in combined for kw in ("rate", "limit", "429", "throttl")):
                    logger.warning("Rate limited on attempt %d: %s", attempt, error_detail)
                    _backoff(attempt)
                    last_error = RuntimeError(f"CLI rate limited: {error_detail}")
                    continue

                # Auth errors are permanent — don't retry
                if "401" in combined or "authentication" in combined:
                    raise RuntimeError(
                        f"Claude CLI authentication failed: {error_detail}. "
                        "Run 'claude auth login' in a terminal."
                    )

                logger.warning("CLI error attempt %d: %s", attempt, error_detail)
                last_error = RuntimeError(f"claude -p failed: {error_detail}")
                _backoff(attempt)
                continue

            if not stdout:
                logger.warning("Empty stdout on attempt %d", attempt)
                last_error = RuntimeError("claude -p returned empty output")
                _backoff(attempt)
                continue

            # Parse JSON response — extract the "result" field
            return _parse_json_response(stdout)

        except subprocess.TimeoutExpired:
            logger.warning("Timeout (%ds) on attempt %d/%d", timeout, attempt, max_retries)
            last_error = TimeoutError(
                f"claude -p timed out after {timeout}s on attempt {attempt}"
            )
            _backoff(attempt)
            continue

    raise last_error or RuntimeError("claude -p failed after all retries")


def _parse_json_response(raw: str) -> str:
    """Extract the LLM response text from ``--output-format json`` output.

    Expected shape::

        {
          "type": "result",
          "subtype": "success",
          "result": "<actual LLM text>",
          ...
        }
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Do NOT silently accept garbage — raise so the retry loop can handle it.
        # Truncated output (e.g. from a killed subprocess) would otherwise
        # propagate through the pipeline as a corrupt "report".
        logger.warning("Failed to parse JSON from claude output: %.200s", raw)
        raise RuntimeError(
            f"Claude CLI returned invalid JSON (possibly truncated): {raw[:200]}"
        )

    if isinstance(data, dict):
        if data.get("is_error"):
            error_msg = data.get("result", "Unknown CLI error")
            raise RuntimeError(f"Claude CLI returned error: {error_msg}")
        result = data.get("result")
        if result is not None:
            return str(result)

    # Unexpected shape — return stringified output
    logger.warning("Unexpected JSON shape from claude CLI: %s", type(data))
    return raw


def _backoff(attempt: int) -> None:
    """Exponential back-off sleep, capped at 60 seconds."""
    delay = min(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)), 60.0)
    logger.debug("Backing off %.1fs before retry", delay)
    time.sleep(delay)


def _apply_stop_sequences(text: str, stop: list[str] | None) -> str:
    """Truncate ``text`` at the first occurrence of any stop sequence."""
    if not stop:
        return text
    earliest_idx = len(text)
    for seq in stop:
        idx = text.find(seq)
        if idx != -1 and idx < earliest_idx:
            earliest_idx = idx
    return text[:earliest_idx]


# LangChain BaseChatModel --------------------------------------------------

class ClaudeCLIChat(BaseChatModel):
    """LangChain chat model that delegates to ``claude -p`` subprocess.

    Parameters
    ----------
    model_name : str
        Model identifier passed to ``--model`` flag. When ``None``, the
        CLI uses whatever model is configured in the user's session.
    timeout : int
        Per-call subprocess timeout in seconds (default 300).
    max_retries : int
        Retries with exponential back-off (default 3).

    Attributes
    ----------
    supports_tool_calls : bool
        Always ``False``. Analyst nodes check this property to decide
        whether to use the pre-fetch path or ``bind_tools``.
    """

    model_name: Optional[str] = None
    timeout: int = _DEFAULT_TIMEOUT_S
    max_retries: int = _DEFAULT_MAX_RETRIES
    _claude_bin: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def model_post_init(self, __context: Any) -> None:
        """Resolve the claude binary path once at construction time."""
        super().model_post_init(__context)
        self._claude_bin = _find_claude_binary()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def _llm_type(self) -> str:
        return "claude_cli"

    @property
    def supports_tool_calls(self) -> bool:
        """Signal to analyst nodes that tool-calling is not available."""
        return False

    # ------------------------------------------------------------------
    # Tool-call guard
    # ------------------------------------------------------------------

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> "ClaudeCLIChat":
        """No-op override — returns ``self`` unchanged.

        The ``claude -p`` CLI does not support native tool-calling.
        Analyst nodes that use ``bind_tools`` will get back this same
        model instance. Because the LLM response will never contain
        ``tool_calls``, the existing analyst code already falls through
        to treating ``result.content`` as the report (e.g.
        ``market_analyst.py`` checks ``len(result.tool_calls) == 0``).

        Phase 2 (pre-fetch refactor) will add a ``supports_tool_calls``
        guard so analysts pre-fetch data into the prompt instead.
        """
        logger.warning(
            "bind_tools() called on ClaudeCLIChat (no-op) — "
            "%d tools ignored: %s. This should only happen during "
            "initialization, not during active inference.",
            len(tools),
            [getattr(t, "name", str(t)) for t in tools],
        )
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        """Not supported — raise with a clear message."""
        raise NotImplementedError(
            "ClaudeCLIChat does not support structured output. "
            "The claude -p CLI has no JSON-mode or tool-calling support. "
            "Use the pre-fetch pattern instead."
        )

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous generation via ``claude -p``."""
        system_prompt, user_prompt = _format_messages(messages)

        # Fall back to runtime lookup if _claude_bin was lost (e.g. after
        # serialization/deserialization — Pydantic private attrs don't survive).
        claude_bin = self._claude_bin or _find_claude_binary()

        response_text = _call_cli(
            user_prompt,
            system_prompt=system_prompt,
            model=self.model_name,
            timeout=self.timeout,
            max_retries=self.max_retries,
            claude_bin=claude_bin,
        )

        # Honour stop sequences by truncating output (CR-02 fix)
        response_text = _apply_stop_sequences(response_text, stop)

        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
