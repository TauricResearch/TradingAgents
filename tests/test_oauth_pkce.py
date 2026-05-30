"""Test PKCE e authorize URL per il provider openai-oauth."""
import base64
import hashlib
from urllib.parse import urlparse, parse_qs

from tradingagents.llm_clients.oauth import pkce


def test_challenge_is_s256_of_verifier():
    verifier, challenge = pkce.generate_pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected
    assert "=" not in challenge
    assert 43 <= len(verifier) <= 128


def test_state_is_urlsafe_and_random():
    a, b = pkce.generate_state(), pkce.generate_state()
    assert a != b
    assert "=" not in a


def test_authorize_url_has_verified_params():
    url = pkce.build_authorize_url("CHALLENGE", "STATE")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == [pkce.OAUTH_CLIENT_ID]
    assert q["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert q["code_challenge"] == ["CHALLENGE"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == ["STATE"]
    assert q["id_token_add_organizations"] == ["true"]
    assert q["codex_cli_simplified_flow"] == ["true"]
    assert q["originator"] == ["codex_cli_rs"]
    # scope esteso verificato dal sorgente
    assert q["scope"] == [
        "openid profile email offline_access api.connectors.read api.connectors.invoke"
    ]
    assert "prompt" not in q


def test_authorize_url_uses_fallback_port():
    url = pkce.build_authorize_url("C", "S", port=1457)
    q = parse_qs(urlparse(url).query)
    assert q["redirect_uri"] == ["http://localhost:1457/auth/callback"]


def test_codex_constants():
    assert pkce.CODEX_BASE_URL == "https://chatgpt.com/backend-api/codex"
    assert pkce.CODEX_DEFAULT_HEADERS["originator"] == "codex_cli_rs"
