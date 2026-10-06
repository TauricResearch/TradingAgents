from __future__ import annotations

from pathlib import Path
from threading import Event
from unittest.mock import Mock

import httpx
import pytest

from cli import prefs, prompts
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph
from tradingagents.llm_clients import chatgpt_auth
from tradingagents.llm_clients.factory import build_llm_kwargs, create_llm_client
from tradingagents.llm_clients.model_catalog import (
    ChatGPTModelCatalogError,
    get_chatgpt_model_options,
)
from tradingagents.llm_clients.validators import validate_model

ACCOUNT_A = "oaiapp_account_a"
ACCOUNT_B = "oaiapp_account_b"


def _account_store(path: Path) -> None:
    state = chatgpt_auth._new_auth()
    state["accounts"] = {
        account_id: {
            "client_id": account_id,
            "issuer": "https://auth.openai.com",
            "subject": f"subject-{account_id}",
            "inference_enabled": True,
            "email": None,
            "ext_agent_host_id": state["ext_agent_host_id"],
            "access_token": f"access-{account_id}",
            "refresh_token": f"refresh-{account_id}",
            "id_token": None,
            "scopes": ["openid", chatgpt_auth.PLAN_SCOPE],
            "expires_at": 4_102_444_800,
            "rotation_pending": False,
            "requires_reauthorization": False,
        }
        for account_id in (ACCOUNT_A, ACCOUNT_B)
    }
    state["selected_client_id"] = ACCOUNT_A
    with chatgpt_auth._locked(path):
        chatgpt_auth._save(path, state)


def _transport(catalogs, on_first_catalog=None):
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        account_id = request.headers["Authorization"].removeprefix("Bearer access-")
        if on_first_catalog is not None and len(calls) == 1:
            on_first_catalog()
        return httpx.Response(200, json={"models": catalogs[account_id]})

    return httpx.MockTransport(handle), calls


@pytest.fixture(autouse=True)
def clear_prompt_account_context():
    token = prompts._CHATGPT_ACCOUNT_ID.set(None)
    yield
    prompts._CHATGPT_ACCOUNT_ID.reset(token)


@pytest.mark.unit
def test_account_catalog_filters_visibility_and_preserves_server_order(tmp_path: Path):
    path = tmp_path / "auth.json"
    _account_store(path)
    transport, requests = _transport({
        ACCOUNT_A: [
            {"visibility": "list", "display_name": "Second", "slug": "second"},
            {"visibility": "hide", "display_name": "Hidden", "slug": "hidden"},
            {"visibility": "list", "display_name": "First", "slug": "first"},
        ],
        ACCOUNT_B: [{"visibility": "list", "display_name": "Other", "slug": "other"}],
    })
    session = chatgpt_auth.pinned_session(
        store_path=path, client_id=ACCOUNT_A, http_transport=transport
    )

    options = get_chatgpt_model_options(session)

    assert options == [("Second", "second"), ("First", "first")]
    assert requests[0].url == "https://api.openai.com/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer access-oaiapp_account_a"


@pytest.mark.unit
def test_model_catalog_rechecks_plan_scope_after_token_refresh(tmp_path: Path):
    path = tmp_path / "auth.json"
    _account_store(path)
    with chatgpt_auth._locked(path):
        state = chatgpt_auth._load_locked(path)
        state["accounts"][ACCOUNT_A]["expires_at"] = 0.0
        chatgpt_auth._save(path, state)

    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "auth.openai.com" and request.url.path.endswith(
            "openid-configuration"
        ):
            return httpx.Response(
                200,
                json={"token_endpoint": "https://auth.openai.com/api/accounts/oauth/token"},
            )
        if request.url.host == "auth.openai.com" and request.url.path.endswith(
            "/oauth/token"
        ):
            return httpx.Response(
                200,
                json={
                    "access_token": "refreshed-access",
                    "refresh_token": "refreshed-refresh",
                    "expires_in": 3600,
                    "scope": "openid profile email offline_access resource.invoke",
                },
            )
        return httpx.Response(
            200,
            json={"models": [{"visibility": "list", "display_name": "A", "slug": "a"}]},
        )

    transport = httpx.MockTransport(handle)
    session = chatgpt_auth.pinned_session(
        store_path=path, client_id=ACCOUNT_A, http_transport=transport
    )

    with pytest.raises(ChatGPTModelCatalogError, match="plan use is not enabled"):
        get_chatgpt_model_options(session)

    assert [request.url.path for request in requests] == [
        "/.well-known/openid-configuration",
        "/api/accounts/oauth/token",
    ]
    saved = chatgpt_auth._stored_auth(path)["accounts"][ACCOUNT_A]
    assert saved["inference_enabled"] is False
    assert chatgpt_auth.PLAN_SCOPE not in saved["scopes"]


@pytest.mark.unit
@pytest.mark.parametrize("models", [None, ["malformed"], [{"visibility": "list", "slug": "missing-name"}]])
def test_malformed_account_catalog_is_rejected(tmp_path: Path, models):
    path = tmp_path / "auth.json"
    _account_store(path)
    transport, _ = _transport({ACCOUNT_A: models, ACCOUNT_B: []})
    session = chatgpt_auth.pinned_session(
        store_path=path, client_id=ACCOUNT_A, http_transport=transport
    )

    with pytest.raises(ChatGPTModelCatalogError):
        get_chatgpt_model_options(session)


@pytest.mark.unit
def test_factory_validates_model_against_the_pinned_account(tmp_path: Path):
    path = tmp_path / "auth.json"
    _account_store(path)
    transport, _ = _transport({
        ACCOUNT_A: [{"visibility": "list", "display_name": "A", "slug": "model-a"}],
        ACCOUNT_B: [{"visibility": "list", "display_name": "B", "slug": "model-b"}],
    })
    session = chatgpt_auth.pinned_session(
        store_path=path, client_id=ACCOUNT_A, http_transport=transport
    )

    client = create_llm_client("chatgpt", "model-a", auth_session=session)

    assert client.kwargs["auth_session"] is session
    assert validate_model("chatgpt", "model-a")
    with pytest.raises(ValueError, match="not available"):
        create_llm_client("chatgpt", "model-b", auth_session=session)


@pytest.mark.unit
def test_custom_endpoint_fails_before_catalog_request(tmp_path: Path):
    path = tmp_path / "auth.json"
    _account_store(path)
    transport, requests = _transport({
        ACCOUNT_A: [{"visibility": "list", "display_name": "A", "slug": "model-a"}],
        ACCOUNT_B: [],
    })
    session = chatgpt_auth.pinned_session(
        store_path=path, client_id=ACCOUNT_A, http_transport=transport
    )

    with pytest.raises(ValueError, match="custom endpoint"):
        create_llm_client(
            "chatgpt",
            "model-a",
            base_url="https://attacker.example/v1",
            auth_session=session,
        )

    assert requests == []


@pytest.mark.unit
def test_chatgpt_kwargs_accept_reasoning_and_reject_forbidden_sampling_caps():
    assert build_llm_kwargs({
        "llm_provider": "chatgpt",
        "openai_reasoning_effort": "high",
    })["reasoning_effort"] == "high"
    with pytest.raises(ValueError, match="does not support temperature"):
        build_llm_kwargs({"llm_provider": "chatgpt", "temperature": "0.2"})
    with pytest.raises(ValueError, match="output-token caps"):
        build_llm_kwargs({"llm_provider": "chatgpt", "max_tokens": "2048"})


@pytest.mark.unit
def test_preferences_do_not_fetch_chatgpt_catalog_for_other_providers(monkeypatch):
    def no_catalog(*_args):
        raise AssertionError("unrelated provider preference sanitization fetched ChatGPT models")

    monkeypatch.setattr(prefs, "_chatgpt_model_catalog", no_catalog)

    assert prefs.sanitize(
        {"llm_provider": "openai", "quick_think_llm": "gpt-6-luna"}, "stock"
    )["quick_think_llm"] == "gpt-6-luna"


@pytest.mark.unit
def test_account_switch_refreshes_picker_and_drops_stale_default(
    monkeypatch, tmp_path: Path
):
    path = tmp_path / "auth.json"
    _account_store(path)
    monkeypatch.setattr(chatgpt_auth, "_default_store_path", lambda: path)
    transport, requests = _transport({
        ACCOUNT_A: [{"visibility": "list", "display_name": "A", "slug": "model-a"}],
        ACCOUNT_B: [{"visibility": "list", "display_name": "B", "slug": "model-b"}],
    })
    original_pinned_session = chatgpt_auth.pinned_session

    def pinned_session(*, client_id=None):
        return original_pinned_session(
            store_path=path, client_id=client_id, http_transport=transport
        )

    monkeypatch.setattr(chatgpt_auth, "pinned_session", pinned_session)
    account_select = Mock()
    account_select.return_value.ask.return_value = ACCOUNT_B
    monkeypatch.setattr(prompts.questionary, "select", account_select)
    assert prompts.select_chatgpt_account() == ACCOUNT_B

    model_select = Mock()
    model_select.return_value.ask.return_value = "model-b"
    monkeypatch.setattr(prompts.questionary, "select", model_select)
    assert prompts.select_shallow_thinking_agent("chatgpt", "model-a") == "model-b"
    model_choices = model_select.call_args.kwargs["choices"]
    assert [(choice.title, choice.value) for choice in model_choices] == [
        ("B", "model-b")
    ]
    assert model_select.call_args.kwargs["default"] is None

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer access-oaiapp_account_b"


@pytest.mark.unit
def test_graph_pins_one_session_before_factories_across_account_switch(
    monkeypatch, tmp_path: Path
):
    path = tmp_path / "auth.json"
    _account_store(path)
    switched = Event()

    def switch_selected_account() -> None:
        with chatgpt_auth._locked(path):
            state = chatgpt_auth._load_locked(path)
            state["selected_client_id"] = ACCOUNT_B
            chatgpt_auth._save(path, state)
        switched.set()

    transport, requests = _transport({
        ACCOUNT_A: [
            {"visibility": "list", "display_name": "Quick", "slug": "quick-a"},
            {"visibility": "list", "display_name": "Deep", "slug": "deep-a"},
        ],
        ACCOUNT_B: [
            {"visibility": "list", "display_name": "Quick B", "slug": "quick-b"},
            {"visibility": "list", "display_name": "Deep B", "slug": "deep-b"},
        ],
    }, on_first_catalog=switch_selected_account)
    original_pinned_session = chatgpt_auth.pinned_session

    def pinned_session(*, client_id=None):
        return original_pinned_session(
            store_path=path, client_id=client_id, http_transport=transport
        )

    monkeypatch.setattr(chatgpt_auth, "pinned_session", pinned_session)
    original_factory = trading_graph.create_tier_client
    sessions = []

    def observe_factory(config, tier, **kwargs):
        sessions.append(kwargs["auth_session"])
        return original_factory(config, tier, **kwargs)

    monkeypatch.setattr(trading_graph, "create_tier_client", observe_factory)
    config = dict(
        DEFAULT_CONFIG,
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        llm_provider="chatgpt",
        chatgpt_account_id=ACCOUNT_A,
        quick_think_llm="quick-a",
        deep_think_llm="deep-a",
    )

    graph = trading_graph.TradingAgentsGraph(
        selected_analysts=("market",), config=config
    )

    assert switched.is_set()
    assert len(sessions) == 2
    assert sessions[0] is sessions[1] is graph._chatgpt_registration_session
    assert all(
        request.headers["Authorization"] == "Bearer access-oaiapp_account_a"
        for request in requests
    )
    assert ACCOUNT_A not in graph._run_signature("stock")


@pytest.mark.unit
def test_chatgpt_tier_uses_pinned_session_with_other_main_provider(monkeypatch, tmp_path: Path):
    path = tmp_path / "auth.json"
    _account_store(path)
    transport, requests = _transport({
        ACCOUNT_A: [{"visibility": "list", "display_name": "Deep", "slug": "deep-a"}],
    })
    original_pinned_session = chatgpt_auth.pinned_session

    def pinned_session(*, client_id=None):
        return original_pinned_session(
            store_path=path, client_id=client_id, http_transport=transport
        )

    monkeypatch.setattr(chatgpt_auth, "pinned_session", pinned_session)
    config = dict(
        DEFAULT_CONFIG,
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        llm_provider="openai",
        deep_think_provider="chatgpt",
        chatgpt_account_id=ACCOUNT_A,
        quick_think_llm="gpt-6-luna",
        deep_think_llm="deep-a",
    )

    graph = trading_graph.TradingAgentsGraph(selected_analysts=("market",), config=config)

    assert graph.deep_thinking_llm._llm_type == "chatgpt-responses"
    assert graph._chatgpt_registration_session is not None
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer access-oaiapp_account_a"
    assert "chatgpt-account=" in graph._run_signature("stock")
