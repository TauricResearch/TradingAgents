"""AgentKey social-data transport.

AgentKey (https://agentkey.app/) proxies ~990 social-media endpoints across
22 platforms (Weibo, Zhihu, Xiaohongshu, Douyin, TikTok, LinkedIn, …) behind a
single authenticated REST surface. Calls are dispatched through:

    POST {base_url}/v1/social/dispatch
    Authorization: Bearer <api_key>
    body: {"path": "weibo/app/fetch_search_all", "params": {...}}

The upstream JSON is returned as-is (TikHub/JustOneAPI shapes, unnormalized).
AgentKey charges per successful (2xx) call, so callers should fetch
deliberately rather than scan endpoints speculatively.

This module is the thin transport layer only: it knows how to authenticate and
POST, and raises :class:`AgentKeyError` on any failure (missing credentials,
network error, non-2xx, unparseable body). The per-channel fetchers in
``agentkey_social`` catch that error and degrade to a placeholder string, so the
sentiment analyst never has to special-case exceptions — mirroring the contract
already used by ``stocktwits.py`` and ``reddit.py``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.agentkey.app"
_DISPATCH_PATH = "/v1/social/dispatch"
_SEARCH_PATH = "/v1/search"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


class AgentKeyError(RuntimeError):
    """Raised when an AgentKey dispatch cannot be completed."""


def _setting(config_key: str, env_var: str, default: str = "") -> str:
    """Read a setting from the runtime config, falling back to the environment.

    The config is consulted first so a programmatic ``set_config`` override wins;
    the env var is the fallback so plain ``.env`` usage works without code.
    """
    try:
        from tradingagents.dataflows.config import get_config

        value = get_config().get(config_key)
        if value:
            return str(value)
    except Exception:  # pragma: no cover - config import should not break fetch
        pass
    return os.environ.get(env_var, default)


def get_api_key() -> str:
    """Return the configured AgentKey API key, or an empty string when unset."""
    return _setting("agentkey_api_key", "AGENTKEY_API_KEY").strip()


def get_base_url() -> str:
    """Return the AgentKey base URL, defaulting to the hosted service."""
    return _setting("agentkey_base_url", "AGENTKEY_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def is_configured() -> bool:
    """True when an API key is available, i.e. AgentKey channels can be used."""
    return bool(get_api_key())


def _post(endpoint: str, body: Dict[str, Any], label: str, timeout: float) -> Dict[str, Any]:
    """POST a JSON body to an AgentKey endpoint and return the parsed response.

    Raises :class:`AgentKeyError` on missing credentials, network error, non-2xx,
    or an unparseable / non-object body so callers can degrade gracefully.
    """
    api_key = get_api_key()
    if not api_key:
        raise AgentKeyError("no AGENTKEY_API_KEY configured")

    req = Request(
        get_base_url() + endpoint,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _UA,
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except HTTPError as exc:  # non-2xx: upstream status passed through
        raise AgentKeyError(f"HTTP {exc.code} for {label}") from exc
    except (URLError, TimeoutError) as exc:
        raise AgentKeyError(f"network error for {label}: {exc}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise AgentKeyError(f"unparseable response for {label}: {exc}") from exc

    if not isinstance(payload, dict):
        raise AgentKeyError(f"unexpected response shape for {label}")
    return payload


def dispatch(path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Dict[str, Any]:
    """Call one AgentKey social endpoint and return the parsed JSON body.

    ``path`` is the TikHub-style relative path (e.g. ``weibo/app/fetch_search_all``)
    and ``params`` are forwarded upstream verbatim.
    """
    return _post(_DISPATCH_PATH, {"path": path, "params": params or {}}, path, timeout)


def search(query: str, type: str = "web", num: int = 10, timeout: float = 15.0) -> Dict[str, Any]:
    """Run an AgentKey web search and return the parsed JSON body.

    Response shape: ``{"results": [{"title", "url", "snippet", ...}], ...}``.
    """
    return _post(_SEARCH_PATH, {"query": query, "type": type, "num": num}, f"search({query!r})", timeout)
