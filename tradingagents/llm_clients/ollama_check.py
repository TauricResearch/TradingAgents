"""
ollama_check.py
Diagnostic utility — verifies Ollama server is reachable and required models are pulled.
"""

from __future__ import annotations

import os
import sys
import requests


def _resolve_base_url(config: dict) -> str:
    """
    Resolve the Ollama ROOT base URL (no /v1 suffix).

    When the user selects Ollama in the CLI, select_llm_provider() returns
    "http://localhost:11434/v1" as backend_url. The health-check endpoint
    GET /api/tags lives at the root, so we strip any trailing /v1.

    Priority: config["backend_url"] (stripped) → OLLAMA_HOST env var → localhost default.
    """
    url = config.get("backend_url") or os.getenv(
        "OLLAMA_HOST", "http://localhost:11434"
    )
    # Strip /v1 suffix added by select_llm_provider() for OpenAI-compat clients
    return url.rstrip("/").removesuffix("/v1")


def ping_ollama(base_url: str, timeout: int = 5) -> bool:
    """
    Return True if Ollama server responds at GET {base_url}/api/tags, else False.
    Never raises — all exceptions are caught.
    Does NOT print; caller handles all output.
    """
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False


def list_local_models(base_url: str) -> list[str]:
    """
    Return model name strings from GET {base_url}/api/tags.
    Response JSON shape: {"models": [{"name": "qwen3:latest"}, ...]}
    Returns [] on any failure.
    """
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


def check_model_available(model_name: str, local_models: list[str]) -> bool:
    """
    Return True if model_name is a substring of any entry in local_models (case-insensitive).
    Example: "qwen3" matches "qwen3:latest".
    """
    needle = model_name.lower()
    return any(needle in m.lower() for m in local_models)


def run_ollama_check(config: dict, exit_on_failure: bool = False) -> bool:
    """
    Full diagnostic using deep_think_llm and quick_think_llm from config.

    Steps:
      1. Resolve root base URL (strips /v1 from backend_url)
      2. Ping server  → warn + return False if unreachable
      3. List and print local models
      4. Check deep_think_llm is pulled
      5. Check quick_think_llm is pulled

    Returns True only when all checks pass.
    Calls sys.exit(1) on first failure when exit_on_failure=True.
    """
    base_url = _resolve_base_url(config)
    deep_model = config.get("deep_think_llm")
    quick_model = config.get("quick_think_llm")
    all_ok = True

    print(f"[Ollama Check] Pinging server at {base_url} ...")

    if not ping_ollama(base_url):
        print(
            f"[Ollama Check] ✗ Cannot reach Ollama at {base_url}\n"
            f"               → Is Ollama running? Try: ollama serve"
        )
        if exit_on_failure:
            sys.exit(1)
        return False

    print("[Ollama Check] ✓ Server is reachable.")

    local_models = list_local_models(base_url)
    if local_models:
        print("[Ollama Check] Available local models:")
        for m in local_models:
            print(f"               - {m}")
    else:
        print("[Ollama Check] ⚠ No models found locally. Try: ollama pull qwen3")

    for label, model in [("Deep", deep_model), ("Quick", quick_model)]:
        if not model:
            continue
        if check_model_available(model, local_models):
            print(f'[Ollama Check] ✓ {label} model "{model}" found.')
        else:
            print(
                f'[Ollama Check] ✗ {label} model "{model}" NOT found locally.\n'
                f"               → Run: ollama pull {model}"
            )
            all_ok = False

    if not all_ok and exit_on_failure:
        sys.exit(1)

    return all_ok
