"""GitHub Copilot LLM client.

Authenticates via the ``gh`` CLI (``gh auth token``) and calls the Copilot
inference API (api.individual.githubcopilot.com) using headers reverse-
engineered from the Copilot CLI (copilot-developer-cli integration ID).

No env var or separate auth module needed — run ``gh auth login`` once.
"""

import subprocess
from copy import deepcopy
from typing import Any, Optional

import requests
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# Required headers for the Copilot inference API (reverse-engineered from
# /usr/local/lib/node_modules/@github/copilot).
_COPILOT_HEADERS = {
    "Copilot-Integration-Id": "copilot-developer-cli",
    "X-GitHub-Api-Version": "2025-05-01",
    "Openai-Intent": "conversation-agent",
}

# Models that only support /responses, not /chat/completions on the Copilot endpoint.
_RESPONSES_ONLY_MODELS = frozenset((
    "gpt-5.4", "gpt-5.4-mini",
    "gpt-5.3-codex", "gpt-5.2-codex",
    "gpt-5.1-codex", "gpt-5.1-codex-mini", "gpt-5.1-codex-max",
))

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "callbacks", "http_client", "http_async_client",
)


def get_github_token() -> Optional[str]:
    """Return a GitHub token via the ``gh`` CLI."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _get_copilot_api_url() -> str:
    """Resolve the Copilot inference base URL via GraphQL, falling back to the
    standard individual endpoint."""
    token = get_github_token()
    if token:
        try:
            resp = requests.post(
                "https://api.github.com/graphql",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": "{ viewer { copilotEndpoints { api } } }"},
                timeout=5,
            )
            if resp.status_code == 200:
                api = resp.json()["data"]["viewer"]["copilotEndpoints"]["api"]
                if api:
                    return api.rstrip("/")
        except requests.exceptions.RequestException:
            pass
    return "https://api.individual.githubcopilot.com"


def list_copilot_models() -> list[tuple[str, str]]:
    """Fetch available Copilot models from the inference API.

    Returns a list of ``(display_label, model_id)`` tuples sorted by model ID.
    Requires ``gh auth login`` with an active Copilot subscription.
    """
    token = get_github_token()
    if not token:
        return []
    try:
        url = _get_copilot_api_url()
        resp = requests.get(
            f"{url}/models",
            headers={"Authorization": f"Bearer {token}", **_COPILOT_HEADERS},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        models = data.get("data", data) if isinstance(data, dict) else data
        chat_models = [m for m in models if not m.get("id", "").startswith("text-embedding")]
        return [(m["id"], m["id"]) for m in sorted(chat_models, key=lambda x: x.get("id", ""))]
    except requests.exceptions.RequestException:
        return []


def check_copilot_auth() -> bool:
    """Return True if a GitHub token with Copilot access is available."""
    token = get_github_token()
    if not token:
        return False
    try:
        url = _get_copilot_api_url()
        resp = requests.get(
            f"{url}/models",
            headers={"Authorization": f"Bearer {token}", **_COPILOT_HEADERS},
            timeout=5,
        )
        return resp.status_code == 200
    except requests.exceptions.RequestException:
        return False  # Network error should be treated as an auth failure


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output."""

    def _create_chat_result(self, response, generation_info=None):
        return super()._create_chat_result(
            _sanitize_copilot_response(response), generation_info
        )

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


def _sanitize_copilot_response(response: Any) -> Any:
    """Normalize Copilot token usage fields for langchain_openai.

    Copilot can return ``service_tier`` along with ``None`` values in
    ``cached_tokens`` or ``reasoning_tokens``. ``langchain_openai`` subtracts
    those fields from the prompt/completion totals, which raises ``TypeError``
    when the detail value is ``None``.
    """
    if isinstance(response, dict):
        response_dict = deepcopy(response)
    elif hasattr(response, "model_dump"):
        response_dict = response.model_dump()
    else:
        return response

    usage = response_dict.get("usage")
    if not isinstance(usage, dict):
        return response_dict

    if response_dict.get("service_tier") not in {"priority", "flex"}:
        return response_dict

    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict) and prompt_details.get("cached_tokens") is None:
        prompt_details["cached_tokens"] = 0

    completion_details = usage.get("completion_tokens_details")
    if (
        isinstance(completion_details, dict)
        and completion_details.get("reasoning_tokens") is None
    ):
        completion_details["reasoning_tokens"] = 0

    return response_dict


class CopilotClient(BaseLLMClient):
    """Client for GitHub Copilot inference API.

    Uses the gh CLI for authentication. Automatically routes models that only
    support the Responses API (gpt-5.4, codex variants) to ``/responses``
    instead of ``/chat/completions``.
    """

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance pointed at the Copilot API."""
        token = get_github_token()
        if not token:
            raise RuntimeError(
                "No GitHub token found. Run `gh auth login` to authenticate."
            )
        copilot_url = _get_copilot_api_url()

        llm_kwargs = {
            "model": self.model,
            "base_url": copilot_url,
            "api_key": token,
            "default_headers": dict(_COPILOT_HEADERS),
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        if self.model in _RESPONSES_ONLY_MODELS:
            llm_kwargs["use_responses_api"] = True

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model("copilot", self.model)
