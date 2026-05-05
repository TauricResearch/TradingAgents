import argparse
import json
from pathlib import Path

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.config import get_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--include-pending", action="store_true")
    args = parser.parse_args()

    cfg = get_config()
    log = TradingMemoryLog(cfg)
    entries = log.load_entries()

    out_path = Path(args.out).expanduser() if args.out else None
    out_f = None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_f = out_path.open("w", encoding="utf-8")

    try:
        for e in entries:
            if not args.include_pending and e.get("pending"):
                continue
            row = {
                "date": e.get("date"),
                "ticker": e.get("ticker"),
                "rating": e.get("rating"),
                "pending": bool(e.get("pending")),
                "raw": e.get("raw"),
                "alpha": e.get("alpha"),
                "holding": e.get("holding"),
                "decision": e.get("decision"),
                "meta": e.get("meta") or {},
                "outcome": e.get("outcome") or {},
                "reflection": e.get("reflection"),
            }
            line = json.dumps(row, ensure_ascii=False)
            if out_f:
                out_f.write(line + "\n")
            else:
                print(line)
    finally:
        if out_f:
            out_f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
