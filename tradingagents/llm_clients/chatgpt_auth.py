"""Sign in with ChatGPT using an app-owned OAuth registration."""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import secrets
import threading
import time
import urllib.parse
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TypedDict

import httpx
import jwt

DISCOVERY_URL = "https://auth.openai.com/.well-known/openid-configuration"
AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = ("openid", "profile", "email", "offline_access", "resource.invoke", PLAN_SCOPE)
CALLBACK_PATH = "/auth/callback"
CALLBACK_TIMEOUT = 180.0


class OAuthError(RuntimeError):
    """An OAuth attempt did not produce a validated registration."""


class Registration(TypedDict):
    client_id: str
    issuer: str
    subject: str
    inference_enabled: bool


class StoredAuth(TypedDict):
    ext_agent_host_id: str
    registration: Registration | None


@dataclass(frozen=True, slots=True)
class AuthResult:
    client_id: str
    issuer: str
    subject: str
    access_token: str
    refresh_token: str | None
    id_token: str
    scopes: frozenset[str]
    inference_enabled: bool
    guidance: str | None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urllib.parse.urlsplit(self.path).path != CALLBACK_PATH:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"TradingAgents sign-in received. You may close this tab.")
        self.server.callback_queue.put(self.path)
        self.server.callback_received.set()

    def log_message(self, format: str, *args: object) -> None:
        """Never log callback URLs, which contain authorization material."""


def _stored_auth(path: Path) -> StoredAuth:
    if not path.exists():
        return {"ext_agent_host_id": f"urn:uuid:{uuid.uuid4()}", "registration": None}
    data = json.loads(path.read_text(encoding="utf-8"))
    host_id = data.get("ext_agent_host_id")
    registration = data.get("registration")
    if not isinstance(host_id, str) or not host_id.startswith("urn:uuid:"):
        raise OAuthError("Saved ChatGPT registration data is invalid.")
    if registration is not None and (
        not isinstance(registration, dict)
        or not isinstance(registration.get("client_id"), str)
        or not isinstance(registration.get("issuer"), str)
        or not isinstance(registration.get("subject"), str)
        or not isinstance(registration.get("inference_enabled"), bool)
    ):
        raise OAuthError("Saved ChatGPT registration data is invalid.")
    return {"ext_agent_host_id": host_id, "registration": registration}


def _save(path: Path, data: StoredAuth) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _serve_callbacks(server: HTTPServer, stop: threading.Event, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    server.timeout = 0.1
    while not stop.is_set() and not server.callback_received.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        server.timeout = min(0.1, remaining)
        server.handle_request()


def _query_value(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name, [])
    if len(values) > 1:
        raise OAuthError("ChatGPT returned an invalid callback.")
    return values[0] if values else None


def _verify_identity(
    client: httpx.Client,
    token: str,
    jwks_uri: str,
    issuer: str,
    client_id: str,
    nonce: str,
) -> tuple[str, str]:
    jwks = client.get(jwks_uri).json()
    kid = jwt.get_unverified_header(token).get("kid")
    keys = [key for key in jwks["keys"] if key.get("kid") == kid]
    if len(keys) != 1:
        raise OAuthError("ChatGPT identity token has no matching signing key.")
    key = jwt.PyJWK.from_dict(keys[0]).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=issuer,
        options={"require": ["exp", "iss", "sub", "nonce"]},
    )
    if claims["nonce"] != nonce:
        raise OAuthError("ChatGPT identity token nonce did not match.")
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject:
        raise OAuthError("ChatGPT identity token subject is invalid.")
    return issuer, subject


def sign_in(
    *,
    store_path: Path | None = None,
    enable_plan_use: bool = False,
    callback_timeout: float = CALLBACK_TIMEOUT,
    browser_open: Callable[[str], bool] = webbrowser.open,
    http_transport: httpx.BaseTransport | None = None,
) -> AuthResult:
    """Run browser sign-in and persist only the validated registration state."""
    if callback_timeout <= 0:
        raise OAuthError("ChatGPT callback timeout must be positive.")
    callback_timeout = min(callback_timeout, CALLBACK_TIMEOUT)
    auth_path = store_path or Path.home() / ".tradingagents" / "chatgpt" / "auth.json"
    saved = _stored_auth(auth_path)
    if not auth_path.exists():
        _save(auth_path, saved)
    registration = saved["registration"]
    returning = registration is not None
    requested_id = registration["client_id"] if returning else "dynamic_agent_client"
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    with httpx.Client(timeout=10.0, transport=http_transport) as client:
        discovery = client.get(DISCOVERY_URL).json()
        issuer = discovery["issuer"]
        server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        server.callback_queue = queue.Queue(maxsize=1)
        server.callback_received = threading.Event()
        redirect_uri = f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}"
        parameters = {
            "client_id": requested_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "ext_agent_host_id": saved["ext_agent_host_id"],
        }
        if returning:
            if enable_plan_use:
                parameters["prompt"] = "consent"
        else:
            parameters["agent_name_hint"] = "TradingAgents"
        authorize_url = f"{discovery['authorization_endpoint']}?{urllib.parse.urlencode(parameters)}"
        stop_listener = threading.Event()
        listener = threading.Thread(
            target=_serve_callbacks,
            args=(server, stop_listener, callback_timeout),
            name="chatgpt-oauth-callback",
            daemon=True,
        )
        listener.start()
        try:
            browser_open(authorize_url)
            try:
                callback_path = server.callback_queue.get(timeout=callback_timeout)
            except queue.Empty as exc:
                raise OAuthError("Timed out waiting for ChatGPT sign-in callback.") from exc
        finally:
            stop_listener.set()
            listener.join(timeout=1.0)
            server.server_close()

        parsed = urllib.parse.urlsplit(callback_path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        callback_state = _query_value(query, "state")
        if callback_state != state:
            raise OAuthError("ChatGPT callback state did not match.")
        oauth_error = _query_value(query, "error")
        if oauth_error == "access_denied":
            raise OAuthError("ChatGPT sign-in was denied.")
        if oauth_error:
            raise OAuthError("ChatGPT sign-in did not complete.")
        code = _query_value(query, "code")
        if not code:
            raise OAuthError("ChatGPT callback did not include an authorization code.")
        callback_client_id = _query_value(query, "client_id")
        if returning:
            client_id = registration["client_id"]
            if callback_client_id is not None and callback_client_id != client_id:
                raise OAuthError("ChatGPT callback client did not match the saved registration.")
        else:
            client_id = callback_client_id or ""
            if not client_id or client_id == "dynamic_agent_client":
                raise OAuthError("ChatGPT did not issue a registration client ID.")

        token_response = client.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": RESOURCE,
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()
        identity = tokens["id_token"]
        validated_issuer, subject = _verify_identity(
            client,
            identity,
            discovery["jwks_uri"],
            issuer,
            client_id,
            nonce,
        )
        if returning and (
            validated_issuer != registration["issuer"] or subject != registration["subject"]
        ):
            raise OAuthError("ChatGPT identity did not match the saved registration.")
        scopes = frozenset(tokens.get("scope", "").split())
        if "openid" not in scopes:
            raise OAuthError("ChatGPT did not grant the required identity scope.")
        enabled = PLAN_SCOPE in scopes
        guidance = None
        if not enabled:
            guidance = (
                "ChatGPT plan use is not enabled. Reauthorize with "
                "enable_plan_use=True to request the full permission set."
            )
        saved["registration"] = {
            "client_id": client_id,
            "issuer": validated_issuer,
            "subject": subject,
            "inference_enabled": enabled,
        }
        _save(auth_path, saved)
        return AuthResult(
            client_id=client_id,
            issuer=validated_issuer,
            subject=subject,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            id_token=identity,
            scopes=scopes,
            inference_enabled=enabled,
            guidance=guidance,
        )
