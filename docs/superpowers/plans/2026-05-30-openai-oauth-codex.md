# OpenAI OAuth (Codex "Sign in with ChatGPT") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere il provider `openai-oauth` che autentica via OAuth PKCE con l'account ChatGPT (flusso Codex) e instrada le chiamate al backend Codex, senza richiedere `OPENAI_API_KEY`.

**Architecture:** Nuovo package `tradingagents/llm_clients/oauth/` (PKCE puro, login con callback locale, token store con refresh). `OpenAIClient` riconosce `openai-oauth`, punta a `https://chatgpt.com/backend-api/codex`, usa un `httpx.Auth` che inietta il bearer fresco e fa refresh+retry su 401. CLI e factory aliasano `openai-oauth` su `openai` per modelli/capabilities.

**Tech Stack:** Python 3.13, langchain-openai (`ChatOpenAI`, Responses API), `httpx`, `http.server`, pytest.

---

## File Structure

- Create: `tradingagents/llm_clients/oauth/__init__.py` — API pubblica (`login`, `OAuthTokenStore`, `ensure_token`, eccezioni).
- Create: `tradingagents/llm_clients/oauth/pkce.py` — PKCE puro + build authorize URL + costanti OAuth.
- Create: `tradingagents/llm_clients/oauth/store.py` — `OAuthTokenStore`, refresh, decode account_id.
- Create: `tradingagents/llm_clients/oauth/flow.py` — login con callback server localhost:1455.
- Create: `tradingagents/llm_clients/oauth/auth.py` — `CodexOAuth(httpx.Auth)` (inject bearer + refresh on 401).
- Modify: `tradingagents/llm_clients/openai_client.py` — ramo `openai-oauth`.
- Modify: `tradingagents/llm_clients/factory.py` — dispatch `openai-oauth`.
- Modify: `tradingagents/llm_clients/api_key_env.py` — `openai-oauth: None`.
- Modify: `tradingagents/llm_clients/validators.py` — alias `openai-oauth`→`openai`.
- Modify: `tradingagents/llm_clients/model_catalog.py` — alias in `get_model_options`.
- Modify: `cli/utils.py` — provider nel dropdown + `ensure_oauth_login`.
- Modify: `cli/main.py` — branch flusso + comando `login`.
- Create: `tests/test_oauth_pkce.py`, `tests/test_oauth_store.py`, `tests/test_oauth_auth.py`, `tests/test_oauth_client.py`, `tests/test_oauth_cli.py`.
- Modify: `README.md`, `.env.example`.

Costanti OAuth condivise (definite una volta in `pkce.py`, importate altrove):

```python
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_HEADERS = {
    "OpenAI-Beta": "responses=experimental",
    "originator": "codex_cli_rs",
}
```

---

## Task 1: PKCE puro e authorize URL

**Files:**
- Create: `tradingagents/llm_clients/oauth/__init__.py` (vuoto per ora)
- Create: `tradingagents/llm_clients/oauth/pkce.py`
- Test: `tests/test_oauth_pkce.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_pkce.py
import base64
import hashlib
from urllib.parse import urlparse, parse_qs

from tradingagents.llm_clients.oauth import pkce


def test_challenge_is_s256_of_verifier():
    verifier, challenge = pkce.generate_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected
    assert 43 <= len(verifier) <= 128
    assert "=" not in challenge


def test_authorize_url_has_required_params():
    url = pkce.build_authorize_url("CHALLENGE", "STATE")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == [pkce.OAUTH_CLIENT_ID]
    assert q["redirect_uri"] == [pkce.OAUTH_REDIRECT_URI]
    assert q["code_challenge"] == ["CHALLENGE"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["STATE"]
    assert "openid" in q["scope"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_pkce.py -v`
Expected: FAIL (ModuleNotFoundError: oauth.pkce)

- [ ] **Step 3: Write minimal implementation**

```python
# tradingagents/llm_clients/oauth/pkce.py
"""PKCE primitives and OAuth constants for the Codex ChatGPT login flow."""
from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import urlencode

OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_HEADERS = {
    "OpenAI-Beta": "responses=experimental",
    "originator": "codex_cli_rs",
}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = _b64url(os.urandom(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def generate_state() -> str:
    return _b64url(os.urandom(24))


def build_authorize_url(code_challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
```

Create empty `tradingagents/llm_clients/oauth/__init__.py` (single blank line).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_pkce.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/oauth/__init__.py tradingagents/llm_clients/oauth/pkce.py tests/test_oauth_pkce.py
git commit -m "feat(oauth): PKCE primitives and authorize URL"
```

---

## Task 2: Token store (persist, expiry, account_id, refresh)

**Files:**
- Create: `tradingagents/llm_clients/oauth/store.py`
- Test: `tests/test_oauth_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_store.py
import base64
import json
import stat
import time

import pytest

from tradingagents.llm_clients.oauth import store as store_mod
from tradingagents.llm_clients.oauth.store import OAuthTokenStore, OAuthNotLoggedIn


def _fake_id_token(account_id="acct_123"):
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": account_id}}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.sig"


def _tokens(expires_in=3600):
    return {
        "id_token": _fake_id_token(),
        "access_token": "ACCESS",
        "refresh_token": "REFRESH",
        "expires_in": expires_in,
    }


def test_save_load_roundtrip_and_permissions(tmp_path):
    path = tmp_path / "oauth_openai.json"
    s = OAuthTokenStore(path=path)
    s.save(_tokens())
    loaded = OAuthTokenStore(path=path).load()
    assert loaded.access_token == "ACCESS"
    assert loaded.refresh_token == "REFRESH"
    assert loaded.account_id == "acct_123"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_load_missing_raises(tmp_path):
    with pytest.raises(OAuthNotLoggedIn):
        OAuthTokenStore(path=tmp_path / "nope.json").load()


def test_is_expired_uses_skew(tmp_path):
    s = OAuthTokenStore(path=tmp_path / "t.json")
    s.save(_tokens(expires_in=100))  # scade tra 100s
    tok = s.load()
    assert tok.is_expired(skew=300) is True   # entro lo skew -> da rinfrescare
    assert tok.is_expired(skew=10) is False


def test_refresh_calls_token_endpoint(tmp_path, monkeypatch):
    path = tmp_path / "t.json"
    s = OAuthTokenStore(path=path)
    s.save(_tokens(expires_in=1))

    calls = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"id_token": _fake_id_token(), "access_token": "NEW",
                    "refresh_token": "REFRESH2", "expires_in": 3600}
        def raise_for_status(self):
            pass

    def fake_post(url, data=None, timeout=None):
        calls["url"] = url
        calls["data"] = data
        return FakeResp()

    monkeypatch.setattr(store_mod.httpx, "post", fake_post)
    new_tok = s.refresh()
    assert calls["url"] == store_mod.OAUTH_TOKEN_URL
    assert calls["data"]["grant_type"] == "refresh_token"
    assert calls["data"]["refresh_token"] == "REFRESH"
    assert new_tok.access_token == "NEW"
    assert s.load().access_token == "NEW"  # persistito
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_store.py -v`
Expected: FAIL (ModuleNotFoundError: oauth.store)

- [ ] **Step 3: Write minimal implementation**

```python
# tradingagents/llm_clients/oauth/store.py
"""Persistence + refresh for Codex OAuth tokens."""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from .pkce import OAUTH_CLIENT_ID, OAUTH_TOKEN_URL


class OAuthError(Exception):
    """Base class for OAuth errors."""


class OAuthNotLoggedIn(OAuthError):
    """No stored token / store missing or unreadable."""


class OAuthRefreshFailed(OAuthError):
    """Refresh token rejected; user must log in again."""


def default_store_path() -> Path:
    override = os.environ.get("TRADINGAGENTS_OAUTH_PATH")
    if override:
        return Path(override)
    home = Path(os.path.expanduser("~")) / ".tradingagents"
    return home / "oauth_openai.json"


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _account_id_from_id_token(id_token: str) -> Optional[str]:
    try:
        payload = json.loads(_b64url_decode(id_token.split(".")[1]))
    except (ValueError, IndexError, json.JSONDecodeError):
        return None
    auth = payload.get("https://api.openai.com/auth", {})
    return auth.get("chatgpt_account_id")


@dataclass
class StoredTokens:
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: float
    account_id: Optional[str]

    def is_expired(self, skew: int = 300) -> bool:
        return time.time() >= (self.expires_at - skew)


class OAuthTokenStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_store_path()

    def save(self, tokens: dict) -> StoredTokens:
        expires_at = time.time() + float(tokens.get("expires_in", 3600))
        record = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "id_token": tokens["id_token"],
            "expires_at": expires_at,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)
        return self._to_tokens(record)

    def load(self) -> StoredTokens:
        try:
            record = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise OAuthNotLoggedIn(
                "Nessun login OAuth trovato. Esegui 'tradingagents login'."
            ) from exc
        return self._to_tokens(record)

    def _to_tokens(self, record: dict) -> StoredTokens:
        return StoredTokens(
            access_token=record["access_token"],
            refresh_token=record["refresh_token"],
            id_token=record["id_token"],
            expires_at=record["expires_at"],
            account_id=_account_id_from_id_token(record["id_token"]),
        )

    def refresh(self) -> StoredTokens:
        current = self.load()
        resp = httpx.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": current.refresh_token,
                "client_id": OAUTH_CLIENT_ID,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise OAuthRefreshFailed(
                "Refresh del token fallito. Esegui di nuovo 'tradingagents login'."
            )
        data = resp.json()
        # Il refresh può non restituire un nuovo refresh_token: riusa il vecchio.
        data.setdefault("refresh_token", current.refresh_token)
        return self.save(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/oauth/store.py tests/test_oauth_store.py
git commit -m "feat(oauth): token store with refresh and account_id decode"
```

---

## Task 3: httpx auth (inject bearer + refresh on 401)

**Files:**
- Create: `tradingagents/llm_clients/oauth/auth.py`
- Test: `tests/test_oauth_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_auth.py
import time

import httpx

from tradingagents.llm_clients.oauth.auth import CodexOAuth
from tradingagents.llm_clients.oauth.store import StoredTokens


class FakeStore:
    def __init__(self, tokens, refreshed):
        self._tokens = tokens
        self._refreshed = refreshed
        self.refresh_calls = 0

    def load(self):
        return self._tokens

    def refresh(self):
        self.refresh_calls += 1
        self._tokens = self._refreshed
        return self._tokens


def _tok(access, exp_offset=3600):
    return StoredTokens(access, "R", "I", time.time() + exp_offset, "acct")


def test_injects_bearer_from_store():
    store = FakeStore(_tok("ACCESS1"), _tok("ACCESS2"))
    auth = CodexOAuth(store)
    request = httpx.Request("GET", "https://example.com")
    flow = auth.auth_flow(request)
    sent = next(flow)
    assert sent.headers["Authorization"] == "Bearer ACCESS1"


def test_proactive_refresh_when_expired():
    store = FakeStore(_tok("OLD", exp_offset=10), _tok("FRESH"))
    auth = CodexOAuth(store)
    sent = next(auth.auth_flow(httpx.Request("GET", "https://x")))
    assert store.refresh_calls == 1
    assert sent.headers["Authorization"] == "Bearer FRESH"


def test_refresh_and_retry_on_401():
    store = FakeStore(_tok("OLD"), _tok("FRESH"))
    auth = CodexOAuth(store)
    flow = auth.auth_flow(httpx.Request("GET", "https://x"))
    first = next(flow)
    assert first.headers["Authorization"] == "Bearer OLD"
    retried = flow.send(httpx.Response(401, request=first))
    assert store.refresh_calls == 1
    assert retried.headers["Authorization"] == "Bearer FRESH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_auth.py -v`
Expected: FAIL (ModuleNotFoundError: oauth.auth)

- [ ] **Step 3: Write minimal implementation**

```python
# tradingagents/llm_clients/oauth/auth.py
"""httpx.Auth that injects the Codex OAuth bearer and refreshes on 401."""
from __future__ import annotations

import httpx


class CodexOAuth(httpx.Auth):
    """Inietta il bearer fresco; refresh proattivo se scaduto e su 401.

    Lo `store` deve esporre ``load() -> StoredTokens`` e ``refresh() ->
    StoredTokens``. Tenuto generico per testabilità.
    """

    def __init__(self, store, skew: int = 300):
        self._store = store
        self._skew = skew

    def _current_access(self) -> str:
        tokens = self._store.load()
        if tokens.is_expired(skew=self._skew):
            tokens = self._store.refresh()
        return tokens.access_token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._current_access()}"
        response = yield request
        if response.status_code == 401:
            fresh = self._store.refresh().access_token
            request.headers["Authorization"] = f"Bearer {fresh}"
            yield request
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_auth.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/oauth/auth.py tests/test_oauth_auth.py
git commit -m "feat(oauth): httpx auth with proactive refresh and 401 retry"
```

---

## Task 4: Login flow (callback server) + package API

**Files:**
- Create: `tradingagents/llm_clients/oauth/flow.py`
- Modify: `tradingagents/llm_clients/oauth/__init__.py`
- Test: `tests/test_oauth_flow.py`

- [ ] **Step 1: Write the failing test** (testa lo scambio code→token, isolando il server)

```python
# tests/test_oauth_flow.py
from tradingagents.llm_clients.oauth import flow as flow_mod


def test_exchange_code_posts_pkce(monkeypatch, tmp_path):
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"id_token": "h.e.s", "access_token": "A",
                    "refresh_token": "R", "expires_in": 3600}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return FakeResp()

    monkeypatch.setattr(flow_mod.httpx, "post", fake_post)
    tokens = flow_mod.exchange_code("THECODE", "VERIFIER")
    assert captured["url"] == flow_mod.OAUTH_TOKEN_URL
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "THECODE"
    assert captured["data"]["code_verifier"] == "VERIFIER"
    assert tokens["access_token"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_flow.py -v`
Expected: FAIL (ModuleNotFoundError: oauth.flow)

- [ ] **Step 3: Write minimal implementation**

```python
# tradingagents/llm_clients/oauth/flow.py
"""Browser-based PKCE login: local callback server on localhost:1455."""
from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

from .pkce import (
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_TOKEN_URL,
    build_authorize_url,
    generate_pkce_pair,
    generate_state,
)
from .store import OAuthTokenStore, OAuthError, StoredTokens

_CALLBACK_PORT = 1455
_SUCCESS_HTML = (
    b"<html><body><h2>Login completato.</h2>"
    b"<p>Puoi chiudere questa scheda e tornare al terminale.</p></body></html>"
)


class OAuthLoginError(OAuthError):
    """Login flow non completato (annullato, timeout, porta occupata, CSRF)."""


def exchange_code(code: str, code_verifier: str) -> dict:
    resp = httpx.post(
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise OAuthLoginError(f"Scambio token fallito (HTTP {resp.status_code}).")
    return resp.json()


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict = {}
    expected_state: str = ""

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_SUCCESS_HTML)
        type(self).result = {
            "code": params.get("code", [None])[0],
            "state": params.get("state", [None])[0],
            "error": params.get("error", [None])[0],
        }

    def log_message(self, *args):  # silenzia il logging di default
        pass


def login(
    open_browser: bool = True,
    timeout: int = 180,
    store: Optional[OAuthTokenStore] = None,
) -> StoredTokens:
    store = store or OAuthTokenStore()
    verifier, challenge = generate_pkce_pair()
    state = generate_state()
    url = build_authorize_url(challenge, state)

    _CallbackHandler.result = {}
    _CallbackHandler.expected_state = state
    try:
        server = HTTPServer(("localhost", _CALLBACK_PORT), _CallbackHandler)
    except OSError as exc:
        raise OAuthLoginError(
            f"Porta {_CALLBACK_PORT} occupata: chiudi il processo che la usa e riprova."
        ) from exc

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if open_browser:
        webbrowser.open(url)
    else:
        print(f"Apri questo URL nel browser per autenticarti:\n{url}")

    try:
        server.timeout = timeout
        deadline_handle = threading.Event()
        # Attendi finché arriva il callback o scade il timeout.
        waited = 0.0
        while not _CallbackHandler.result and waited < timeout:
            server.handle_request()  # gestisce una richiesta (callback o favicon)
            waited += 0.1
    finally:
        server.server_close()

    result = _CallbackHandler.result
    if not result or result.get("error"):
        raise OAuthLoginError("Login annullato o fallito.")
    if result.get("state") != state:
        raise OAuthLoginError("State non valido (possibile CSRF). Login annullato.")
    if not result.get("code"):
        raise OAuthLoginError("Nessun authorization code ricevuto.")

    tokens = exchange_code(result["code"], verifier)
    return store.save(tokens)
```

Aggiorna il package `__init__.py`:

```python
# tradingagents/llm_clients/oauth/__init__.py
"""OAuth (Codex "Sign in with ChatGPT") per TradingAgents."""
from .flow import login, OAuthLoginError, exchange_code
from .store import (
    OAuthTokenStore,
    StoredTokens,
    OAuthError,
    OAuthNotLoggedIn,
    OAuthRefreshFailed,
    default_store_path,
)
from .auth import CodexOAuth
from .pkce import CODEX_BASE_URL, CODEX_HEADERS


def ensure_token(store: OAuthTokenStore | None = None) -> StoredTokens:
    """Carica i token; se scaduti fa refresh; se assenti solleva OAuthNotLoggedIn."""
    store = store or OAuthTokenStore()
    tokens = store.load()  # solleva OAuthNotLoggedIn se manca
    if tokens.is_expired():
        tokens = store.refresh()
    return tokens


__all__ = [
    "login", "exchange_code", "ensure_token", "CodexOAuth",
    "OAuthTokenStore", "StoredTokens", "default_store_path",
    "OAuthError", "OAuthNotLoggedIn", "OAuthRefreshFailed", "OAuthLoginError",
    "CODEX_BASE_URL", "CODEX_HEADERS",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_flow.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/oauth/flow.py tradingagents/llm_clients/oauth/__init__.py tests/test_oauth_flow.py
git commit -m "feat(oauth): browser PKCE login flow with local callback server"
```

---

## Task 5: Cablare `OpenAIClient` per `openai-oauth`

**Files:**
- Modify: `tradingagents/llm_clients/openai_client.py`
- Test: `tests/test_oauth_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_client.py
import time

import pytest

from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.oauth import store as store_mod


@pytest.fixture
def logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "o.json"))
    s = store_mod.OAuthTokenStore()
    # id_token con account_id
    import base64, json
    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct_xyz"}}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    s.save({"id_token": f"h.{body}.s", "access_token": "A",
            "refresh_token": "R", "expires_in": 3600})
    return s


def test_oauth_client_targets_codex_backend(logged_in):
    client = OpenAIClient("gpt-5.4", provider="openai-oauth")
    llm = client.get_llm()
    assert "chatgpt.com/backend-api/codex" in str(llm.openai_api_base)
    # header account-id presente
    headers = llm.default_headers or {}
    assert headers.get("chatgpt-account-id") == "acct_xyz"
    assert llm.use_responses_api is True


def test_oauth_client_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "missing.json"))
    from tradingagents.llm_clients.oauth import OAuthNotLoggedIn
    with pytest.raises(OAuthNotLoggedIn):
        OpenAIClient("gpt-5.4", provider="openai-oauth").get_llm()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_client.py -v`
Expected: FAIL (provider openai-oauth non gestito; base_url errato)

- [ ] **Step 3: Write minimal implementation**

In `tradingagents/llm_clients/openai_client.py`, aggiungi l'import in cima (dopo gli altri import locali):

```python
from .oauth import ensure_token, CodexOAuth, OAuthTokenStore
from .oauth import CODEX_BASE_URL, CODEX_HEADERS
```

In `OpenAIClient.get_llm()`, subito dopo `llm_kwargs = {"model": self.model}`, aggiungi il ramo OAuth **prima** del blocco `if self.provider in _PROVIDER_BASE_URL:`:

```python
        if self.provider == "openai-oauth":
            import httpx
            store = OAuthTokenStore()
            tokens = ensure_token(store)  # solleva OAuthNotLoggedIn se assente
            auth = CodexOAuth(store)
            llm_kwargs["base_url"] = self.base_url or CODEX_BASE_URL
            llm_kwargs["api_key"] = "oauth"  # placeholder; auth reale via httpx
            llm_kwargs["use_responses_api"] = True
            llm_kwargs["http_client"] = httpx.Client(auth=auth)
            llm_kwargs["http_async_client"] = httpx.AsyncClient(auth=auth)
            headers = dict(CODEX_HEADERS)
            if tokens.account_id:
                headers["chatgpt-account-id"] = tokens.account_id
            llm_kwargs["default_headers"] = headers
            for key in _PASSTHROUGH_KWARGS:
                if key in self.kwargs and key not in llm_kwargs:
                    llm_kwargs[key] = self.kwargs[key]
            return NormalizedChatOpenAI(**llm_kwargs)
```

Nota: il ramo `if self.provider == "openai": llm_kwargs["use_responses_api"] = True` resta invariato; `openai-oauth` ritorna prima.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/openai_client.py tests/test_oauth_client.py
git commit -m "feat(oauth): route openai-oauth provider to Codex backend with refreshing auth"
```

---

## Task 6: factory, api_key_env, validators, model_catalog alias

**Files:**
- Modify: `tradingagents/llm_clients/factory.py`
- Modify: `tradingagents/llm_clients/api_key_env.py`
- Modify: `tradingagents/llm_clients/validators.py`
- Modify: `tradingagents/llm_clients/model_catalog.py`
- Test: `tests/test_oauth_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_wiring.py
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.validators import validate_model
from tradingagents.llm_clients.model_catalog import get_model_options


def test_factory_dispatches_openai_oauth():
    client = create_llm_client("openai-oauth", "gpt-5.4")
    assert isinstance(client, OpenAIClient)
    assert client.provider == "openai-oauth"


def test_openai_oauth_requires_no_env_key():
    assert get_api_key_env("openai-oauth") is None


def test_openai_oauth_validates_like_openai():
    assert validate_model("openai-oauth", "gpt-5.4") is True
    assert validate_model("openai-oauth", "not-a-model") is False


def test_model_options_alias():
    assert get_model_options("openai-oauth", "deep") == get_model_options("openai", "deep")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_wiring.py -v`
Expected: FAIL (factory non gestisce openai-oauth; KeyError model_options)

- [ ] **Step 3: Write minimal implementation**

`factory.py`: aggiungi `"openai-oauth"` alla tupla `_OPENAI_COMPATIBLE`:

```python
_OPENAI_COMPATIBLE = (
    "openai", "openai-oauth", "xai", "deepseek",
    "qwen", "qwen-cn",
    "glm", "glm-cn",
    "minimax", "minimax-cn",
    "ollama", "openrouter",
)
```

`api_key_env.py`: aggiungi nella mappa `PROVIDER_API_KEY_ENV` (dopo `"openai"`):

```python
    # OAuth (Sign in with ChatGPT): nessuna env key, auth via token store.
    "openai-oauth": None,
```

`validators.py`: normalizza l'alias all'inizio di `validate_model`:

```python
def validate_model(provider: str, model: str) -> bool:
    provider_lower = provider.lower()
    if provider_lower == "openai-oauth":
        provider_lower = "openai"

    if provider_lower in ("ollama", "openrouter"):
        return True
    if provider_lower not in VALID_MODELS:
        return True
    return model in VALID_MODELS[provider_lower]
```

`model_catalog.py`: alias in `get_model_options`:

```python
def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """Return shared model options for a provider and selection mode."""
    key = provider.lower()
    if key == "openai-oauth":
        key = "openai"
    return MODEL_OPTIONS[key][mode]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_wiring.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tradingagents/llm_clients/factory.py tradingagents/llm_clients/api_key_env.py tradingagents/llm_clients/validators.py tradingagents/llm_clients/model_catalog.py tests/test_oauth_wiring.py
git commit -m "feat(oauth): wire openai-oauth into factory, validators, catalog"
```

---

## Task 7: CLI (dropdown provider + ensure_oauth_login + comando login)

**Files:**
- Modify: `cli/utils.py`
- Modify: `cli/main.py`
- Test: `tests/test_oauth_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_oauth_cli.py
from cli import utils as cli_utils


def test_provider_dropdown_includes_oauth(monkeypatch):
    captured = {}

    class FakeQ:
        def ask(self):
            return ("openai-oauth", None)

    def fake_select(*a, **k):
        captured["choices"] = k.get("choices") or (a[1] if len(a) > 1 else None)
        return FakeQ()

    monkeypatch.setattr(cli_utils.questionary, "select", fake_select)
    provider, url = cli_utils.select_llm_provider()
    assert provider == "openai-oauth"
    titles = [c.title for c in captured["choices"]]
    assert any("ChatGPT OAuth" in t for t in titles)


def test_ensure_oauth_login_triggers_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_OAUTH_PATH", str(tmp_path / "o.json"))
    called = {"login": 0}

    def fake_login(**kwargs):
        called["login"] += 1
        class T: account_id = "acct"
        return T()

    monkeypatch.setattr(cli_utils, "oauth_login", fake_login)
    cli_utils.ensure_oauth_login("openai-oauth")
    assert called["login"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_oauth_cli.py -v`
Expected: FAIL (voce dropdown assente; `ensure_oauth_login`/`oauth_login` non definiti)

- [ ] **Step 3: Write minimal implementation**

`cli/utils.py` — aggiungi import in cima (vicino agli altri import del package):

```python
from tradingagents.llm_clients.oauth import (
    login as oauth_login,
    ensure_token,
    OAuthNotLoggedIn,
)
```

`cli/utils.py` — in `select_llm_provider`, aggiungi la voce subito dopo `("OpenAI", "openai", "https://api.openai.com/v1"),`:

```python
        ("OpenAI (ChatGPT OAuth)", "openai-oauth", None),
```

`cli/utils.py` — aggiungi la funzione (dopo `ensure_api_key`):

```python
def ensure_oauth_login(provider: str):
    """Per 'openai-oauth': garantisce un token valido, altrimenti avvia il login.

    Ritorna i token (con account_id) o esce con messaggio se l'utente annulla.
    """
    if provider.lower() != "openai-oauth":
        return None
    try:
        return ensure_token()
    except OAuthNotLoggedIn:
        console.print(
            "\n[yellow]Nessun login ChatGPT trovato. Apro il browser per "
            "l'autenticazione OAuth...[/yellow]"
        )
        try:
            tokens = oauth_login()
        except Exception as exc:  # OAuthLoginError e simili
            console.print(f"[red]Login fallito: {exc}[/red]")
            exit(1)
        console.print("[green]Login completato.[/green]")
        return tokens
```

`cli/main.py` — nel flusso interattivo, dopo `ensure_api_key(selected_llm_provider)` (riga ~583), aggiungi:

```python
    if selected_llm_provider == "openai-oauth":
        ensure_oauth_login(selected_llm_provider)
```

e assicurati che `ensure_oauth_login` sia importato da `cli.utils` insieme alle altre funzioni.

`cli/main.py` — aggiungi un comando typer dedicato. Individua l'oggetto `app = typer.Typer(...)` e aggiungi:

```python
@app.command()
def login(no_browser: bool = typer.Option(False, "--no-browser",
          help="Stampa l'URL invece di aprire il browser")):
    """Autenticati con il tuo account ChatGPT (OAuth, provider openai-oauth)."""
    from tradingagents.llm_clients.oauth import login as do_login
    tokens = do_login(open_browser=not no_browser)
    acct = tokens.account_id or "(sconosciuto)"
    typer.echo(f"Login completato. Account: {acct}")
```

Nota: il comando interattivo principale esistente potrebbe essere registrato come `@app.command()` di default; se l'app usa un singolo callback, aggiungere `login` come comando separato è compatibile (typer supporta più comandi).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_oauth_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run full suite + commit**

Run: `.venv/bin/pytest -q`
Expected: tutta la suite passa (vecchi test inclusi).

```bash
git add cli/utils.py cli/main.py tests/test_oauth_cli.py
git commit -m "feat(oauth): CLI provider option, auto-login, and 'login' command"
```

---

## Task 8: Documentazione (README + .env.example)

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Aggiorna `.env.example`** — aggiungi sotto la sezione LLM Providers:

```
# Sign in with ChatGPT (OAuth, provider "openai-oauth"): nessuna API key.
# Esegui `tradingagents login` o scegli "OpenAI (ChatGPT OAuth)" nella CLI.
# Override opzionale del path del token store:
#TRADINGAGENTS_OAUTH_PATH=~/.tradingagents/oauth_openai.json
```

- [ ] **Step 2: Aggiorna `README.md`** — nella sezione "Required APIs", dopo il blocco `export`, aggiungi:

```markdown
#### Sign in with ChatGPT (OAuth)

In alternativa alla `OPENAI_API_KEY`, puoi usare il tuo abbonamento ChatGPT
(Plus/Pro) con il provider `openai-oauth`:

```bash
tradingagents login          # apre il browser per l'autenticazione OAuth
tradingagents                # poi scegli "OpenAI (ChatGPT OAuth)"
```

I token sono salvati in `~/.tradingagents/oauth_openai.json` (permessi 0600)
e rinnovati automaticamente. Le chiamate passano per il backend Codex di
ChatGPT. Funzionalità community/non ufficiale: gli endpoint non sono
documentati ufficialmente da OpenAI e l'uso è soggetto ai loro Termini.
```

- [ ] **Step 3: Commit**

```bash
git add README.md .env.example
git commit -m "docs(oauth): document Sign in with ChatGPT provider"
```

---

## Task 9: Fork + Pull Request

**Files:** nessuno (operazioni git/gh)

- [ ] **Step 1: Esegui l'intera suite**

Run: `.venv/bin/pytest -q`
Expected: tutti i test passano.

- [ ] **Step 2: Fork e push**

```bash
gh repo fork TauricResearch/TradingAgents --remote --remote-name fork
git push fork feat/openai-oauth-codex
```

- [ ] **Step 3: Apri la PR**

```bash
gh pr create --repo TauricResearch/TradingAgents \
  --head SeriumTW:feat/openai-oauth-codex \
  --title "feat: Sign in with ChatGPT (OAuth) provider 'openai-oauth'" \
  --body "$(cat <<'EOF'
Aggiunge il provider `openai-oauth` che autentica via OAuth PKCE con
l'account ChatGPT (flusso Codex) e instrada le chiamate al backend Codex,
senza richiedere `OPENAI_API_KEY`.

- Nuovo package `tradingagents/llm_clients/oauth/` (PKCE, login browser,
  token store con refresh, httpx auth con refresh+retry su 401).
- `OpenAIClient` instrada `openai-oauth` su `chatgpt.com/backend-api/codex`
  con header `chatgpt-account-id` e Responses API.
- CLI: voce provider + auto-login + comando `tradingagents login`.
- Test unitari deterministici; nessuna modifica ai provider esistenti.

Nota: endpoint Codex non ufficialmente documentati per uso esterno
(funzionalità community).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Verifica**

Run: `gh pr view --repo TauricResearch/TradingAgents --web` (opzionale) per controllare la PR.

---

## Note di esecuzione

- Usa sempre `.venv/bin/pytest` (l'ambiente del progetto).
- Se `cli/main.py` non espone un oggetto `typer.Typer` riutilizzabile per
  `@app.command()`, verifica come è registrato il comando esistente
  (`pyproject` punta a `cli.main:app`) e aggiungi `login` come comando dello
  stesso `app`.
- Il test reale del login (browser) NON è in CI: resta una verifica manuale
  via `tradingagents login`.
