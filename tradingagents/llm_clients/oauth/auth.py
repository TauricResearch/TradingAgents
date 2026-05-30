"""httpx.Auth che inietta il bearer OAuth Codex e rinnova su scadenza/401."""
from __future__ import annotations

import httpx

from .store import DEFAULT_SKEW_SECONDS


class CodexOAuth(httpx.Auth):
    """Inietta ``Authorization: Bearer`` con token fresco; refresh+retry su 401.

    Lo ``store`` deve esporre ``load() -> StoredTokens`` (con ``is_expired``) e
    ``refresh() -> StoredTokens``. Tenuto generico per testabilità.
    """

    def __init__(self, store, skew: int = DEFAULT_SKEW_SECONDS):
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
            # Token forse revocato/scaduto a metà sessione: refresh e un retry.
            fresh = self._store.refresh().access_token
            request.headers["Authorization"] = f"Bearer {fresh}"
            yield request
