import contextlib
import os
import threading
from typing import Any

from .api_key_env import AWS_SIGV4_CREDENTIAL_ENV_VARS, BEDROCK_BEARER_TOKEN_ENV
from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

# Bedrock has no global default region; us-west-2 hosts the broadest model set.
_DEFAULT_REGION = "us-west-2"
_BEDROCK_CLASS = None

# Mutating os.environ is process-global; serialize the brief scrub window in
# get_llm so concurrent client construction can't observe a half-scrubbed env.
_ENV_SCRUB_LOCK = threading.Lock()


@contextlib.contextmanager
def _bearer_auth_env():
    """Transiently clear ambient AWS SigV4 credential env vars when a Bedrock
    bearer token is set, so client construction uses bearer auth cleanly.

    langchain-aws's bearer branch still builds the boto3 client through the
    standard session, which eagerly resolves the SigV4 chain — so a stale
    ``AWS_PROFILE`` (``ProfileNotFound``), partial access keys, or container
    credential hints would raise at construction even though the bearer token
    alone authenticates. An explicit token is an unambiguous "use bearer auth"
    signal, so we remove those vars for the duration of construction and restore
    them in ``finally`` (env is left exactly as found). No-op when no token is set,
    preserving the SigV4 credential-chain path untouched.
    """
    if not os.environ.get(BEDROCK_BEARER_TOKEN_ENV):
        yield
        return
    with _ENV_SCRUB_LOCK:
        saved = {
            var: os.environ.pop(var)
            for var in AWS_SIGV4_CREDENTIAL_ENV_VARS
            if var in os.environ
        }
        try:
            yield
        finally:
            os.environ.update(saved)


def _bedrock_class():
    """Lazily import langchain-aws (the optional ``[bedrock]`` extra) and return a
    ChatBedrockConverse subclass with normalized content output.

    Imported on demand so the optional dependency (and boto3) isn't required by
    the rest of the package; cached after the first call.
    """
    global _BEDROCK_CLASS
    if _BEDROCK_CLASS is not None:
        return _BEDROCK_CLASS

    try:
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:
        raise ImportError(
            "AWS Bedrock support requires the optional 'langchain-aws' dependency. "
            'Install it with: pip install "tradingagents[bedrock]"'
        ) from exc

    class NormalizedChatBedrockConverse(ChatBedrockConverse):
        """ChatBedrockConverse with normalized (string) content output."""

        def invoke(self, input, config=None, **kwargs):
            return normalize_content(super().invoke(input, config, **kwargs))

    _BEDROCK_CLASS = NormalizedChatBedrockConverse
    return _BEDROCK_CLASS


class BedrockClient(BaseLLMClient):
    """Client for Amazon Bedrock via the Converse API (langchain-aws).

    Two authentication modes are supported, with the bearer token taking
    precedence when both are configured:

    1. **Bedrock API key (bearer token)** — set ``AWS_BEARER_TOKEN_BEDROCK`` to a
       Bedrock API key (created in the AWS console / via IAM). langchain-aws reads
       it automatically and sends ``Authorization: Bearer <token>`` instead of
       SigV4, so no AWS access key, secret, or profile is needed. This is the
       simplest setup for a single-account run. When a token is set, ambient AWS
       SigV4 credential env vars (a stale ``AWS_PROFILE``, partial access keys,
       container-credential hints) are transiently ignored during construction so
       they cannot derail bearer auth — see ``_bearer_auth_env``.
    2. **AWS SigV4 credential chain** — the standard chain (env access keys,
       ``~/.aws/credentials``, ``AWS_PROFILE``, or an IAM role) when no bearer
       token is set.

    Either way an explicit region is required (the bearer token carries none):
    set ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` (otherwise this falls back to
    ``us-west-2``). The model name is a Bedrock model ID or cross-region
    inference profile ID, e.g. ``us.anthropic.claude-opus-4-8``.
    """

    def get_llm(self) -> Any:
        """Return a configured ChatBedrockConverse instance."""
        self.warn_if_unknown_model()
        chat_cls = _bedrock_class()

        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or _DEFAULT_REGION
        )
        llm_kwargs = {"model": self.model, "region_name": region}
        for key in ("temperature", "max_tokens", "max_retries", "callbacks"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]
        # Construct inside the bearer-auth env guard so an explicit token isn't
        # derailed by ambient SigV4 credential env vars (no-op without a token).
        with _bearer_auth_env():
            return chat_cls(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for Bedrock (any model ID accepted)."""
        return validate_model("bedrock", self.model)
