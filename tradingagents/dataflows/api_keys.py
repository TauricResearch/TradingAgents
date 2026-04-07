from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


_DOC_ENV_MAP = {
    "ALPHA_VANTAGE_API_KEY": "Alpha Vantage",
    "NAVER_CLIENT_ID": "Naver.Client ID",
    "NAVER_CLIENT_SECRET": "Naver.Client Secret",
    "OPENDART_API_KEY": "OpenDart",
}


def _get_api_keys_doc_path() -> Path:
    return Path(__file__).resolve().parents[2] / "Docs" / "list_api_keys.md"


@lru_cache(maxsize=1)
def _load_documented_keys() -> dict[str, str]:
    path = _get_api_keys_doc_path()
    if not path.exists():
        return {}

    content = path.read_text(encoding="utf-8")
    parsed: dict[str, str] = {}
    current_section = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Alpha Vantage:"):
            _, value = line.split(":", 1)
            parsed["ALPHA_VANTAGE_API_KEY"] = value.strip()
            current_section = None
            continue

        if line.startswith("OpenDart:"):
            _, value = line.split(":", 1)
            parsed["OPENDART_API_KEY"] = value.strip()
            current_section = None
            continue

        if line.endswith(":") and not line.startswith("-"):
            current_section = line[:-1].strip()
            continue

        if line.startswith("-") and ":" in line and current_section == "Naver":
            key, value = line[1:].split(":", 1)
            normalized_key = key.strip().lower()
            if normalized_key == "client id":
                parsed["NAVER_CLIENT_ID"] = value.strip()
            elif normalized_key == "client secret":
                parsed["NAVER_CLIENT_SECRET"] = value.strip()
            continue

    return parsed


def get_api_key(env_name: str) -> str | None:
    value = os.getenv(env_name)
    if value:
        return value.strip()

    documented = _load_documented_keys().get(env_name)
    if documented:
        return documented.strip()

    return None
