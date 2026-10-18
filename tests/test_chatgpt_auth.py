"""Sign in with ChatGPT: the sign-in is checked, kept private, renewed once, and revoked.

OpenAI is replaced by a fake that signs ID tokens with a key made here, so every
check of the sign-in (signature, issuer, audience, nonce, plan scope) runs for real.
"""

import base64
import json
import socket
import stat
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from tradingagents.llm_clients import chatgpt_auth as auth

# The suite refuses all connections; the loopback test lets 127.0.0.1 through only.
_CONNECT, _GETADDRINFO = socket.socket.connect, socket.getaddrinfo
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLIENT = "oaiapp_test"
SUBJECT = "user-123"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _id_token(key=KEY, **claims) -> str:
    payload = {"iss": auth.ISSUER, "aud": CLIENT, "sub": SUBJECT, "email": "a@example.com",
               "exp": time.time() + 3600, **claims}
    head = _b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{_b64(signature)}"


def _jwks():
    numbers = KEY.public_key().public_numbers()
    return {"keys": [{"kid": "k1", "kty": "RSA", "e": _b64(numbers.e.to_bytes(3, "big")),
                      "n": _b64(numbers.n.to_bytes(256, "big"))}]}


class _Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class FakeOpenAI:
    """Answers the JWKS, token and revoke endpoints and records what was sent."""

    def __init__(self, token_body=None, status=200):
        self.posts = []
        self.token_body = token_body
        self.status = status
        self.lock = threading.Lock()
        self.keys_reachable = True
        self.revoke_status = 200
        self.post_error = None

    def get(self, url, timeout):
        assert url == auth.JWKS_URL
        if not self.keys_reachable:
            raise auth.requests.ConnectionError("down")
        return _Response(_jwks())

    def post(self, url, timeout, data):
        with self.lock:
            self.posts.append((url, data))
        if url == auth.REVOKE_URL:
            return _Response({}, self.revoke_status)
        if self.post_error is not None:
            raise self.post_error
        time.sleep(0.05)   # let a racing refresher reach the lock
        body = self.token_body(data) if callable(self.token_body) else self.token_body
        return _Response(body, self.status)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_FILE", tmp_path / "home" / "chatgpt-auth.json")
    monkeypatch.setattr(auth, "_retry_after", 0.0)
    return tmp_path


@pytest.fixture
def openai(monkeypatch):
    fake = FakeOpenAI()
    monkeypatch.setattr(auth.requests, "get", fake.get)
    monkeypatch.setattr(auth.requests, "post", fake.post)
    return fake


def _signed_in(expires_at, earliest=None, refresh_token="r1"):
    auth.AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    auth._write({"host_id": "urn:uuid:h", "account": {"client_id": CLIENT, "email": "a@example.com",
                                                      "subject": SUBJECT},
                 "tokens": {"access_token": "a1", "refresh_token": refresh_token,
                            "expires_at": expires_at, "earliest_refresh_at": earliest}})


def _renewal(data):
    return {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600,
            "id_token": _id_token(), "scope": auth.SCOPE}


# --- the ID token ----------------------------------------------------------------

@pytest.mark.unit
def test_a_genuine_id_token_is_accepted():
    assert auth._validated_claims(_id_token(nonce="n"), CLIENT, "n", _jwks()["keys"])["sub"] == SUBJECT


@pytest.mark.unit
@pytest.mark.parametrize("token, nonce", [
    (lambda: _id_token(nonce="other"), "n"),
    (lambda: _id_token(aud="oaiapp_someone_else", nonce="n"), "n"),
    (lambda: _id_token(iss="https://evil.example", nonce="n"), "n"),
    (lambda: _id_token(exp=time.time() - 600, nonce="n"), "n"),
])
def test_an_id_token_for_another_sign_in_is_refused(token, nonce):
    with pytest.raises(auth.ChatGPTAuthError):
        auth._validated_claims(token(), CLIENT, nonce, _jwks()["keys"])


@pytest.mark.unit
def test_an_id_token_signed_by_another_key_is_refused():
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(auth.ChatGPTAuthError, match="do not verify"):
        auth._validated_claims(_id_token(key=stranger, nonce="n"), CLIENT, "n", _jwks()["keys"])


# --- tokens ----------------------------------------------------------------------

@pytest.mark.unit
def test_nobody_signed_in_is_told_how_to_sign_in(home, openai):
    with pytest.raises(auth.ChatGPTAuthError, match="tradingagents login chatgpt"):
        auth.credential()
    with pytest.raises(auth.ChatGPTAuthError, match="tradingagents login chatgpt"):
        auth.access_token()
    assert openai.posts == []


@pytest.mark.unit
def test_a_fresh_token_is_used_without_asking_openai(home, openai):
    _signed_in(expires_at=time.time() + 3000)
    assert auth.credential()() == "a1"
    assert openai.posts == []


@pytest.mark.unit
def test_a_token_near_expiry_is_renewed_with_the_stored_refresh_token(home, openai):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body = _renewal
    assert auth.access_token() == "a2"
    (url, sent), = openai.posts
    assert url == auth.TOKEN_URL and sent["refresh_token"] == "r1" and sent["client_id"] == CLIENT
    stored = json.loads(auth.AUTH_FILE.read_text())
    assert stored["tokens"]["refresh_token"] == "r2" and stored["account"]["subject"] == SUBJECT
    assert stat.S_IMODE(auth.AUTH_FILE.stat().st_mode) == 0o600


@pytest.mark.unit
def test_renewal_waits_for_the_time_openai_allows_while_the_token_still_works(home, openai):
    now = time.time()
    _signed_in(expires_at=now + 200, earliest=now + 100)
    assert auth.access_token() == "a1"
    assert openai.posts == []


@pytest.mark.unit
def test_concurrent_runs_renew_once_and_never_replay_a_used_refresh_token(home, openai):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body = _renewal
    tokens = []
    threads = [threading.Thread(target=lambda: tokens.append(auth.access_token())) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert tokens == ["a2"] * 4
    assert [sent["refresh_token"] for _, sent in openai.posts] == ["r1"]


@pytest.mark.unit
def test_a_refused_renewal_asks_to_sign_in_again_and_keeps_the_file(home, openai):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body, openai.status = {"error": "invalid_grant"}, 400
    with pytest.raises(auth.ChatGPTAuthError, match="invalid_grant.*login chatgpt"):
        auth.access_token()
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r1"


@pytest.mark.unit
def test_a_renewal_for_another_account_is_refused(home, openai):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body = lambda data: {**_renewal(data), "id_token": _id_token(sub="someone-else")}
    with pytest.raises(auth.ChatGPTAuthError, match="another account"):
        auth.access_token()


# --- signing in and out ------------------------------------------------------------

def _nonce_of(printed):
    url = next(line for line in printed if line.startswith(auth.AUTHORIZE_URL))
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))["nonce"]


def _paster(printed, edit=lambda query: query):
    calls = []

    def read_line():
        calls.append(1)
        if len(calls) > 1:
            threading.Event().wait()
        url = next(line for line in printed if line.startswith(auth.AUTHORIZE_URL))
        asked = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        query = edit({"code": "c1", "state": asked["state"], "client_id": CLIENT})
        return f"{asked['redirect_uri']}?{urllib.parse.urlencode(query)}"

    return read_line


@pytest.mark.unit
def test_signing_in_by_pasting_the_redirect_saves_a_private_sign_in(home, openai):
    printed = []

    def token(data):
        assert data["grant_type"] == "authorization_code" and data["client_id"] == CLIENT
        assert data["code"] == "c1" and data["code_verifier"]
        return {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600,
                "id_token": _id_token(nonce=_nonce_of(printed)), "scope": auth.SCOPE}

    openai.token_body = token
    email = auth.sign_in(say=printed.append, read_line=_paster(printed), timeout=10, port=0)
    assert email == "a@example.com"
    stored = json.loads(auth.AUTH_FILE.read_text())
    assert stored["account"] == {"client_id": CLIENT, "email": "a@example.com", "subject": SUBJECT}
    assert stored["host_id"].startswith("urn:uuid:")
    assert stat.S_IMODE(auth.AUTH_FILE.stat().st_mode) == 0o600
    asked = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(printed[1]).query))
    assert asked["client_id"] == auth.DYNAMIC_CLIENT_ID and asked["agent_name_hint"] == "TradingAgents"
    assert asked["code_challenge_method"] == "S256" and asked["redirect_uri"].startswith("http://127.0.0.1:")


@pytest.mark.unit
def test_an_answer_for_another_sign_in_attempt_is_ignored(home, openai):
    printed = []
    with pytest.raises(auth.ChatGPTAuthError, match="timed out"):
        auth.sign_in(say=printed.append, read_line=_paster(printed, lambda q: {**q, "state": "forged"}),
                     timeout=1, port=0)
    assert any("not the address" in line for line in printed)
    assert openai.posts == [] and not auth.AUTH_FILE.exists()


def _status(url):
    try:
        return urllib.request.urlopen(url, timeout=5).status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.mark.unit
def test_the_browser_answer_reaches_the_loopback_and_strays_are_ignored(home, openai, monkeypatch):
    refused_connect, refused_lookup = socket.socket.connect, socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", lambda sock, address: (
        _CONNECT if address[0] == "127.0.0.1" else refused_connect)(sock, address))
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: (
        _GETADDRINFO if host == "127.0.0.1" else refused_lookup)(host, *a, **k))
    printed = []
    openai.token_body = lambda data: {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600,
                                      "id_token": _id_token(nonce=_nonce_of(printed)), "scope": auth.SCOPE}

    def browser():
        while not any(line.startswith(auth.AUTHORIZE_URL) for line in printed):
            time.sleep(0.01)
        asked = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(printed[1]).query))
        results.append(_status(f"{asked['redirect_uri']}?error=access_denied"))
        results.append(_status(f"{asked['redirect_uri']}?code=c1&state={asked['state']}&client_id={CLIENT}"))

    results = []
    threading.Thread(target=browser, daemon=True).start()
    email = auth.sign_in(say=printed.append, read_line=threading.Event().wait, timeout=10, port=0)
    assert email == "a@example.com" and results == [400, 200]


@pytest.mark.unit
def test_a_sign_in_without_plan_usage_is_refused(home, openai):
    printed = []
    openai.token_body = lambda data: {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600,
                                      "id_token": _id_token(nonce=_nonce_of(printed)),
                                      "scope": "openid email offline_access"}
    with pytest.raises(auth.ChatGPTAuthError, match="approve plan usage"):
        auth.sign_in(say=printed.append, read_line=_paster(printed), timeout=10, port=0)
    assert not auth.AUTH_FILE.exists()


@pytest.mark.unit
def test_signing_out_revokes_the_sign_in_and_keeps_only_the_host_id(home, openai):
    _signed_in(expires_at=time.time() + 3000)
    assert auth.sign_out() == "revoked"
    (url, sent), = openai.posts
    assert url == auth.REVOKE_URL and sent["token"] == "r1" and sent["client_id"] == CLIENT
    assert json.loads(auth.AUTH_FILE.read_text()) == {"host_id": "urn:uuid:h"}
    assert auth.signed_in_as() is None
    assert auth.sign_out() is None


@pytest.mark.unit
def test_unreachable_keys_stop_a_renewal_before_the_refresh_token_is_spent(home, openai):
    _signed_in(expires_at=time.time() - 1)
    openai.token_body, openai.keys_reachable = _renewal, False
    with pytest.raises(auth.ChatGPTUnreachable, match="Could not reach OpenAI"):
        auth.access_token()
    assert openai.posts == []
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r1"


@pytest.mark.unit
@pytest.mark.parametrize("failure", ["keys", "network", 429, 503])
def test_a_temporary_failure_keeps_a_token_that_still_works(home, openai, failure):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body = _renewal
    if failure == "keys":
        openai.keys_reachable = False
    elif failure == "network":
        openai.post_error = auth.requests.ConnectionError("reset")
    else:
        openai.token_body, openai.status = {"error": "busy"}, failure
    assert auth.access_token() == "a1"
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r1"
    if failure == "keys":
        assert openai.posts == []


@pytest.mark.unit
@pytest.mark.parametrize("failure", ["network", 408, 503])
def test_a_temporary_failure_after_expiry_says_to_try_again_not_to_sign_in(home, openai, failure):
    _signed_in(expires_at=time.time() - 1)
    if failure == "network":
        openai.post_error = auth.requests.Timeout("slow")
    else:
        openai.token_body, openai.status = {"error": "busy"}, failure
    with pytest.raises(auth.ChatGPTUnreachable) as raised:
        auth.access_token()
    assert "try again" in str(raised.value) and "login" not in str(raised.value)


@pytest.mark.unit
def test_signing_in_again_revokes_the_replaced_sign_in(home, openai):
    _signed_in(expires_at=time.time() + 3000, refresh_token="old")
    printed = []
    openai.token_body = lambda data: {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600,
                                      "id_token": _id_token(nonce=_nonce_of(printed)), "scope": auth.SCOPE}
    auth.sign_in(say=printed.append, read_line=_paster(printed), timeout=10, port=0)
    assert openai.posts[-1][0] == auth.REVOKE_URL and openai.posts[-1][1]["token"] == "old"
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r2"


@pytest.mark.unit
def test_another_account_cannot_replace_the_signed_in_one(home, openai):
    _signed_in(expires_at=time.time() + 3000)
    printed = []
    openai.token_body = lambda data: {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600,
                                      "id_token": _id_token(nonce=_nonce_of(printed), sub="someone-else"),
                                      "scope": auth.SCOPE}
    with pytest.raises(auth.ChatGPTAuthError, match="logout chatgpt"):
        auth.sign_in(say=printed.append, read_line=_paster(printed), timeout=10, port=0)
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r1"


@pytest.mark.unit
def test_signing_out_while_openai_is_unreachable_still_forgets_the_sign_in(home, openai):
    _signed_in(expires_at=time.time() + 3000)
    openai.revoke_status = 503
    assert auth.sign_out() == "forgotten"
    assert auth.signed_in_as() is None


@pytest.mark.unit
def test_after_a_temporary_failure_renewal_waits_a_minute_before_trying_again(home, openai):
    _signed_in(expires_at=time.time() + 200)
    openai.post_error = auth.requests.ConnectionError("reset")
    clock = [time.time()]
    assert auth.access_token(now=lambda: clock[0]) == "a1"
    assert auth.access_token(now=lambda: clock[0] + 30) == "a1"
    assert len(openai.posts) == 1
    openai.post_error, openai.token_body = None, _renewal
    assert auth.access_token(now=lambda: clock[0] + 61) == "a2"


@pytest.mark.unit
def test_after_expiry_a_failed_renewal_is_not_retried_within_the_minute(home, openai):
    _signed_in(expires_at=time.time() - 1)
    openai.post_error = auth.requests.ConnectionError("reset")
    for _ in range(3):
        with pytest.raises(auth.ChatGPTUnreachable, match="try again"):
            auth.access_token()
    assert len(openai.posts) == 1


@pytest.mark.unit
def test_an_unreadable_renewal_answer_keeps_a_token_that_still_works(home, openai):
    _signed_in(expires_at=time.time() + 60)
    openai.token_body = lambda data: ["not", "a", "token"]
    assert auth.access_token() == "a1"
    assert json.loads(auth.AUTH_FILE.read_text())["tokens"]["refresh_token"] == "r1"


@pytest.mark.unit
def test_a_network_failure_while_signing_in_is_reported_not_raised_raw(home, openai):
    printed = []
    openai.post_error = auth.requests.ConnectionError("reset")
    with pytest.raises(auth.ChatGPTUnreachable, match="sign you in to ChatGPT.*try again"):
        auth.sign_in(say=printed.append, read_line=_paster(printed), timeout=10, port=0)
    assert not auth.AUTH_FILE.exists()
