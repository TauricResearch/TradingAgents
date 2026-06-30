"""Canonical provider -> API-key env-var mapping.

A single source of truth for which environment variable holds the API
key for each supported LLM provider. Used by the CLI's interactive key
prompt (cli/utils.ensure_api_key) and by anything else that needs to
ask "does this provider require a key, and which env var is it?".

When adding a new provider, register its env var here so the CLI flow
prompts for it automatically instead of failing on first API call.
"""

from __future__ import annotations

# Amazon Bedrock's native API key (added by AWS in 2025) is a bearer token read
# from this env var. It is an alternative to the AWS SigV4 credential chain, not
# a replacement: Bedrock is intentionally mapped to ``None`` in
# ``PROVIDER_API_KEY_ENV`` below so the CLI never force-prompts for a single key —
# credential-chain users (IAM role / profile) must not be nagged for a token they
# do not use. The bearer token is honored automatically by langchain-aws/botocore
# when set, so it needs no wiring beyond being documented and discoverable.
BEDROCK_BEARER_TOKEN_ENV = "AWS_BEARER_TOKEN_BEDROCK"

# Env vars that drive AWS SigV4 credential resolution. langchain-aws's bearer
# branch still builds the boto3 client through the standard session, so any of
# these — even a stale/invalid one — is resolved eagerly and can raise at
# construction (e.g. a non-existent ``AWS_PROFILE`` -> ``ProfileNotFound``, or a
# partial ``AWS_ACCESS_KEY_ID`` with no secret) EVEN WHEN a valid bearer token is
# present. An explicit Bedrock API key is an unambiguous "use bearer auth" signal,
# so the client transiently clears these around construction (see
# ``BedrockClient.get_llm``) to make "a bearer token alone just works" actually
# hold. The same list seeds the CLI credential-chain heuristic and the tests.
AWS_SIGV4_CREDENTIAL_ENV_VARS = (
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_ROLE_ARN",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    "AWS_CONTAINER_CREDENTIALS_FULL_URI",
)

PROVIDER_API_KEY_ENV: dict[str, str | None] = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "azure":      "AZURE_OPENAI_API_KEY",
    # Bedrock has two valid auth modes — the AWS SigV4 credential chain (IAM role
    # / profile / access keys) OR a native bearer token (AWS_BEARER_TOKEN_BEDROCK,
    # see BEDROCK_BEARER_TOKEN_ENV). Neither is a single forced key, so this stays
    # None and the CLI advises rather than prompts (see cli.utils.ensure_api_key).
    "bedrock":    None,
    "xai":        "XAI_API_KEY",
    "deepseek":   "DEEPSEEK_API_KEY",
    # Dual-region providers each carry their own account; keys are not
    # interchangeable between the international and China endpoints.
    "qwen":       "DASHSCOPE_API_KEY",
    "qwen-cn":    "DASHSCOPE_CN_API_KEY",
    "glm":        "ZHIPU_API_KEY",
    "glm-cn":     "ZHIPU_CN_API_KEY",
    "minimax":    "MINIMAX_API_KEY",
    "minimax-cn": "MINIMAX_CN_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    # Additional hosted OpenAI-compatible providers (model is user-specified).
    # kimi -> Moonshot AI; nvidia -> NVIDIA NIM.
    "mistral":    "MISTRAL_API_KEY",
    "kimi":       "MOONSHOT_API_KEY",
    "groq":       "GROQ_API_KEY",
    "nvidia":     "NVIDIA_API_KEY",
    # Local runtimes do not authenticate.
    "ollama":     None,
    # Generic OpenAI-compatible endpoint: the client reads this when set (keyed
    # relays), but it is marked key-optional in the provider registry so the CLI
    # never forces a prompt and keyless local servers still work.
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}


def get_api_key_env(provider: str) -> str | None:
    """Return the env var name for `provider`'s API key, or None if not applicable.

    Unknown providers also return None — callers should treat that as
    "no key check possible" rather than as "no key required".
    """
    return PROVIDER_API_KEY_ENV.get(provider.lower())
