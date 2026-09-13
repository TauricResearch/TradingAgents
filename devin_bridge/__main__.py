"""Command-line entry point for the Devin bridge sidecar.

Run with::

    python -m devin_bridge
    python -m devin_bridge --help
    python -m devin_bridge --list-models
    python -m devin_bridge --model <model-id>
    python -m devin_bridge --quick-model MODEL_A --deep-model MODEL_B
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from .config import BridgeConfig, resolve_config_from_cli


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m devin_bridge",
        description="Local OpenAI Chat Completions bridge backed by the Devin CLI.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind host (default: 127.0.0.1, loopback only)",
    )
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Bind port (default: 8765)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Devin model for BOTH quick and deep (shorthand). "
             "Default: Devin CLI configured/default model",
    )
    parser.add_argument(
        "--quick-model", default=None,
        help="Devin model for devin-quick alias (overrides --model). "
             "Default: Devin CLI configured/default model",
    )
    parser.add_argument(
        "--deep-model", default=None,
        help="Devin model for devin-deep alias (overrides --model). "
             "Default: Devin CLI configured/default model",
    )
    parser.add_argument(
        "--timeout", type=int, default=180,
        help="Per-request Devin timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--max-concurrency", type=int, default=1,
        help="Maximum concurrent Devin invocations (default: 1)",
    )
    parser.add_argument(
        "--runtime-dir", default="",
        help="Devin runtime workspace directory (default: auto, outside checkout)",
    )
    parser.add_argument(
        "--export-dir", default="",
        help="Directory for Devin export files (default: none)",
    )
    parser.add_argument(
        "--devin-bin", default="",
        help="Path to Devin CLI binary (default: auto-detect)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="List available Devin models and exit (no inference, no server)",
    )
    args = parser.parse_args(argv)
    return args


def list_models() -> int:
    """Query the authenticated Devin CLI for available models and print them."""
    from .config import BridgeConfig

    config = BridgeConfig()
    devin_bin = config.resolve_devin_bin()

    try:
        result = subprocess.run(
            [devin_bin, "models", "list"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print(f"Error: Devin binary not found at {devin_bin}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("Error: devin models list timed out", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print(f"Error: devin models list failed: {result.stderr.strip()}", file=sys.stderr)
        return 1

    # Print the raw output — it already includes display names and CLI identifiers.
    print(result.stdout)
    return 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.list_models:
        sys.exit(list_models())

    # Resolve quick/deep models from CLI + environment.
    quick_model, deep_model = resolve_config_from_cli(
        model=args.model,
        quick_model=args.quick_model,
        deep_model=args.deep_model,
    )

    config = BridgeConfig(
        host=args.host,
        port=args.port,
        quick_model=quick_model,
        deep_model=deep_model,
        timeout=args.timeout,
        max_concurrency=args.max_concurrency,
        runtime_dir=args.runtime_dir,
        export_dir=args.export_dir or None,
        devin_bin=args.devin_bin,
        debug=args.debug,
    )

    level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[bridge] %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from .server import run_server
    run_server(config)


if __name__ == "__main__":
    main()
