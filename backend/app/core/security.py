import os
import re
from typing import Any

# Regex patterns matching common LLM and Cloud provider secret keys
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),          # OpenAI, OpenRouter, Groq, DeepSeek
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),      # Anthropic
    re.compile(r"AIza[0-9A-Za-z-_]{30,}", re.IGNORECASE),          # Google Cloud / Gemini
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE), # Bearer tokens
]

# Known environment variables storing API keys
SENSITIVE_ENV_VARS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "MINIMAX_API_KEY",
    "FINANCIAL_MODELING_PREP_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "FRED_API_KEY",
]


def mask_secret_key(val: str | None) -> str:
    """Mask an API key for safe UI and API preview.

    Examples:
        'sk-proj-1234567890abcdef' -> 'sk-...cdef'
        'short12' -> 's...2'
        None or '' -> ''
    """
    if not val:
        return ""
    clean = val.strip()
    length = len(clean)
    if length >= 8:
        return f"{clean[:3]}...{clean[-4:]}"
    elif length > 2:
        return f"{clean[0]}...{clean[-1]}"
    return "***"


def sanitize_sensitive_text(text: str | None) -> str:
    """Scrub potential API keys and secrets from error messages and tracebacks."""
    if not text:
        return ""

    sanitized = str(text)

    # 1. Redact via known regex patterns
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_API_KEY]", sanitized)

    # 2. Redact active environment secrets if present in the text
    for env_var in SENSITIVE_ENV_VARS:
        secret_val = os.getenv(env_var)
        if secret_val and len(secret_val.strip()) >= 6:
            clean_secret = secret_val.strip()
            if clean_secret in sanitized:
                sanitized = sanitized.replace(clean_secret, "[REDACTED_API_KEY]")

    return sanitized


def sanitize_sensitive_data(data: Any) -> Any:
    """Recursively scrub sensitive information from dictionary or list structures before DB save or SSE broadcast."""
    if isinstance(data, str):
        return sanitize_sensitive_text(data)
    elif isinstance(data, dict):
        cleaned_dict = {}
        for k, v in data.items():
            # If the key itself indicates a secret, mask or sanitize
            if any(term in k.lower() for term in ("api_key", "secret", "token", "password", "authorization")):
                if isinstance(v, str):
                    cleaned_dict[k] = mask_secret_key(v)
                else:
                    cleaned_dict[k] = "[REDACTED]"
            else:
                cleaned_dict[k] = sanitize_sensitive_data(v)
        return cleaned_dict
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_sensitive_data(item) for item in data)
    return data


def sanitize_ticker(ticker: str | None, default: str = "TICKER") -> str:
    """Sanitize ticker input to alphanumeric, hyphens, and underscores, preventing path traversal and command injection."""
    if not ticker:
        return default
    first_token = str(ticker).strip().split()[0].split(";")[0]
    cleaned = "".join(c for c in first_token if c.isalnum() or c in ("-", "_")).upper()
    return cleaned or default


def sanitize_date(trade_date: str | None, default: str = "") -> str:
    """Sanitize date string input to alphanumeric, hyphens, and underscores."""
    if not trade_date:
        return default
    first_token = str(trade_date).strip().split()[0].split(";")[0]
    cleaned = "".join(c for c in first_token if c.isalnum() or c in ("-", "_"))
    return cleaned or default
