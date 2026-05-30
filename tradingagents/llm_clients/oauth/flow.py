"""Login OAuth PKCE via browser con server di callback locale.

Apre ``localhost:1455`` (fallback ``1457`` — le uniche porte nella allow-list
Hydra di OpenAI) su ``/auth/callback``, valida lo ``state`` (anti-CSRF) e scambia
il code per i token. Allineato a openai/codex/login/src/server.rs.
"""
from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse, parse_qs

import httpx

from .pkce import (
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_PORT,
    OAUTH_REDIRECT_FALLBACK_PORT,
    OAUTH_TOKEN_URL,
    build_authorize_url,
    generate_pkce_pair,
    generate_state,
    redirect_uri_for_port,
)
from .store import OAuthError, OAuthTokenStore, StoredTokens

_SUCCESS_HTML = (
    b"<!doctype html><html><head><meta charset='utf-8'>"
    b"<title>TradingAgents - Login</title></head><body style='font-family:sans-serif'>"
    b"<h2>Login completato.</h2>"
    b"<p>Puoi chiudere questa scheda e tornare al terminale.</p></body></html>"
)
_ERROR_HTML = (
    b"<!doctype html><html><head><meta charset='utf-8'></head><body style='font-family:sans-serif'>"
    b"<h2>Login non riuscito.</h2><p>Torna al terminale.</p></body></html>"
)


class OAuthLoginError(OAuthError):
    """Login non completato (annullato, timeout, porta occupata, CSRF)."""


def exchange_code(code: str, code_verifier: str, *, port: int = OAUTH_REDIRECT_PORT) -> dict:
    """Scambia l'authorization code per i token (POST form-urlencoded, 5 campi)."""
    resp = httpx.post(
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri_for_port(port),
            "client_id": OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise OAuthLoginError(f"Scambio token fallito (HTTP {resp.status_code}).")
    return resp.json()


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handler che cattura code/state da /auth/callback in un dict condiviso."""

    # Impostati da login() prima di servire.
    result: dict = {}

    def do_GET(self):  # noqa: N802 (firma BaseHTTPRequestHandler)
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.send_header("Connection", "close")
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        captured = {
            "code": params.get("code", [None])[0],
            "state": params.get("state", [None])[0],
            "error": params.get("error", [None])[0],
        }
        type(self).result = captured
        body = _SUCCESS_HTML if captured.get("code") and not captured.get("error") else _ERROR_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silenzia il logging su stderr
        pass


def _bind_callback_server() -> tuple[HTTPServer, int]:
    """Apre il server sulla 1455, altrimenti sulla 1457; errore se entrambe occupate."""
    last_exc: Optional[OSError] = None
    for port in (OAUTH_REDIRECT_PORT, OAUTH_REDIRECT_FALLBACK_PORT):
        try:
            return HTTPServer(("localhost", port), _CallbackHandler), port
        except OSError as exc:  # porta occupata
            last_exc = exc
    raise OAuthLoginError(
        f"Porte {OAUTH_REDIRECT_PORT}/{OAUTH_REDIRECT_FALLBACK_PORT} occupate: "
        f"chiudi il processo che le usa (es. Codex CLI) e riprova."
    ) from last_exc


def login(
    open_browser: bool = True,
    timeout: int = 180,
    store: Optional[OAuthTokenStore] = None,
) -> StoredTokens:
    """Esegue il login OAuth PKCE e salva i token. Ritorna gli ``StoredTokens``."""
    store = store or OAuthTokenStore()
    verifier, challenge = generate_pkce_pair()
    state = generate_state()

    _CallbackHandler.result = {}
    server, port = _bind_callback_server()
    url = build_authorize_url(challenge, state, port=port)

    if open_browser:
        webbrowser.open(url)
    else:
        print(f"Apri questo URL nel browser per autenticarti:\n{url}")

    try:
        server.timeout = timeout
        waited = 0
        # handle_request() ritorna dopo ogni connessione o dopo `timeout`.
        # Continua finché non arriva il callback con code/error o scade il tempo.
        while not _CallbackHandler.result and waited < timeout:
            server.handle_request()
            waited += server.timeout or timeout
    finally:
        server.server_close()

    result = _CallbackHandler.result
    if not result or result.get("error"):
        raise OAuthLoginError(
            "Login annullato o fallito" + (f": {result.get('error')}" if result.get("error") else ".")
        )
    if result.get("state") != state:
        raise OAuthLoginError("State non valido (possibile CSRF). Login annullato.")
    if not result.get("code"):
        raise OAuthLoginError("Nessun authorization code ricevuto (timeout?).")

    tokens = exchange_code(result["code"], verifier, port=port)
    return store.save(tokens)
