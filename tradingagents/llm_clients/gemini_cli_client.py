"""Google Gemini CLI subscription provider — routes LLM calls through the
local ``gemini -p`` headless CLI instead of the Generative Language API.

Users authenticated via ``gemini auth`` (GOOGLE_GENAI_USE_GCA / OAuth) get
the full multi-agent pipeline without an API key. Like Claude Code, each
call spawns one subprocess; auth is whatever the CLI already holds.

Differences from Claude Code that drive this subclass:

- Gemini CLI has no ``--system-prompt`` flag, so we inline the system prompt
  into the prompt argument with a clear ``<system>`` / ``<user>`` partition.
- Tools/MCP are governed by ``--approval-mode plan`` (read-only) plus an
  empty ``--allowed-mcp-server-names`` to keep the subprocess from running
  any tools itself; project tools run in langgraph's ToolNode via the
  JSON-envelope protocol inherited from :class:`SubprocessChatModel`.
- Response format with ``-o json`` is ``{"response": "...", ...}`` rather
  than Claude's ``{"result": ..., "structured_output": ...}``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .base_client import BaseLLMClient
from .subprocess_chat_base import SubprocessChatModel
from .validators import validate_model


class ChatGeminiCli(SubprocessChatModel):
    """LangChain BaseChatModel that delegates each call to ``gemini -p``."""

    model: str = "gemini-2.5-flash"
    yolo: bool = False  # let the model auto-approve actions; usually leave False
    force_subscription: bool = False

    @property
    def _llm_type(self) -> str:
        return "gemini_cli"

    def _binary_name(self) -> str:
        return "gemini"

    def _binary_env_var(self) -> str:
        return "GEMINI_CLI_BIN"

    def _build_command(
        self,
        binary: str,
        system_prompt: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> List[str]:
        cmd: List[str] = [
            binary,
            "--prompt",
            "",  # actual prompt is sent on stdin
            "--output-format",
            "json",
            "--approval-mode",
            "plan",  # read-only — no edits, no shell, no writes
            "--allowed-mcp-server-names",
            "",  # disable user-configured MCP servers
        ]
        if self.model:
            cmd += ["--model", self.model]
        if self.yolo:
            cmd = [c if c != "plan" else "yolo" for c in cmd]
        return cmd

    def _subprocess_input(self, system_prompt: str, user_prompt: str) -> str:
        """Inline the system prompt into stdin since Gemini has no --system-prompt flag."""
        if not system_prompt:
            return user_prompt
        return f"<<SYSTEM>>\n{system_prompt}\n<<END SYSTEM>>\n\n<<USER>>\n{user_prompt}\n<<END USER>>\n"

    def _subprocess_env(self, parent_env: Dict[str, str]) -> Dict[str, str]:
        if self.force_subscription:
            # Strip API-key-style env vars so the CLI falls back to OAuth.
            for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                parent_env.pop(var, None)
        return parent_env

    def _parse_response(
        self,
        stdout: str,
        json_schema: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[Any]]:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"`gemini -p` returned non-JSON output: {stdout[:500]}") from exc

        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"`gemini -p` returned error: {str(msg)[:500]}")

        # Gemini's --output-format json schema:
        #   { "response": "...", "stats": {...}, "session_id": "..." }
        text = ""
        if isinstance(payload, dict):
            text = payload.get("response") or payload.get("result") or ""
        if not isinstance(text, str):
            text = json.dumps(text)

        structured: Optional[Any] = None
        if json_schema is not None:
            # Gemini CLI does not expose a --json-schema flag like Claude Code;
            # the schema is included in the prompt by the base class via a
            # tool-protocol-like instruction. Best effort: parse the response
            # text as JSON and surface as structured if it parses cleanly.
            structured = _try_parse_json(text)

        return text, structured


_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _try_parse_json(text: str) -> Optional[Any]:
    """Best-effort JSON extraction for CLIs without a --json-schema flag.

    Tries: raw parse → fenced block → first balanced object.
    """
    s = text.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    m = _FENCED_JSON.search(s)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Find first balanced { ... }
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


_PASSTHROUGH_KWARGS = (
    "timeout",
    "yolo",
    "append_system_prompt",
    "force_subscription",
    "binary_path",
)


class GeminiCliClient(BaseLLMClient):
    """Client routing through the user's Gemini CLI subscription via ``gemini -p``."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs: Any):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs: Dict[str, Any] = {"model": self.model}
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs and self.kwargs[key] is not None:
                llm_kwargs[key] = self.kwargs[key]
        return ChatGeminiCli(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("gemini_cli", self.model)
