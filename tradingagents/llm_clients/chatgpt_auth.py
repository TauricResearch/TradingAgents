"""Sign in with ChatGPT, so a run uses the person's ChatGPT Plus or Pro plan.

This follows OpenAI's documented flow for open-source apps ("Sign in with ChatGPT":
developers.openai.com/siwc): dynamic client registration, PKCE, and a loopback
redirect on 127.0.0.1. The sign-in, its tokens and this host's id live in one file
under ~/.tradingagents, readable only by its owner. Access tokens last an hour and
are refreshed under a lock shared by every thread and process, because each refresh
rotates the refresh token and replaying a used one ends the sign-in.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import uuid
from collections.abc import Callable
from pathlib import Path

import requests

from tradingagents.dataflows.files import locked
from tradingagents.default_config import _TRADINGAGENTS_HOME

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = f"{ISSUER}/api/accounts/authorize"
TOKEN_URL = f"{ISSUER}/api/accounts/oauth/token"
REVOKE_URL = f"{ISSUER}/api/accounts/oauth/revoke"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"
API_BASE = "https://api.openai.com/v1"
DYNAMIC_CLIENT_ID = "dynamic_agent_client"
APP_NAME = "TradingAgents"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
CALLBACK_PATH = "/auth/callback"
DEFAULT_PORT = 1455
REFRESH_MARGIN = 300          # refresh when the access token has under 5 minutes left
RETRY_AFTER = 60              # after OpenAI could not renew, wait this long before trying again
TIMEOUT = 30

AUTH_FILE = Path(_TRADINGAGENTS_HOME) / "chatgpt-auth.json"
LOGIN_HINT = "Not signed in to ChatGPT; run `tradingagents login chatgpt`."


_retry_after = 0.0            # no renewal attempt in this process before this time


class ChatGPTAuthError(RuntimeError):
    """Signing in or refreshing failed; the message says what to do."""


class ChatGPTUnreachable(ChatGPTAuthError):
    """OpenAI could not be reached or was busy; the sign-in itself is still good."""


# --- the auth file -------------------------------------------------------------------

def _read() -> dict:
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    """Write the auth file whole, readable only by its owner. Unlike a cache, a failed
    write must surface: losing a rotated refresh token would end the sign-in."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = AUTH_FILE.with_name(f"{AUTH_FILE.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(temp, AUTH_FILE)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def _host_id(data: dict) -> str:
    return data.get("host_id") or f"urn:uuid:{uuid.uuid4()}"


def signed_in_as() -> str | None:
    """The signed-in account's email, or None."""
    data = _read()
    return (data.get("account") or {}).get("email") if data.get("tokens") else None


# --- tokens --------------------------------------------------------------------------

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signing_keys() -> list[dict]:
    """OpenAI's ID-token signing keys. Fetched before a token request, so nothing can fail
    on the network between OpenAI issuing tokens and this file keeping them."""
    try:
        keys = requests.get(JWKS_URL, timeout=TIMEOUT).json()["keys"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise ChatGPTUnreachable(f"Could not reach OpenAI to check the sign-in ({type(exc).__name__}); "
                                 "try again.") from None
    return keys if isinstance(keys, list) else []


def _validated_claims(id_token: str, client_id: str, nonce: str | None, keys: list[dict]) -> dict:
    """The ID token's claims after checking its RS256 signature against OpenAI's keys,
    issuer, audience, expiry and (at sign-in) nonce, as the sign-in guide requires."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    try:
        header_b64, payload_b64, signature_b64 = id_token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        key = next((k for k in keys if k.get("kid") == header.get("kid") and k.get("kty") == "RSA"), None)
        if header.get("alg") != "RS256" or key is None:
            raise InvalidSignature
        public = rsa.RSAPublicNumbers(int.from_bytes(_b64url_decode(key["e"]), "big"),
                                      int.from_bytes(_b64url_decode(key["n"]), "big")).public_key()
        public.verify(_b64url_decode(signature_b64), f"{header_b64}.{payload_b64}".encode(),
                      padding.PKCS1v15(), hashes.SHA256())
        claims = json.loads(_b64url_decode(payload_b64))
    except (InvalidSignature, ValueError, KeyError, TypeError, AttributeError):
        raise ChatGPTAuthError("ChatGPT sign-in returned an ID token OpenAI's keys do not verify.") from None
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if (claims.get("iss") != ISSUER or client_id not in audiences or not claims.get("sub")
            or claims.get("exp", 0) + 5 < time.time()
            or (nonce is not None and claims.get("nonce") != nonce)):
        raise ChatGPTAuthError("ChatGPT sign-in returned an ID token that does not match this sign-in.")
    return claims


def _token_record(response: dict, now: float, previous: dict | None = None) -> dict:
    previous = previous or {}
    return {
        "access_token": response["access_token"],
        "refresh_token": response.get("refresh_token") or previous.get("refresh_token"),
        "expires_at": now + int(response.get("expires_in") or 3600),
        "earliest_refresh_at": response.get("earliest_refresh_at"),
        "scopes": sorted((response.get("scope") or "").split()) or previous.get("scopes", []),
    }


def _oauth_error(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = body.get("error")
    if isinstance(error, dict):
        return error.get("code") or error.get("message") or f"HTTP {response.status_code}"
    return error or f"HTTP {response.status_code}"


def _token_request(form: dict, task: str, refused: str) -> dict:
    """OpenAI's answer to a token request, or the error to show: ``ChatGPTUnreachable``
    when OpenAI could not answer (try again), ``ChatGPTAuthError`` when it refused."""
    try:
        response = requests.post(TOKEN_URL, timeout=TIMEOUT, data=form)
    except requests.RequestException as exc:
        raise ChatGPTUnreachable(f"Could not reach OpenAI to {task} ({type(exc).__name__}); try again.") from None
    if response.status_code in (408, 429) or response.status_code >= 500:
        raise ChatGPTUnreachable(f"OpenAI could not {task} now ({_oauth_error(response)}); try again.")
    if response.status_code != 200:
        raise ChatGPTAuthError(f"OpenAI did not {task} ({_oauth_error(response)}); {refused}.")
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
        raise ChatGPTUnreachable(f"OpenAI's answer could not be read when asked to {task}; try again.")
    return body


def _refresh(data: dict, now: float) -> dict:
    tokens, account = data["tokens"], data["account"]
    keys = _signing_keys()
    body = _token_request({"grant_type": "refresh_token", "client_id": account["client_id"],
                           "refresh_token": tokens["refresh_token"], "resource": API_BASE},
                          "renew your ChatGPT sign-in", "run `tradingagents login chatgpt` again")
    if body.get("id_token"):
        claims = _validated_claims(body["id_token"], account["client_id"], None, keys)
        if claims["sub"] != account.get("subject"):
            raise ChatGPTAuthError("The renewed ChatGPT sign-in belongs to another account.")
    return {**data, "tokens": _token_record(body, now, tokens)}


def _due(tokens: dict, now: float) -> bool:
    """Whether to renew: under five minutes left, and OpenAI accepts a renewal by now
    (``earliest_refresh_at``), unless the token has already run out."""
    expires = tokens.get("expires_at", 0)
    earliest = tokens.get("earliest_refresh_at")
    if now < expires - REFRESH_MARGIN:
        return False
    return now >= expires or not isinstance(earliest, (int, float)) or now >= earliest


def access_token(now: Callable[[], float] = time.time) -> str:
    """A valid access token, renewed when it has under five minutes left.

    Renewal happens under a lock every thread and process shares, and starts from
    the token on disk: another run may have renewed it already, and the refresh
    token it rotated away must never be sent again. When OpenAI cannot be reached
    or is busy, a token that still works is used and renewal is tried again a minute later."""
    global _retry_after
    tokens = _read().get("tokens")
    if not tokens:
        raise ChatGPTAuthError(LOGIN_HINT)
    if not _due(tokens, now()):
        return tokens["access_token"]
    with locked(AUTH_FILE):
        data = _read()
        if not data.get("tokens"):
            raise ChatGPTAuthError(LOGIN_HINT)
        tokens = data["tokens"]
        if _due(tokens, now()):
            still_works = tokens.get("expires_at", 0) > now()
            if now() < _retry_after:
                if still_works:
                    return tokens["access_token"]
                raise ChatGPTUnreachable("OpenAI could not renew your ChatGPT sign-in a moment ago; "
                                         "try again in a minute.")
            try:
                data = _refresh(data, now())
            except ChatGPTUnreachable:
                _retry_after = now() + RETRY_AFTER
                if not still_works:
                    raise
                return tokens["access_token"]
            _write(data)
        return data["tokens"]["access_token"]


def credential() -> Callable[[], str]:
    """The api_key callable for the chatgpt provider; raises now when nobody is signed in,
    so a run stops before it starts rather than at its first model call."""
    if not _read().get("tokens"):
        raise ChatGPTAuthError(LOGIN_HINT)
    return access_token


def list_models() -> list[tuple[str, str]]:
    """(name, model ID) for each model the signed-in plan offers, in OpenAI's order."""
    response = requests.get(f"{API_BASE}/models", timeout=10,
                            headers={"Authorization": f"Bearer {access_token()}"})
    response.raise_for_status()
    models = [m for m in response.json().get("models", [])
              if isinstance(m, dict) and isinstance(m.get("slug"), str)
              and m.get("visibility") == "list" and m.get("supported_in_api", True)]
    models.sort(key=lambda m: m.get("priority") or 0)
    return [(m.get("display_name") or m["slug"], m["slug"]) for m in models]


# --- signing in and out --------------------------------------------------------------

class _Callback:
    """The first answer carrying this attempt's ``state``; stray or stale requests are ignored."""

    def __init__(self, state: str):
        self.state = state
        self.params: dict | None = None
        self.received = threading.Event()
        self._lock = threading.Lock()

    def accept(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url.strip())
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if parsed.path != CALLBACK_PATH or params.get("state") != self.state:
            return False
        with self._lock:
            if self.params is None:
                self.params = params
                self.received.set()
        return True


def _listen(callback: _Callback, port: int) -> http.server.HTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 5   # a connection that sends nothing cannot hold up the real answer

        def do_GET(self):  # noqa: N802 (http.server's name)
            ok = callback.accept(self.path)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            if ok:
                self.wfile.write(b"Return to the terminal to finish signing in to TradingAgents.\n")

        def log_message(self, *args):  # the URL carries the sign-in code
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    # A short poll interval lets the server stop promptly once the answer has arrived.
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return server


def _revoke(tokens: dict, client_id: str | None) -> bool:
    try:
        response = requests.post(REVOKE_URL, timeout=TIMEOUT, data={
            "token": tokens.get("refresh_token"), "token_type_hint": "refresh_token",
            "client_id": client_id,
        })
    except requests.RequestException:
        return False
    return response.status_code == 200


def sign_in(say: Callable[[str], None] = print, read_line: Callable[[], str] = input,
            timeout: float = 600, port: int = DEFAULT_PORT) -> str:
    """Sign in with ChatGPT and save the result; returns the account's email.

    The address to open is printed. The browser comes back to 127.0.0.1; when this
    machine is remote or in a container, paste the address the browser ends up on.
    The pasted line is read in a thread that can outlive this call, so sign in as the
    last prompt of a process (``tradingagents login chatgpt``)."""
    data = _read()
    host_id = _host_id(data)
    account = data.get("account") or {}
    client_id = account.get("client_id") or DYNAMIC_CLIENT_ID
    state, nonce, verifier = (_b64url(secrets.token_bytes(32)), _b64url(secrets.token_bytes(32)),
                              _b64url(secrets.token_bytes(64)))
    callback = _Callback(state)
    server = _listen(callback, port)
    try:
        redirect_uri = f"http://127.0.0.1:{server.server_address[1]}{CALLBACK_PATH}"
        params = {
            "client_id": client_id, "ext_agent_host_id": host_id, "response_type": "code",
            "redirect_uri": redirect_uri, "scope": SCOPE, "resource": API_BASE, "state": state,
            "nonce": nonce, "code_challenge_method": "S256",
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        }
        if client_id == DYNAMIC_CLIENT_ID:
            params["agent_name_hint"] = APP_NAME
        elif account.get("email"):
            params["login_hint"] = account["email"]
        say("Continue with ChatGPT: open this address and sign in with your Plus or Pro plan:")
        say(f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}")
        say("If the browser cannot reach this machine, paste here the address it ends up on.")

        def read_pasted():
            try:
                while not callback.received.is_set():
                    if not callback.accept(read_line()) and not callback.received.is_set():
                        say("That is not the address this sign-in ends on; paste the whole address.")
            except (EOFError, OSError):
                return

        threading.Thread(target=read_pasted, daemon=True).start()
        if not callback.received.wait(timeout):
            raise ChatGPTAuthError("Signing in with ChatGPT timed out; run `tradingagents login chatgpt` again.")
    finally:
        server.shutdown()
        server.server_close()

    answer = callback.params
    if answer.get("error"):
        raise ChatGPTAuthError(f"ChatGPT sign-in was not completed ({answer['error']}).")
    issued = answer.get("client_id") or client_id
    if issued == DYNAMIC_CLIENT_ID or (account.get("client_id") and issued != account["client_id"]):
        raise ChatGPTAuthError("ChatGPT sign-in did not register TradingAgents; run "
                               "`tradingagents logout chatgpt`, then sign in again.")
    keys = _signing_keys()
    body = _token_request({"grant_type": "authorization_code", "client_id": issued,
                           "code": answer.get("code", ""), "code_verifier": verifier,
                           "redirect_uri": redirect_uri, "resource": API_BASE},
                          "sign you in to ChatGPT", "sign in again")
    claims = _validated_claims(body.get("id_token") or "", issued, nonce, keys)
    if account.get("subject") and claims["sub"] != account["subject"]:
        raise ChatGPTAuthError(f"This machine is signed in as {account.get('email') or 'another account'}; "
                               "run `tradingagents logout chatgpt` first.")
    if PLAN_SCOPE not in (body.get("scope") or "").split():
        raise ChatGPTAuthError("ChatGPT did not allow TradingAgents to use your plan; "
                               "sign in again and approve plan usage.")
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked(AUTH_FILE):
        replaced = _read().get("tokens")
        _write({
            "host_id": host_id,
            "account": {"client_id": issued, "email": claims.get("email"), "subject": claims["sub"]},
            "tokens": _token_record(body, time.time()),
        })
    if replaced:
        _revoke(replaced, issued)
    return claims.get("email") or "your ChatGPT account"


def sign_out() -> str | None:
    """Revoke the sign-in at OpenAI and forget it, keeping only this host's id.
    Returns None when nobody was signed in, "revoked", or "forgotten" when OpenAI
    could not be reached to revoke it."""
    if not _read().get("tokens"):
        return None
    with locked(AUTH_FILE):
        data = _read()
        tokens = data.get("tokens")
        if not tokens:
            return None
        revoked = _revoke(tokens, (data.get("account") or {}).get("client_id"))
        _write({"host_id": _host_id(data)})
    return "revoked" if revoked else "forgotten"
