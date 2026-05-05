# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Cache administration CLI.

Examples:
    python -m tradingagents.dataflows.cache_admin stats
    python -m tradingagents.dataflows.cache_admin clear --kind ohlcv
    python -m tradingagents.dataflows.cache_admin clear --kind ohlcv --func _fetch_pykrx_ohlcv
    python -m tradingagents.dataflows.cache_admin clear --all
"""

import argparse
import shutil
from pathlib import Path

from .config import get_config


def _root() -> Path:
    return Path(get_config()["data_cache_dir"])


def cmd_stats() -> int:
    root = _root()
    if not root.exists():
        print(f"(no cache yet at {root})")
        return 0

    print(f"Cache root: {root}")
    print(f"{'kind':<20} {'func':<40} {'files':>8} {'size_mb':>10}")
    print("-" * 80)
    total_files = 0
    total_bytes = 0
    for kind_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for func_dir in sorted(p for p in kind_dir.iterdir() if p.is_dir()):
            files = list(func_dir.glob("*.parquet"))
            size = sum(f.stat().st_size for f in files)
            total_files += len(files)
            total_bytes += size
            print(f"{kind_dir.name:<20} {func_dir.name:<40} {len(files):>8} {size / 1e6:>10.2f}")
    print("-" * 80)
    print(f"{'TOTAL':<60} {total_files:>8} {total_bytes / 1e6:>10.2f}")
    return 0


def cmd_clear(kind: str | None, func: str | None, all_: bool) -> int:
    root = _root()
    if not root.exists():
        print("(nothing to clear)")
        return 0

    if all_:
        shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        print(f"cleared all cache under {root}")
        return 0

    if not kind:
        print("error: --kind required (or use --all)")
        return 2

    target = root / kind
    if func:
        target = target / func

    # Guard against path traversal (e.g., --kind ../../etc)
    try:
        resolved_target = target.resolve()
        resolved_root = root.resolve()
    except OSError as e:
        print(f"error: cannot resolve path {target}: {e}")
        return 2
    if not resolved_target.is_relative_to(resolved_root):
        print(f"error: path {resolved_target} escapes cache root {resolved_root}")
        return 2

    if target.exists():
        shutil.rmtree(target)
        print(f"cleared {target}")
    else:
        print(f"(nothing at {target})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="cache_admin")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats", help="show cache size by kind/func")
    pc = sub.add_parser("clear", help="clear cache entries")
    pc.add_argument("--kind", help="cache kind (e.g. ohlcv, universe)")
    pc.add_argument("--func", help="function name within the kind")
    pc.add_argument("--all", dest="all_", action="store_true", help="clear everything")

    args = p.parse_args()
    if args.cmd == "stats":
        return cmd_stats()
    if args.cmd == "clear":
        return cmd_clear(args.kind, args.func, args.all_)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
