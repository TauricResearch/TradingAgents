import re
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from tradingagents.llm_clients.codex_app_server import (
    CodexAppServerAuthError,
    CodexAppServerBinaryError,
    CodexInvocationResult,
    CodexStructuredOutputError,
)
from tradingagents.llm_clients.codex_message_codec import normalize_input_messages
from tradingagents.llm_clients.codex_binary import resolve_codex_binary
from tradingagents.llm_clients.codex_preflight import run_codex_preflight
from tradingagents.llm_clients.codex_schema import (
    build_plain_response_schema,
    build_tool_response_schema,
    normalize_tools_for_codex,
)
from tradingagents.llm_clients.factory import create_llm_client


def lookup_price(ticker: str) -> str:
    """Return the latest price snapshot for a ticker."""


def lookup_volume(ticker: str) -> str:
    """Return the latest volume snapshot for a ticker."""


class FakeCodexSession:
    def __init__(
        self,
        *,
        codex_binary=None,
        request_timeout=0,
        workspace_dir="",
        cleanup_threads=True,
        responses=None,
        account_payload=None,
        models_payload=None,
    ):
        self.codex_binary = codex_binary
        self.request_timeout = request_timeout
        self.workspace_dir = workspace_dir
        self.cleanup_threads = cleanup_threads
        self.responses = deque(responses or [])
        self.account_payload = account_payload or {
            "account": {"type": "chatgpt"},
            "requiresOpenaiAuth": False,
        }
        self.models_payload = models_payload or {
            "data": [{"id": "gpt-5.4", "model": "gpt-5.4"}]
        }
        self.started = 0
        self.closed = 0
        self.invocations = []

    def start(self):
        self.started += 1

    def close(self):
        self.closed += 1

    def account_read(self):
        return self.account_payload

    def model_list(self, include_hidden=True):
        return self.models_payload

    def invoke(
        self,
        *,
        prompt,
        model,
        output_schema,
        reasoning_effort,
        summary,
        personality,
    ):
        self.invocations.append(
            {
                "prompt": prompt,
                "model": model,
                "output_schema": output_schema,
                "reasoning_effort": reasoning_effort,
                "summary": summary,
                "personality": personality,
            }
        )
        if not self.responses:
            raise AssertionError("No fake Codex responses left.")
        return CodexInvocationResult(final_text=self.responses.popleft(), notifications=[])


class CodexProviderTests(unittest.TestCase):
    def test_resolve_codex_binary_uses_windows_vscode_fallback(self):
        fake_home = Path("C:/Users/tester")
        candidate = fake_home / ".vscode/extensions/openai.chatgpt-1.0.0/bin/windows-x86_64/codex.exe"

        with (
            patch("tradingagents.llm_clients.codex_binary.os.name", "nt"),
            patch("tradingagents.llm_clients.codex_binary.Path.home", return_value=fake_home),
            patch("tradingagents.llm_clients.codex_binary.shutil.which", return_value=None),
            patch(
                "tradingagents.llm_clients.codex_binary.Path.glob",
                return_value=[candidate],
            ),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mocked_stat,
        ):
            mocked_stat.return_value.st_mtime = 1
            resolved = resolve_codex_binary(None)

        self.assertEqual(resolved, str(candidate))

    def test_resolve_codex_binary_skips_unusable_path_alias_on_windows(self):
        fake_home = Path("C:/Users/tester")
        alias_path = "C:/Program Files/WindowsApps/OpenAI.Codex/app/resources/codex.exe"
        candidate = fake_home / ".vscode/extensions/openai.chatgpt-1.0.0/bin/windows-x86_64/codex.exe"

        with (
            patch("tradingagents.llm_clients.codex_binary.os.name", "nt"),
            patch("tradingagents.llm_clients.codex_binary.Path.home", return_value=fake_home),
            patch("tradingagents.llm_clients.codex_binary.shutil.which", return_value=alias_path),
            patch(
                "tradingagents.llm_clients.codex_binary.Path.glob",
                return_value=[candidate],
            ),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.stat") as mocked_stat,
            patch(
                "tradingagents.llm_clients.codex_binary._is_usable_codex_binary",
                side_effect=lambda path: path != alias_path,
            ),
        ):
            mocked_stat.return_value.st_mtime = 1
            resolved = resolve_codex_binary(None)

        self.assertEqual(resolved, str(candidate))

    def test_resolve_codex_binary_uses_env_override(self):
        with (
            patch("tradingagents.llm_clients.codex_binary.os.name", "nt"),
            patch("tradingagents.llm_clients.codex_binary.shutil.which", return_value=None),
            patch.dict("os.environ", {"CODEX_BINARY": "C:/custom/codex.exe"}, clear=False),
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "tradingagents.llm_clients.codex_binary._is_usable_codex_binary",
                return_value=True,
            ),
        ):
            resolved = resolve_codex_binary(None)

        self.assertEqual(Path(resolved), Path("C:/custom/codex.exe"))

    def test_resolve_codex_binary_checks_explicit_binary_usability(self):
        with (
            patch("tradingagents.llm_clients.codex_binary.os.name", "nt"),
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "tradingagents.llm_clients.codex_binary._is_usable_codex_binary",
                return_value=False,
            ),
        ):
            resolved = resolve_codex_binary("C:/custom/codex.exe")

        self.assertEqual(Path(resolved), Path("C:/custom/codex.exe"))

    def test_message_normalization_supports_str_messages_and_openai_dicts(self):
        normalized = normalize_input_messages(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "lookup_price",
                                "arguments": '{"ticker":"NVDA"}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_123", "content": "42"},
            ]
        )

        self.assertIsInstance(normalized[0], SystemMessage)
        self.assertIsInstance(normalized[1], HumanMessage)
        self.assertIsInstance(normalized[2], AIMessage)
        self.assertEqual(normalized[2].tool_calls[0]["name"], "lookup_price")
        self.assertEqual(normalized[2].tool_calls[0]["args"], {"ticker": "NVDA"})
        self.assertIsInstance(normalized[3], ToolMessage)

    def test_output_schema_construction_builds_exact_tool_branches(self):
        tool_schemas = normalize_tools_for_codex([lookup_price])
        schema = build_tool_response_schema(tool_schemas)
        required_schema = build_tool_response_schema(tool_schemas, allow_final=False)
        plain_schema = build_plain_response_schema()

        self.assertEqual(plain_schema["required"], ["answer"])
        self.assertEqual(schema["properties"]["mode"]["enum"], ["final", "tool_calls"])
        tool_branch = schema["properties"]["tool_calls"]["items"]
        self.assertEqual(tool_branch["properties"]["name"]["const"], "lookup_price")
        self.assertIn("arguments", tool_branch["required"])
        self.assertEqual(required_schema["properties"]["mode"]["const"], "tool_calls")

        generic_schema = build_tool_response_schema(
            normalize_tools_for_codex([lookup_price, lookup_volume])
        )
        generic_items = generic_schema["properties"]["tool_calls"]["items"]
        self.assertEqual(generic_items["properties"]["name"]["type"], "string")
        self.assertIn("enum", generic_items["properties"]["name"])
        self.assertEqual(generic_items["properties"]["arguments_json"]["type"], "string")

    def test_plain_final_response_parsing(self):
        session = FakeCodexSession(
            responses=['{"answer":"Final decision"}'],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        result = llm.invoke("Give me the final answer.")

        self.assertEqual(result.content, "Final decision")
        self.assertEqual(session.started, 1)

    def test_invoke_accepts_openai_style_message_dicts(self):
        session = FakeCodexSession(
            responses=['{"answer":"From dict transcript"}'],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        result = llm.invoke(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ]
        )

        self.assertEqual(result.content, "From dict transcript")
        self.assertIn("[System]\nsystem", session.invocations[0]["prompt"])
        self.assertIn("[Human]\nuser", session.invocations[0]["prompt"])

    def test_invoke_accepts_langchain_message_sequences(self):
        session = FakeCodexSession(
            responses=['{"answer":"From BaseMessage transcript"}'],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        result = llm.invoke(
            [
                SystemMessage(content="system"),
                HumanMessage(content="user"),
            ]
        )

        self.assertEqual(result.content, "From BaseMessage transcript")
        self.assertIn("[System]\nsystem", session.invocations[0]["prompt"])
        self.assertIn("[Human]\nuser", session.invocations[0]["prompt"])

    def test_tool_call_response_parsing_populates_ai_message_tool_calls(self):
        session = FakeCodexSession(
            responses=[
                '{"mode":"tool_calls","content":"Need data first","tool_calls":[{"name":"lookup_price","arguments":{"ticker":"NVDA"}}]}'
            ],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        prompt = ChatPromptTemplate.from_messages(
            [("system", "Use tools if needed."), ("human", "Analyze NVDA")]
        )
        result = (prompt | llm.bind_tools([lookup_price])).invoke({})

        self.assertEqual(result.content, "Need data first")
        self.assertEqual(result.tool_calls[0]["name"], "lookup_price")
        self.assertEqual(result.tool_calls[0]["args"], {"ticker": "NVDA"})
        self.assertRegex(result.tool_calls[0]["id"], r"^call_[0-9a-f]{32}$")

    def test_multi_tool_response_parses_arguments_json(self):
        session = FakeCodexSession(
            responses=[
                '{"mode":"tool_calls","content":"","tool_calls":[{"name":"lookup_price","arguments_json":"{\\"ticker\\":\\"NVDA\\"}"}]}'
            ],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        result = llm.bind_tools([lookup_price, lookup_volume]).invoke("Analyze NVDA")

        self.assertEqual(result.tool_calls[0]["name"], "lookup_price")
        self.assertEqual(result.tool_calls[0]["args"], {"ticker": "NVDA"})

    def test_bind_tools_honors_required_and_named_tool_choice(self):
        required_session = FakeCodexSession(
            responses=[
                '{"mode":"tool_calls","content":"Calling tool","tool_calls":[{"name":"lookup_price","arguments":{"ticker":"NVDA"}}]}'
            ],
        )
        required_llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: required_session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        required_result = required_llm.bind_tools([lookup_price], tool_choice="required").invoke(
            "Analyze NVDA"
        )
        self.assertTrue(required_result.tool_calls)
        self.assertEqual(
            required_session.invocations[0]["output_schema"]["properties"]["mode"]["const"],
            "tool_calls",
        )
        self.assertIn(
            "must respond with one or more tool calls",
            required_session.invocations[0]["prompt"].lower(),
        )

        named_session = FakeCodexSession(
            responses=[
                '{"mode":"tool_calls","content":"Calling named tool","tool_calls":[{"name":"lookup_price","arguments":{"ticker":"MSFT"}}]}'
            ],
        )
        named_llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: named_session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        named_result = named_llm.bind_tools(
            [lookup_price],
            tool_choice={"type": "function", "function": {"name": "lookup_price"}},
        ).invoke("Analyze MSFT")
        self.assertEqual(named_result.tool_calls[0]["name"], "lookup_price")
        tool_item = named_session.invocations[0]["output_schema"]["properties"]["tool_calls"]["items"]
        self.assertEqual(tool_item["properties"]["name"]["const"], "lookup_price")
        self.assertIn(
            "must call the tool named `lookup_price`",
            named_session.invocations[0]["prompt"].lower(),
        )

    def test_malformed_json_retries_and_surfaces_error_when_exhausted(self):
        session = FakeCodexSession(
            responses=["not json", '{"answer":"Recovered"}'],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            codex_max_retries=1,
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        result = llm.invoke("Recover after malformed JSON.")
        self.assertEqual(result.content, "Recovered")
        self.assertEqual(len(session.invocations), 2)
        self.assertIn(
            "previous response did not satisfy tradingagents validation",
            session.invocations[1]["prompt"].lower(),
        )

        failing_session = FakeCodexSession(
            responses=["still bad", "still bad again"],
        )
        failing_llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            codex_max_retries=1,
            session_factory=lambda **kwargs: failing_session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        with self.assertRaises(CodexStructuredOutputError):
            failing_llm.invoke("This should fail.")

    def test_runtime_errors_do_not_retry_as_json_failures(self):
        class FailingSession(FakeCodexSession):
            def invoke(self, **kwargs):
                raise RuntimeError("transport exploded")

        session = FailingSession()
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            codex_max_retries=2,
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        with self.assertRaisesRegex(RuntimeError, "transport exploded"):
            llm.invoke("fail fast")

    def test_provider_codex_smoke_covers_bind_tools_and_direct_invoke_paths(self):
        session = FakeCodexSession(
            responses=[
                '{"mode":"tool_calls","content":"Fetching market data","tool_calls":[{"name":"lookup_price","arguments":{"ticker":"NVDA"}}]}',
                '{"answer":"Rating: Buy\\nExecutive Summary: Add gradually."}',
            ],
        )
        llm = create_llm_client(
            "codex",
            "gpt-5.4",
            codex_binary="C:/fake/codex",
            codex_workspace_dir="C:/tmp/codex-workspace",
            session_factory=lambda **kwargs: session,
            preflight_runner=lambda **kwargs: None,
        ).get_llm()

        analyst_prompt = ChatPromptTemplate.from_messages(
            [("system", "Use tools when you need extra data."), ("human", "Analyze NVDA.")]
        )
        market_result = (analyst_prompt | llm.bind_tools([lookup_price])).invoke({})
        self.assertTrue(market_result.tool_calls)
        self.assertEqual(market_result.tool_calls[0]["name"], "lookup_price")

        decision = llm.invoke("Produce the final trade decision.")
        self.assertIn("Rating: Buy", decision.content)
        self.assertEqual(len(session.invocations), 2)

    def test_preflight_detects_missing_auth_and_missing_binary(self):
        valid_factory = lambda **kwargs: FakeCodexSession(
            account_payload={
                "account": {"type": "chatgpt", "email": "user@example.com"},
                "requiresOpenaiAuth": True,
            }
        )
        result = run_codex_preflight(
            codex_binary="C:\\fake\\codex.exe",
            model="gpt-5.4",
            request_timeout=10.0,
            workspace_dir="C:/tmp/codex-workspace",
            cleanup_threads=True,
            session_factory=valid_factory,
        )
        self.assertEqual(result.account["type"], "chatgpt")

        authless_factory = lambda **kwargs: FakeCodexSession(
            account_payload={"account": None, "requiresOpenaiAuth": True}
        )
        with self.assertRaises(CodexAppServerAuthError):
            run_codex_preflight(
                codex_binary="C:\\fake\\codex.exe",
                model="gpt-5.4",
                request_timeout=10.0,
                workspace_dir="C:/tmp/codex-workspace",
                cleanup_threads=True,
                session_factory=authless_factory,
            )

        with patch(
            "tradingagents.llm_clients.codex_preflight.resolve_codex_binary",
            return_value=None,
        ):
            with self.assertRaises(CodexAppServerBinaryError):
                run_codex_preflight(
                    codex_binary="definitely-missing-codex-binary",
                    model="gpt-5.4",
                    request_timeout=10.0,
                    workspace_dir="C:/tmp/codex-workspace",
                    cleanup_threads=True,
                )

    def test_preflight_uses_resolved_binary_path(self):
        captured = {}

        def factory(**kwargs):
            captured["codex_binary"] = kwargs["codex_binary"]
            return FakeCodexSession(**kwargs)

        with patch(
            "tradingagents.llm_clients.codex_preflight.resolve_codex_binary",
            return_value="C:/resolved/codex.exe",
        ):
            run_codex_preflight(
                codex_binary=None,
                model="gpt-5.4",
                request_timeout=10.0,
                workspace_dir="C:/tmp/codex-workspace",
                cleanup_threads=True,
                session_factory=factory,
            )

        self.assertEqual(captured["codex_binary"], "C:/resolved/codex.exe")


if __name__ == "__main__":
    unittest.main()
