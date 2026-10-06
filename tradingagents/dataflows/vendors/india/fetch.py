"""Polite downloads from the exchanges' public archives, cached for good.

Every request waits its turn per host (one a second by default, set with
TRADINGAGENTS_INDIA_REQUEST_INTERVAL), says who is asking (TradingAgents and its
version; set TRADINGAGENTS_INDIA_USER_AGENT to add your own contact), retries a
timeout or a server error with growing pauses, and honours Retry-After.

Nothing here works around an access control. archives.nseindia.com answers a
path it does not serve (bhavcopies before 2016, say) with the same Akamai
"Access Denied" page it would use to refuse a client, so a 403 is checked
against a file the host always serves: if that is refused too, the host is
refusing us and ``SourceBlocked`` stops the run; if not, the one file is
reported missing. A 429 that outlasts its Retry-After also stops the run.

Each download is written once under ``<data_cache_dir>/india/raw/`` and read
from there afterwards, so re-parsing never fetches again.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from urllib.parse import urlsplit

import requests

from tradingagents.dataflows.errors import VendorError

logger = logging.getLogger(__name__)

PROJECT_URL = "https://github.com/sushant-mishra-dtu/TradingAgents-Jev"
CANARY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_RETRIES = 3
_MAX_RETRY_AFTER = 300.0


class SourceBlocked(VendorError):
    """The host is refusing this client (403 on a file it always serves, or 429
    that will not clear). Systemic: the run stops rather than keep asking."""


class FetchFailed(VendorError):
    """One file could not be fetched after retries; the run logs it and goes on."""


def default_user_agent() -> str:
    try:
        version = metadata.version("tradingagents")
    except metadata.PackageNotFoundError:
        version = "dev"
    return f"TradingAgents/{version} (India data layer; +{PROJECT_URL})"


class ArchiveClient:
    """GETs files from the exchanges' archives: throttled, retried, cached."""

    def __init__(self, raw_dir: str | Path, *, interval: float = 1.0, user_agent: str | None = None,
                 timeout: float = 30.0, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 canary_url: str = CANARY_URL):
        self.raw_dir = Path(raw_dir)
        self.interval = max(0.0, float(interval))
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent or default_user_agent(),
                                     "Accept": "*/*", "Accept-Language": "en-IN,en;q=0.8"})
        self.sleep, self.clock = sleep, clock
        self.canary_url = canary_url
        self._last: dict[str, float] = {}
        self.requests = 0
        self.downloaded = 0  # bytes

    # Cache ---------------------------------------------------------------------
    def path(self, relative: str) -> Path:
        path = (self.raw_dir / relative).resolve()
        if self.raw_dir.resolve() not in path.parents:
            raise ValueError(f"cache path escapes the raw directory: {relative!r}")
        return path

    def cached(self, relative: str) -> bytes | None:
        path = self.path(relative)
        return path.read_bytes() if path.is_file() else None

    def store(self, relative: str, data: bytes) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
        return path

    # Network -------------------------------------------------------------------
    def get(self, url: str, cache_as: str, *, refresh: bool = False) -> bytes | None:
        """The file at ``url``, from the cache when it is there. None when the
        archive has no such file (404, or a path the host does not serve)."""
        if not refresh and (data := self.cached(cache_as)) is not None:
            return data
        data = self._download(url)
        if data is not None:
            self.store(cache_as, data)
        return data

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = self.interval - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def _request(self, url: str) -> requests.Response:
        self._wait(urlsplit(url).netloc)
        self.requests += 1
        return self.session.get(url, timeout=self.timeout)

    def _download(self, url: str) -> bytes | None:
        pause = 2.0
        for attempt in range(1, _RETRIES + 1):
            try:
                response = self._request(url)
            except requests.RequestException as exc:
                if attempt == _RETRIES:
                    raise FetchFailed(f"{url}: {type(exc).__name__} after {attempt} tries") from exc
                self.sleep(pause)
                pause *= 2
                continue
            status = response.status_code
            if status == 200:
                self.downloaded += len(response.content)
                return response.content
            if status == 404:
                return None
            if status == 403:
                if self._refused():
                    raise SourceBlocked(f"{urlsplit(url).netloc} refuses this client (403 on {url} "
                                        f"and on {self.canary_url})")
                logger.info("403 on %s while the host still serves others: treated as missing", url)
                return None
            if status == 429:
                wait = _retry_after(response.headers.get("Retry-After"), pause)
                if attempt == _RETRIES or wait > _MAX_RETRY_AFTER:
                    raise SourceBlocked(f"{urlsplit(url).netloc} keeps throttling (429 on {url})")
                self.sleep(wait)
                pause *= 2
                continue
            if 500 <= status < 600 and attempt < _RETRIES:
                self.sleep(pause)
                pause *= 2
                continue
            raise FetchFailed(f"{url}: HTTP {status}")
        raise FetchFailed(f"{url}: no answer after {_RETRIES} tries")

    def _refused(self) -> bool:
        """Whether a 403 means "not you" or "not this file": ask for a file the
        host always serves, once."""
        if not self.canary_url:
            return True
        try:
            return self._request(self.canary_url).status_code in (401, 403, 429)
        except requests.RequestException:
            return True


def _retry_after(value: str | None, default: float) -> float:
    try:
        return max(0.0, float(value)) if value else default
    except ValueError:
        return default
