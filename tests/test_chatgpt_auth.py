"""Tests for the app-owned Sign in with ChatGPT OAuth boundary."""

from __future__ import annotations

import json
import socket
import urllib.parse
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
        self.claim_audience: str | None = None
        self.claim_nonce: str | None = None
        self.tamper_signature = False
        self.granted_scope = FULL_SCOPE
        self.exchange_forms: list[dict[str, str]] = []
        self.authorization: dict[str, str] = {}
        self.responses_requests = 0
        self.interrupt_socket_first = False
        self.callback_port: int | None = None

    def _token(self, client_id: str, nonce: str) -> str:
        token = jwt.encode(
            {
                "iss": ISSUER,
                "sub": self.claim_subject,
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
                    "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
                },
            )
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json={"keys": [self.jwk]})
        if request.url.path == "/api/accounts/oauth/token":
            form = urllib.parse.parse_qs(request.content.decode())
            normalized = {name: values[0] for name, values in form.items()}
            self.exchange_forms.append(normalized)
            token = self._token(normalized["client_id"], self.authorization["nonce"])
            return httpx.Response(
                200,
                json={
                    "access_token": "fixture-access",
                    "refresh_token": "fixture-refresh",
                    "id_token": token,
                    "scope": self.granted_scope,
                    "token_type": "Bearer",
                },
            )
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
                    else ISSUED_ID
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
