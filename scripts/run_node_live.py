#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _api_get(base_url: str, run_id: str) -> dict:
    response = requests.get(f"{base_url}/api/run/{run_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def _trigger_pipeline(
    *,
    base_url: str,
    ticker: str,
    date: str,
    portfolio_id: str,
    analysts: list[str],
    market_report_file: str,
) -> str:
    payload: dict[str, object] = {
        "ticker": ticker,
        "date": date,
        "portfolio_id": portfolio_id,
        "selected_analysts": analysts,
    }
    if market_report_file:
        payload["market_report_file"] = market_report_file
    response = requests.post(f"{base_url}/api/run/pipeline", json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    return str(data["run_id"])


def _print_event(event: dict) -> None:
    node_id = str(event.get("node_id") or "")
    event_type = str(event.get("type") or "")
    message = str(event.get("message") or event.get("response") or "").strip()
    print(f"--- {node_id} [{event_type}]")
    if message:
        print(message[:500].replace("\n", "\\n"))


def _matches_watch(event: dict, watch_nodes: set[str], watch_all_system: bool) -> bool:
    node_id = str(event.get("node_id") or "")
    if node_id in watch_nodes:
        return True
    if watch_all_system and node_id == "__system__":
        return True
    return False


def _write_artifact(base_url: str, run_id: str, output_file: str) -> None:
    if not output_file:
        return
    run = _api_get(base_url, run_id)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"Saved run JSON to {output_path}")


def _validate_news_prompt(base_url: str, run_id: str) -> int:
    run = _api_get(base_url, run_id)
    prompt_text = ""
    for event in run.get("events", []):
        if str(event.get("node_id") or "") == "News Analyst":
            prompt_text = str(event.get("prompt") or "")
            if prompt_text:
                break

    if not prompt_text:
        print("News Analyst prompt not found in run events.")
        return 2

    has_old_block = "CRITICAL OUTPUT REQUIREMENTS" in prompt_text
    has_old_self_validation = "SELF-VALIDATION CHECK" in prompt_text
    has_sparse_guidance = "If the evidence window is sparse" in prompt_text

    print("Prompt checks:")
    print(f"- has_old_block={has_old_block}")
    print(f"- has_old_self_validation={has_old_self_validation}")
    print(f"- has_sparse_guidance={has_sparse_guidance}")

    if has_old_block or has_old_self_validation or not has_sparse_guidance:
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trigger and monitor a node-scoped live pipeline run from terminal."
    )
    parser.add_argument("--base-url", default="http://localhost:8088")
    parser.add_argument("--run-id", default="", help="Monitor an existing run id.")
    parser.add_argument("--trigger", action="store_true", help="Trigger a new pipeline run.")
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    parser.add_argument("--portfolio-id", default="main_portfolio")
    parser.add_argument("--analysts", default="news", help="Comma-separated analyst list.")
    parser.add_argument("--market-report-file", default="")
    parser.add_argument(
        "--watch-nodes",
        default="News Analyst,News Fact Checker",
        help="Comma-separated node names to stream.",
    )
    parser.add_argument("--show-system", action="store_true", help="Include __system__ events.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--stop-on-timeout", action="store_true")
    parser.add_argument(
        "--write-run-json",
        default="",
        help="Optional file path to persist the final run status payload.",
    )
    parser.add_argument(
        "--validate-news-prompt",
        action="store_true",
        help="Validate News Analyst prompt no longer has rigid legacy block.",
    )
    args = parser.parse_args()

    run_id = args.run_id.strip()
    analysts = _parse_csv(args.analysts)
    watch_nodes = set(_parse_csv(args.watch_nodes))

    if args.trigger:
        run_id = _trigger_pipeline(
            base_url=args.base_url,
            ticker=args.ticker.upper(),
            date=args.date,
            portfolio_id=args.portfolio_id,
            analysts=analysts or ["news"],
            market_report_file=args.market_report_file.strip(),
        )
        print(f"Triggered run_id={run_id}")
    elif not run_id:
        print("Provide --run-id or use --trigger.", file=sys.stderr)
        return 1

    seen = 0
    last_status = None
    started = time.time()
    while True:
        run = _api_get(args.base_url, run_id)
        status = str(run.get("status") or "")
        events = run.get("events", [])

        if status != last_status:
            print(f"status={status} events={len(events)}")
            last_status = status

        for event in events[seen:]:
            if _matches_watch(event, watch_nodes, args.show_system):
                _print_event(event)
        seen = len(events)

        if status in {"completed", "failed"}:
            print(f"final_status={status}")
            error = run.get("error")
            if error:
                print(f"error={error}")
            _write_artifact(args.base_url, run_id, args.write_run_json)
            if args.validate_news_prompt:
                return _validate_news_prompt(args.base_url, run_id)
            return 0

        if time.time() - started > args.timeout_seconds:
            print(f"timeout after {args.timeout_seconds}s (run_id={run_id})")
            if args.stop_on_timeout:
                response = requests.post(
                    f"{args.base_url}/api/run/{run_id}/stop",
                    timeout=30,
                )
                print(f"stop_status={response.status_code} stop_response={response.text}")
            _write_artifact(args.base_url, run_id, args.write_run_json)
            if args.validate_news_prompt:
                return _validate_news_prompt(args.base_url, run_id)
            return 124

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
