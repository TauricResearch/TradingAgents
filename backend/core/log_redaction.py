"""Secret-scrubbing for logs.

A single :class:`RedactionFilter` is attached to every logging handler that can
persist or display records (the console handler and the async DB handler). It
masks two things, in order of reliability:

1. **Exact secret values** read from the environment at startup — every
   provider API key, the JWT ``SECRET_KEY``, the Fernet ``ENCRYPTION_KEY`` and
   the data-vendor keys. If the literal value appears anywhere in a message or
   traceback it is replaced. This catches keys leaked inside SDK exception
   reprs / request URLs that no generic pattern would recognise.
2. **Common key shapes** (``sk-...``, ``AIza...``, ``Bearer ...``,
   ``api_key=...``) as defense-in-depth for anything not sourced from our env.

The filter mutates the record so the redaction is shared by all downstream
handlers (idempotent), covering both the rendered message and the exception
traceback.
"""
from __future__ import annotations

import logging
import os
import re
import traceback

_MASK = "***REDACTED***"

# Env vars whose *values* must never appear in logs. Kept in one place so the
# list of provider keys stays close to llm_clients.api_key_env.
_SENSITIVE_ENV_VARS = (
    "SECRET_KEY", "ENCRYPTION_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "AZURE_OPENAI_API_KEY",
    "XAI_API_KEY", "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY", "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY", "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY", "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY", "NVIDIA_API_KEY", "LITELLM_API_KEY",
    "ALPHA_VANTAGE_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
)

# Generic provider-key shapes (defense-in-depth).
_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),          # OpenAI / Anthropic (sk-ant-...)
    re.compile(r"xai-[A-Za-z0-9_\-]{12,}"),         # xAI
    re.compile(r"nvapi-[A-Za-z0-9_\-]{12,}"),       # NVIDIA
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),          # Google
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),  # Authorization: Bearer xxx
    # key/secret/token/password = "<value>"  (json or kwargs form)
    re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|secret|token|password)"
        r"(\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{6,})"
    ),
]


def _build_literals() -> list[str]:
    """Collect non-trivial secret values present in the environment, longest
    first so overlapping values are masked greedily."""
    values: set[str] = set()
    for name in _SENSITIVE_ENV_VARS:
        val = os.environ.get(name)
        if val and len(val) >= 6:  # skip empty / trivially short
            values.add(val)
    return sorted(values, key=len, reverse=True)


def redact_text(text: str, literals: list[str] | None = None) -> str:
    if not text:
        return text
    literals = _LITERALS if literals is None else literals
    for secret in literals:
        if secret in text:
            text = text.replace(secret, _MASK)
    for pat in _PATTERNS:
        if pat.groups >= 3:  # the labelled key=value pattern: keep label, mask value
            text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASK}", text)
        else:
            text = pat.sub(_MASK, text)
    return text


# Built once at import; env is already loaded by the time logging is configured.
_LITERALS = _build_literals()


class RedactionFilter(logging.Filter):
    """Scrubs secrets from the message and any exception traceback in-place."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # Render args into the message now, then redact and drop args so no
            # downstream formatter re-substitutes the raw values.
            msg = record.getMessage()
            redacted = redact_text(msg)
            if redacted != msg:
                record.msg = redacted
                record.args = ()

            if record.exc_info:
                record.exc_text = redact_text(
                    "".join(traceback.format_exception(*record.exc_info))
                )
                record.exc_info = None  # prevent any handler re-formatting the raw trace
            elif record.exc_text:
                record.exc_text = redact_text(record.exc_text)
        except Exception:
            # Redaction must never drop a log record; fall back to passing it
            # through unchanged rather than raising inside logging.
            pass
        return True


# Shared singleton — attach the same instance to every handler.
redaction_filter = RedactionFilter()


def install_redaction(*handlers: logging.Handler) -> None:
    """Attach the redaction filter to the given handlers (idempotent)."""
    for h in handlers:
        if redaction_filter not in h.filters:
            h.addFilter(redaction_filter)
