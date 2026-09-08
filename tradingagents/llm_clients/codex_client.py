"""Codex local client.

This provider lets users who have Codex through a ChatGPT plan run the
TradingAgents workflow through their local Codex authentication instead of an
OpenAI Platform API key. It intentionally uses the published ``openai-codex``
SDK rather than reading Codex credential files directly.

Codex is an agent surface, not a Chat Completions-compatible model API. The
adapter below provides the small LangChain chat-model surface this project
needs, including a JSON-mediated bridge for tool calls.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
from collections.abc import Iterable
from threading import Lock
from time import perf_counter
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field

from .base_client import BaseLLMClient
from .validators import validate_model

logger = logging.getLogger(__name__)

CODEX_INSTALL_COMMAND = 'python -m pip install -e ".[codex]"'
CODEX_UPDATE_COMMAND = "python -m pip install -U --pre openai-codex"
CODEX_LOGIN_COMMAND = "codex login"
CODEX_CLI_UPDATE_COMMAND = "codex update"
CODEX_CLI_INSTALL_COMMAND = "npm install -g @openai/codex"
CODEX_CLI_VERIFY_COMMAND = "codex --version"
CODEX_ACCOUNT_CHECK_COMMAND = (
    'python -c "from openai_codex import Codex; '
    'c=Codex(); print(c.account()); c.close()"'
)
CODEX_MODEL_LIST_COMMAND = (
    'python -c "from openai_codex import Codex; '
    'c=Codex(); print([m.id for m in c.models().data]); c.close()"'
)


class CodexSetupError(RuntimeError):
    """Actionable setup error for the Codex provider."""


class _CodexRuntime:
    """One long-lived Codex app-server process shared by local model instances.

    The Codex SDK starts its app-server during ``Codex()`` construction. Starting
    a process for each LangChain invocation dominated short TradingAgents runs,
    particularly when analysts make several tool and report calls. Threads stay
    per invocation so agents still get isolated conversations; only the local
    authenticated runtime is shared.
    """

    def __init__(self) -> None:
        self._codex: Any | None = None
        self._lock = Lock()

    def get(self) -> Any:
        with self._lock:
            if self._codex is None:
                self._codex = _new_codex_client()
            return self._codex

    def close(self) -> None:
        with self._lock:
            if self._codex is not None:
                self._codex.close()
                self._codex = None


_CODEX_RUNTIME = _CodexRuntime()
atexit.register(_CODEX_RUNTIME.close)


def _codex_cli_path() -> str | None:
    """Prefer the user's installed CLI over the SDK's pinned bundled runtime."""
    configured = os.environ.get("TRADINGAGENTS_CODEX_CLI_PATH")
    if configured:
        return configured
    return shutil.which("codex")


def _new_codex_client() -> Any:
    """Create Codex against the newest available local CLI when possible.

    The Python SDK bundles a CLI release, but that release can lag behind the
    separately installed Codex CLI and therefore omit newer subscription
    models. The SDK supports supplying a CLI binary explicitly; this keeps
    authentication local while matching the runtime users invoke in a terminal.
    """
    from openai_codex import Codex

    cli_path = _codex_cli_path()
    if not cli_path:
        return Codex()

    from openai_codex.client import CodexConfig

    return Codex(CodexConfig(codex_bin=cli_path))


def _content_to_text(content: Any) -> str:
    """Normalize LangChain or OpenAI-style message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return str(content)


def _message_to_text(message: BaseMessage | dict[str, Any]) -> str:
    if isinstance(message, dict):
        return _content_to_text(message.get("content", ""))
    return _content_to_text(message.content)


def _messages_to_prompt(messages: list[BaseMessage | dict[str, Any]]) -> str:
    chunks = []
    for message in messages:
        role = (
            message.get("role", "user")
            if isinstance(message, dict)
            else getattr(message, "type", message.__class__.__name__)
        )
        text = _message_to_text(message).strip()
        if text:
            chunks.append(f"{role.upper()}:\n{text}")
    return "\n\n".join(chunks)


def _input_to_text(input_: Any) -> str:
    """Normalize LangChain prompt inputs into plain text for Codex."""
    if isinstance(input_, str):
        return input_
    if isinstance(input_, list):
        return _messages_to_prompt(input_)
    if hasattr(input_, "to_messages"):
        return _messages_to_prompt(input_.to_messages())
    return str(input_)


def _tool_schema(tool: Any) -> dict[str, Any]:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        parameters = args_schema.model_json_schema()
    else:
        parameters = getattr(tool, "args", {}) or {}
    return {
        "name": getattr(tool, "name", tool.__class__.__name__),
        "description": getattr(tool, "description", "") or "",
        "parameters": parameters,
    }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make Pydantic's schema compatible with Codex structured output.

    Codex requires every object to explicitly reject undeclared properties.
    It also requires all declared object keys to be listed as required; nullable
    values remain nullable through their ``anyOf`` schema rather than omission.
    """
    if isinstance(schema, dict):
        strict = {key: _strict_json_schema(value) for key, value in schema.items()}
        properties = strict.get("properties")
        if isinstance(properties, dict):
            strict["additionalProperties"] = False
            strict["required"] = list(properties)
        return strict
    if isinstance(schema, list):
        return [_strict_json_schema(item) for item in schema]
    return schema


def _available_model_ids(codex: Any) -> list[str]:
    """Return model IDs advertised by the installed Codex SDK/runtime."""
    client = getattr(codex, "_client", None)
    raw_request = getattr(client, "_request_raw", None)
    if callable(raw_request):
        try:
            # Newer Codex CLIs can add protocol enum values before the Python
            # SDK understands them. Read the raw model-list response so model
            # availability remains forward-compatible.
            raw = raw_request("model/list", {"includeHidden": False})
            data = raw.get("data", []) if isinstance(raw, dict) else []
            return [str(model["id"]) for model in data if isinstance(model, dict) and model.get("id")]
        except Exception as exc:  # noqa: BLE001 - fall back to the SDK parser
            logger.warning("Could not read the raw Codex model list: %s", exc)
    try:
        models = codex.models()
    except Exception as exc:  # noqa: BLE001 - availability check is best-effort
        logger.warning("Could not list Codex models before invocation: %s", exc)
        return []

    data = getattr(models, "data", models)
    ids = []
    for model in data or []:
        model_id = getattr(model, "id", None) or getattr(model, "model", None)
        if model_id:
            ids.append(str(model_id))
    return ids


def _codex_setup_message(
    problem: str,
    *,
    original_error: str | None = None,
    available_models: Iterable[str] | None = None,
    recovery_steps: Iterable[str] = (),
) -> str:
    lines = [problem]
    steps = list(recovery_steps)
    if steps:
        lines.extend(["", "Next steps:"])
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    if available_models:
        lines.extend(["", "Models currently reported by your installed runtime:"])
        lines.append(", ".join(available_models))
    if original_error:
        lines.extend(["", f"Original Codex error: {original_error}"])
    return "\n".join(lines)


def _looks_like_newer_codex_required(message: str) -> bool:
    lowered = message.lower()
    return "requires a newer version of codex" in lowered or "update codex" in lowered


def _looks_like_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "not authenticated",
            "authentication",
            "unauthorized",
            "login",
            "sign in",
            "requires_openai_auth",
        )
    )


def _looks_like_schema_error(message: str) -> bool:
    lowered = message.lower()
    return "invalid_json_schema" in lowered or "response_format" in lowered


def _auth_recovery_steps() -> list[str]:
    return [
        f"Sign in with ChatGPT: {CODEX_LOGIN_COMMAND}",
        f"Confirm the saved login: {CODEX_ACCOUNT_CHECK_COMMAND}",
    ]


def _model_recovery_steps(cli_available: bool | None = None) -> list[str]:
    """Return every recovery step needed for a model-unavailable error."""
    if cli_available is None:
        cli_available = _codex_cli_path() is not None
    if not cli_available:
        return [
            "Install the standalone Codex CLI (requires Node.js): "
            f"{CODEX_CLI_INSTALL_COMMAND}",
            f"Open a new terminal and confirm installation: {CODEX_CLI_VERIFY_COMMAND}",
            f"Sign in with ChatGPT: {CODEX_LOGIN_COMMAND}",
            "Restart TradingAgents; it will then use the standalone CLI for current models.",
        ]
    return [
        f"Update the standalone Codex CLI: {CODEX_CLI_UPDATE_COMMAND}",
        f"Confirm the installed version: {CODEX_CLI_VERIFY_COMMAND}",
        f"Confirm the saved login: {CODEX_ACCOUNT_CHECK_COMMAND}",
        "Restart TradingAgents. If the model is still unavailable, choose one of "
        "the models reported by this runtime because your current account may not offer it.",
    ]


def preflight_codex_runtime(models: str | Iterable[str]) -> list[str]:
    """Validate Codex SDK/auth/model availability before the graph starts."""
    try:
        __import__("openai_codex")
    except ImportError as exc:
        raise CodexSetupError(
            _codex_setup_message(
                "Codex provider is selected, but the `openai-codex` SDK is not installed.",
                original_error=str(exc),
                recovery_steps=[f"Install the optional provider dependency: {CODEX_INSTALL_COMMAND}"],
            )
        ) from exc

    requested_models = [models] if isinstance(models, str) else list(models)
    try:
        with _new_codex_client() as codex:
            try:
                account = codex.account()
            except Exception as exc:  # noqa: BLE001 - convert SDK detail to user steps
                raise CodexSetupError(
                    _codex_setup_message(
                        "Codex provider is selected, but TradingAgents could not verify "
                        "a local Codex/ChatGPT login.",
                        original_error=str(exc),
                        recovery_steps=_auth_recovery_steps(),
                    )
                ) from exc

            if not account:
                raise CodexSetupError(
                    _codex_setup_message(
                        "Codex provider is selected, but no local Codex/ChatGPT "
                        "account was found.",
                        recovery_steps=_auth_recovery_steps(),
                    )
                )

            available = _available_model_ids(codex)
    except CodexSetupError:
        raise
    except Exception as exc:  # noqa: BLE001 - SDK startup/runtime failure
        message = str(exc)
        if _looks_like_auth_error(message):
            problem = (
                "Codex provider is selected, but the local Codex/ChatGPT "
                "session is not ready."
            )
        else:
            problem = "Codex provider is selected, but the Codex SDK/runtime is not ready."
        steps = _auth_recovery_steps() if _looks_like_auth_error(message) else _model_recovery_steps()
        raise CodexSetupError(
            _codex_setup_message(problem, original_error=message, recovery_steps=steps)
        ) from exc

    missing = [model for model in requested_models if available and model not in available]
    if missing:
        standalone_cli_available = _codex_cli_path() is not None
        problem = (
            "Codex provider is selected, but the configured model is not available "
            "in your installed Codex SDK/runtime."
        )
        if not standalone_cli_available:
            problem = (
                "Codex provider is selected, but the configured model requires the "
                "standalone Codex CLI and no `codex` command was found."
            )
        if any(model.startswith("gpt-5.6") for model in missing):
            problem += " GPT-5.6 models may require a newer Codex app/CLI/SDK."
        raise CodexSetupError(
            _codex_setup_message(
                problem,
                available_models=available,
                original_error=f"Unavailable model(s): {', '.join(missing)}",
                recovery_steps=_model_recovery_steps(standalone_cli_available),
            )
        )
    return available


class CodexStructuredOutput:
    """Prompt-level structured-output adapter for Codex.

    Codex does not currently expose a LangChain-native structured-output API,
    but the agents only require that ``with_structured_output`` returns an
    object with ``invoke`` that yields a Pydantic instance. We satisfy that
    contract by asking Codex for schema-conforming JSON, parsing it, and letting
    Pydantic perform the final validation.
    """

    def __init__(self, llm: CodexChatModel, schema: type[BaseModel]):
        self.llm = llm
        self.schema = schema

    def invoke(self, input_: Any, config=None, **kwargs) -> BaseModel:
        prompt = _input_to_text(input_)
        output_schema = _strict_json_schema(self.schema.model_json_schema())
        schema_json = json.dumps(output_schema, indent=2)
        structured_prompt = (
            f"{prompt}\n\n"
            "Return ONLY valid JSON that conforms to this JSON schema. "
            "Do not wrap the JSON in markdown fences. Do not include commentary "
            "outside the JSON object.\n\n"
            f"{schema_json}"
        )
        raw = self.llm._run_codex(
            structured_prompt,
            output_schema=output_schema,
        )
        parsed = _extract_json_object(raw)
        if parsed is None:
            raise ValueError(f"Codex returned non-JSON structured output: {raw!r}")
        result = self.schema.model_validate(parsed)
        self.llm._notify_codex_status("on_codex_structured_output")
        return result


class CodexChatModel(BaseChatModel):
    """LangChain chat wrapper around the local Codex SDK."""

    model_name: str = "gpt-5.4"
    tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "codex-local"

    def bind_tools(self, tools, **kwargs):  # noqa: D401 - LangChain signature
        """Return a copy of this model configured with LangChain tools."""
        return self.model_copy(update={"tools": list(tools)})

    def with_structured_output(self, schema, *, method=None, **kwargs):
        return CodexStructuredOutput(self, schema)

    def _notify_codex_status(self, method_name: str, **kwargs: Any) -> None:
        """Send optional Codex telemetry to LangChain callback handlers."""
        callbacks = getattr(self, "callbacks", None)
        handlers = getattr(callbacks, "handlers", callbacks)
        if not isinstance(handlers, Iterable) or isinstance(handlers, (str, bytes)):
            return
        for handler in handlers:
            callback = getattr(handler, method_name, None)
            if callable(callback):
                callback(**kwargs)

    def record_structured_fallback(self, agent_name: str, error: Exception) -> None:
        """Record a visible fallback when the shared structured helper retries."""
        self._notify_codex_status(
            "on_codex_structured_fallback",
            agent_name=agent_name,
            error=str(error),
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager=None,
        **kwargs,
    ) -> ChatResult:
        prompt = _messages_to_prompt(messages)
        if self.tools:
            prompt = self._add_tool_protocol(prompt)

        raw = self._run_codex(prompt)
        message = self._to_ai_message(raw)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _add_tool_protocol(self, prompt: str) -> str:
        tool_specs = [_tool_schema(tool) for tool in self.tools]
        return (
            f"{prompt}\n\n"
            "You may either answer directly or request tool calls. If you need tools, "
            "return ONLY valid JSON in this exact shape:\n"
            '{"tool_calls":[{"name":"tool_name","args":{}}]}\n'
            "If you have enough information for a final answer, return normal prose "
            "and do not wrap it in JSON.\n\n"
            f"Available tools:\n{json.dumps(tool_specs, indent=2)}"
        )

    def _run_codex(
        self,
        prompt: str,
        *,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        started = perf_counter()
        try:
            from openai_codex import Sandbox
        except ImportError as exc:
            raise ImportError(
                "The Codex provider requires the optional SDK. Install it with "
                '`pip install ".[codex]"` or `pip install openai-codex`, then run '
                "`codex login` and sign in with ChatGPT."
            ) from exc

        try:
            codex = _CODEX_RUNTIME.get()
            available = _available_model_ids(codex)
            if available and self.model_name not in available:
                raise CodexSetupError(
                    _codex_setup_message(
                        "The configured Codex model is not available in your "
                        "installed Codex SDK/runtime.",
                        available_models=available,
                        original_error=f"Unavailable model: {self.model_name}",
                        recovery_steps=_model_recovery_steps(),
                    )
                )
            thread = codex.thread_start(
                model=self.model_name,
                sandbox=Sandbox.read_only,
                ephemeral=True,
            )
            result = thread.run(prompt, output_schema=output_schema)
        except CodexSetupError:
            self._notify_codex_status(
                "on_codex_request_end",
                duration_seconds=perf_counter() - started,
                error="Codex setup error",
            )
            raise
        except Exception as exc:
            message = str(exc)
            if _looks_like_newer_codex_required(message):
                problem = "This Codex model requires a newer Codex app/CLI/SDK."
            elif _looks_like_auth_error(message):
                problem = (
                    "TradingAgents could not use your local Codex/ChatGPT login "
                    "for this request."
                )
            elif _looks_like_schema_error(message):
                problem = (
                    "TradingAgents sent a Codex structured-output schema that the "
                    "installed runtime rejected. This is an integration error, not "
                    "a Codex login problem."
                )
            else:
                problem = "Codex local invocation failed."
            self._notify_codex_status(
                "on_codex_request_end",
                duration_seconds=perf_counter() - started,
                error=problem,
            )
            if _looks_like_newer_codex_required(message):
                steps = _model_recovery_steps() + [
                    f"If available, update the Codex CLI too: {CODEX_CLI_UPDATE_COMMAND}"
                ]
            elif _looks_like_auth_error(message):
                steps = _auth_recovery_steps()
            elif _looks_like_schema_error(message):
                steps = [
                    "Restart TradingAgents after applying the current Codex provider update.",
                    "No Codex re-login is required for this error.",
                ]
            else:
                steps = [f"Confirm the saved login: {CODEX_ACCOUNT_CHECK_COMMAND}"]
            raise RuntimeError(
                _codex_setup_message(
                    problem,
                    original_error=message,
                    recovery_steps=steps,
                )
            ) from exc

        self._notify_codex_status(
            "on_codex_request_end",
            duration_seconds=perf_counter() - started,
        )
        return str(getattr(result, "final_response", "") or "")

    def _to_ai_message(self, raw: str) -> AIMessage:
        parsed = _extract_json_object(raw) if self.tools else None
        tool_calls = parsed.get("tool_calls") if isinstance(parsed, dict) else None
        if isinstance(tool_calls, list) and tool_calls:
            normalized = []
            for idx, call in enumerate(tool_calls):
                if not isinstance(call, dict) or not call.get("name"):
                    continue
                args = call.get("args") or {}
                if not isinstance(args, dict):
                    logger.warning("Ignoring Codex tool call with non-object args: %s", call)
                    continue
                normalized.append({
                    "name": str(call["name"]),
                    "args": args,
                    "id": str(call.get("id") or f"codex_tool_{idx}"),
                })
            if normalized:
                return AIMessage(content="", tool_calls=normalized)
        return AIMessage(content=raw)


class CodexClient(BaseLLMClient):
    """Client for Codex local/ChatGPT-authenticated runs."""

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        preflight_codex_runtime(self.model)
        return CodexChatModel(
            model_name=self.model,
            callbacks=self.kwargs.get("callbacks"),
        )

    def validate_model(self) -> bool:
        return validate_model("codex", self.model)
