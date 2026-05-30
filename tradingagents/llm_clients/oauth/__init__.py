"""OAuth "Sign in with ChatGPT" (flusso Codex) per TradingAgents.

Espone il login PKCE, lo store dei token con refresh, l'auth httpx e le
costanti del backend Codex. Vedi docs/superpowers/specs per il protocollo
verificato dal sorgente openai/codex.
"""
from .pkce import (
    OAUTH_CLIENT_ID,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    OAUTH_REDIRECT_PORT,
    OAUTH_REDIRECT_FALLBACK_PORT,
    OAUTH_SCOPE,
    CODEX_BASE_URL,
    CODEX_DEFAULT_HEADERS,
    generate_pkce_pair,
    generate_state,
    build_authorize_url,
    redirect_uri_for_port,
)
from .store import (
    OAuthTokenStore,
    StoredTokens,
    OAuthError,
    OAuthNotLoggedIn,
    OAuthRefreshFailed,
    default_store_path,
)
from .auth import CodexOAuth
from .payload import apply_codex_payload_constraints
from .flow import login, exchange_code, OAuthLoginError


def ensure_token(store: "OAuthTokenStore | None" = None) -> "StoredTokens":
    """Carica i token; se scaduti fa refresh; se assenti solleva OAuthNotLoggedIn."""
    store = store or OAuthTokenStore()
    tokens = store.load()
    if tokens.is_expired():
        tokens = store.refresh()
    return tokens


__all__ = [
    "OAUTH_CLIENT_ID",
    "OAUTH_AUTHORIZE_URL",
    "OAUTH_TOKEN_URL",
    "OAUTH_REDIRECT_PORT",
    "OAUTH_REDIRECT_FALLBACK_PORT",
    "OAUTH_SCOPE",
    "CODEX_BASE_URL",
    "CODEX_DEFAULT_HEADERS",
    "generate_pkce_pair",
    "generate_state",
    "build_authorize_url",
    "redirect_uri_for_port",
    "OAuthTokenStore",
    "StoredTokens",
    "OAuthError",
    "OAuthNotLoggedIn",
    "OAuthRefreshFailed",
    "default_store_path",
    "CodexOAuth",
    "apply_codex_payload_constraints",
    "login",
    "exchange_code",
    "OAuthLoginError",
    "ensure_token",
]
