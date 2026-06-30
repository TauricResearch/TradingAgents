"""Amazon Bedrock — first-class native client via the optional langchain-aws extra.

Auth uses either the AWS SigV4 credential chain or a native bearer token
(AWS_BEARER_TOKEN_BEDROCK); the model is a Bedrock model ID / inference profile
ID; langchain-aws is imported lazily with a clear install hint when the
[bedrock] extra is absent.
"""
import os
import sys

import pytest

from tradingagents.llm_clients.api_key_env import (
    AWS_SIGV4_CREDENTIAL_ENV_VARS,
    BEDROCK_BEARER_TOKEN_ENV,
    get_api_key_env,
)
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.validators import validate_model

# Reuse the production SigV4 var list (covers AWS_PROFILE *and* AWS_DEFAULT_PROFILE,
# partial keys, container creds) so the test scrub can't drift from what the client
# actually clears. Also clear the bearer token unless a test sets it explicitly.
_AWS_CRED_VARS = AWS_SIGV4_CREDENTIAL_ENV_VARS


def _scrub_aws_env(monkeypatch):
    """Remove ambient AWS auth env vars so auth-mode tests are deterministic."""
    for var in (*_AWS_CRED_VARS, BEDROCK_BEARER_TOKEN_ENV):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.unit
def test_factory_routes_bedrock():
    client = create_llm_client("bedrock", "us.anthropic.claude-opus-4-8")
    assert type(client).__name__ == "BedrockClient"


@pytest.mark.unit
def test_bedrock_any_model_and_no_key_env():
    assert validate_model("bedrock", "any.model-id:0") is True
    # Bedrock has two valid auth modes (bearer token OR SigV4 chain), neither a
    # single forced key — so the canonical map intentionally stays None.
    assert get_api_key_env("bedrock") is None
    assert BEDROCK_BEARER_TOKEN_ENV == "AWS_BEARER_TOKEN_BEDROCK"


@pytest.mark.unit
def test_helpful_error_when_langchain_aws_absent(monkeypatch):
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    monkeypatch.setitem(sys.modules, "langchain_aws", None)  # force ImportError on import
    with pytest.raises(ImportError, match=r"bedrock"):
        create_llm_client("bedrock", "m").get_llm()


@pytest.mark.unit
def test_construction_when_extra_installed(monkeypatch):
    """SigV4 path: region passthrough with deterministic fake static creds.

    Scrubs ambient AWS env so the developer's real profile/role/token can't
    contaminate the result, then provides fake static access keys to exercise
    the credential-chain branch independent of the local environment.
    """
    pytest.importorskip("langchain_aws")
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.delenv("AWS_REGION", raising=False)
    llm = create_llm_client("bedrock", "us.anthropic.claude-sonnet-4-6").get_llm()
    assert type(llm).__name__ == "NormalizedChatBedrockConverse"
    assert llm.region_name == "eu-west-1"


@pytest.mark.unit
def test_construction_with_bearer_token_only(monkeypatch):
    """A bearer token alone (no AWS access keys) must construct without raising.

    This is the gate for "AWS_BEARER_TOKEN_BEDROCK just works": langchain-aws
    runs its model_validator at construction and, with a token but no AWS access
    keys, takes the bearer branch instead of raising for missing credentials.
    """
    pytest.importorskip("langchain_aws")
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv(BEDROCK_BEARER_TOKEN_ENV, "test-bedrock-api-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.delenv("AWS_REGION", raising=False)

    llm = create_llm_client("bedrock", "us.anthropic.claude-sonnet-4-6").get_llm()
    assert type(llm).__name__ == "NormalizedChatBedrockConverse"
    assert llm.region_name == "us-west-2"
    # The bearer token must reach botocore's request signer (bearer auth), rather
    # than the client silently falling back to (absent) SigV4 credentials.
    signer = llm.client._request_signer
    auth_token = getattr(signer, "_auth_token", None) or getattr(signer, "auth_token", None)
    assert auth_token is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "contaminant",
    [
        {"AWS_PROFILE": "definitely-not-a-real-profile-xyz"},
        {"AWS_DEFAULT_PROFILE": "definitely-not-a-real-profile-xyz"},
        {"AWS_ACCESS_KEY_ID": "AKIAFAKE"},  # partial creds (no secret)
        {"AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/credentials/fake"},
    ],
)
def test_bearer_token_ignores_ambient_sigv4_env(monkeypatch, contaminant):
    """A bearer token must construct cleanly despite stray ambient SigV4 env vars.

    This is the real-world regression guard: developers commonly export a global
    AWS_PROFILE (or have partial keys / container-credential hints in the env).
    Without the bearer-auth env scrub, langchain-aws's bearer branch resolves the
    ambient chain and raises (e.g. ProfileNotFound) even though the token alone
    authenticates. The scrub must also restore the env afterward.
    """
    pytest.importorskip("langchain_aws")
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv(BEDROCK_BEARER_TOKEN_ENV, "test-bedrock-api-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.delenv("AWS_REGION", raising=False)
    for var, value in contaminant.items():
        monkeypatch.setenv(var, value)

    llm = create_llm_client("bedrock", "us.anthropic.claude-sonnet-4-6").get_llm()
    assert type(llm).__name__ == "NormalizedChatBedrockConverse"
    signer = llm.client._request_signer
    auth_token = getattr(signer, "_auth_token", None) or getattr(signer, "auth_token", None)
    assert auth_token is not None
    # Env must be restored exactly as it was (scrub is transient, not destructive).
    for var, value in contaminant.items():
        assert os.environ.get(var) == value


@pytest.mark.unit
def test_bearer_scrub_is_noop_without_token(monkeypatch):
    """Without a bearer token, the SigV4 credential chain must be left intact.

    A scrub that ran unconditionally would break IAM-role / profile users. Verify
    static creds reach the signer (SigV4) when no token is present.
    """
    pytest.importorskip("langchain_aws")
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    monkeypatch.delenv("AWS_REGION", raising=False)

    llm = create_llm_client("bedrock", "us.anthropic.claude-sonnet-4-6").get_llm()
    assert type(llm).__name__ == "NormalizedChatBedrockConverse"
    # SigV4 path: the static creds must still be resolvable (not scrubbed away).
    assert llm.client._get_credentials() is not None


@pytest.mark.unit
def test_region_defaults_to_us_west_2(monkeypatch):
    """With neither AWS_REGION nor AWS_DEFAULT_REGION set, region falls back."""
    pytest.importorskip("langchain_aws")
    import tradingagents.llm_clients.bedrock_client as bc
    monkeypatch.setattr(bc, "_BEDROCK_CLASS", None)
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv(BEDROCK_BEARER_TOKEN_ENV, "test-bedrock-api-key")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

    llm = create_llm_client("bedrock", "us.anthropic.claude-opus-4-8").get_llm()
    assert llm.region_name == "us-west-2"


# ---- CLI credential advisory (ensure_api_key) ----------------------------
# Bedrock must NEVER force the single-key prompt — that would derail IAM-role /
# profile users. The CLI only advises when neither auth mode looks configured.


@pytest.fixture
def cli_utils(monkeypatch):
    """Reload cli.utils so module state is fresh per test."""
    import importlib

    import cli.utils as cli_utils_module
    return importlib.reload(cli_utils_module)


@pytest.mark.unit
def test_ensure_api_key_bedrock_returns_bearer_token(monkeypatch, cli_utils):
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv(BEDROCK_BEARER_TOKEN_ENV, "test-token")
    from unittest.mock import patch
    with patch.object(cli_utils, "questionary") as mock_q:
        result = cli_utils.ensure_api_key("bedrock")
    assert result == "test-token"
    mock_q.password.assert_not_called()  # never prompts


@pytest.mark.unit
def test_ensure_api_key_bedrock_credential_chain_no_prompt(monkeypatch, cli_utils):
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv("AWS_PROFILE", "my-sso-profile")
    from unittest.mock import patch
    with patch.object(cli_utils, "questionary") as mock_q, \
         patch.object(cli_utils.console, "print") as mock_print:
        result = cli_utils.ensure_api_key("bedrock")
    assert result is None
    mock_q.password.assert_not_called()
    mock_print.assert_not_called()  # chain configured -> stay silent


@pytest.mark.unit
def test_ensure_api_key_bedrock_default_profile_no_warning(monkeypatch, cli_utils):
    """AWS_DEFAULT_PROFILE (not just AWS_PROFILE) counts as a configured chain."""
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv("AWS_DEFAULT_PROFILE", "my-default-profile")
    from unittest.mock import patch
    with patch.object(cli_utils, "questionary") as mock_q, \
         patch.object(cli_utils.console, "print") as mock_print:
        result = cli_utils.ensure_api_key("bedrock")
    assert result is None
    mock_q.password.assert_not_called()
    mock_print.assert_not_called()


@pytest.mark.unit
def test_ensure_api_key_bedrock_warns_when_token_and_profile_coexist(monkeypatch, cli_utils):
    """Bearer token + active AWS_PROFILE: return token AND warn it overrides profile."""
    _scrub_aws_env(monkeypatch)
    monkeypatch.setenv(BEDROCK_BEARER_TOKEN_ENV, "test-token")
    monkeypatch.setenv("AWS_PROFILE", "some-stale-profile")
    from unittest.mock import patch
    with patch.object(cli_utils, "questionary") as mock_q, \
         patch.object(cli_utils.console, "print") as mock_print:
        result = cli_utils.ensure_api_key("bedrock")
    assert result == "test-token"
    mock_q.password.assert_not_called()
    advice = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
    assert "AWS_PROFILE" in advice and "ignored" in advice


@pytest.mark.unit
def test_ensure_api_key_bedrock_no_auth_advises_without_prompt(monkeypatch, cli_utils):
    _scrub_aws_env(monkeypatch)
    from unittest.mock import patch
    with patch.object(cli_utils, "questionary") as mock_q, \
         patch.object(cli_utils.console, "print") as mock_print:
        result = cli_utils.ensure_api_key("bedrock")
    assert result is None
    mock_q.password.assert_not_called()  # advisory only, never blocks
    assert mock_print.called
    advice = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
    assert BEDROCK_BEARER_TOKEN_ENV in advice
