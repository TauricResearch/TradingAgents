"""Check that a Gemini route can generate before starting a report batch."""

import argparse
import os
import re
import sys

from dotenv import dotenv_values
from google import genai
from google.genai import types

from scripts.claude_proxy import client_key

_RESET_TIME = re.compile(r"['\"]reset_time['\"]\s*:\s*['\"]([^'\"]+)['\"]")


def probe_models(base_url: str, models: list[str], thinking_level: str, mode: str) -> None:
    if mode == "proxy":
        key = client_key()
    else:
        key = os.environ.get("GOOGLE_API_KEY") or dotenv_values(".env").get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Direct Gemini mode requires GOOGLE_API_KEY in the environment or .env.")

    client = genai.Client(
        api_key=key,
        vertexai=False,
        http_options=types.HttpOptions(base_url=base_url, timeout=15000),
    )
    config = types.GenerateContentConfig(
        max_output_tokens=64,
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for model in dict.fromkeys(models):
        try:
            client.models.generate_content(model=model, contents="Reply with OK only.", config=config)
        except Exception as exc:
            message = str(exc)
            if "Individual quota reached" in message or "model_cooldown" in message:
                reset = _RESET_TIME.search(message)
                wait = f" (resets in {reset.group(1)})" if reset else ""
                reason = (
                    f"upstream quota exhausted{wait}; wait for its reset or use "
                    "a model/account with capacity"
                )
            elif "429" in message or "RESOURCE_EXHAUSTED" in message:
                reason = "rate limited by the upstream provider"
            elif "503" in message or "MODEL_CAPACITY_EXHAUSTED" in message:
                reason = "no upstream capacity available"
            else:
                reason = f"{type(exc).__name__}: {message[:200]}"
            raise RuntimeError(f"Gemini {mode} probe failed for {model}: {reason}") from None
        print(f"Gemini {mode} probe OK: {model}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("proxy", "direct"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--thinking-level", required=True)
    parser.add_argument("models", nargs="+")
    args = parser.parse_args()
    try:
        probe_models(args.base_url, args.models, args.thinking_level, args.mode)
    except (ValueError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
