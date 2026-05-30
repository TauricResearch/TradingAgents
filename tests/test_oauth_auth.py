"""Test dell'auth httpx CodexOAuth: iniezione bearer e refresh su 401."""
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
    sent = next(auth.auth_flow(httpx.Request("GET", "https://example.com")))
    assert sent.headers["Authorization"] == "Bearer ACCESS1"
    assert store.refresh_calls == 0


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


def test_no_retry_on_200():
    store = FakeStore(_tok("OK"), _tok("X"))
    auth = CodexOAuth(store)
    flow = auth.auth_flow(httpx.Request("GET", "https://x"))
    first = next(flow)
    try:
        flow.send(httpx.Response(200, request=first))
    except StopIteration:
        pass
    assert store.refresh_calls == 0
