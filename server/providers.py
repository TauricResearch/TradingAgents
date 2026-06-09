"""Provider→model map and API-key presence. Ported from webui.py."""
from __future__ import annotations

import os

PROVIDER_MODELS: dict[str, list[str]] = {
    "doubao": ["doubao-seed-1-6-flash-250828", "doubao-seed-1-6-250615", "doubao-1-5-pro-32k-250115"],
    "qwen": ["qwen-plus", "qwen-turbo", "qwen-max"],
    "google": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
               "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview"],
    "openai": ["gpt-5.4-mini", "gpt-5.4", "gpt-5"],
    "anthropic": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "glm": ["glm-4-plus", "glm-4.5"],
    "xai": ["grok-4", "grok-4-mini"],
    "openrouter": ["openai/gpt-5", "anthropic/claude-sonnet-4-6"],
}

PROVIDER_KEY_ENV: dict[str, str] = {
    "google": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY", "glm": "ZHIPU_API_KEY",
    "doubao": "ARK_API_KEY",
    "xai": "XAI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}


def provider_table() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for prov, models in PROVIDER_MODELS.items():
        key_env = PROVIDER_KEY_ENV.get(prov)
        out[prov] = {
            "models": models,
            "key_env": key_env,
            "key_present": bool(os.getenv(key_env)) if key_env else True,
        }
    return out
