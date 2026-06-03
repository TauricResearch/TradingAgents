"""LangChain chat-model adapter for the OpenAI Codex CLI.

Bridges whatever auth the local ``codex`` CLI is already configured with
(ChatGPT subscription via ``codex --login``, or ``OPENAI_API_KEY``) into
the LangChain ``BaseChatModel`` surface that TradingAgents expects from
``tradingagents.llm_clients.factory.create_llm_client``.

Scope: pure chat. ``bind_tools`` raises ``NotImplementedError`` — the
codex CLI runs its OWN tool-use loop with built-in Bash / file
operations in a sandbox, and there is no documented hook for handing
it LangChain tool descriptors the way ``claude_agent_sdk`` exposes
``create_sdk_mcp_server``. ``with_structured_output`` also raises so the
project's ``bind_structured`` helper falls back to free-text generation
for the manager / trader / portfolio agents.

Unlike the claude-code adapter, this is a thin subprocess wrapper —
codex ships only as a Node CLI, no Python SDK.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .base_client import BaseLLMClient

logger = logging.getLogger(__name__)


# Models the codex CLI accepts via ``-m``. Codex passes the value through
# to OpenAI's API, so anything the user's account is entitled to should
# work — we list a representative set for the CLI picker. Unknown values
# trigger the standard ``warn_if_unknown_model`` warning, never a hard fail.
_KNOWN_MODELS = {
    "o4-mini",
    "o4",
    "o3-mini",
    "o3",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5",
    "gpt-5-mini",
}

_DEFAULT_TIMEOUT_S = 600


def _flatten_messages(messages: List[BaseMessage]) -> str:
    """Collapse a LangChain message list into a single prompt string.

    The codex CLI takes the prompt as one positional argv — there is no
    separate system / user channel. Sections are labelled inline so the
    model can tell system instructions apart from prior turns and the
    current user message.
    """
    blocks: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if not content:
            continue
        if isinstance(msg, SystemMessage):
            blocks.append(f"[System]\n{content}")
        elif isinstance(msg, AIMessage):
            blocks.append(f"[Previous assistant turn]\n{content}")
        elif isinstance(msg, HumanMessage):
            blocks.append(content)
        else:
            blocks.append(content)
    return "\n\n".join(blocks)


class CodexChatModel(BaseChatModel):
    """LangChain chat model backed by the Codex CLI subprocess.

    Each ``invoke`` shells out to ``codex -q -m <model> -a full-auto``
    with the flattened prompt as the trailing positional argument.
    ``-q`` (quiet) keeps the CLI from emitting intermediate reasoning
    / tool-call narration — only the final assistant text reaches
    stdout. ``-a full-auto`` keeps the loop from blocking on permission
    prompts in non-interactive contexts.
    """

    model: str = "o4-mini"
    timeout_s: int = _DEFAULT_TIMEOUT_S
    approval_mode: str = "full-auto"

    model_config = {"protected_namespaces": ()}

    @property
    def _llm_type(self) -> str:
        return "codex"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "provider": "codex"}

    def _build_argv(self, prompt: str) -> list[str]:
        return [
            "codex",
            "-q",                       # quiet: only final assistant output
            "-m", self.model,
            "-a", self.approval_mode,   # don't block on tool approvals
            "--no-project-doc",         # don't auto-include codex.md from cwd
            prompt,
        ]

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = _flatten_messages(messages)
        if not prompt:
            raise ValueError("CodexChatModel received an empty prompt.")

        argv = self._build_argv(prompt)
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "The `codex` CLI is not on PATH. Install with one of:\n"
                "  npm install -g @openai/codex\n"
                "  pnpm add -g @openai/codex\n"
                "  brew install codex\n"
                "then run `codex --login` to authenticate."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"codex exceeded the {self.timeout_s}s timeout while generating "
                f"a response for model {self.model!r}."
            ) from e

        if result.returncode != 0:
            raise RuntimeError(
                f"codex exited with code {result.returncode}. "
                f"stderr: {(result.stderr or '').strip()[:500]}"
            )

        text = (result.stdout or "").strip()
        if not text:
            raise RuntimeError(
                f"codex returned empty stdout (exit code {result.returncode}). "
                f"stderr: {(result.stderr or '').strip()[:500]}"
            )

        logger.info(
            "codex call: model=%s prompt_len=%d output_len=%d",
            self.model, len(prompt), len(text),
        )

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    def bind_tools(self, tools, **kwargs):
        # codex runs its own internal tool-use loop with built-in
        # Bash / file operations. There is no documented way to hand it
        # LangChain tool descriptors. Analyst nodes that bind LangChain
        # tools must stay on a key-based provider (or claude-code which
        # has an SDK MCP bridge).
        raise NotImplementedError(
            "CodexChatModel does not support LangChain bind_tools(). The "
            "codex CLI runs its own tool-use loop with built-in tools and "
            "does not accept external LangChain tool descriptors. Route "
            "tool-using analyst nodes through a key-based provider."
        )

    def with_structured_output(self, schema, **kwargs):
        # Same NotImplementedError pattern as the claude-code adapter so
        # the project's ``bind_structured`` helper catches it and
        # transparently degrades manager / trader / portfolio-manager
        # to free-text generation.
        raise NotImplementedError(
            "CodexChatModel does not support with_structured_output(); "
            "tradingagents will fall back to free-text generation."
        )


class CodexClient(BaseLLMClient):
    """Factory wrapper exposed by ``create_llm_client('codex', ...)``."""

    provider = "codex"

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        if base_url is not None:
            # codex CLI's endpoint is configured at install time via
            # ``codex --login``; we don't expose a runtime override.
            raise ValueError(
                "The 'codex' provider has no base_url — endpoint and auth "
                "are owned by the local `codex` CLI's configured session."
            )
        super().__init__(model, base_url=None, **kwargs)

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        if shutil.which("codex") is None:
            # Fail loudly at construction so a misconfigured environment
            # is caught before the graph runs and starts spending tokens
            # in the rest of the pipeline.
            raise RuntimeError(
                "The 'codex' provider requires the codex CLI on PATH. "
                "Install with `npm install -g @openai/codex` and run "
                "`codex --login`."
            )
        return CodexChatModel(model=self.model)

    def validate_model(self) -> bool:
        return self.model in _KNOWN_MODELS
