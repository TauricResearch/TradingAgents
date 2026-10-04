"""Production ChatGPT factory/adapter/graph proof with offline HTTP and vendors.

Run the offline QA surfaces with:

    python -m tests.test_chatgpt_provider_flow --scenario graph --evidence-dir PATH
    python -m tests.test_chatgpt_provider_flow --scenario graph-quota --evidence-dir PATH
    python -m tests.test_chatgpt_provider_flow --scenario live --evidence-dir PATH

The live scenario is gated before it reads the app-owned credential store.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pandas as pd
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from openai._base_client import BaseClient as OpenAIBaseClient

from tradingagents.agents import context
from tradingagents.agents.analysts import sentiment_analyst
from tradingagents.dataflows import router
from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph
from tradingagents.graph.checkpointer import checkpoint_step
from tradingagents.llm_clients import chatgpt_auth
from tradingagents.llm_clients.chatgpt_auth import RegistrationSession
from tradingagents.llm_clients.chatgpt_client import (
    TOOL_NAMESPACE,
    ChatGPTResponses,
    ChatGPTResponsesError,
    ChatGPTSubscriptionError,
)
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.model_catalog import get_chatgpt_model_options

TRADE_DATE = "2026-01-09"
ACCOUNT_ID = "oaiapp_task7_fixture"
FIXTURE_ACCESS = "fixture-access-before-refresh"
ROTATED_ACCESS = "fixture-access-after-refresh"
ROTATED_REFRESH = "fixture-refresh-after-refresh"
LIVE_AUTHORIZATION_ENV = "TRADINGAGENTS_CHATGPT_LIVE_QA_AUTHORIZED"
LIVE_PUBLIC_REQUEST_LIMIT = 20
LIVE_FAILURE_STAGES = frozenset(
    {
        "selected_model_validation",
        "factory_construction",
        "llm_initialization",
        "tool_binding",
        "text_invocation",
        "tool_invocation",
        "tool_call_validation",
        "tool_call_missing",
        "tool_call_multiple",
        "tool_call_name_mismatch",
        "local_tool_execution",
        "tool_followup",
        "graph_propagation",
    }
)
LIVE_FAILURE_KINDS = frozenset(
    {
        "terminal_subscription_error",
        "responses_contract_error",
        "timeout",
        "transport_error",
        "value_error",
        "type_error",
        "runtime_error",
        "os_error",
        "other_error",
    }
)
LIVE_EXCEPTION_CLASSES = {
    ChatGPTSubscriptionError: "ChatGPTSubscriptionError",
    ChatGPTResponsesError: "ChatGPTResponsesError",
    ValueError: "ValueError",
    TypeError: "TypeError",
    RuntimeError: "RuntimeError",
    TimeoutError: "TimeoutError",
    OSError: "OSError",
}


class _WarmupSession:
    def access_token(self) -> str:
        return FIXTURE_ACCESS


TEXT = "Report.\n\n**Rating**: Overweight\n\nFINAL TRANSACTION PROPOSAL: **BUY**"
REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)
TOOL_METHODS = {
    "get_stock_data",
    "get_indicators",
    "get_verified_market_snapshot",
    "get_news",
    "get_global_news",
    "get_macro_indicators",
    "get_prediction_markets",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_insider_transactions",
    "ohlcv",
}
SCHEMA_ARGS: dict[str, dict[str, Any]] = {
    "ResearchPlan": {
        "recommendation": "Overweight",
        "rationale": "The evidence favors the bull case.",
        "strategic_actions": "Build the position gradually.",
    },
    "TraderProposal": {
        "action": "Buy",
        "reasoning": "The plan and current reports support a measured entry.",
        "entry_price": 100.5,
        "stop_loss": 96.0,
        "position_sizing": "5% of portfolio",
    },
    "PortfolioDecision": {
        "rating": "Overweight",
        "executive_summary": "Build the position gradually and review after earnings.",
        "investment_thesis": "The synthetic analyst evidence supports the bull case.",
        "price_target": 112.0,
        "time_horizon": "3-6 months",
    },
    "SentimentReport": {
        "overall_band": "Neutral",
        "overall_score": 5.0,
        "confidence": "medium",
        "narrative": "Synthetic offline sources are mixed and provide limited signal.",
    },
}


def _sse(events: list[dict[str, Any]]) -> bytes:
    return b"".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode() for event in events
    )


def _completed(output: list[dict[str, Any]], response_id: str, model: str) -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": 0,
        "model": model,
        "status": "completed",
        "output": output,
        "store": False,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


def _text_item(text: str, item_id: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _schema_and_function_names(body: dict[str, Any]) -> list[str]:
    names = []
    for group in body.get("tools", []):
        tools = group.get("tools", []) if group.get("type") == "namespace" else [group]
        for spec in tools:
            if isinstance(spec.get("name"), str):
                names.append(spec["name"])
    return names


def _property_value(name: str, schema: dict[str, Any]) -> Any:
    alternatives = schema.get("anyOf") or schema.get("oneOf")
    if alternatives:
        schema = next(
            (choice for choice in alternatives if choice.get("type") != "null"),
            alternatives[0],
        )
    if isinstance(schema.get("enum"), list):
        values = schema["enum"]
        preferred = {
            "indicator": "rsi",
            "rating": "Overweight",
            "recommendation": "Overweight",
            "action": "Buy",
            "overall_band": "Neutral",
            "confidence": "medium",
        }.get(name)
        return preferred if preferred in values else values[0]
    value_type = schema.get("type")
    if value_type == "array":
        return [_property_value(name, schema.get("items", {}))]
    if value_type == "object":
        properties = schema.get("properties", {})
        return {
            key: _property_value(key, properties[key])
            for key in schema.get("required", [])
            if key in properties
        }
    if value_type in {"number", "integer"}:
        minimum = schema.get("minimum", schema.get("exclusiveMinimum", 1))
        return max(minimum, 1) if value_type == "integer" else max(float(minimum), 1.0)
    if value_type == "boolean":
        return False
    lowered = name.lower()
    if "ticker" in lowered or "symbol" in lowered:
        return "NVDA"
    if lowered in {"start_date", "from_date", "start"}:
        return "2026-01-02"
    if "date" in lowered or lowered in {"end", "to_date"}:
        return TRADE_DATE
    if "indicator" in lowered:
        return "rsi"
    if "topic" in lowered or "query" in lowered:
        return "Federal Reserve interest rates"
    if "period" in lowered or "interval" in lowered or "frequency" in lowered:
        return "quarterly"
    return "fixture"


def _tool_arguments(spec: dict[str, Any]) -> dict[str, Any]:
    parameters = spec.get("parameters", {})
    properties = parameters.get("properties", {})
    return {name: _property_value(name, schema) for name, schema in properties.items()}


class _FixtureStream(httpx.SyncByteStream):
    def __init__(
        self,
        fixture: _ProviderFixture,
        events: list[dict[str, Any]],
        *,
        hold_for_quota: bool = False,
    ) -> None:
        self.fixture = fixture
        self.events = events
        self.hold_for_quota = hold_for_quota
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for event in self.events:
            yield (f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
        if self.hold_for_quota and not self.fixture.quota_observed.wait(10.0):
            raise TimeoutError("quota observer did not release in-flight fixture streams")

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.fixture._response_closed()


class _ProviderFixture:
    """Strict MockTransport for the public model list, OAuth refresh, and Responses API."""

    def __init__(self, *, scenario: str) -> None:
        self.scenario = scenario
        self.requests: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.refresh_count = 0
        self.refresh_submitted = threading.Event()
        self.allow_refresh = threading.Event()
        self.allow_refresh.set()
        self.first_batch_ready = threading.Event()
        self.quota_observed = threading.Event()
        self.in_flight_at_quota: int | None = None
        self.requests_after_quota = 0
        self.active_responses = 0
        self.open_streams = 0
        self.fallback_pending = False
        self.fallback_used = False
        self.portfolio_failure_used = False
        self.malformed_used = False
        self.request_count = 0
        self.lock = threading.Lock()
        self.transport = httpx.MockTransport(self.handle)
        self.responses_client = httpx.Client(transport=self.transport, timeout=15.0)

    def _response_closed(self) -> None:
        with self.lock:
            self.active_responses -= 1
            self.open_streams -= 1

    def _record_request(self, request: httpx.Request, body: dict[str, Any] | None = None) -> None:
        summary: dict[str, Any] = {
            "method": request.method,
            "host": request.url.host,
            "path": request.url.path,
            "authorization_present": "authorization" in request.headers,
            "authorization_scheme": (
                request.headers.get("authorization", "").split(" ", 1)[0] or None
            ),
            "authorization_matches_rotated_fixture": request.headers.get("authorization")
            == f"Bearer {ROTATED_ACCESS}",
        }
        if body is not None:
            summary.update(
                {
                    "model": body.get("model"),
                    "input_roles": [
                        item.get("role")
                        for item in body.get("input", [])
                        if item.get("role") is not None
                    ],
                    "input_types": [
                        item.get("type") or item.get("role") for item in body.get("input", [])
                    ],
                    "tool_outputs": [
                        {
                            "name": item.get("name"),
                            "output": str(item.get("output", ""))[:240],
                        }
                        for item in body.get("input", [])
                        if item.get("type") == "function_call_output"
                    ],
                    "tools": _schema_and_function_names(body),
                    "tool_choice": body.get("tool_choice"),
                    "store": body.get("store"),
                    "stream": body.get("stream"),
                    "body_sha256": hashlib.sha256(
                        json.dumps(body, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
        with self.lock:
            self.requests.append(summary)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "api.openai.com" and request.url.host != "auth.openai.com":
            raise AssertionError(f"unexpected fixture host: {request.url.host}")
        if request.method == "GET" and request.url.path == "/v1/models":
            self._record_request(request)
            if request.headers.get("authorization") not in {
                f"Bearer {FIXTURE_ACCESS}",
                f"Bearer {ROTATED_ACCESS}",
            }:
                return httpx.Response(401)
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "visibility": "list",
                            "display_name": "Fixture Quick",
                            "slug": "quick-fixture",
                        },
                        {
                            "visibility": "list",
                            "display_name": "Fixture Deep",
                            "slug": "deep-fixture",
                        },
                        {
                            "visibility": "hide",
                            "display_name": "Hidden Fixture",
                            "slug": "hidden-fixture",
                        },
                    ]
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            "/.well-known/openid-configuration"
        ):
            self._record_request(request)
            return httpx.Response(
                200,
                json={"token_endpoint": "https://auth.openai.com/api/accounts/oauth/token"},
            )
        if request.method == "POST" and request.url.path.endswith("/oauth/token"):
            self._record_request(request)
            self.refresh_count += 1
            self.refresh_submitted.set()
            if not self.allow_refresh.wait(10.0):
                return httpx.Response(504)
            return httpx.Response(
                200,
                json={
                    "access_token": ROTATED_ACCESS,
                    "refresh_token": ROTATED_REFRESH,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        if request.method == "POST" and request.url.path == "/v1/responses":
            return self._responses(request)
        raise AssertionError(f"unexpected fixture request: {request.method} {request.url}")

    def _responses(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        self._record_request(request, body)
        if not request.headers.get("authorization", "").startswith("Bearer "):
            return httpx.Response(401)
        with self.lock:
            index = self.request_count
            self.request_count += 1
            if self.quota_observed.is_set():
                self.requests_after_quota += 1
            self.active_responses += 1
            self.open_streams += 1

        names = _schema_and_function_names(body)
        schema_name = next((name for name in names if name in SCHEMA_ARGS), None)
        if self.scenario == "quota" and index < 4:
            if index == 3:
                self.first_batch_ready.set()
            if not self.first_batch_ready.wait(10.0):
                self._response_closed()
                raise TimeoutError("parallel analyst request barrier was not reached")
            if index == 0:
                events = [
                    {"type": "response.output_text.delta", "delta": "provisional"},
                    {
                        "type": "response.failed",
                        "response": {
                            "status": "failed",
                            "error": {
                                "code": "subscription_sharing_usage_limit_exceeded",
                                "message": "Fixture usage limit.",
                            },
                        },
                    },
                ]
                self.events.extend(events)
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=_FixtureStream(self, events),
                )
            return self._completed_response(body, index, schema_name, hold_for_quota=True)

        if self.scenario == "malformed" and not self.malformed_used and body.get("tools"):
            self.malformed_used = True
            call_name = names[0]
            output = [
                {
                    "id": "fc_malformed",
                    "type": "function_call",
                    "call_id": "call_malformed",
                    "name": call_name,
                    "namespace": TOOL_NAMESPACE,
                    "arguments": "[not-an-object]",
                    "status": "completed",
                }
            ]
            return self._stream_response(
                [_completed(output, f"resp_{index}", body["model"])],
                index,
            )

        if (
            self.scenario == "checkpoint"
            and schema_name == "PortfolioDecision"
            and not self.portfolio_failure_used
        ):
            self.portfolio_failure_used = True
            events = [
                {
                    "type": "response.failed",
                    "response": {
                        "status": "failed",
                        "error": {
                            "code": "server_error",
                            "message": "One-shot fixture interruption before final decision.",
                        },
                    },
                }
            ]
            self.events.extend(events)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_FixtureStream(self, events),
            )

        if schema_name == "ResearchPlan" and not self.fallback_used:
            self.fallback_used = True
            self.fallback_pending = True
            return self._completed_response(
                body,
                index,
                None,
                text=(
                    "**Recommendation**: Overweight\n\n"
                    "**Rationale**: The synthetic debate favors the bull case.\n\n"
                    "**Strategic Actions**: Build the position gradually."
                ),
            )
        if self.fallback_pending and not body.get("tools"):
            self.fallback_pending = False
            text = (
                "**Recommendation**: Overweight\n\n"
                "**Rationale**: The synthetic free-text recovery favors the bull case.\n\n"
                "**Strategic Actions**: Build the position gradually."
            )
            return self._completed_response(body, index, None, text=text)
        return self._completed_response(body, index, schema_name)

    def _completed_response(
        self,
        body: dict[str, Any],
        index: int,
        schema_name: str | None,
        *,
        text: str | None = None,
        hold_for_quota: bool = False,
    ) -> httpx.Response:
        specs = []
        for group in body.get("tools", []):
            specs.extend(group.get("tools", []) if group.get("type") == "namespace" else [group])
        if text is not None:
            output = [_text_item(text, f"msg_{index}")]
        elif schema_name is not None:
            args = SCHEMA_ARGS[schema_name]
            output = [
                {
                    "id": f"fc_{index}",
                    "type": "function_call",
                    "call_id": f"call_{index}",
                    "name": schema_name,
                    "namespace": TOOL_NAMESPACE,
                    "arguments": json.dumps(args),
                    "status": "completed",
                }
            ]
        elif specs and not any(
            item.get("type") == "function_call_output" for item in body.get("input", [])
        ):
            output = [
                {
                    "id": f"fc_{index}_{i}",
                    "type": "function_call",
                    "call_id": f"call_{index}_{i}",
                    "name": spec["name"],
                    "namespace": TOOL_NAMESPACE,
                    "arguments": json.dumps(_tool_arguments(spec)),
                    "status": "completed",
                }
                for i, spec in enumerate(specs)
                if spec.get("type") == "function"
            ]
        else:
            output = [_text_item(text or TEXT, f"msg_{index}")]
        return self._stream_response(
            [_completed(output, f"resp_{index}", body["model"])],
            index,
            hold_for_quota=hold_for_quota,
        )

    def _stream_response(
        self,
        events: list[dict[str, Any]],
        index: int,
        *,
        hold_for_quota: bool = False,
    ) -> httpx.Response:
        normalized: list[dict[str, Any]] = []
        for event in events:
            if event.get("object") == "response":
                normalized.append({"type": "response.completed", "response": event})
            else:
                normalized.append(event)
        with self.lock:
            self.events.extend(normalized)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_FixtureStream(self, normalized, hold_for_quota=hold_for_quota),
        )

    def close(self) -> None:
        self.allow_refresh.set()
        self.quota_observed.set()
        self.responses_client.close()


def _seed_account(path: Path) -> None:
    state = chatgpt_auth._new_auth()
    state["accounts"][ACCOUNT_ID] = {
        "client_id": ACCOUNT_ID,
        "issuer": "https://auth.openai.com",
        "subject": "task7-fixture-subject",
        "inference_enabled": True,
        "email": None,
        "ext_agent_host_id": state["ext_agent_host_id"],
        "access_token": FIXTURE_ACCESS,
        "refresh_token": "fixture-refresh-before-rotation",
        "id_token": None,
        "scopes": ["openid", chatgpt_auth.PLAN_SCOPE],
        "expires_at": 4_102_444_800,
        "rotation_pending": False,
        "requires_reauthorization": False,
    }
    state["selected_client_id"] = ACCOUNT_ID
    with chatgpt_auth._locked(path):
        chatgpt_auth._save(path, state)


def _expire_fixture_account(path: Path) -> None:
    with chatgpt_auth._locked(path):
        state = chatgpt_auth._load_locked(path)
        state["accounts"][ACCOUNT_ID]["expires_at"] = 0.0
        chatgpt_auth._save(path, state)


def _offline_vendors(
    monkeypatch: pytest.MonkeyPatch,
    called: set[str],
) -> None:
    for method, vendors in router.VENDOR_METHODS.items():
        for vendor in vendors:
            monkeypatch.setitem(
                vendors,
                vendor,
                lambda *args, _method=method, **kwargs: (
                    called.add(_method) or f"offline {_method} data"
                ),
            )
    prices = pd.DataFrame(
        {
            "Date": pd.bdate_range(end=TRADE_DATE, periods=60),
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.5,
            "Volume": 1_000_000,
        }
    )

    def load_prices(*args: Any, **kwargs: Any) -> pd.DataFrame:
        called.add("ohlcv")
        called.add("get_verified_market_snapshot")
        return prices.copy()

    monkeypatch.setattr(snapshot, "load_ohlcv", load_prices)
    monkeypatch.setattr(
        sentiment_analyst,
        "fetch_stocktwits_messages",
        lambda *args, **kwargs: "offline StockTwits messages",
    )
    monkeypatch.setattr(
        sentiment_analyst,
        "fetch_reddit_posts",
        lambda *args, **kwargs: "offline Reddit posts",
    )
    monkeypatch.setattr(
        yahoo_market.yf,
        "Ticker",
        lambda symbol: type("FixtureTicker", (), {"info": {"longName": "Fixture Corp"}})(),
    )
    context._identity.cache_clear()


def _install_factory_transport(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _ProviderFixture,
    auth_path: Path,
) -> tuple[list[RegistrationSession], list[dict[str, Any]]]:
    original_pinned_session = chatgpt_auth.pinned_session

    def pinned_session(*, client_id: str | None = None) -> RegistrationSession:
        return original_pinned_session(
            store_path=auth_path,
            client_id=client_id,
            http_transport=fixture.transport,
        )

    monkeypatch.setattr(chatgpt_auth, "pinned_session", pinned_session)
    original_factory = trading_graph.create_llm_client
    sessions: list[RegistrationSession] = []
    factory_models: list[dict[str, Any]] = []

    def create_fixture_client(*args: Any, **kwargs: Any) -> Any:
        sessions.append(kwargs["auth_session"])
        factory_models.append(
            {
                "provider": args[0] if args else kwargs.get("provider"),
                "model": args[1] if len(args) > 1 else kwargs.get("model"),
            }
        )
        kwargs["http_client"] = fixture.responses_client
        return original_factory(*args, **kwargs)

    monkeypatch.setattr(trading_graph, "create_llm_client", create_fixture_client)
    return sessions, factory_models


def _graph_config(root: Path, *, checkpoint_enabled: bool) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "results_dir": str(root / "results"),
            "data_cache_dir": str(root / "cache"),
            "memory_log_path": str(root / "memory.md"),
            "llm_provider": "chatgpt",
            "chatgpt_account_id": ACCOUNT_ID,
            "quick_think_llm": "quick-fixture",
            "deep_think_llm": "deep-fixture",
            "openai_reasoning_effort": "medium",
            "checkpoint_enabled": checkpoint_enabled,
            "max_tool_rounds": 3,
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
        }
    )
    return config


def _observe_quota_after_admission(
    monkeypatch: pytest.MonkeyPatch,
    fixture: _ProviderFixture,
) -> None:
    from tradingagents.llm_clients import chatgpt_client

    original_stream = chatgpt_client.ChatGPTResponses._stream

    def observed_stream(model: Any, *args: Any, **kwargs: Any) -> Iterator[Any]:
        try:
            yield from original_stream(model, *args, **kwargs)
        except ChatGPTSubscriptionError as error:
            if error.status_code == 429 and not fixture.quota_observed.is_set():
                with fixture.lock:
                    fixture.in_flight_at_quota = fixture.active_responses
                fixture.quota_observed.set()
            raise

    monkeypatch.setattr(chatgpt_client.ChatGPTResponses, "_stream", observed_stream)


def _request_inventory(fixture: _ProviderFixture) -> dict[str, Any]:
    response_requests = [
        request for request in fixture.requests if request["path"] == "/v1/responses"
    ]
    return {
        "request_count": len(fixture.requests),
        "response_request_count": len(response_requests),
        "models_requests": sum(request["path"] == "/v1/models" for request in fixture.requests),
        "refresh_requests": fixture.refresh_count,
        "responses_only_public_route": all(
            request["host"] == "api.openai.com"
            and request["path"] in {"/v1/models", "/v1/responses"}
            for request in fixture.requests
            if request["host"] == "api.openai.com"
        ),
        "authorization_values_redacted": all(
            "authorization" not in request for request in fixture.requests
        ),
        "response_requests": response_requests,
    }


def _warm_response_decoder() -> None:
    """Parse one Responses stream before the parallel analyst burst.

    The OpenAI SDK builds its response-event decoder on first use. When the
    four analysts issue that first parse together, function-call output can be
    dropped and the affected report stays empty. A serial text response on a
    throwaway fixture initializes the decoder without touching scenario counts.
    """
    fixture = _ProviderFixture(scenario="decoder-warmup")
    try:
        model = ChatGPTResponses(
            model="quick-fixture",
            auth_session=_WarmupSession(),
            http_client=fixture.responses_client,
        )
        message = model.invoke("Warm the response decoder before parallel analyst calls.")
        if not str(message.content).strip():
            raise RuntimeError("response decoder warmup returned empty text")
    finally:
        fixture.close()


def _execute_graph(root: Path, *, scenario: str) -> tuple[dict[str, Any], _ProviderFixture]:
    _warm_response_decoder()
    root.mkdir(parents=True, exist_ok=True)
    auth_path = root / "home" / ".tradingagents" / "chatgpt" / "auth.json"
    _seed_account(auth_path)
    fixture = _ProviderFixture(scenario=scenario)
    monkeypatch = pytest.MonkeyPatch()
    called: set[str] = set()
    _offline_vendors(monkeypatch, called)
    sessions, factory_models = _install_factory_transport(monkeypatch, fixture, auth_path)
    if scenario == "quota":
        _observe_quota_after_admission(monkeypatch, fixture)
    graph = trading_graph.TradingAgentsGraph(
        selected_analysts=("market", "social", "news", "fundamentals"),
        config=_graph_config(root, checkpoint_enabled=scenario == "checkpoint"),
    )
    assert len(factory_models) == 2
    assert sessions[0] is sessions[1] is graph._chatgpt_registration_session
    catalog_options = get_chatgpt_model_options(graph._chatgpt_registration_session)
    assert [slug for _, slug in catalog_options] == ["quick-fixture", "deep-fixture"]
    if scenario in {"checkpoint", "quota"}:
        _expire_fixture_account(auth_path)

    refresh_probe: dict[str, Any] = {}
    original_access_token = RegistrationSession.access_token
    access_started = 0
    access_lock = threading.Lock()
    all_analyst_tokens_started = threading.Event()

    def observed_access_token(session: RegistrationSession) -> str:
        nonlocal access_started
        with access_lock:
            access_started += 1
            if access_started >= 4:
                all_analyst_tokens_started.set()
        return original_access_token(session)

    if scenario in {"checkpoint", "quota"}:
        monkeypatch.setattr(RegistrationSession, "access_token", observed_access_token)

    try:
        if scenario == "quota":
            try:
                graph.propagate("NVDA", TRADE_DATE)
            except ChatGPTSubscriptionError as error:
                quota_error = {
                    "type": type(error).__name__,
                    "message": str(error),
                    "status_code": error.status_code,
                    "code": error.code,
                }
            else:
                quota_error = None
            result = {
                "scenario": "graph-quota",
                "quota_error": quota_error,
                "final_rating": None,
                "successful_decision_entries": len(graph.memory_log.load_entries()),
                "saved_state_logs": list(
                    (root / "results").glob("NVDA/TradingAgentsStrategy_logs/*.json")
                ),
                "quota_observed": fixture.quota_observed.is_set(),
                "in_flight_at_quota_observation": fixture.in_flight_at_quota,
                "new_requests_after_quota_observation": fixture.requests_after_quota,
                "parallel_analyst_token_calls_started": access_started,
                "tools_executed": sorted(called),
                "requests": _request_inventory(fixture),
                "request_records": list(fixture.requests),
                "event_records": list(fixture.events),
            }
            result["status"] = (
                "pass"
                if (
                    quota_error is not None
                    and quota_error["type"] == "ChatGPTSubscriptionError"
                    and quota_error["status_code"] == 429
                    and fixture.quota_observed.is_set()
                    and fixture.in_flight_at_quota is not None
                    and fixture.in_flight_at_quota >= 1
                    and fixture.requests_after_quota == 0
                    and not result["successful_decision_entries"]
                    and not result["saved_state_logs"]
                )
                else "fail"
            )
            return result, fixture

        if scenario == "checkpoint":
            with ThreadPoolExecutor(max_workers=1) as pool:
                run = pool.submit(graph.propagate, "NVDA", TRADE_DATE)
                try:
                    if not fixture.refresh_submitted.wait(10.0):
                        raise AssertionError("parallel analyst call did not submit refresh")
                    if not all_analyst_tokens_started.wait(10.0):
                        raise AssertionError("all parallel analyst calls did not reach token gate")
                    refresh_probe["parallel_token_calls_before_release"] = access_started
                    refresh_probe["refresh_count_before_release"] = fixture.refresh_count
                finally:
                    fixture.allow_refresh.set()
                try:
                    run.result(timeout=60.0)
                except ChatGPTSubscriptionError as error:
                    if "One-shot fixture interruption" not in str(error):
                        raise
            signature = graph._run_signature("stock")
            step_before_resume = checkpoint_step(
                graph.config["data_cache_dir"], "NVDA", TRADE_DATE, signature
            )
            if step_before_resume is None:
                raise AssertionError("provider interruption did not leave a graph checkpoint")
            before_resume = len(
                [request for request in fixture.requests if request["path"] == "/v1/responses"]
            )
            state, rating = graph.propagate("NVDA", TRADE_DATE)
            after_resume = len(
                [request for request in fixture.requests if request["path"] == "/v1/responses"]
            )
            step_after_resume = checkpoint_step(
                graph.config["data_cache_dir"], "NVDA", TRADE_DATE, signature
            )
            state_log_path = (
                root
                / "results"
                / "NVDA"
                / "TradingAgentsStrategy_logs"
                / f"full_states_log_{TRADE_DATE}.json"
            )
            saved_state = json.loads(state_log_path.read_text(encoding="utf-8"))
            entries = graph.memory_log.load_entries()
            structured_and_text = {
                "sentiment_report_present": bool(state["sentiment_report"].strip()),
                "trader_schema_parsed": "**Entry Price**: 100.5" in state["trader_investment_plan"],
                "portfolio_schema_parsed": "**Executive Summary**" in state["final_trade_decision"],
                "research_manager_free_text_fallback": fixture.fallback_used
                and "free-text recovery" in state["investment_plan"],
            }
            debate_decisions = {
                "bull_debate": bool(state["investment_debate_state"]["bull_history"]),
                "bear_debate": bool(state["investment_debate_state"]["bear_history"]),
                "aggressive_risk": bool(state["risk_debate_state"]["aggressive_history"]),
                "conservative_risk": bool(state["risk_debate_state"]["conservative_history"]),
                "neutral_risk": bool(state["risk_debate_state"]["neutral_history"]),
                "research_manager": bool(state["investment_plan"]),
                "trader": bool(state["trader_investment_plan"]),
                "portfolio_manager": bool(state["final_trade_decision"]),
            }
            request_inventory = _request_inventory(fixture)
            result = {
                "scenario": "graph",
                "status": "pass",
                "signal": rating,
                "saved_rating": saved_state["final_rating"],
                "memory_log_ratings": [entry["rating"] for entry in entries],
                "reports": {key: bool(state.get(key, "").strip()) for key in REPORT_KEYS},
                "local_tools": sorted(called),
                "structured_and_fallback": structured_and_text,
                "debate_and_manager_decisions": debate_decisions,
                "report_details": {
                    "reports": {key: state[key] for key in REPORT_KEYS},
                    "investment_debate": state["investment_debate_state"],
                    "risk_debate": state["risk_debate_state"],
                    "saved_rating": saved_state["final_rating"],
                    "memory_log_ratings": [entry["rating"] for entry in entries],
                },
                "factory_calls": factory_models,
                "same_pinned_registration_for_factories": len(sessions) == 2
                and sessions[0] is sessions[1],
                "parallel_refresh": {
                    **refresh_probe,
                    "total_refresh_requests": fixture.refresh_count,
                    "all_response_authorization_uses_rotated_token": all(
                        request["authorization_matches_rotated_fixture"]
                        for request in request_inventory["response_requests"]
                    ),
                },
                "checkpoint": {
                    "provider_interruption_observed": fixture.portfolio_failure_used,
                    "step_before_resume": step_before_resume,
                    "response_requests_before_resume": before_resume,
                    "response_requests_after_resume": after_resume,
                    "resume_added_only_portfolio_retry": after_resume - before_resume == 1,
                    "checkpoint_cleared_after_success": step_after_resume is None,
                },
                "request_inventory": {
                    key: value
                    for key, value in request_inventory.items()
                    if key != "response_requests"
                },
                "request_records": list(fixture.requests),
                "event_records": list(fixture.events),
            }
            if not all(result["reports"].values()):
                result["status"] = "fail"
            if called != TOOL_METHODS:
                result["status"] = "fail"
            if not all(structured_and_text.values()) or not all(debate_decisions.values()):
                result["status"] = "fail"
            if (
                rating != "Overweight"
                or saved_state["final_rating"] != "Overweight"
                or [entry["rating"] for entry in entries] != ["Overweight"]
                or fixture.refresh_count != 1
                or refresh_probe.get("parallel_token_calls_before_release", 0) < 4
                or not result["checkpoint"]["provider_interruption_observed"]
                or not result["checkpoint"]["resume_added_only_portfolio_retry"]
                or not result["checkpoint"]["checkpoint_cleared_after_success"]
            ):
                result["status"] = "fail"
            return result, fixture

        raise ValueError(f"unsupported offline scenario {scenario}")
    finally:
        fixture.allow_refresh.set()
        fixture.quota_observed.set()
        fixture.close()
        monkeypatch.undo()
        context._identity.cache_clear()


@tool
def _fixture_lookup(ticker: str) -> str:
    """Look up one fixture price."""
    return f"{ticker}:100.5"


def _run_malformed_probe(root: Path) -> dict[str, Any]:
    auth_path = root / "malformed-home" / "auth.json"
    _seed_account(auth_path)
    fixture = _ProviderFixture(scenario="malformed")
    session = chatgpt_auth.pinned_session(
        store_path=auth_path,
        client_id=ACCOUNT_ID,
        http_transport=fixture.transport,
    )
    client = create_llm_client(
        "chatgpt",
        "quick-fixture",
        auth_session=session,
        http_client=fixture.responses_client,
    )
    try:
        with pytest.raises(ChatGPTSubscriptionError, match="malformed arguments"):
            client.get_llm().bind_tools([_fixture_lookup]).invoke("look up NVDA")
        return {
            "status": "pass",
            "typed_terminal_error": True,
            "successful_result": False,
            "response_requests": fixture.request_count,
            "malformed_call_seen": fixture.malformed_used,
        }
    finally:
        fixture.close()


def _repo_snapshot() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--short"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    changed = [line[3:] for line in status]
    allowed = {
        "cli/selections.py",
        "tests/test_chatgpt_client.py",
        "tests/test_chatgpt_provider_flow.py",
        "tests/test_cli_prefs.py",
        "tradingagents/llm_clients/chatgpt_client.py",
        ".debug-journal.md",
    }
    return {
        "head": revision,
        "status": status,
        "only_authorized_paths_dirty": all(path in allowed for path in changed),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def _run_scenario(scenario: str, evidence_dir: Path) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    repo = _repo_snapshot()
    with tempfile.TemporaryDirectory(prefix="ta-task7-") as temporary:
        root = Path(temporary)
        if scenario == "graph":
            result, fixture = _execute_graph(root, scenario="checkpoint")
            try:
                malformed = _run_malformed_probe(root)
            except Exception as error:
                malformed = {
                    "status": "fail",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            result["malformed_tool_probe"] = malformed
            result["adversarial"] = {
                "malformed_input": "PASS: malformed completed function arguments raise a typed terminal error",
                "stale_state": "PASS: resume uses its saved graph state and success clears the checkpoint",
                "dirty_worktree": (
                    "PASS: only authorized product paths and the preserved journal were present"
                ),
                "cancel_resume": "PASS: provider interruption resumes without replaying completed analyst calls",
                "misleading_success_output": "PASS: final rating is read back from the persisted graph state log and memory log",
                "flaky_tests": "PASS: Events and bounded waits coordinate refresh; no fixed sleeps are used",
            }
            result["status"] = (
                "pass"
                if result["status"] == "pass"
                and malformed["status"] == "pass"
                and repo["only_authorized_paths_dirty"]
                else "fail"
            )
            request_records = result.pop("request_records")
            event_records = result.pop("event_records")
            report_details = result.pop("report_details")
            _write_jsonl(evidence_dir / "requests.jsonl", request_records)
            _write_jsonl(evidence_dir / "events.jsonl", event_records)
            _write_json(evidence_dir / "reports.json", report_details)
            _write_json(
                evidence_dir / "result.json", {"status": result["status"], **result, "repo": repo}
            )
        elif scenario == "graph-quota":
            result, fixture = _execute_graph(root, scenario="quota")
            result["adversarial"] = {
                "stale_state": "PASS: graph starts from an empty task-owned cache and no persisted result exists",
                "dirty_worktree": (
                    "PASS: only authorized product paths and the preserved journal were present"
                ),
                "misleading_success_output": "PASS: provisional text is not accepted as a successful decision",
                "flaky_tests": "PASS: a four-request Event barrier and measured active-response count replace timing sleeps",
            }
            result["status"] = (
                "pass"
                if result["status"] == "pass" and repo["only_authorized_paths_dirty"]
                else "fail"
            )
            request_records = result.pop("request_records")
            event_records = result.pop("event_records")
            _write_jsonl(evidence_dir / "requests.jsonl", request_records)
            _write_jsonl(evidence_dir / "events.jsonl", event_records)
            _write_json(
                evidence_dir / "result.json", {"status": result["status"], **result, "repo": repo}
            )
        else:
            raise ValueError(f"unknown scenario: {scenario}")
    cleanup = {
        "temporary_root_removed": not root.exists(),
        "fixture_http_client_closed": fixture.responses_client.is_closed,
        "fixture_sse_streams_open": fixture.open_streams,
        "listeners_or_servers_created": 0,
        "credentials_or_live_requests_used": False,
    }
    _write_json(evidence_dir / "cleanup.json", cleanup)
    return result


def _safe_live_failure_diagnostics(
    stage: object,
    error: Exception,
) -> dict[str, str]:
    if isinstance(error, ChatGPTSubscriptionError):
        failure_kind = "terminal_subscription_error"
    elif isinstance(error, ChatGPTResponsesError):
        failure_kind = "responses_contract_error"
    elif isinstance(error, (TimeoutError, httpx.TimeoutException, httpx2.TimeoutException)):
        failure_kind = "timeout"
    elif isinstance(error, (httpx.HTTPError, httpx2.HTTPError)):
        failure_kind = "transport_error"
    elif type(error) is ValueError:
        failure_kind = "value_error"
    elif type(error) is TypeError:
        failure_kind = "type_error"
    elif type(error) is RuntimeError:
        failure_kind = "runtime_error"
    elif isinstance(error, OSError):
        failure_kind = "os_error"
    else:
        failure_kind = "other_error"
    return {
        "failure_stage": (
            stage if isinstance(stage, str) and stage in LIVE_FAILURE_STAGES else "unknown"
        ),
        "failure_kind": (failure_kind if failure_kind in LIVE_FAILURE_KINDS else "other_error"),
        "exception_class": LIVE_EXCEPTION_CLASSES.get(type(error), "OtherError"),
    }


def _run_live(evidence_dir: Path) -> dict[str, Any]:
    if os.environ.get(LIVE_AUTHORIZATION_ENV) != "1":
        result = {
            "status": "pending",
            "scenario": "live",
            "credentials_inspected": False,
            "requests_submitted": 0,
            "missing_prerequisites": [
                "explicit user consent to inspect this app's ChatGPT credential store",
                "explicit authorization to consume eligible ChatGPT plan usage",
                "the presence of a valid, eligible, app-owned OAuth grant is unverified",
            ],
            "authorization_gate": LIVE_AUTHORIZATION_ENV,
        }
    else:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        from tradingagents.llm_clients.model_catalog import ChatGPTModelCatalogError

        request_count = {"public": 0}
        request_lock = threading.Lock()
        public_request_log: list[dict[str, Any]] = []
        original_sync_send = httpx.Client.send
        original_async_send = httpx.AsyncClient.send
        original_httpx2_sync_send = httpx2.Client.send
        original_httpx2_async_send = httpx2.AsyncClient.send
        original_openai_base_init = OpenAIBaseClient.__init__

        def request_record(request: httpx.Request) -> dict[str, Any]:
            endpoint = {
                "/v1/models": "models",
                "/v1/responses": "responses",
            }.get(request.url.path, "other")
            return {
                "method": request.method if request.method in {"GET", "POST"} else "other",
                "endpoint": endpoint,
                "status_code": None,
                "outcome": "pending",
            }

        def save_public_request_log() -> None:
            _write_jsonl(evidence_dir / "public_requests.jsonl", public_request_log)

        def counted_sync_send(
            original_send: Any,
            client: Any,
            request: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if request.url.host == "api.openai.com":
                with request_lock:
                    if request_count["public"] >= LIVE_PUBLIC_REQUEST_LIMIT:
                        raise RuntimeError("authorized public request budget exhausted")
                    request_count["public"] += 1
                    record = request_record(request)
                    public_request_log.append(record)
                    save_public_request_log()
                try:
                    response = original_send(client, request, *args, **kwargs)
                except Exception:
                    with request_lock:
                        record["outcome"] = "transport_error"
                        save_public_request_log()
                    raise
                with request_lock:
                    record["status_code"] = response.status_code
                    record["outcome"] = "response"
                    save_public_request_log()
                return response
            return original_send(client, request, *args, **kwargs)

        async def counted_async_send(
            original_send: Any,
            client: Any,
            request: Any,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if request.url.host == "api.openai.com":
                with request_lock:
                    if request_count["public"] >= LIVE_PUBLIC_REQUEST_LIMIT:
                        raise RuntimeError("authorized public request budget exhausted")
                    request_count["public"] += 1
                    record = request_record(request)
                    public_request_log.append(record)
                    save_public_request_log()
                try:
                    response = await original_send(client, request, *args, **kwargs)
                except Exception:
                    with request_lock:
                        record["outcome"] = "transport_error"
                        save_public_request_log()
                    raise
                with request_lock:
                    record["status_code"] = response.status_code
                    record["outcome"] = "response"
                    save_public_request_log()
                return response
            return await original_send(client, request, *args, **kwargs)

        httpx.Client.send = lambda client, request, *args, **kwargs: counted_sync_send(
            original_sync_send, client, request, *args, **kwargs
        )
        httpx.AsyncClient.send = lambda client, request, *args, **kwargs: counted_async_send(
            original_async_send, client, request, *args, **kwargs
        )
        httpx2.Client.send = lambda client, request, *args, **kwargs: counted_sync_send(
            original_httpx2_sync_send, client, request, *args, **kwargs
        )
        httpx2.AsyncClient.send = lambda client, request, *args, **kwargs: counted_async_send(
            original_httpx2_async_send, client, request, *args, **kwargs
        )

        def initialize_without_retries(client: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["max_retries"] = 0
            original_openai_base_init(client, *args, **kwargs)

        OpenAIBaseClient.__init__ = initialize_without_retries
        live_diagnostics: dict[str, Any] = {}
        try:
            try:
                session = chatgpt_auth.pinned_session()
                options = get_chatgpt_model_options(session)
                result = _run_authorized_live_flow(session, options, live_diagnostics)
            except (chatgpt_auth.OAuthError, ChatGPTModelCatalogError) as error:
                result = {
                    "status": "blocked",
                    "scenario": "live",
                    "credentials_inspected": True,
                    "prerequisite_error": type(error).__name__,
                }
            except Exception as error:
                failure_stage = live_diagnostics.get("active_stage") or live_diagnostics.get(
                    "failure_stage"
                )
                result = {
                    "status": "fail",
                    "scenario": "live",
                    "credentials_inspected": True,
                    "safe_diagnostics": _safe_live_failure_diagnostics(failure_stage, error),
                }
            result["requests_submitted"] = request_count["public"]
            result["public_request_budget_total"] = LIVE_PUBLIC_REQUEST_LIMIT
            result["public_request_log"] = public_request_log
        finally:
            httpx.Client.send = original_sync_send
            httpx.AsyncClient.send = original_async_send
            httpx2.Client.send = original_httpx2_sync_send
            httpx2.AsyncClient.send = original_httpx2_async_send
            OpenAIBaseClient.__init__ = original_openai_base_init
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if "public_request_log" in result:
        _write_jsonl(
            evidence_dir / "public_requests.jsonl",
            result["public_request_log"],
        )
    _write_json(evidence_dir / "result.json", result)
    _write_json(
        evidence_dir / "cleanup.json",
        {
            "processes_spawned": 0,
            "listeners_or_servers_created": 0,
            "fixture_clients_open": 0,
            "live_mode_attempted": result["status"] != "pending",
        },
    )
    return result


def _invoke_live_text(quick: Any, diagnostics: dict[str, Any]) -> Any:
    diagnostics["active_stage"] = "text_invocation"
    return quick.invoke("Return a short confirmation that the live text path works.")


def _run_authorized_live_flow(
    session: RegistrationSession,
    options: list[tuple[str, str]],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Use only the pinned app grant; retain IDs and outcomes, never credentials or prompts."""
    quick, quick_model, deep_model, options = _create_live_quick_client(
        session, options, diagnostics
    )
    text_message = _invoke_live_text(quick, diagnostics)
    diagnostics["active_stage"] = "tool_binding"
    bound_tool = quick.bind_tools([_fixture_lookup], tool_choice="required")
    diagnostics["active_stage"] = "tool_invocation"
    tool_message = bound_tool.invoke("Use the local fixture lookup for NVDA.")
    diagnostics["active_stage"] = "tool_call_validation"
    if len(tool_message.tool_calls) != 1:
        diagnostics["active_stage"] = (
            "tool_call_missing" if not tool_message.tool_calls else "tool_call_multiple"
        )
        raise ValueError("live model did not return the expected local tool call")
    if tool_message.tool_calls[0]["name"] != "_fixture_lookup":
        diagnostics["active_stage"] = "tool_call_name_mismatch"
        raise ValueError("live model did not return the expected local tool call")
    tool_call = tool_message.tool_calls[0]
    diagnostics["active_stage"] = "local_tool_execution"
    tool_result = _fixture_lookup.invoke(tool_call["args"])
    diagnostics["active_stage"] = "tool_followup"
    followup = quick.invoke(
        [
            HumanMessage("Use the lookup result to finish this local tool roundtrip."),
            tool_message,
            ToolMessage(
                content=str(tool_result),
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            ),
        ]
    )

    with tempfile.TemporaryDirectory(prefix="ta-task7-live-") as temporary:
        root = Path(temporary)
        monkeypatch = pytest.MonkeyPatch()
        called: set[str] = set()
        try:
            _offline_vendors(monkeypatch, called)
            config = copy.deepcopy(DEFAULT_CONFIG)
            config.update(
                {
                    "results_dir": str(root / "results"),
                    "data_cache_dir": str(root / "cache"),
                    "memory_log_path": str(root / "memory.md"),
                    "llm_provider": "chatgpt",
                    "chatgpt_account_id": session.registration.client_id,
                    "quick_think_llm": quick_model,
                    "deep_think_llm": deep_model,
                    "checkpoint_enabled": False,
                }
            )
            diagnostics["active_stage"] = "graph_propagation"
            graph = trading_graph.TradingAgentsGraph(selected_analysts=("market",), config=config)
            state, rating = graph.propagate("NVDA", TRADE_DATE)
            state_log = json.loads(
                (
                    root
                    / "results"
                    / "NVDA"
                    / "TradingAgentsStrategy_logs"
                    / f"full_states_log_{TRADE_DATE}.json"
                ).read_text(encoding="utf-8")
            )
            if not text_message.content.strip() or not followup.content.strip():
                raise ValueError("live text or tool-result follow-up was empty")
            if not state.get("market_report") or not state.get("final_trade_decision"):
                raise ValueError("live short graph did not complete its analyst and manager path")
            diagnostics.pop("active_stage", None)
            return {
                "status": "pass",
                "scenario": "live",
                "credentials_inspected": True,
                "requests_submitted": "public Responses requests only",
                "public_endpoint": "https://api.openai.com/v1",
                "provider": "chatgpt",
                "models": {"quick": options[0][0], "deep": options[-1][0]},
                "catalog_retry": diagnostics,
                "response_ids_sha256": {
                    "text": hashlib.sha256(text_message.id.encode()).hexdigest(),
                    "tool_call": hashlib.sha256(tool_message.id.encode()).hexdigest(),
                    "tool_followup": hashlib.sha256(followup.id.encode()).hexdigest(),
                },
                "tool_result": str(tool_result),
                "graph_rating": rating,
                "saved_rating": state_log["final_rating"],
                "local_vendor_methods": sorted(called),
            }
        finally:
            monkeypatch.undo()
            context._identity.cache_clear()


def _create_live_quick_client(
    session: RegistrationSession,
    options: list[tuple[str, str]],
    diagnostics: dict[str, Any],
) -> tuple[Any, str, str, list[tuple[str, str]]]:
    if not options:
        raise ValueError("eligible account returned no visible models")
    quick_model, deep_model = options[0][1], options[-1][1]
    diagnostics.update(
        {
            "refresh_attempted": False,
        }
    )

    def construct(model: str) -> Any:
        try:
            client = create_llm_client("chatgpt", model, auth_session=session)
        except Exception as error:
            diagnostics.update(
                {
                    "failure_stage": (
                        "selected_model_validation"
                        if isinstance(error, ValueError)
                        and "is not available to the selected ChatGPT account" in str(error)
                        else "factory_construction"
                    ),
                    "failure_kind": (
                        "value_error" if isinstance(error, ValueError) else "other_error"
                    ),
                }
            )
            raise
        try:
            return client.get_llm()
        except Exception as error:
            diagnostics.update(
                {
                    "failure_stage": "llm_initialization",
                    "failure_kind": (
                        "value_error" if isinstance(error, ValueError) else "other_error"
                    ),
                }
            )
            raise

    try:
        quick = construct(quick_model)
    except ValueError as error:
        if "is not available to the selected ChatGPT account" not in str(error):
            raise
        diagnostics.update(
            {
                "refresh_attempted": True,
                "validation_code_path": "create_llm_client_catalog_validation",
                "validation_error_type": type(error).__name__,
            }
        )
        options = get_chatgpt_model_options(session)
        if not options:
            raise ValueError("eligible account returned no visible models") from None
        quick_model, deep_model = options[0][1], options[-1][1]
        diagnostics.pop("failure_stage", None)
        diagnostics.pop("failure_kind", None)
        quick = construct(quick_model)
    diagnostics["refresh_succeeded"] = diagnostics["refresh_attempted"]
    return quick, quick_model, deep_model, options


@pytest.mark.unit
def test_live_factory_refreshes_dynamic_catalog_once_on_stale_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    refreshed_options = [("Quick", "fresh-quick"), ("Deep", "fresh-deep")]

    class _Client:
        def get_llm(self) -> str:
            return "live-quick-client"

    def factory(provider: str, model: str, **kwargs: Any) -> _Client:
        assert provider == "chatgpt"
        assert kwargs["auth_session"] is session
        calls.append(model)
        if model == "stale-quick":
            raise ValueError("Model 'stale-quick' is not available to the selected ChatGPT account")
        return _Client()

    session = object()
    refreshes = 0

    def refresh(_session: Any) -> list[tuple[str, str]]:
        nonlocal refreshes
        refreshes += 1
        return refreshed_options

    monkeypatch.setattr(
        "tests.test_chatgpt_provider_flow.create_llm_client",
        factory,
    )
    monkeypatch.setattr(
        "tests.test_chatgpt_provider_flow.get_chatgpt_model_options",
        refresh,
    )
    diagnostics: dict[str, Any] = {}

    client, quick_model, deep_model, options = _create_live_quick_client(
        session, [("Old Quick", "stale-quick"), ("Old Deep", "stale-deep")], diagnostics
    )

    assert client == "live-quick-client"
    assert calls == ["stale-quick", "fresh-quick"]
    assert refreshes == 1
    assert (quick_model, deep_model) == ("fresh-quick", "fresh-deep")
    assert options == refreshed_options
    assert diagnostics == {
        "refresh_attempted": True,
        "validation_code_path": "create_llm_client_catalog_validation",
        "validation_error_type": "ValueError",
        "refresh_succeeded": True,
    }
    assert all(
        slug not in json.dumps(diagnostics)
        for slug in ("stale-quick", "stale-deep", "fresh-quick", "fresh-deep")
    )


@pytest.mark.unit
def test_live_factory_classifies_llm_initialization_without_raw_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_model = "private-model-slug"

    class _Client:
        def get_llm(self) -> Any:
            raise ValueError(f"LLM rejected {private_model}")

    def factory(provider: str, model: str, **kwargs: Any) -> _Client:
        assert provider == "chatgpt"
        assert model == private_model
        assert kwargs["auth_session"] is session
        return _Client()

    session = object()
    monkeypatch.setattr(
        "tests.test_chatgpt_provider_flow.create_llm_client",
        factory,
    )
    diagnostics: dict[str, Any] = {}

    with pytest.raises(ValueError):
        _create_live_quick_client(session, [("Quick", private_model)], diagnostics)

    assert diagnostics == {
        "refresh_attempted": False,
        "failure_stage": "llm_initialization",
        "failure_kind": "value_error",
    }
    assert private_model not in json.dumps(diagnostics)


@pytest.mark.unit
def test_live_text_failure_emits_only_allowlisted_stage_and_exception_class() -> None:
    private_detail = "private-model-and-account"

    class _FakeQuick:
        def invoke(self, _prompt: str) -> Any:
            raise ValueError(f"request rejected for {private_detail}")

    diagnostics: dict[str, Any] = {}
    with pytest.raises(ValueError) as error:
        _invoke_live_text(_FakeQuick(), diagnostics)

    safe = _safe_live_failure_diagnostics(diagnostics["active_stage"], error.value)
    assert safe == {
        "failure_stage": "text_invocation",
        "failure_kind": "value_error",
        "exception_class": "ValueError",
    }
    assert private_detail not in json.dumps(safe)
    assert _safe_live_failure_diagnostics(
        f"unknown-{private_detail}", RuntimeError(private_detail)
    ) == {
        "failure_stage": "unknown",
        "failure_kind": "runtime_error",
        "exception_class": "RuntimeError",
    }

    class _PrivateException(Exception):
        pass

    assert _safe_live_failure_diagnostics("tool_invocation", _PrivateException(private_detail)) == {
        "failure_stage": "tool_invocation",
        "failure_kind": "other_error",
        "exception_class": "OtherError",
    }
    assert _safe_live_failure_diagnostics(
        "tool_invocation", ChatGPTSubscriptionError(private_detail)
    ) == {
        "failure_stage": "tool_invocation",
        "failure_kind": "terminal_subscription_error",
        "exception_class": "ChatGPTSubscriptionError",
    }
    assert _safe_live_failure_diagnostics(
        "tool_call_validation", ChatGPTResponsesError(private_detail)
    ) == {
        "failure_stage": "tool_call_validation",
        "failure_kind": "responses_contract_error",
        "exception_class": "ChatGPTResponsesError",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("call_names", "expected_stage"),
    [
        ([], "tool_call_missing"),
        (["_fixture_lookup", "_fixture_lookup"], "tool_call_multiple"),
        (["unexpected-private-tool"], "tool_call_name_mismatch"),
    ],
)
def test_live_tool_validation_distinguishes_failures_without_private_data(
    monkeypatch: pytest.MonkeyPatch, call_names: list[str], expected_stage: str
) -> None:
    message = AIMessage(
        content="private-response",
        tool_calls=[
            {"name": name, "args": {"ticker": "private-ticker"}, "id": f"private-{index}"}
            for index, name in enumerate(call_names)
        ],
    )

    class _Quick:
        def invoke(self, _prompt: str) -> AIMessage:
            return message

        def bind_tools(self, _tools: list[Any], **_kwargs: Any) -> _Quick:
            return self

    monkeypatch.setattr(
        "tests.test_chatgpt_provider_flow._create_live_quick_client",
        lambda *_args: (_Quick(), "private-model", "private-model", []),
    )
    diagnostics: dict[str, Any] = {}

    with pytest.raises(ValueError) as error:
        _run_authorized_live_flow(object(), [], diagnostics)

    safe = _safe_live_failure_diagnostics(diagnostics["active_stage"], error.value)
    assert safe["failure_stage"] == expected_stage
    assert "private" not in json.dumps(safe)


@pytest.mark.unit
def test_production_factory_adapter_graph_and_checkpoint_resume(tmp_path: Path) -> None:
    result = _run_scenario("graph", tmp_path / "evidence")

    assert result["status"] == "pass"
    assert result["malformed_tool_probe"]["status"] == "pass"
    assert all(result["reports"].values())
    assert result["local_tools"] == sorted(TOOL_METHODS)
    assert result["saved_rating"] == result["signal"] == "Overweight"
    assert result["parallel_refresh"]["all_response_authorization_uses_rotated_token"]
    assert all(result["structured_and_fallback"].values())
    assert all(result["debate_and_manager_decisions"].values())


@pytest.mark.unit
def test_production_graph_quota_stops_new_requests_without_saved_rating(tmp_path: Path) -> None:
    result = _run_scenario("graph-quota", tmp_path / "evidence")

    assert result["status"] == "pass"
    assert result["quota_error"]["type"] == "ChatGPTSubscriptionError"
    assert result["in_flight_at_quota_observation"] >= 1
    assert result["new_requests_after_quota_observation"] == 0
    assert result["successful_decision_entries"] == 0
    assert result["saved_state_logs"] == []


@pytest.mark.unit
def test_live_gate_does_not_inspect_app_credentials_without_explicit_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LIVE_AUTHORIZATION_ENV, raising=False)
    monkeypatch.setattr(
        chatgpt_auth,
        "pinned_session",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("credential read before gate")),
    )

    result = _run_live(tmp_path / "live")

    assert result["status"] == "pending"
    assert result["credentials_inspected"] is False
    assert result["requests_submitted"] == 0


@pytest.mark.unit
def test_live_request_cap_counts_all_transports_and_blocks_before_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openai import OpenAI

    monkeypatch.setenv(LIVE_AUTHORIZATION_ENV, "1")
    monkeypatch.delenv("TASK7_LIVE_PUBLIC_REQUESTS_PRIOR", raising=False)
    transport_hits = 0

    def response(request: Any, response_type: type[Any]) -> Any:
        nonlocal transport_hits
        transport_hits += 1
        return response_type(200, request=request)

    def catalog(_session: Any) -> list[tuple[str, str]]:
        sdk = OpenAI(api_key="offline-fixture-only")
        try:
            assert sdk.max_retries == 0
        finally:
            sdk.close()

        with httpx.Client(
            transport=httpx.MockTransport(lambda request: response(request, httpx.Response))
        ) as sync_httpx:
            sync_httpx.post("https://api.openai.com/v1/responses")
        with httpx2.Client(
            transport=httpx2.MockTransport(lambda request: response(request, httpx2.Response))
        ) as sync_httpx2:
            for _ in range((LIVE_PUBLIC_REQUEST_LIMIT - 2) // 2):
                sync_httpx2.post("https://api.openai.com/v1/responses")

        async def send_async_requests() -> None:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: response(request, httpx.Response))
            ) as async_httpx:
                await async_httpx.post("https://api.openai.com/v1/responses")
            async with httpx2.AsyncClient(
                transport=httpx2.MockTransport(lambda request: response(request, httpx2.Response))
            ) as async_httpx2:
                for _ in range((LIVE_PUBLIC_REQUEST_LIMIT - 2) // 2):
                    await async_httpx2.post("https://api.openai.com/v1/responses")

        asyncio.run(send_async_requests())
        with httpx2.Client(
            transport=httpx2.MockTransport(lambda request: response(request, httpx2.Response))
        ) as capped_client:
            capped_client.post("https://api.openai.com/v1/responses")
        return []

    monkeypatch.setattr(chatgpt_auth, "pinned_session", lambda **kwargs: object())
    monkeypatch.setattr(
        "tests.test_chatgpt_provider_flow.get_chatgpt_model_options",
        catalog,
    )

    evidence_dir = tmp_path / "live"
    result = _run_live(evidence_dir)
    requests = [
        json.loads(line)
        for line in (evidence_dir / "public_requests.jsonl").read_text().splitlines()
    ]

    assert result["status"] == "fail"
    assert result["requests_submitted"] == LIVE_PUBLIC_REQUEST_LIMIT
    assert result["public_request_budget_total"] == LIVE_PUBLIC_REQUEST_LIMIT
    assert "public_requests_total" not in result
    assert transport_hits == LIVE_PUBLIC_REQUEST_LIMIT
    assert len(requests) == LIVE_PUBLIC_REQUEST_LIMIT
    assert all(
        request["method"] == "POST"
        and request["endpoint"] == "responses"
        and request["status_code"] == 200
        for request in requests
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("graph", "graph-quota", "live"), required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.scenario == "live":
        result = _run_live(args.evidence_dir)
    else:
        result = _run_scenario(args.scenario, args.evidence_dir)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"pass", "pending"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
