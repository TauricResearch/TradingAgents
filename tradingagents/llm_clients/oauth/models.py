"""Scoperta dei modelli realmente disponibili per l'account ChatGPT.

Il backend Codex accetta solo i modelli abilitati per il piano dell'utente
(gli altri -> HTTP 400). L'endpoint ``GET /codex/models`` è autorevole per i
piani Plus/Pro ma ritorna una lista VUOTA per il piano free, anche quando alcuni
modelli funzionano. Quindi, in fallback, sondiamo i candidati con una richiesta
``/responses`` minima e teniamo quelli che rispondono 200. Il risultato è messo
in cache per account per evitare di risondare a ogni run.
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

import httpx

from .pkce import CODEX_BASE_URL, CODEX_DEFAULT_HEADERS
from .store import OAuthTokenStore, StoredTokens, default_store_path

MODELS_ENDPOINT = "/models"
RESPONSES_ENDPOINT = "/responses"
_DEFAULT_CLIENT_VERSION = "0.50.0"
# Cache valida un giorno: oltre, si ri-scopre (il piano/entitlement può cambiare).
_CACHE_TTL_SECONDS = 24 * 3600


def _auth_headers(tokens: StoredTokens) -> dict:
    headers = dict(CODEX_DEFAULT_HEADERS)
    headers["Authorization"] = f"Bearer {tokens.access_token}"
    if tokens.account_id:
        headers["ChatGPT-Account-ID"] = tokens.account_id
    if tokens.is_fedramp:
        headers["X-OpenAI-Fedramp"] = "true"
    if tokens.residency:
        headers["x-openai-internal-codex-residency"] = tokens.residency
    return headers


def fetch_models_endpoint(tokens: StoredTokens, *, client_version: str = _DEFAULT_CLIENT_VERSION) -> list[str]:
    """Modelli dichiarati da ``GET /codex/models`` (può essere vuoto sul free)."""
    try:
        resp = httpx.get(
            CODEX_BASE_URL + MODELS_ENDPOINT,
            headers=_auth_headers(tokens),
            params={"client_version": client_version},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return []
    items = data.get("models") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("slug") or it.get("model")
        else:
            mid = it
        if isinstance(mid, str) and mid:
            out.append(mid)
    return out


def probe_model(tokens: StoredTokens, model: str, *, timeout: int = 20) -> bool:
    """True se il backend accetta ``model`` (HTTP 200), False su 400/altro.

    Apre lo stream solo per leggere lo status (prima di consumare il body), così
    il costo è minimo: il 400 torna subito, il 200 viene chiuso immediatamente.
    """
    body = {
        "model": model,
        "store": False,
        "stream": True,
        "instructions": ".",
        "input": [{"role": "user", "content": "hi", "type": "message"}],
    }
    headers = _auth_headers(tokens)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "text/event-stream"
    try:
        with httpx.stream(
            "POST", CODEX_BASE_URL + RESPONSES_ENDPOINT, headers=headers, json=body, timeout=timeout
        ) as resp:
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def discover_available_models(
    tokens: StoredTokens,
    candidates: Iterable[str],
    *,
    allow_probe: bool = True,
    max_workers: int = 6,
) -> list[str]:
    """Scopre i modelli usabili: prima l'endpoint, poi (se vuoto) il probe.

    Preserva l'ordine di ``candidates`` nel risultato del probe.
    """
    candidates = list(dict.fromkeys(c for c in candidates if c and c != "custom"))
    endpoint_models = fetch_models_endpoint(tokens)
    if endpoint_models:
        # Mantieni solo i candidati noti, nell'ordine dell'endpoint, più eventuali
        # extra serviti dall'endpoint ma non nel catalogo.
        known = set(candidates)
        ordered = [m for m in endpoint_models if m in known]
        extra = [m for m in endpoint_models if m not in known]
        return ordered + extra
    if not allow_probe or not candidates:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        flags = list(ex.map(lambda m: probe_model(tokens, m), candidates))
    return [m for m, ok in zip(candidates, flags) if ok]


class ModelAvailabilityCache:
    """Cache per-account dei modelli disponibili (sidecar del token store)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_store_path().parent / "oauth_models.json"

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get(self, account_id: Optional[str]) -> Optional[list[str]]:
        if not account_id:
            return None
        entry = self._read().get(account_id)
        if not isinstance(entry, dict):
            return None
        ts = entry.get("ts", 0)
        if not isinstance(ts, (int, float)) or (time.time() - ts) > _CACHE_TTL_SECONDS:
            return None
        models = entry.get("models")
        return models if isinstance(models, list) else None

    def set(self, account_id: Optional[str], models: list[str]) -> None:
        if not account_id:
            return
        data = self._read()
        data[account_id] = {"models": models, "ts": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self.path)


def available_models(
    store: OAuthTokenStore,
    candidates: Iterable[str],
    *,
    refresh: bool = False,
    cache: Optional[ModelAvailabilityCache] = None,
) -> list[str]:
    """Modelli disponibili per l'account (cache-aware). Vuoto se non scopribili.

    Su cache-miss (o ``refresh``) esegue la scoperta e la mette in cache. In caso
    di errore di rete ritorna [] (il chiamante può ripiegare sul catalogo).
    """
    cache = cache or ModelAvailabilityCache()
    tokens = store.load()
    if tokens.is_expired():
        tokens = store.refresh()
    if not refresh:
        cached = cache.get(tokens.account_id)
        if cached is not None:
            return cached
    models = discover_available_models(tokens, candidates)
    if models:
        cache.set(tokens.account_id, models)
    return models
