"""Persistenza + refresh dei token OAuth Codex.

Comportamento allineato a openai/codex (login/src/{token_data.rs,auth/manager.rs}):
- scadenza derivata dal claim ``exp`` del JWT access_token (NON da expires_in);
- account_id / fedramp / residency dai claim dell'id_token;
- refresh con body JSON (Content-Type: application/json), 3 campi, con rotazione
  del refresh_token.
"""
from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from .pkce import OAUTH_CLIENT_ID, OAUTH_TOKEN_URL

# Finestra di refresh proattivo: openai/codex usa 5 minuti
# (CHATGPT_ACCESS_TOKEN_REFRESH_WINDOW_MINUTES).
DEFAULT_SKEW_SECONDS = 300
# Fallback quando l'access_token non ha un claim exp leggibile (raro).
_FALLBACK_LIFETIME_SECONDS = 3600

_AUTH_CLAIM = "https://api.openai.com/auth"


class OAuthError(Exception):
    """Base per gli errori OAuth."""


class OAuthNotLoggedIn(OAuthError):
    """Nessun token salvato / store mancante o illeggibile."""


class OAuthRefreshFailed(OAuthError):
    """Refresh token rifiutato: serve un nuovo login."""


def default_store_path() -> Path:
    """Path del file token, override via ``TRADINGAGENTS_OAUTH_PATH``."""
    override = os.environ.get("TRADINGAGENTS_OAUTH_PATH")
    if override:
        return Path(os.path.expanduser(override))
    return Path(os.path.expanduser("~")) / ".tradingagents" / "oauth_openai.json"


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decodifica il payload di un JWT (base64url) SENZA verifica firma.

    Restituisce {} se il token non è un JWT a tre segmenti decodificabile.
    La firma non è verificata perché il valore è informativo (account_id,
    exp), non un gate di sicurezza — coerente con openai/codex.
    """
    try:
        payload_segment = token.split(".")[1]
        return json.loads(_b64url_decode(payload_segment))
    except (ValueError, IndexError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _auth_claims(token: str) -> dict[str, Any]:
    claims = decode_jwt_payload(token)
    value = claims.get(_AUTH_CLAIM)
    return value if isinstance(value, dict) else {}


# Claims dell'id_token (NON verificato in firma) finiscono in header HTTP:
# validiamo la forma per evitare header injection / valori malformati.
_HEADER_CLAIM_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def _clean_header_claim(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and _HEADER_CLAIM_RE.match(value) else None


def account_id_from_id_token(id_token: str) -> Optional[str]:
    return _clean_header_claim(_auth_claims(id_token).get("chatgpt_account_id"))


def is_fedramp_from_id_token(id_token: str) -> bool:
    return bool(_auth_claims(id_token).get("chatgpt_account_is_fedramp", False))


def residency_from_id_token(id_token: str) -> Optional[str]:
    claims = _auth_claims(id_token)
    return _clean_header_claim(
        claims.get("chatgpt_data_residency") or claims.get("chatgpt_compute_residency")
    )


def _expiry_from_access_token(access_token: str) -> float:
    """Scadenza (epoch) dal claim ``exp`` del JWT access_token.

    Fallback a ``now + _FALLBACK_LIFETIME_SECONDS`` se exp non è leggibile.
    """
    exp = decode_jwt_payload(access_token).get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        return float(exp)
    return time.time() + _FALLBACK_LIFETIME_SECONDS


@dataclass
class StoredTokens:
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: float
    account_id: Optional[str]
    is_fedramp: bool = False
    residency: Optional[str] = None

    def is_expired(self, skew: int = DEFAULT_SKEW_SECONDS) -> bool:
        return time.time() >= (self.expires_at - skew)


class OAuthTokenStore:
    """Legge/scrive i token OAuth su file con permessi 0600."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_store_path()

    # -- serializzazione -----------------------------------------------------
    def _to_tokens(self, record: dict) -> StoredTokens:
        id_token = record.get("id_token", "")
        return StoredTokens(
            access_token=record["access_token"],
            refresh_token=record["refresh_token"],
            id_token=id_token,
            expires_at=float(record.get("expires_at") or _expiry_from_access_token(record["access_token"])),
            account_id=account_id_from_id_token(id_token),
            is_fedramp=is_fedramp_from_id_token(id_token),
            residency=residency_from_id_token(id_token),
        )

    def save(self, tokens: dict) -> StoredTokens:
        """Persiste i token (atomico, 0600). ``tokens`` = risposta del token endpoint."""
        record = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "id_token": tokens.get("id_token", ""),
            "expires_at": _expiry_from_access_token(tokens["access_token"]),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp crea il file già a 0600 con nome unico: nessuna finestra
        # world-readable (TOCTOU) e nessuna collisione sul nome .tmp.
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".oauth_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(record))
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return self._to_tokens(record)

    def load(self) -> StoredTokens:
        try:
            record = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise OAuthNotLoggedIn(
                "Nessun login OAuth trovato. Esegui 'tradingagents login'."
            ) from exc
        try:
            return self._to_tokens(record)
        except KeyError as exc:
            raise OAuthNotLoggedIn(
                "File token OAuth incompleto. Esegui di nuovo 'tradingagents login'."
            ) from exc

    # -- refresh -------------------------------------------------------------
    def refresh(self) -> StoredTokens:
        """Rinnova l'access token (body JSON) e ripersiste, gestendo la rotazione."""
        current = self.load()
        resp = httpx.post(
            OAUTH_TOKEN_URL,
            json={
                "client_id": OAUTH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": current.refresh_token,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            # Estrai il codice d'errore (formato {"error": {...}} o {"detail": ...})
            # per distinguere gli errori permanenti dal refresh token.
            err_code = ""
            try:
                body = resp.json()
                if isinstance(body, dict):
                    err = body.get("error")
                    if isinstance(err, dict):
                        err_code = err.get("code") or err.get("type") or ""
                    elif isinstance(err, str):
                        err_code = err
                    elif isinstance(body.get("detail"), str):
                        err_code = body["detail"]
            except (ValueError, json.JSONDecodeError):
                pass
            permanent = {"refresh_token_expired", "refresh_token_reused", "refresh_token_invalidated"}
            hint = (
                " Il refresh token non è più valido."
                if str(err_code) in permanent
                else ""
            )
            raise OAuthRefreshFailed(
                f"Refresh del token fallito (HTTP {resp.status_code}{', ' + str(err_code) if err_code else ''})."
                f"{hint} Esegui di nuovo 'tradingagents login'."
            )
        data = resp.json()
        # access_token sempre atteso; refresh_token ruota solo se presente;
        # id_token può non essere rinviato (riusa il precedente).
        merged = {
            "access_token": data.get("access_token") or current.access_token,
            "refresh_token": data.get("refresh_token") or current.refresh_token,
            "id_token": data.get("id_token") or current.id_token,
        }
        return self.save(merged)
