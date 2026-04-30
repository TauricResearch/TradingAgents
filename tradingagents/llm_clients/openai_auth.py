import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional


_HERMES_REPO_PATH = Path.home() / ".hermes" / "hermes-agent"


def build_openai_runtime_config(
    config: Dict[str, Any],
    *,
    current_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve OpenAI runtime auth kwargs and optional base_url override.

    Supports plain API keys, zero-arg token providers, shell commands that print
    a short-lived bearer token, and Hermes-managed OpenAI Codex OAuth tokens.
    """
    auth_kwargs = build_openai_auth_kwargs(config)
    base_url = current_base_url

    if _should_use_hermes_codex_auth(config):
        creds = resolve_hermes_codex_runtime_credentials()
        auth_kwargs.setdefault("api_key_provider", _hermes_codex_token_provider())
        if not base_url:
            base_url = creds.get("base_url")

    return {
        "auth_kwargs": auth_kwargs,
        "base_url": base_url,
    }


def build_openai_auth_kwargs(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract OpenAI auth-related kwargs from config."""
    kwargs: Dict[str, Any] = {}

    if config.get("openai_api_key") is not None:
        kwargs["api_key"] = config["openai_api_key"]
    if config.get("openai_api_key_provider") is not None:
        kwargs["api_key_provider"] = config["openai_api_key_provider"]
    if config.get("openai_api_key_command"):
        kwargs["api_key_command"] = config["openai_api_key_command"]

    return kwargs


def build_api_key_provider(
    *,
    api_key: Optional[Any] = None,
    api_key_provider: Optional[Callable[[], str]] = None,
    api_key_command: Optional[str] = None,
):
    """Resolve the auth object to pass into ChatOpenAI.

    Priority:
    1. explicit api_key (string or callable)
    2. explicit api_key_provider callable
    3. shell command that prints a token
    """
    if api_key is not None:
        return api_key
    if api_key_provider is not None:
        return api_key_provider
    if api_key_command:
        return _command_token_provider(api_key_command)
    return None


def resolve_hermes_codex_runtime_credentials() -> Dict[str, Any]:
    """Read a fresh Hermes-managed Codex OAuth token and base_url.

    Imports Hermes lazily so TradingAgents still imports cleanly on systems
    without Hermes installed.
    """
    auth_module = _import_hermes_auth_module()
    resolver = getattr(auth_module, "resolve_codex_runtime_credentials", None)
    if resolver is None:
        raise RuntimeError("Hermes auth module does not expose resolve_codex_runtime_credentials()")
    creds = resolver(refresh_if_expiring=True)
    if not isinstance(creds, dict):
        raise RuntimeError("Hermes Codex resolver returned an invalid credential payload")
    api_key = str(creds.get("api_key", "") or "").strip()
    if not api_key:
        raise RuntimeError("Hermes Codex credentials did not include an api_key")
    return creds


def _should_use_hermes_codex_auth(config: Dict[str, Any]) -> bool:
    return bool(
        config.get("openai_use_hermes_codex_auth")
        or config.get("use_hermes_codex_auth")
    )


def _hermes_codex_token_provider() -> Callable[[], str]:
    def provider() -> str:
        creds = resolve_hermes_codex_runtime_credentials()
        return str(creds.get("api_key", "") or "").strip()

    return provider


def _import_hermes_auth_module():
    try:
        return importlib.import_module("hermes_cli.auth")
    except ModuleNotFoundError:
        hermes_path = str(_HERMES_REPO_PATH)
        if _HERMES_REPO_PATH.exists() and hermes_path not in sys.path:
            sys.path.insert(0, hermes_path)
        return importlib.import_module("hermes_cli.auth")


def _command_token_provider(command: str) -> Callable[[], str]:
    def provider() -> str:
        completed = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    return provider
