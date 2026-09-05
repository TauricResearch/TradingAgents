"""Record one local game-opportunity board observation."""

from __future__ import annotations

import argparse
import json
from datetime import date

from .artifact_store import JsonArtifactStore
from .game_opportunity_history import record_game_opportunity_board


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record and compare the game opportunity radar.")
    parser.add_argument("--data-dir", default=".research-data")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)

    batch = record_game_opportunity_board(
        JsonArtifactStore(args.data_dir),
        as_of_date=args.as_of,
    )
    print(
        json.dumps(
            {
                "as_of_date": batch.as_of_date.isoformat(),
                "event_count": batch.event_count,
                "companies": [
                    {
                        "symbol": result.snapshot.symbol,
                        "level": result.snapshot.level.value,
                        "score": result.snapshot.score,
                        "events": [event.model_dump(mode="json") for event in result.events],
                    }
                    for result in batch.results
                ],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
