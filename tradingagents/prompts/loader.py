"""Small helpers for loading packaged prompt text."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

_PROMPT_PACKAGE = "tradingagents.prompts"
_GLOBAL_POLICY = "global_policy.txt"


def load_prompt(path: str) -> str:
    """Load a built-in prompt file as UTF-8 text."""
    try:
        return resources.files(_PROMPT_PACKAGE).joinpath(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Built-in prompt file is missing: {path}") from exc


@lru_cache(maxsize=1)
def load_global_policy() -> str:
    """Load the shared policy applied to every LLM agent prompt."""
    return load_prompt(_GLOBAL_POLICY)


def with_global_policy(role_prompt: str) -> str:
    """Prepend the shared global policy to one role-specific prompt."""
    return f"{load_global_policy().rstrip()}\n\n{role_prompt.lstrip()}"


def render_agent_prompt(path: str, **values: object) -> str:
    """Load a role prompt, prepend the global policy, and interpolate values."""
    return with_global_policy(load_prompt(path)).format(**values)
