"""Command-line entry point: ``python -m desk_adapter <run|capabilities|resolve>``.

Order matters: reserve fd 1 and prepare the environment BEFORE importing
``tradingagents`` (the engine reads dir env vars and loads ``.env`` at import).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desk_adapter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="stream one analysis run as NDJSON")
    p_run.add_argument("--config", required=True, help="path to the resolved run-config JSON")
    p_run.add_argument("--base-dir", default=None, help="app data dir for results/cache/memory")

    sub.add_parser("capabilities", help="dump provider/model/vendor surface as one JSON object")

    p_res = sub.add_parser("resolve", help="realize pending outcomes (no analysis)")
    p_res.add_argument("--config", default=None)
    p_res.add_argument("--ticker", default=None)
    p_res.add_argument("--all", action="store_true")
    p_res.add_argument("--base-dir", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Reserve the protocol channel first; everything else may write to stderr.
    from desk_adapter.protocol import SCHEMA_VERSION, Emitter, reserve_stdout

    real_out = reserve_stdout()
    logging.basicConfig(stream=sys.stderr, level=os.environ.get("DESK_LOG_LEVEL", "WARNING"))
    logging.captureWarnings(True)

    args = _build_parser().parse_args(argv)

    from desk_adapter.env import prepare_environment

    prepare_environment(getattr(args, "base_dir", None))

    run_id = os.environ.get("DESK_RUN_ID") or uuid.uuid4().hex
    emitter = Emitter(real_out, run_id)
    emitter.emit("handshake", schema_version=SCHEMA_VERSION, pid=os.getpid())

    if args.cmd == "capabilities":
        from desk_adapter.introspect import capabilities_command

        return capabilities_command(emitter)

    from desk_adapter import run as run_mod

    if args.cmd == "run":
        return run_mod.run_command(args, emitter)
    if args.cmd == "resolve":
        return run_mod.resolve_command(args, emitter)
    return 2


if __name__ == "__main__":
    sys.exit(main())
