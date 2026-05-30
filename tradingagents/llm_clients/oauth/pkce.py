"""PKCE primitives, costanti OAuth e costanti del backend Codex.

Valori verificati dal sorgente openai/codex (branch main, 2026-05-30):
codex-rs/login/src/{server.rs,auth/manager.rs,auth/default_client.rs} e
codex-rs/model-provider-info/src/lib.rs. Vedi docs/superpowers/specs.
"""
from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import urlencode

# --- OAuth (auth.openai.com) ------------------------------------------------
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # client pubblico Codex CLI
OAUTH_ISSUER = "https://auth.openai.com"
OAUTH_AUTHORIZE_URL = f"{OAUTH_ISSUER}/oauth/authorize"
OAUTH_TOKEN_URL = f"{OAUTH_ISSUER}/oauth/token"

# Solo 1455 (default) e 1457 (fallback) sono nella allow-list Hydra di OpenAI:
# il redirect_uri DEVE usare una di queste porte, non una arbitraria.
OAUTH_REDIRECT_PORT = 1455
OAUTH_REDIRECT_FALLBACK_PORT = 1457

# Scope esteso usato dal codice corrente (server.rs:497), include i connettori.
OAUTH_SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"

# Originator del client ufficiale (default_client.rs:36). Alcuni path del backend
# rifiutano originator non in whitelist con 403, quindi lo inviamo.
ORIGINATOR = "codex_cli_rs"

# --- Backend Codex (chatgpt.com) -------------------------------------------
# model-provider-info/src/lib.rs:37 — il path /responses viene appeso da langchain.
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

# Header statici per ogni richiesta al backend (Authorization è iniettato a parte
# dall'auth httpx perché va rinnovato; ChatGPT-Account-ID è per-sessione).
CODEX_DEFAULT_HEADERS = {
    "originator": ORIGINATOR,
}


def _b64url(raw: bytes) -> str:
    """base64url senza padding (come pkce.rs in openai/codex)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """Ritorna ``(code_verifier, code_challenge)`` con metodo S256.

    ``code_challenge = base64url-nopad(SHA256(code_verifier))``.
    """
    verifier = _b64url(os.urandom(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_state() -> str:
    """State anti-CSRF: 32 byte random base64url-nopad."""
    return _b64url(os.urandom(32))


def redirect_uri_for_port(port: int) -> str:
    """redirect_uri per la porta effettivamente in ascolto."""
    return f"http://localhost:{port}/auth/callback"


def build_authorize_url(code_challenge: str, state: str, *, port: int = OAUTH_REDIRECT_PORT) -> str:
    """Costruisce l'URL di authorize con i parametri verificati dal sorgente."""
    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri_for_port(port),
        "scope": OAUTH_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": ORIGINATOR,
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
