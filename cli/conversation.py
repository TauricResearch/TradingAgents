"""Run the existing graph with an actively responding chat assistant, not an LLM API."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from tradingagents.conversation import (
    ConversationBridgeError,
    conversation_directory,
    pending_requests,
    read_json,
    request_path,
    submit_response,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Run analysis; wait for chat-supplied answers")
    start.add_argument("ticker")
    start.add_argument("--date", type=date.fromisoformat, default=date.today())
    start.add_argument(
        "--analysts",
        nargs="+",
        choices=["market", "news", "fundamentals", "social"],
        default=["market", "news", "fundamentals"],
    )
    start.add_argument("--language", default="Korean")
    start.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Seconds per response (default: env override or 1800)",
    )
    pending = commands.add_parser("pending", help="List unanswered requests")
    show = commands.add_parser("show", help="Read full messages and tool schemas")
    show.add_argument("request_id")
    respond = commands.add_parser("respond", help="Validate and submit one answer")
    answer = respond.add_mutually_exclusive_group(required=True)
    answer.add_argument("--file", type=Path, help="Response JSON file")
    answer.add_argument("--json", help="Response JSON object")
    answer.add_argument("--text", help="Plain response; requires --request-id")
    respond.add_argument("--request-id")
    cancel = commands.add_parser("cancel", help="Cancel one waiting request and stop its run")
    cancel.add_argument("request_id")
    for command in (start, pending, show, respond, cancel):
        command.add_argument(
            "--directory",
            type=Path,
            default=conversation_directory(),
            help="Shared exchange directory (use a separate one per run)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    directory = args.directory.expanduser().resolve()
    try:
        if args.command == "start":
            from tradingagents.default_config import DEFAULT_CONFIG
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            config = {
                **DEFAULT_CONFIG,
                "llm_provider": "conversation",
                "deep_think_llm": "conversation",
                "quick_think_llm": "conversation",
                "backend_url": None,
                "conversation_dir": str(directory),
                "conversation_timeout": args.timeout,
                "output_language": args.language,
            }
            print(f"Conversation exchange: {directory}", flush=True)
            print(
                "Waiting requests must be answered by the assistant. No orders are placed.",
                flush=True,
            )
            graph = TradingAgentsGraph(selected_analysts=args.analysts, config=config)
            state, signal = graph.propagate(args.ticker, args.date.isoformat())
            report = graph.save_reports(state, args.ticker)
            result = {"rating": signal, "report_directory": str(report)}
        elif args.command == "pending":
            result = [
                {key: request[key] for key in ("request_id", "agent", "expires_at")}
                for request in pending_requests(directory)
            ]
        elif args.command == "show":
            result = read_json(request_path(directory, args.request_id))
        else:
            if args.command == "cancel":
                value = {"request_id": args.request_id, "cancel": True}
            elif args.text is not None:
                if not args.request_id:
                    parser.error("--text requires --request-id")
                value = {"request_id": args.request_id, "content": args.text}
            else:
                value = read_json(args.file) if args.file else json.loads(args.json)
                if not isinstance(value, dict):
                    raise ValueError("Response must be a JSON object")
                if args.request_id and value.get("request_id") != args.request_id:
                    raise ValueError("--request-id does not match the response JSON")
            result = {"response": str(submit_response(directory, value))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (ConversationBridgeError, OSError, ValueError) as exc:
        parser.exit(2, f"Conversation error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
