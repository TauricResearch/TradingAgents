"""Synchronize official NPPA game approvals into the local research cache."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from .game_approvals import (
    GameApprovalKind,
    JsonGameApprovalStore,
    match_game_approval,
)
from .nppa_provider import NppaApprovalProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync official NPPA game approvals.")
    parser.add_argument("--data-dir", default=".research-data")
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--kind",
        choices=["all", *(item.value for item in GameApprovalKind)],
        default="all",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    kinds = list(GameApprovalKind) if args.kind == "all" else [GameApprovalKind(args.kind)]
    records = NppaApprovalProvider().fetch(args.start, args.end, kinds=kinds)
    if not args.dry_run:
        JsonGameApprovalStore(args.data_dir).save(records)
    matches = [match_game_approval(record) for record in records]
    status_counts = Counter(item.status.value for item in matches)
    symbol_counts = Counter(item.symbol for item in matches if item.symbol)
    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "start": args.start.isoformat(),
                "end": args.end.isoformat(),
                "records": len(records),
                "status_counts": dict(sorted(status_counts.items())),
                "symbol_counts": dict(sorted(symbol_counts.items())),
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
