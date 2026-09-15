"""Offline protocol tests, including the real graph with synthetic tool data."""

from __future__ import annotations

import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from cli.conversation import main
from tradingagents.agents.schemas import PortfolioDecision
from tradingagents.agents.utils.structured import invoke_structured_or_freetext
from tradingagents.conversation import (
    ConversationBridgeError,
    ConversationCancelledError,
    ConversationTimeoutError,
    pending_requests,
    publish_json,
    read_json,
    request_path,
    submit_response,
    validate_response,
)
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.conversation_client import ConversationChatModel


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Conversation tests must not contact an API")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def llm(tmp_path):
    return ConversationChatModel(
        directory=tmp_path, timeout_seconds=3, poll_seconds=0.005, cache=False
    )


def next_request(directory, future):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if requests := pending_requests(directory):
            return requests[0]
        if future.done():
            future.result()  # Surface a worker exception rather than hiding it in a timeout.
            pytest.fail("Invocation finished without the expected request")
        time.sleep(0.005)
    pytest.fail("No pending conversation request")


def answer(request, *, content="", name=None, args=None):
    response = {"request_id": request["request_id"], "content": content}
    if name:
        response["tool_calls"] = [{"id": "call_1", "name": name, "args": args or {}}]
    return response


def test_factory_needs_no_key_and_honors_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_CONVERSATION_TIMEOUT", "20")
    client = create_llm_client("CONVERSATION", "conversation", conversation_dir=tmp_path)
    assert client.validate_model()
    assert get_api_key_env("conversation") is None
    assert client.get_llm().directory == tmp_path
    assert client.get_llm().timeout_seconds == 20
    with pytest.raises(ValueError):
        create_llm_client("conversation", "conversation", conversation_timeout=0).get_llm()


def test_plain_response_cli_and_atomic_publication(llm, tmp_path, capsys):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, "테스트 요청", stop=["STOP"])
        request = next_request(tmp_path, future)
        assert request["messages"][0]["data"]["content"] == "테스트 요청"
        capsys.readouterr()
        assert main(["pending", "--directory", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out)[0]["request_id"] == request["request_id"]
        assert main(["show", request["request_id"], "--directory", str(tmp_path)]) == 0
        assert json.loads(capsys.readouterr().out) == request
        assert (
            main(
                [
                    "respond",
                    "--request-id",
                    request["request_id"],
                    "--text",
                    "현재 대화의 응답STOP 이후 생략",
                    "--directory",
                    str(tmp_path),
                ]
            )
            == 0
        )
        result = future.result(timeout=4)
    assert result.content == "현재 대화의 응답"
    assert result.response_metadata["provider"] == "conversation"
    folder = request_path(tmp_path, request["request_id"]).parent
    assert read_json(folder / "done.json")["status"] == "completed"
    assert not pending_requests(tmp_path)
    with pytest.raises(ValueError, match="completed"):
        submit_response(tmp_path, answer(request, content="second answer"))
    with pytest.raises(FileExistsError):
        publish_json(folder / "response.json", {"overwrite": True})
    assert read_json(folder / "response.json")["content"].startswith("현재 대화")
    assert (folder / "request.json").stat().st_mode & 0o077 == 0


@tool
def double(value: int) -> int:
    """Double an integer (an offline test tool)."""
    return value * 2


def test_tools_and_structured_output_roundtrip(llm, tmp_path):
    messages = [HumanMessage(content="Double 3")]
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.bind_tools([double]).invoke, messages)
        request = next_request(tmp_path, future)
        assert request["tools"][0]["function"]["name"] == "double"
        submit_response(tmp_path, answer(request, name="double", args={"value": 3}))
        call = future.result(timeout=4)
        executed = double.invoke(call.tool_calls[0])
        assert isinstance(executed, ToolMessage)
        assert executed.content == "6"
        messages += [call, executed]
        future = executor.submit(llm.with_structured_output(PortfolioDecision).invoke, messages)
        request = next_request(tmp_path, future)
        assert request["messages"][-1]["type"] == "tool"
        assert request["messages"][-1]["data"]["tool_call_id"] == "call_1"
        assert request["tool_choice"] == "any"
        submit_response(
            tmp_path,
            answer(
                request,
                name="PortfolioDecision",
                args={
                    "rating": "Hold",
                    "executive_summary": "Synthetic test only",
                    "investment_thesis": "No market evidence; not an investment recommendation",
                },
            ),
        )
        result = future.result(timeout=4)
    assert isinstance(result, PortfolioDecision)
    assert result.rating.value == "Hold"


@pytest.mark.parametrize(
    "bad",
    [
        {"request_id": "wrong", "content": "x"},
        {"content": ""},
        {"content": 123},
        {"content": "x", "unexpected": True},
        {"cancel": "true"},
        {"tool_calls": [{"id": "a", "name": "shell", "args": {}}]},
        {"tool_calls": [{"id": "a", "name": "double", "args": "not an object"}]},
        {"tool_calls": [{"id": "a", "name": "double", "args": {}}] * 2},
    ],
)
def test_invalid_response_rejected(bad):
    request = {"request_id": uuid4().hex, "tools": [{"function": {"name": "double"}}]}
    with pytest.raises(ValueError):
        validate_response(request, {"request_id": request["request_id"], **bad})


@pytest.mark.parametrize("request_id", ["../escape", "", "x" * 32, None, 123])
def test_invalid_request_path(tmp_path, request_id):
    with pytest.raises(ValueError):
        request_path(tmp_path, request_id)


def test_required_and_forbidden_tools():
    request = {"request_id": uuid4().hex, "tools": [{"function": {"name": "double"}}]}
    for choice in (
        "any",
        "required",
        "double",
        {"type": "function", "function": {"name": "double"}},
    ):
        request["tool_choice"] = choice
        with pytest.raises(ValueError, match="requires"):
            validate_response(request, answer(request, content="not a tool call"))
    request["tool_choice"] = "none"
    with pytest.raises(ValueError, match="does not allow"):
        validate_response(request, answer(request, name="double"))


def test_timeout_does_not_trigger_structured_fallback(tmp_path):
    model = ConversationChatModel(directory=tmp_path, timeout_seconds=0.03, poll_seconds=0.005)
    plain = MagicMock()
    with pytest.raises(ConversationTimeoutError):
        invoke_structured_or_freetext(
            model.with_structured_output(PortfolioDecision), plain, "test", str, "test agent"
        )
    plain.invoke.assert_not_called()
    paths = list(tmp_path.glob("*/done.json"))
    assert len(paths) == 1
    assert read_json(paths[0])["status"] == "timed_out"
    assert not pending_requests(tmp_path)
    request = read_json(paths[0].with_name("request.json"))
    with pytest.raises(ValueError, match="expired"):
        submit_response(tmp_path, answer(request, content="too late"))


def test_cancel_stops_without_fallback(llm, tmp_path):
    plain = MagicMock()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            invoke_structured_or_freetext,
            llm.with_structured_output(PortfolioDecision),
            plain,
            "test",
            str,
            "test agent",
        )
        request = next_request(tmp_path, future)
        assert main(["cancel", request["request_id"], "--directory", str(tmp_path)]) == 0
        with pytest.raises(ConversationCancelledError):
            future.result(timeout=4)
    plain.invoke.assert_not_called()
    assert (
        read_json(request_path(tmp_path, request["request_id"]).with_name("done.json"))["status"]
        == "cancelled"
    )


def test_malformed_direct_write_aborts_run(llm, tmp_path):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(llm.invoke, "test")
        request = next_request(tmp_path, future)
        publish_json(
            request_path(tmp_path, request["request_id"]).with_name("response.json"),
            {"request_id": "wrong", "content": "bad answer"},
        )
        with pytest.raises(ConversationBridgeError):
            future.result(timeout=4)
    assert not pending_requests(tmp_path)


def test_concurrent_requests_are_correlated(llm, tmp_path):
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(llm.invoke, prompt) for prompt in ("first", "second")]
        deadline = time.monotonic() + 2
        while len(requests := pending_requests(tmp_path)) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert len(requests) == 2
        for request in reversed(requests):
            prompt = request["messages"][0]["data"]["content"]
            submit_response(tmp_path, answer(request, content=f"answer to {prompt}"))
        assert [future.result(timeout=4).content for future in futures] == [
            "answer to first",
            "answer to second",
        ]


def test_existing_graph_reaches_final_rating_with_file_answers(llm, tmp_path):
    @tool("get_stock_data")
    def synthetic_prices(symbol: str, start_date: str, end_date: str) -> str:
        """Synthetic prices for a protocol test; never live market data."""
        return "SYNTHETIC FIXTURE: price=100; no live market evidence"

    graph = GraphSetup(
        llm,
        llm,
        {"market": ToolNode([synthetic_prices])},
        ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
    )
    workflow = graph.setup_graph(["market"]).compile()
    state = Propagator().create_initial_state("TEST", "2026-09-01")
    schemas = {
        "Research Manager": (
            "ResearchPlan",
            {
                "recommendation": "Hold",
                "rationale": "Synthetic fixture only",
                "strategic_actions": "No trade; protocol test",
            },
        ),
        "Trader": ("TraderProposal", {"action": "Hold", "reasoning": "Synthetic fixture only"}),
        "Portfolio Manager": (
            "PortfolioDecision",
            {
                "rating": "Hold",
                "executive_summary": "Synthetic fixture only",
                "investment_thesis": "No market recommendation; protocol test",
            },
        ),
    }
    seen = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(workflow.invoke, state, {"recursion_limit": 40})
        for _ in range(10):
            request = next_request(tmp_path, future)
            agent = request["agent"]
            seen.append(agent)
            if len(seen) == 1:
                response = answer(
                    request,
                    name="get_stock_data",
                    args={
                        "symbol": "TEST",
                        "start_date": "2026-08-01",
                        "end_date": "2026-09-01",
                    },
                )
            elif agent in schemas:
                name, args = schemas[agent]
                response = answer(request, name=name, args=args)
            else:
                if agent == "Market Analyst":
                    assert "SYNTHETIC FIXTURE" in request["messages"][-1]["data"]["content"]
                response = answer(
                    request, content="Synthetic fixture only; no investment recommendation."
                )
            submit_response(tmp_path, response)
        final = future.result(timeout=4)
    assert seen == [
        "Market Analyst",
        "Market Analyst",
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Conservative Analyst",
        "Neutral Analyst",
        "Portfolio Manager",
    ]
    assert SignalProcessor().process_signal(final["final_trade_decision"]) == "Hold"
    assert not pending_requests(tmp_path)
