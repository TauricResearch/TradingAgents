"""Command-line composition root for the four offline research phases."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from tradingagents.research.artifacts import FilesystemArtifactStore
from tradingagents.research.contracts import ModelCheckpointSpec


def _dates(value: str) -> tuple[date, ...]:
    try:
        dates = tuple(date.fromisoformat(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must be comma-separated ISO dates") from exc
    if not dates:
        raise argparse.ArgumentTypeError("at least one decision date is required")
    return dates


def _print_ref(reference) -> None:
    print(json.dumps(asdict(reference), sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        default=str(Path.home() / ".tradingagents" / "research-artifacts"),
        help=(
            "Root directory for immutable content-addressed artifacts "
            "(default: ~/.tradingagents/research-artifacts)"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="Freeze point-in-time evidence")
    snapshot.add_argument(
        "--db",
        default=os.getenv("MEDIA_DB_URL"),
        help="Read-only collector database URL (default: MEDIA_DB_URL)",
    )
    snapshot.add_argument("--run-id", required=True)
    snapshot.add_argument("--dates", required=True, type=_dates)

    decide = subparsers.add_parser("decide", help="Commit model decisions without labels")
    decide.add_argument("--snapshot", required=True, help="Committed snapshot artifact ID")
    decide.add_argument("--checkpoint", required=True, type=Path, help="Model checkpoint JSON")
    decide.add_argument(
        "--arm",
        choices=("global_events", "without_public_reaction"),
        default="global_events",
        help="Evidence arm; both arms reuse the same committed snapshot",
    )

    label = subparsers.add_parser("label", help="Attach labels to committed decisions")
    label.add_argument("--decisions", required=True, help="Committed decision artifact ID")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate committed decisions and labels")
    evaluate.add_argument("--decisions", required=True)
    evaluate.add_argument("--labels", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    store = FilesystemArtifactStore(args.artifacts)
    if args.command == "snapshot":
        from tradingagents.research.snapshot import build_media_snapshot, commit_snapshot

        if not args.db:
            raise SystemExit("snapshot requires --db or MEDIA_DB_URL")
        snapshot = build_media_snapshot(
            db_url=args.db,
            run_id=args.run_id,
            decision_dates=args.dates,
        )
        _print_ref(commit_snapshot(store, snapshot))
        return
    if args.command == "decide":
        # Model code and credentials enter only this composition branch.
        from tradingagents.research.decide import decide_from_artifact
        from tradingagents.research.model import create_global_forecast_model

        checkpoint = ModelCheckpointSpec.model_validate_json(
            args.checkpoint.read_text(encoding="utf-8")
        )
        model = create_global_forecast_model(checkpoint)
        _print_ref(
            decide_from_artifact(
                artifact_store=store,
                snapshot_artifact_id=args.snapshot,
                checkpoint=checkpoint,
                model=model,
                arm=args.arm,
            )
        )
        return
    if args.command == "label":
        # Outcome code enters only after a committed decision ID is supplied.
        from tradingagents.research.label import label_from_artifact
        from tradingagents.research.outcomes import YFinanceAdjustedOpenOutcomeProvider

        _print_ref(
            label_from_artifact(
                artifact_store=store,
                decision_artifact_id=args.decisions,
                provider=YFinanceAdjustedOpenOutcomeProvider(),
            )
        )
        return
    from tradingagents.research.evaluate import evaluate_from_artifacts

    _print_ref(
        evaluate_from_artifacts(
            artifact_store=store,
            decision_artifact_id=args.decisions,
            label_artifact_id=args.labels,
        )
    )


if __name__ == "__main__":
    main()
