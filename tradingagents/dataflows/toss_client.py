"""Low-level client for the Toss Securities Open API.

Handles OAuth2 token issuance (client credentials grant) with in-process
caching and a thin REST wrapper with rate-limit backoff. Higher-level data and
order modules build on top of this.

Credentials are read from the environment:
    TOSS_APP_KEY     -> client_id
    TOSS_APP_SECRET  -> client_secret
"""

import os
import time
import threading
import logging

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.tossinvest.com"

# Refresh the access token this many seconds before it actually expires, so a
# request never goes out with a token that lapses mid-flight.
_TOKEN_EXPIRY_MARGIN = 60


class TossAPIError(Exception):
    """Raised when the Toss API returns an error envelope or HTTP error."""

    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"[{status} {code}] {message}")


class TossClient:
    """Singleton-style Toss Open API client with token caching."""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._client_id = os.getenv("TOSS_APP_KEY")
        self._client_secret = os.getenv("TOSS_APP_SECRET")
        if not self._client_id or not self._client_secret:
            raise TossAPIError(
                0,
                "missing-credentials",
                "TOSS_APP_KEY / TOSS_APP_SECRET environment variables are not set.",
            )
        self._session = requests.Session()
        self._token = None
        self._token_expiry = 0.0
        self._token_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "TossClient":
        """Return a process-wide shared client (created lazily)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # -- auth ---------------------------------------------------------------

    def _access_token(self) -> str:
        with self._token_lock:
            if self._token and time.time() < self._token_expiry:
                return self._token

            resp = self._session.post(
                f"{BASE_URL}/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                raise TossAPIError(
                    resp.status_code, "token-issue-failed", resp.text[:300]
                )
            body = resp.json()
            self._token = body["access_token"]
            self._token_expiry = time.time() + body["expires_in"] - _TOKEN_EXPIRY_MARGIN
            return self._token

    # -- request ------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict = None,
        json: dict = None,
        account_seq: int = None,
        max_retries: int = 4,
    ) -> dict:
        """Make an authenticated request, retrying on 429 rate limits.

        Returns the parsed JSON body. Raises :class:`TossAPIError` on the API
        error envelope or unrecoverable HTTP errors.
        """
        url = f"{BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        if account_seq is not None:
            headers["X-Tossinvest-Account"] = str(account_seq)

        for attempt in range(max_retries + 1):
            resp = self._session.request(
                method, url, headers=headers, params=params, json=json, timeout=20
            )

            if resp.status_code == 429 and attempt < max_retries:
                retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "Toss rate limited on %s, retrying in %.1fs (attempt %d/%d)",
                    path, retry_after, attempt + 1, max_retries,
                )
                time.sleep(retry_after)
                continue

            if resp.status_code >= 400:
                try:
                    err = resp.json().get("error", {})
                    raise TossAPIError(
                        resp.status_code,
                        err.get("code", "unknown"),
                        err.get("message", resp.text[:300]),
                    )
                except ValueError:
                    raise TossAPIError(resp.status_code, "http-error", resp.text[:300])

            return resp.json()

        raise TossAPIError(429, "rate-limit-exceeded", f"Exhausted retries for {path}")
