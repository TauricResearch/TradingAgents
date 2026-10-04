#!/usr/bin/env python3
"""Resolve CLIProxyAPI's client key or check its advertised Claude/Codex/Gemini models."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def client_key():
    key = os.environ.get("CLIPROXY_API_KEY")
    if key:
        return key
    path = Path(os.environ.get("CLIPROXY_CONFIG", "/opt/homebrew/etc/cliproxyapi.conf"))
    try:
        import yaml

        config = yaml.safe_load(path.read_text()) or {}
        # v8 moved client keys to access.api-keys and wins over the legacy root list.
        access = config.get("access") or {}
        keys = access["api-keys"] if "api-keys" in access else config.get("api-keys", [])
        if isinstance(keys, list) and keys and isinstance(keys[0], str) and keys[0]:
            return keys[0]
    except (ImportError, OSError, ValueError):
        pass
    except Exception:
        # YAML parser errors can contain secret-bearing source lines.
        raise ValueError("Could not parse proxy config; set CLIPROXY_API_KEY.") from None
    raise ValueError("Set CLIPROXY_API_KEY or CLIPROXY_CONFIG (YAML with api-keys).")


def check_models(base_url, models, provider="claude"):
    # Anthropic's SDK accepts the server root; tolerate callers including /v1.
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    request = urllib.request.Request(
        url + "/models", headers={"Authorization": "Bearer " + client_key()}
    )
    # Homebrew may return before a newly started server begins listening.
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                available = {item["id"] for item in json.load(response)["data"]}
            break
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Proxy model check returned HTTP {exc.code}; check the client key.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 4:
                raise ValueError("Cannot reach CLIProxyAPI; check its server and base URL.") from None
            time.sleep(1)
        except (ValueError, KeyError, TypeError):
            raise ValueError("Proxy returned an invalid model list.") from None
    if not all(isinstance(model, str) for model in available):
        raise ValueError("Proxy returned an invalid model list.")
    label = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}[provider]
    prefixes = {"claude": ("claude",), "codex": ("gpt-", "o1", "o3", "o4", "codex"),
                "gemini": ("gemini",)}[provider]
    matching = sorted(model for model in available if model.lower().startswith(prefixes))
    auth_hint = (
        "Configure Gemini credentials in CLIProxyAPI. " if provider == "gemini"
        else f"If {label} is not authenticated, run: cliproxyapi --{provider}-login. "
    )
    missing = [model for model in models if model not in available]
    if missing:
        raise ValueError(
            "Proxy does not advertise: " + ", ".join(missing)
            + f". Available {label} models: " + (", ".join(matching) or "none")
            + ". " + auth_hint
            + "Otherwise set TRADINGAGENTS_DEEP_MODEL / TRADINGAGENTS_QUICK_MODEL "
            "to advertised model IDs."
        )
    print("Proxy preflight OK: " + ", ".join(models))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", action="store_true", help="Emit client key for shell capture only")
    parser.add_argument("--base-url", default="http://127.0.0.1:8317")
    parser.add_argument("--provider", choices=("claude", "codex", "gemini"), default="claude")
    parser.add_argument("models", nargs="*")
    args = parser.parse_args()
    try:
        if args.key:
            print(client_key())
        else:
            check_models(args.base_url, args.models, args.provider)
    except ValueError as exc:
        print(f"CLIProxyAPI: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
