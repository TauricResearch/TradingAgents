"""Provider→model map and API-key presence. Ported from webui.py."""
from __future__ import annotations

import os

# Doubao only. Deep model is fixed to the non-reasoning Doubao 1.5 Pro and the
# quick model to Seed 1.6 Flash in server/runs.py; the UI no longer offers a
# provider/model choice. This map remains for key-presence reporting.
PROVIDER_MODELS: dict[str, list[str]] = {
    "doubao": ["doubao-1-5-pro-32k-250115", "doubao-seed-1-6-flash-250828"],
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
