import os
from typing import Any, Optional

from .openai_client import OpenAIClient

# GitHub Models pins REST behaviour behind ``X-GitHub-Api-Version``. When the
# header is absent the endpoint silently falls back to ``2022-11-28``; pinning
# here gives us the documented surface and avoids drift when GitHub eventually
# retires the legacy version. Users override by passing their own
# ``default_headers``.
_API_VERSION = "2026-03-10"

_MISSING_TOKEN_MSG = (
    "GitHub Copilot requires a personal access token. Set the GITHUB_TOKEN "
    "environment variable (PAT must include the `models:read` scope) or "
    "pass api_key=... when constructing the client. Without a token the "
    "underlying OpenAI SDK falls back to OPENAI_API_KEY and emits a "
    "misleading credentials error."
)


class GitHubCopilotClient(OpenAIClient):
    """Client for GitHub Models / Copilot via the OpenAI-compatible
    inference endpoint (https://models.github.ai/inference).

    Subclasses :class:`OpenAIClient` so streaming, tool-calling, structured
    output, and content normalization all flow through the existing OpenAI
    plumbing. Layered on top:

    1. Provider is pinned to ``"github_copilot"`` so the parent's
       ``_PROVIDER_CONFIG`` entry supplies the base URL and ``GITHUB_TOKEN``
       env-var fallback automatically.
    2. ``X-GitHub-Api-Version`` is injected into ``default_headers`` so the
       API responds with the modern, documented surface.
    3. Missing-token detection upfront so the user sees an actionable
       Copilot-specific message instead of an OpenAI-SDK ``OPENAI_API_KEY``
       complaint.

    A future swap to ``langchain-github-copilot`` (currently incompatible
    with langchain-core 1.x) is a one-class change inside ``get_llm()`` —
    no other file needs to move.
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        # Pre-bake the ``X-GitHub-Api-Version`` header into kwargs at
        # construction time so ``get_llm()`` stays a pure read of
        # ``self.kwargs`` and is safe to call repeatedly. Caller-supplied
        # entries win over the provider default, which lets users pin a
        # different API version when they need to.
        user_headers = kwargs.pop("default_headers", None) or {}
        kwargs["default_headers"] = {
            "X-GitHub-Api-Version": _API_VERSION,
            **user_headers,
        }
        super().__init__(model, base_url, provider="github_copilot", **kwargs)

    def get_llm(self) -> Any:
        # Fail fast with a useful message if the user has no token. The
        # OpenAI SDK's own validator otherwise complains about
        # ``OPENAI_API_KEY``, which is the wrong env var for this provider.
        # The check stays here (not in ``__init__``) because the parent
        # ``OpenAIClient.get_llm`` reads ``os.environ`` lazily, so users
        # can set ``GITHUB_TOKEN`` after construction but before invocation.
        token = self.kwargs.get("api_key") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError(_MISSING_TOKEN_MSG)
        return super().get_llm()
