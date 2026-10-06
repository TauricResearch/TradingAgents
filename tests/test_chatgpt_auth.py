"""Tests for the app-owned Sign in with ChatGPT OAuth boundary."""

from __future__ import annotations

import json
import multiprocessing
import os
import socket
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tradingagents.llm_clients import chatgpt_auth

ISSUER = "https://auth.openai.com"
CLIENT_ID = "oaiapp_saved"
ISSUED_ID = "oaiapp_issued"
FULL_SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
IDENTITY_SCOPE = "openid profile email"
_SOCKET_CONNECT = socket.socket.connect


def _loopback_get(redirect_uri: str, query: str) -> None:
    parsed = urllib.parse.urlsplit(redirect_uri)
    with socket.socket() as connection:
        connection.settimeout(2.0)
        _SOCKET_CONNECT(connection, ("127.0.0.1", parsed.port))
        connection.sendall(
            (
                f"GET {parsed.path}?{query} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{parsed.port}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
        )
        response = b""
        while chunk := connection.recv(4096):
            response += chunk
    assert b"200 OK" in response


class OAuthFixture:
    """Wire-level fake for discovery, JWKS, token exchange, and loopback return."""

    def __init__(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        self.jwk["kid"] = "fixture-key"
        self.state_override: str | None = None
        self.callback_client_id: str | None = None
        self.omit_client_id = False
        self.callback_error: str | None = None
        self.callback_code = "fixture-code"
        self.claim_subject = "account-subject"
        self.claim_email = "same@example.test"
        self.claim_audience: str | None = None
        self.claim_nonce: str | None = None
        self.tamper_signature = False
        self.granted_scope = FULL_SCOPE
        self.exchange_forms: list[dict[str, str]] = []
        self.authorization: dict[str, str] = {}
        self.responses_requests = 0
        self.interrupt_socket_first = False
        self.callback_port: int | None = None
        self.issued_client_id = ISSUED_ID
        self.refresh_forms: list[dict[str, str]] = []
        self.refresh_status = 200
        self.refresh_scope: str | None = None
        self.access_token = "fixture-access"
        self.refresh_submitted: threading.Event | None = None
        self.allow_refresh: threading.Event | None = None
        self.revocation_status = 200
        self.revocation_forms: list[dict[str, str]] = []
        self.revocation_submitted: threading.Event | None = None
        self.allow_revocation: threading.Event | None = None

    def _token(self, client_id: str, nonce: str) -> str:
        token = jwt.encode(
            {
                "iss": ISSUER,
                "sub": self.claim_subject,
                "email": self.claim_email,
                "aud": self.claim_audience or client_id,
                "exp": 4_102_444_800,
                "iat": 1_700_000_000,
                "nonce": self.claim_nonce or nonce,
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.jwk["kid"]},
        )
        if self.tamper_signature:
            header, payload, signature = token.split(".")
            replacement = "A" if signature[0] != "A" else "B"
            token = f"{header}.{payload}.{replacement}{signature[1:]}"
        return token

    def http_handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": chatgpt_auth.AUTHORIZE_URL,
                    "token_endpoint": f"{ISSUER}/api/accounts/oauth/token",
                    "revocation_endpoint": f"{ISSUER}/api/accounts/oauth/revoke",
                    "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
                },
            )
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json={"keys": [self.jwk]})
        if request.url.path == "/api/accounts/oauth/token":
            form = urllib.parse.parse_qs(request.content.decode())
            normalized = {name: values[0] for name, values in form.items()}
            if normalized.get("grant_type") == "refresh_token":
                self.refresh_forms.append(normalized)
                if self.refresh_submitted is not None:
                    self.refresh_submitted.set()
                if self.allow_refresh is not None and not self.allow_refresh.wait(3.0):
                    return httpx.Response(504)
                if self.refresh_status >= 400:
                    error = "invalid_grant" if self.refresh_status == 400 else "temporary"
                    return httpx.Response(self.refresh_status, json={"error": error})
                tokens = {
                    "access_token": "rotated-access",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
                if self.refresh_scope is not None:
                    tokens["scope"] = self.refresh_scope
                return httpx.Response(200, json=tokens)
            self.exchange_forms.append(normalized)
            token = self._token(normalized["client_id"], self.authorization["nonce"])
            return httpx.Response(
                200,
                json={
                    "access_token": self.access_token,
                    "refresh_token": "fixture-refresh",
                    "id_token": token,
                    "scope": self.granted_scope,
                    "token_type": "Bearer",
                },
            )
        if request.url.path == "/api/accounts/oauth/revoke":
            form = urllib.parse.parse_qs(request.content.decode())
            self.revocation_forms.append({name: values[0] for name, values in form.items()})
            if self.revocation_submitted is not None:
                self.revocation_submitted.set()
            if self.allow_revocation is not None and not self.allow_revocation.wait(3.0):
                return httpx.Response(504)
            return httpx.Response(self.revocation_status)
        if request.url.path.endswith("/responses"):
            self.responses_requests += 1
            return httpx.Response(200, json={"output": []})
        return httpx.Response(404)

    def browser(self, authorization_url: str) -> bool:
        self.authorization = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(authorization_url).query)
        )
        redirect_uri = self.authorization["redirect_uri"]
        self.callback_port = urllib.parse.urlsplit(redirect_uri).port
        if self.interrupt_socket_first:
            with socket.socket() as connection:
                _SOCKET_CONNECT(connection, ("127.0.0.1", self.callback_port))
        if self.callback_code == "timeout":
            return True
        query = {
            "state": self.state_override or self.authorization["state"],
            "code": self.callback_code,
        }
        if self.callback_error:
            query.pop("code")
            query["error"] = self.callback_error
        if not self.omit_client_id:
            query["client_id"] = (
                self.callback_client_id
                if self.callback_client_id is not None
                else (
                    CLIENT_ID
                    if self.authorization["client_id"] != "dynamic_agent_client"
                    else self.issued_client_id
                )
            )
        _loopback_get(redirect_uri, urllib.parse.urlencode(query))
        return True

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.http_handler)


def _saved_registration(path: Path, *, subject: str = "account-subject") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ext_agent_host_id": "urn:uuid:stable-host",
                "registration": {
                    "client_id": CLIENT_ID,
                    "issuer": ISSUER,
                    "subject": subject,
                    "inference_enabled": True,
                },
            }
        ),
        encoding="utf-8",
    )


def _sign_in(fixture: OAuthFixture, path: Path, **kwargs: object) -> chatgpt_auth.AuthResult:
    return chatgpt_auth.sign_in(
        store_path=path,
        browser_open=fixture.browser,
        http_transport=fixture.transport,
        callback_timeout=0.05 if fixture.callback_code == "timeout" else 2.0,
        **kwargs,
    )


def test_valid_signed_identity_registers_inference(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    auth_file = tmp_path / "auth.json"

    result = _sign_in(fixture, auth_file)

    assert result.subject == "account-subject"
    assert result.client_id == ISSUED_ID
    assert result.inference_enabled
    assert fixture.exchange_forms[0]["client_id"] == ISSUED_ID
    assert fixture.authorization["client_id"] == "dynamic_agent_client"
    assert fixture.authorization["agent_name_hint"] == "TradingAgents"
    assert urllib.parse.urlsplit(fixture.authorization["redirect_uri"]).path == "/auth/callback"
    assert fixture.authorization["code_challenge_method"] == "S256"
    assert (
        fixture.exchange_forms[0]["redirect_uri"] == fixture.authorization["redirect_uri"]
    )
    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"]["inference_enabled"]


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda fixture: setattr(fixture, "tamper_signature", True), jwt.InvalidSignatureError),
        (lambda fixture: setattr(fixture, "claim_audience", "other-client"), jwt.InvalidAudienceError),
        (lambda fixture: setattr(fixture, "claim_nonce", "wrong-nonce"), chatgpt_auth.OAuthError),
    ],
)
def test_invalid_identity_never_registers(mutate, error, tmp_path: Path) -> None:
    fixture = OAuthFixture()
    mutate(fixture)
    auth_file = tmp_path / "auth.json"

    with pytest.raises(error):
        _sign_in(fixture, auth_file)

    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"] is None


def test_wrong_state_stops_before_exchange(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.state_override = "wrong-state"
    auth_file = tmp_path / "auth.json"

    with pytest.raises(chatgpt_auth.OAuthError, match="state"):
        _sign_in(fixture, auth_file)

    assert fixture.exchange_forms == []
    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"] is None


def test_access_denied_stops_before_exchange(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.callback_error = "access_denied"
    auth_file = tmp_path / "auth.json"

    with pytest.raises(chatgpt_auth.OAuthError, match="denied"):
        _sign_in(fixture, auth_file)

    assert fixture.exchange_forms == []


def test_timeout_cleans_up_listener_without_exchange(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.callback_code = "timeout"
    auth_file = tmp_path / "auth.json"

    with pytest.raises(chatgpt_auth.OAuthError, match="Timed out"):
        _sign_in(fixture, auth_file)

    assert fixture.exchange_forms == []
    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"] is None


def test_returning_callback_without_client_id_uses_saved_id_once(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.omit_client_id = True
    auth_file = tmp_path / "auth.json"
    _saved_registration(auth_file)

    result = _sign_in(fixture, auth_file)

    assert result.client_id == CLIENT_ID
    assert len(fixture.exchange_forms) == 1
    assert fixture.exchange_forms[0]["client_id"] == CLIENT_ID
    assert fixture.authorization["client_id"] == CLIENT_ID
    assert fixture.authorization["ext_agent_host_id"] == "urn:uuid:stable-host"
    assert "agent_name_hint" not in fixture.authorization
    assert "id_token_hint" not in fixture.authorization


def test_returning_callback_with_different_client_id_preserves_registration(
    tmp_path: Path,
) -> None:
    fixture = OAuthFixture()
    fixture.callback_client_id = "oaiapp_other"
    auth_file = tmp_path / "auth.json"
    _saved_registration(auth_file)
    before = auth_file.read_text(encoding="utf-8")

    with pytest.raises(chatgpt_auth.OAuthError, match="client"):
        _sign_in(fixture, auth_file)

    assert fixture.exchange_forms == []
    assert auth_file.read_text(encoding="utf-8") == before


def test_returning_identity_mismatch_preserves_credentials(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.claim_subject = "different-subject"
    auth_file = tmp_path / "auth.json"
    _saved_registration(auth_file)
    before = auth_file.read_text(encoding="utf-8")

    with pytest.raises(chatgpt_auth.OAuthError, match="identity"):
        _sign_in(fixture, auth_file)

    assert len(fixture.exchange_forms) == 1
    assert auth_file.read_text(encoding="utf-8") == before


def test_new_registration_without_issued_client_id_is_not_exchanged(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.omit_client_id = True
    auth_file = tmp_path / "auth.json"

    with pytest.raises(chatgpt_auth.OAuthError, match="client ID"):
        _sign_in(fixture, auth_file)

    assert fixture.exchange_forms == []
    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"] is None


def test_missing_plan_scope_persists_disabled_sign_in_without_responses(
    tmp_path: Path,
) -> None:
    fixture = OAuthFixture()
    fixture.granted_scope = IDENTITY_SCOPE
    auth_file = tmp_path / "auth.json"

    result = _sign_in(fixture, auth_file)

    saved = json.loads(auth_file.read_text(encoding="utf-8"))
    assert not result.inference_enabled
    assert "reauthorize" in result.guidance.lower()
    assert not saved["registration"]["inference_enabled"]
    assert fixture.responses_requests == 0


def test_explicit_complete_scope_reauthorization_enables_inference(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    auth_file = tmp_path / "auth.json"
    _saved_registration(auth_file)

    result = _sign_in(fixture, auth_file, enable_plan_use=True)

    assert result.inference_enabled
    assert fixture.authorization["prompt"] == "consent"
    assert set(fixture.authorization["scope"].split()) == set(chatgpt_auth.SCOPES)
    assert json.loads(auth_file.read_text(encoding="utf-8"))["registration"]["inference_enabled"]


def test_ordinary_returning_sign_in_does_not_force_consent(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    auth_file = tmp_path / "auth.json"
    _saved_registration(auth_file)

    _sign_in(fixture, auth_file)

    assert "prompt" not in fixture.authorization


def test_duplicate_callback_fields_are_rejected_before_exchange(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    auth_file = tmp_path / "auth.json"

    def duplicate_state(url: str) -> bool:
        fixture.authorization = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        redirect_uri = fixture.authorization["redirect_uri"]
        query = urllib.parse.urlencode(
            {"state": fixture.authorization["state"], "code": "code"}
        ) + "&state=second"
        _loopback_get(redirect_uri, query)
        return True

    with pytest.raises(chatgpt_auth.OAuthError, match="callback"):
        chatgpt_auth.sign_in(
            store_path=auth_file,
            browser_open=duplicate_state,
            http_transport=fixture.transport,
            callback_timeout=2.0,
        )

    assert fixture.exchange_forms == []


def test_listener_survives_interrupted_client_socket(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    fixture.interrupt_socket_first = True
    result = _sign_in(fixture, tmp_path / "auth.json")
    assert result.inference_enabled


def _seed_expiring_account(path: Path) -> chatgpt_auth.RegistrationSession:
    state = chatgpt_auth._new_auth()
    state["accounts"][CLIENT_ID] = {
        "client_id": CLIENT_ID,
        "issuer": ISSUER,
        "subject": "account-subject",
        "inference_enabled": True,
        "email": "same@example.test",
        "ext_agent_host_id": state["ext_agent_host_id"],
        "access_token": "old-access",
        "refresh_token": "old-refresh",
        "id_token": "old-id",
        "scopes": ["openid", "offline_access"],
        "expires_at": 0.0,
        "rotation_pending": False,
        "requires_reauthorization": False,
    }
    state["selected_client_id"] = CLIENT_ID
    with chatgpt_auth._locked(path):
        chatgpt_auth._save(path, state)
    return chatgpt_auth.pinned_session(store_path=path)


def _spawn_refresh(
    path: str,
    start: multiprocessing.synchronize.Event,
    ready: multiprocessing.queues.Queue,
    results: multiprocessing.queues.Queue,
    refresh_count: multiprocessing.sharedctypes.Synchronized,
) -> None:
    ready.put("ready")
    if not start.wait(5.0):
        results.put("start-timeout")
        return

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={"token_endpoint": f"{ISSUER}/api/accounts/oauth/token"},
            )
        if request.url.path.endswith("/oauth/token"):
            with refresh_count.get_lock():
                refresh_count.value += 1
            return httpx.Response(
                200,
                json={
                    "access_token": "process-access",
                    "refresh_token": "process-refresh",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(404)

    session = chatgpt_auth.pinned_session(
        store_path=Path(path),
        http_transport=httpx.MockTransport(handler),
    )
    try:
        results.put(session.access_token())
    except chatgpt_auth.OAuthError as exc:
        results.put(type(exc).__name__)


def _crash_after_refresh_submission(
    path: str,
    submitted: multiprocessing.synchronize.Event,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={"token_endpoint": f"{ISSUER}/api/accounts/oauth/token"},
            )
        if request.url.path.endswith("/oauth/token"):
            submitted.set()
            os._exit(37)
        return httpx.Response(404)

    session = chatgpt_auth.pinned_session(
        store_path=Path(path),
        http_transport=httpx.MockTransport(handler),
    )
    session.access_token()


def test_credentials_survive_restart_with_protected_permissions(tmp_path: Path) -> None:
    fixture = OAuthFixture()
    path = tmp_path / "chatgpt" / "auth.json"

    result = _sign_in(fixture, path)

    reloaded = chatgpt_auth.pinned_session(store_path=path)
    assert reloaded.registration.client_id == result.client_id
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded.registration.host_id == saved["ext_agent_host_id"]
    assert saved["accounts"][result.client_id]["refresh_token"] == "fixture-refresh"
    if os.name != "nt":
        assert path.parent.stat().st_mode & 0o777 == 0o700
        assert path.parent.parent.stat().st_mode & 0o777 == 0o700
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.with_name("auth.json.lock").stat().st_mode & 0o777 == 0o600


def test_account_choices_keep_same_subject_registrations_separate(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    first = OAuthFixture()
    _sign_in(first, path)
    first_session = chatgpt_auth.pinned_session(store_path=path)
    second = OAuthFixture()
    second.issued_client_id = "oaiapp_second"
    second.access_token = "second-access"

    _sign_in(second, path, add_account=True)

    accounts = chatgpt_auth.saved_accounts(store_path=path)
    assert [account.client_id for account in accounts] == [ISSUED_ID, "oaiapp_second"]
    assert {account.subject for account in accounts} == {"account-subject"}
    assert {account.email for account in accounts} == {"same@example.test"}
    assert chatgpt_auth.pinned_session(store_path=path).registration.client_id == "oaiapp_second"
    assert first_session.access_token() == "fixture-access"


def _seed_two_accounts(path: Path) -> None:
    _sign_in(OAuthFixture(), path)
    second = OAuthFixture()
    second.issued_client_id = "oaiapp_second"
    _sign_in(second, path, add_account=True)


def test_failed_validated_sign_in_does_not_commit_account_switch(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_two_accounts(path)
    failed_switch = OAuthFixture()
    failed_switch.callback_client_id = ISSUED_ID
    failed_switch.claim_subject = "different-subject"

    with pytest.raises(chatgpt_auth.OAuthError, match="identity"):
        _sign_in(failed_switch, path, account_client_id=ISSUED_ID)

    assert chatgpt_auth.pinned_session(store_path=path).registration.client_id == "oaiapp_second"


def test_successful_validated_sign_in_commits_account_switch(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_two_accounts(path)
    returning = OAuthFixture()
    returning.callback_client_id = ISSUED_ID

    _sign_in(returning, path, account_client_id=ISSUED_ID)

    assert chatgpt_auth.pinned_session(store_path=path).registration.client_id == ISSUED_ID


def test_concurrent_sessions_reload_one_rotated_token_set(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    session = _seed_expiring_account(path)
    fixture = OAuthFixture()
    gate = threading.Barrier(3)
    quick = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)
    deep = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)

    def request_token(pinned: chatgpt_auth.RegistrationSession) -> str:
        gate.wait(timeout=2.0)
        return pinned.access_token()

    with ThreadPoolExecutor(max_workers=2) as pool:
        quick_future = pool.submit(request_token, quick)
        deep_future = pool.submit(request_token, deep)
        gate.wait(timeout=2.0)
        tokens = {quick_future.result(timeout=3.0), deep_future.result(timeout=3.0)}

    stored = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    assert tokens == {"rotated-access"}
    assert len(fixture.refresh_forms) == 1
    assert fixture.refresh_forms[0]["client_id"] == CLIENT_ID
    assert fixture.refresh_forms[0]["resource"] == chatgpt_auth.RESOURCE
    assert stored["access_token"] == "rotated-access"
    assert stored["refresh_token"] == "rotated-refresh"
    assert stored["rotation_pending"] is False
    assert session.registration.client_id == quick.registration.client_id


def test_refresh_updates_granted_scopes_and_disables_revoked_plan_use(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    fixture = OAuthFixture()
    fixture.refresh_scope = IDENTITY_SCOPE
    session = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)

    assert session.access_token() == "rotated-access"

    saved = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    account = chatgpt_auth.saved_accounts(store_path=path)[0]
    assert saved["scopes"] == sorted(IDENTITY_SCOPE.split())
    assert saved["inference_enabled"] is False
    assert account.inference_enabled is False
    assert saved["access_token"] == "rotated-access"
    assert saved["refresh_token"] == "rotated-refresh"
    assert saved["rotation_pending"] is False


def test_revoked_refresh_clears_tokens_but_retains_registration(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    fixture = OAuthFixture()
    fixture.refresh_status = 400
    session = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)

    with pytest.raises(chatgpt_auth.ReauthorizationRequired, match="rejected"):
        session.access_token()

    saved = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    assert saved["client_id"] == CLIENT_ID
    assert saved["access_token"] is None
    assert saved["refresh_token"] is None
    assert saved["requires_reauthorization"] is True
    assert len(fixture.refresh_forms) == 1


def test_transient_refresh_failure_preserves_grant(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    fixture = OAuthFixture()
    fixture.refresh_status = 503
    session = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)

    with pytest.raises(chatgpt_auth.TemporaryAuthError):
        session.access_token()

    saved = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    assert saved["access_token"] == "old-access"
    assert saved["refresh_token"] == "old-refresh"
    assert saved["rotation_pending"] is False
    assert saved["requires_reauthorization"] is False


def test_separate_processes_share_one_refresh_and_replacement(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    ready = context.Queue()
    results = context.Queue()
    refresh_count = context.Value("i", 0)
    processes = [
        context.Process(
            target=_spawn_refresh,
            args=(str(path), start, ready, results, refresh_count),
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        assert [ready.get(timeout=5.0) for _ in processes] == ["ready", "ready"]
        start.set()
        tokens = [results.get(timeout=8.0) for _ in processes]
        for process in processes:
            process.join(timeout=8.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3.0)
            assert process.exitcode == 0
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=3.0)
        ready.close()
        ready.join_thread()
        results.close()
        results.join_thread()

    saved = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    assert tokens == ["process-access", "process-access"]
    assert refresh_count.value == 1
    assert saved["access_token"] == "process-access"
    assert saved["refresh_token"] == "process-refresh"
    assert saved["rotation_pending"] is False


def test_restart_after_acknowledged_rotation_requires_sign_in(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    context = multiprocessing.get_context("spawn")
    submitted = context.Event()
    process = context.Process(
        target=_crash_after_refresh_submission,
        args=(str(path), submitted),
    )
    process.start()
    try:
        assert submitted.wait(5.0)
        process.join(timeout=5.0)
        assert process.exitcode == 37
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=3.0)

    fixture = OAuthFixture()
    restarted = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)
    with pytest.raises(chatgpt_auth.ReauthorizationRequired, match="interrupted"):
        restarted.access_token()
    auth_data = json.loads(path.read_text(encoding="utf-8"))
    saved = auth_data["accounts"][CLIENT_ID]
    assert fixture.refresh_forms == []
    assert saved["client_id"] == CLIENT_ID
    assert auth_data["registration"]["client_id"] == CLIENT_ID
    assert saved["refresh_token"] is None
    assert saved["requires_reauthorization"] is True


def test_logout_clears_local_tokens_when_revocation_is_unconfirmed(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    fixture = OAuthFixture()
    fixture.revocation_status = 503
    host_id = chatgpt_auth.pinned_session(store_path=path).registration.host_id

    result = chatgpt_auth.logout(store_path=path, http_transport=fixture.transport)

    auth_data = json.loads(path.read_text(encoding="utf-8"))
    saved = auth_data["accounts"][CLIENT_ID]
    assert result.client_id == CLIENT_ID
    assert result.revocation_confirmed is False
    assert fixture.revocation_forms[0]["token"] == "old-refresh"
    assert saved["client_id"] == CLIENT_ID
    assert saved["ext_agent_host_id"] == host_id
    assert auth_data["registration"]["client_id"] == CLIENT_ID
    assert saved["access_token"] is None
    assert saved["refresh_token"] is None
    assert saved["requires_reauthorization"] is True


def test_logout_lock_prevents_a_waiting_refresh_from_resurrecting_tokens(
    tmp_path: Path,
) -> None:
    path = tmp_path / "auth.json"
    _seed_expiring_account(path)
    fixture = OAuthFixture()
    fixture.revocation_submitted = threading.Event()
    fixture.allow_revocation = threading.Event()
    session = chatgpt_auth.pinned_session(store_path=path, http_transport=fixture.transport)
    logout_results: list[chatgpt_auth.LogoutResult] = []
    refresh_results: list[str] = []
    refresh_errors: list[type[chatgpt_auth.OAuthError]] = []
    logout_thread = threading.Thread(
        target=lambda: logout_results.append(
            chatgpt_auth.logout(store_path=path, http_transport=fixture.transport)
        )
    )
    logout_thread.start()
    assert fixture.revocation_submitted.wait(3.0)

    def refresh_after_logout_attempt() -> None:
        try:
            refresh_results.append(session.access_token())
        except chatgpt_auth.OAuthError as exc:
            refresh_errors.append(type(exc))

    refresh_thread = threading.Thread(target=refresh_after_logout_attempt)
    refresh_thread.start()
    fixture.allow_revocation.set()
    logout_thread.join(timeout=3.0)
    refresh_thread.join(timeout=3.0)

    assert not logout_thread.is_alive()
    assert not refresh_thread.is_alive()
    assert logout_results[0].revocation_confirmed
    assert refresh_results == []
    assert refresh_errors == [chatgpt_auth.ReauthorizationRequired]
    assert fixture.refresh_forms == []
    saved = json.loads(path.read_text(encoding="utf-8"))["accounts"][CLIENT_ID]
    assert saved["client_id"] == CLIENT_ID
    assert saved["access_token"] is None
    assert saved["refresh_token"] is None
