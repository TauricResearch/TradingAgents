"""Sign in with ChatGPT using an app-owned OAuth registration."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import queue
import secrets
import tempfile
import threading
import time
import urllib.parse
import uuid
import webbrowser
from collections.abc import Callable, Iterator
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
_TOKEN_SKEW_SECONDS = 60.0
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class OAuthError(RuntimeError):
    """An OAuth attempt did not produce a validated registration."""


class Registration(TypedDict):
    client_id: str
    issuer: str
    subject: str
    inference_enabled: bool


class CredentialRecord(TypedDict, total=False):
    client_id: str
    issuer: str
    subject: str
    inference_enabled: bool
    email: str | None
    ext_agent_host_id: str
    access_token: str | None
    refresh_token: str | None
    id_token: str | None
    scopes: list[str]
    expires_at: float
    rotation_pending: bool
    requires_reauthorization: bool


class StoredAuth(TypedDict):
    ext_agent_host_id: str
    registration: Registration | None
    selected_client_id: str | None
    accounts: dict[str, CredentialRecord]


@dataclass(frozen=True, slots=True)
class AuthResult:
    client_id: str
    issuer: str
    subject: str
    email: str | None
    access_token: str
    refresh_token: str | None
    id_token: str
    scopes: frozenset[str]
    inference_enabled: bool
    guidance: str | None
    expires_at: float


@dataclass(frozen=True, slots=True)
class SavedAccount:
    """A registration choice; client ID keeps equal-email registrations distinct."""

    client_id: str
    issuer: str
    subject: str
    email: str | None
    inference_enabled: bool
    requires_reauthorization: bool


@dataclass(frozen=True, slots=True)
class PinnedRegistration:
    """Stable identity for a graph's account, independent of later selection."""

    client_id: str
    issuer: str
    subject: str
    host_id: str
    discriminator: str


@dataclass(frozen=True, slots=True)
class LogoutResult:
    """Local logout result and whether the provider confirmed revocation."""

    client_id: str | None
    revocation_confirmed: bool


class ReauthorizationRequired(OAuthError):
    """Saved refresh credentials cannot safely be reused."""


class TemporaryAuthError(OAuthError):
    """A temporary provider or transport failure prevented renewal."""


@dataclass(frozen=True, slots=True)
class RegistrationSession:
    """A pinned account reference that reloads credentials only under the store lock."""

    store_path: Path
    registration: PinnedRegistration
    http_transport: httpx.BaseTransport | None = None

    def access_token(self) -> str:
        """Return a fresh access token for this pinned registration."""
        return _access_token(self.store_path, self.registration, self.http_transport)


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


def _default_store_path() -> Path:
    """Return the app-owned ChatGPT credential file."""
    return Path.home() / ".tradingagents" / "chatgpt" / "auth.json"


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Serialize credential reads and writes across threads and processes."""
    path = path.resolve()
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
    with thread_lock:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            path.parent.chmod(0o700)
            if path.parent.name == "chatgpt":
                path.parent.parent.chmod(0o700)
            if path.exists():
                path.chmod(0o600)
        lock_path = path.with_name(f"{path.name}.lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        if os.name != "nt":
            os.chmod(lock_path, 0o600)
        with os.fdopen(lock_fd, "r+b") as handle, _process_lock(handle):
            yield


@contextlib.contextmanager
def _process_lock(handle) -> Iterator[None]:
    """Hold one byte or inode lock, depending on the host operating system."""
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _new_auth() -> StoredAuth:
    """Create empty state with a persistent opaque host identifier."""
    return {
        "ext_agent_host_id": f"urn:uuid:{uuid.uuid4()}",
        "registration": None,
        "selected_client_id": None,
        "accounts": {},
    }


def _stored_auth(path: Path) -> StoredAuth:
    """Parse stored state and migrate the task-1 single-registration format."""
    if not path.exists():
        return _new_auth()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise OAuthError("Saved ChatGPT registration data is invalid.")
    data = raw
    host_id = data.get("ext_agent_host_id")
    if not isinstance(host_id, str) or not host_id.startswith("urn:uuid:"):
        raise OAuthError("Saved ChatGPT registration data is invalid.")
    raw_accounts = data.get("accounts")
    accounts: dict[str, CredentialRecord] = {}
    if isinstance(raw_accounts, dict):
        for client_id, raw_record in raw_accounts.items():
            if not isinstance(client_id, str) or not isinstance(raw_record, dict):
                raise OAuthError("Saved ChatGPT registration data is invalid.")
            if not _valid_registration(raw_record, client_id):
                raise OAuthError("Saved ChatGPT registration data is invalid.")
            accounts[client_id] = raw_record
    else:
        legacy = data.get("registration")
        if legacy is not None:
            if not isinstance(legacy, dict):
                raise OAuthError("Saved ChatGPT registration data is invalid.")
            legacy_client_id = legacy.get("client_id")
            if not _valid_registration(legacy, legacy_client_id):
                raise OAuthError("Saved ChatGPT registration data is invalid.")
            accounts[legacy_client_id] = {
                **legacy,
                "ext_agent_host_id": host_id,
                "access_token": None,
                "refresh_token": None,
                "id_token": None,
                "rotation_pending": False,
                "requires_reauthorization": True,
            }
    selected = data.get("selected_client_id")
    if selected is None and accounts:
        selected = next(iter(accounts))
    if not isinstance(selected, str) and selected is not None:
        raise OAuthError("Saved ChatGPT registration data is invalid.")
    if selected is not None and selected not in accounts:
        selected = None
    selected_record = accounts.get(selected) if selected is not None else None
    registration = _registration_view(selected_record)
    return {
        "ext_agent_host_id": host_id,
        "registration": registration,
        "selected_client_id": selected,
        "accounts": accounts,
    }


def _valid_registration(record: dict[str, object], client_id: str | None) -> bool:
    """Check the minimal identity fields at the JSON trust boundary."""
    return (
        isinstance(client_id, str)
        and record.get("client_id") == client_id
        and isinstance(record.get("issuer"), str)
        and isinstance(record.get("subject"), str)
        and isinstance(record.get("inference_enabled"), bool)
    )


def _registration_view(record: CredentialRecord | None) -> Registration | None:
    """Return the non-secret account identity compatible with task-1 readers."""
    if record is None:
        return None
    return {
        "client_id": record["client_id"],
        "issuer": record["issuer"],
        "subject": record["subject"],
        "inference_enabled": record["inference_enabled"],
    }


def _save(path: Path, data: StoredAuth) -> None:
    """Atomically persist credentials without suppressing permission errors."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
        if path.parent.name == "chatgpt":
            path.parent.parent.chmod(0o700)
    data["registration"] = _registration_view(
        data["accounts"].get(data["selected_client_id"])
        if data["selected_client_id"] is not None
        else None
    )
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if os.name != "nt":
            path.chmod(0o600)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _load_locked(path: Path) -> StoredAuth:
    """Load and migrate state while the caller holds the stable sidecar lock."""
    return _stored_auth(path)


def _commit_registration(path: Path, result: AuthResult, host_id: str) -> None:
    """Save a validated registration and its tokens as the selected account."""
    with _locked(path):
        state = _load_locked(path)
        account: CredentialRecord = {
            "client_id": result.client_id,
            "issuer": result.issuer,
            "subject": result.subject,
            "inference_enabled": result.inference_enabled,
            "email": result.email,
            "ext_agent_host_id": host_id,
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "id_token": result.id_token,
            "scopes": sorted(result.scopes),
            "expires_at": result.expires_at,
            "rotation_pending": False,
            "requires_reauthorization": result.refresh_token is None,
        }
        state["accounts"][result.client_id] = account
        state["selected_client_id"] = result.client_id
        _save(path, state)


def _pinned_registration(
    state: StoredAuth,
    client_id: str,
) -> PinnedRegistration:
    """Build a graph-safe identity without retaining an account-selection pointer."""
    record = state["accounts"].get(client_id)
    if record is None:
        raise OAuthError("The selected ChatGPT registration is unavailable.")
    return PinnedRegistration(
        client_id=client_id,
        issuer=record["issuer"],
        subject=record["subject"],
        host_id=record.get("ext_agent_host_id", state["ext_agent_host_id"]),
        discriminator=hashlib.sha256(client_id.encode()).hexdigest()[:24],
    )


def saved_accounts(*, store_path: Path | None = None) -> tuple[SavedAccount, ...]:
    """List registrations separately, keyed by client ID rather than email."""
    path = store_path or _default_store_path()
    with _locked(path):
        state = _load_locked(path)
        return tuple(
            SavedAccount(
                client_id=record["client_id"],
                issuer=record["issuer"],
                subject=record["subject"],
                email=record.get("email"),
                inference_enabled=record["inference_enabled"],
                requires_reauthorization=record.get("requires_reauthorization", False),
            )
            for record in state["accounts"].values()
        )


def pinned_session(
    *,
    store_path: Path | None = None,
    client_id: str | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> RegistrationSession:
    """Pin the selected or explicitly named account once for a graph run."""
    path = store_path or _default_store_path()
    with _locked(path):
        state = _load_locked(path)
        selected = client_id or state["selected_client_id"]
        if selected is None:
            raise OAuthError("No ChatGPT account is signed in.")
        registration = _pinned_registration(state, selected)
    return RegistrationSession(path, registration, http_transport)


def _clear_tokens(record: CredentialRecord) -> None:
    """Remove unusable tokens while leaving the registration identity intact."""
    record["access_token"] = None
    record["refresh_token"] = None
    record["id_token"] = None
    record["expires_at"] = 0.0
    record["rotation_pending"] = False
    record["requires_reauthorization"] = True


def _access_token(
    path: Path,
    registration: PinnedRegistration,
    transport: httpx.BaseTransport | None,
) -> str:
    """Reload and renew one pinned account while holding both store locks."""
    with _locked(path):
        state = _load_locked(path)
        record = state["accounts"].get(registration.client_id)
        if record is None or (
            record["issuer"] != registration.issuer
            or record["subject"] != registration.subject
        ):
            raise ReauthorizationRequired("The pinned ChatGPT registration is no longer available.")
        if record.get("rotation_pending", False):
            _clear_tokens(record)
            _save(path, state)
            raise ReauthorizationRequired(
                "A ChatGPT token rotation was interrupted; sign in again to continue."
            )
        access = record.get("access_token")
        refresh = record.get("refresh_token")
        if record.get("requires_reauthorization", False) or not access or not refresh:
            raise ReauthorizationRequired("Sign in again to renew this ChatGPT account.")
        if record.get("expires_at", 0.0) > time.time() + _TOKEN_SKEW_SECONDS:
            return access

        try:
            with httpx.Client(timeout=10.0, transport=transport) as client:
                discovery_response = client.get(DISCOVERY_URL)
                discovery_response.raise_for_status()
                discovery = discovery_response.json()
        except httpx.RequestError as exc:
            raise TemporaryAuthError("ChatGPT token renewal discovery failed.") from exc
        except httpx.HTTPStatusError as exc:
            raise TemporaryAuthError("ChatGPT token renewal could not reach discovery.") from exc

        record["rotation_pending"] = True
        _save(path, state)
        try:
            with httpx.Client(timeout=10.0, transport=transport) as client:
                response = client.post(
                    discovery["token_endpoint"],
                    data={
                        "grant_type": "refresh_token",
                        "client_id": registration.client_id,
                        "refresh_token": refresh,
                        "resource": RESOURCE,
                    },
                )
        except httpx.RequestError as exc:
            raise ReauthorizationRequired(
                "ChatGPT token renewal may have completed; sign in again rather than replaying it."
            ) from exc

        if response.status_code in (408, 429) or response.status_code >= 500:
            record["rotation_pending"] = False
            _save(path, state)
            raise TemporaryAuthError("ChatGPT token renewal is temporarily unavailable.")
        if response.status_code >= 400:
            _clear_tokens(record)
            _save(path, state)
            raise ReauthorizationRequired("ChatGPT rejected the saved refresh grant; sign in again.")

        tokens = response.json()
        new_access = tokens.get("access_token")
        new_refresh = tokens.get("refresh_token", refresh)
        expires_in = tokens.get("expires_in", 3600)
        granted_scope = tokens.get("scope")
        if (
            not isinstance(new_access, str)
            or not new_access
            or not isinstance(new_refresh, str)
            or not new_refresh
            or not isinstance(expires_in, (int, float))
            or isinstance(expires_in, bool)
            or (granted_scope is not None and not isinstance(granted_scope, str))
        ):
            raise ReauthorizationRequired(
                "ChatGPT returned an uncertain token rotation; sign in again."
            )
        record["access_token"] = new_access
        record["refresh_token"] = new_refresh
        record["id_token"] = tokens.get("id_token", record.get("id_token"))
        if granted_scope is not None:
            record["scopes"] = sorted(granted_scope.split())
            record["inference_enabled"] = PLAN_SCOPE in record["scopes"]
        record["expires_at"] = time.time() + expires_in
        record["rotation_pending"] = False
        record["requires_reauthorization"] = False
        _save(path, state)
        return new_access


def logout(
    *,
    store_path: Path | None = None,
    client_id: str | None = None,
    http_transport: httpx.BaseTransport | None = None,
) -> LogoutResult:
    """Revoke the pinned/selected account when possible and always clear locally."""
    path = store_path or _default_store_path()
    with _locked(path):
        state = _load_locked(path)
        selected = client_id or state["selected_client_id"]
        if selected is None or selected not in state["accounts"]:
            return LogoutResult(None, True)
        record = state["accounts"][selected]
        token = record.get("refresh_token") or record.get("access_token")
        confirmed = token is None
        if token is not None:
            try:
                with httpx.Client(timeout=10.0, transport=http_transport) as client:
                    discovery_response = client.get(DISCOVERY_URL)
                    discovery_response.raise_for_status()
                    endpoint = discovery_response.json().get("revocation_endpoint")
                    if endpoint:
                        response = client.post(
                            endpoint,
                            data={
                                "client_id": selected,
                                "token": token,
                                "token_type_hint": (
                                    "refresh_token"
                                    if record.get("refresh_token")
                                    else "access_token"
                                ),
                            },
                        )
                        confirmed = response.status_code < 400
            except (httpx.HTTPError, KeyError, ValueError):
                confirmed = False
        _clear_tokens(record)
        _save(path, state)
        return LogoutResult(selected, confirmed)


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
) -> tuple[str, str, str | None]:
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
    email = claims.get("email")
    return issuer, subject, email if isinstance(email, str) else None


def sign_in(
    *,
    store_path: Path | None = None,
    enable_plan_use: bool = False,
    account_client_id: str | None = None,
    add_account: bool = False,
    callback_timeout: float = CALLBACK_TIMEOUT,
    browser_open: Callable[[str], bool] = webbrowser.open,
    http_transport: httpx.BaseTransport | None = None,
) -> AuthResult:
    """Run browser sign-in and persist only the validated registration state."""
    if callback_timeout <= 0:
        raise OAuthError("ChatGPT callback timeout must be positive.")
    callback_timeout = min(callback_timeout, CALLBACK_TIMEOUT)
    if add_account and account_client_id is not None:
        raise OAuthError("Choose either an existing account or add a new account.")
    auth_path = store_path or _default_store_path()
    with _locked(auth_path):
        saved = _load_locked(auth_path)
        if not auth_path.exists():
            _save(auth_path, saved)
    selected_id = (
        account_client_id
        if account_client_id is not None
        else saved["selected_client_id"]
    )
    if not add_account and selected_id is not None and selected_id not in saved["accounts"]:
        raise OAuthError("The requested ChatGPT registration is not saved.")
    account = (
        saved["accounts"].get(selected_id)
        if selected_id is not None and not add_account
        else None
    )
    registration = _registration_view(account)
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
        validated_issuer, subject, email = _verify_identity(
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
        expires_in = tokens.get("expires_in", 3600)
        if (
            not isinstance(expires_in, (int, float))
            or isinstance(expires_in, bool)
            or expires_in <= 0
        ):
            raise OAuthError("ChatGPT token response expiry is invalid.")
        result = AuthResult(
            client_id=client_id,
            issuer=validated_issuer,
            subject=subject,
            email=email,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            id_token=identity,
            scopes=scopes,
            inference_enabled=enabled,
            guidance=guidance,
            expires_at=time.time() + expires_in,
        )
        _commit_registration(auth_path, result, saved["ext_agent_host_id"])
        return result
