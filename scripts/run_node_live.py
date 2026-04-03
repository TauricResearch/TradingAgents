#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
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


def _last_event_brief(events: list[dict]) -> str:
    if not events:
        return "none"
    last = events[-1]
    node = str(last.get("node_id") or "")
    event_type = str(last.get("type") or "")
    ident = str(last.get("identifier") or "")
    timestamp = str(last.get("timestamp") or "")
    message = str(last.get("message") or last.get("response") or "").strip()
    message_head = message[:140].replace("\n", "\\n")
    return (
        f"node={node} type={event_type} identifier={ident or '<none>'} "
        f"ts={timestamp or '<none>'} msg={message_head or '<empty>'}"
    )


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


def _coerce_market_structured(raw_value: object) -> dict | None:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _find_latest_analysts_checkpoint(*, run_id: str, ticker: str, date: str) -> Path | None:
    pattern = f"reports/daily/{date}/{run_id}/{ticker.upper()}/report/*analysts_checkpoint.json"
    candidates = sorted(glob.glob(pattern))
    if not candidates:
        return None
    return Path(candidates[-1])


def _validate_market_checkpoint(
    *,
    run_id: str,
    ticker: str,
    date: str,
    require_structured: bool,
    required_fields: list[str],
    disallow_macro_fallback: bool,
) -> int:
    checkpoint_path = _find_latest_analysts_checkpoint(
        run_id=run_id,
        ticker=ticker,
        date=date,
    )
    if checkpoint_path is None:
        print("Market checkpoint not found.")
        print(f"Expected under reports/daily/{date}/{run_id}/{ticker.upper()}/report/")
        return 2

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    print(f"Market checkpoint: {checkpoint_path}")

    market_report = str(payload.get("market_report") or "").strip()
    macro_regime_report = str(payload.get("macro_regime_report") or "").strip()

    macro_fallback_detected = (
        bool(market_report)
        and bool(macro_regime_report)
        and market_report == macro_regime_report
    )
    print(f"macro_fallback_detected={macro_fallback_detected}")
    if disallow_macro_fallback and macro_fallback_detected:
        print("Market validation failed: macro_regime_report equals full market_report.")
        return 3

    structured = _coerce_market_structured(payload.get("market_report_structured"))
    has_structured = structured is not None
    print(f"has_market_report_structured={has_structured}")

    if require_structured and not has_structured:
        print("Market validation failed: missing market_report_structured.")
        return 4

    if has_structured and required_fields:
        missing_fields = [field for field in required_fields if field not in structured]
        print(f"missing_required_fields={missing_fields}")
        if missing_fields:
            print("Market validation failed: required structured fields missing.")
            return 5

    return 0


def _validate_downstream_entry(
    *,
    base_url: str,
    run_id: str,
    ticker: str,
    after_node: str,
    entry_nodes: list[str],
) -> int:
    run = _api_get(base_url, run_id)
    events = list(run.get("events") or [])
    ticker_upper = str(ticker or "").upper().strip()
    after_node = str(after_node or "").strip()
    entry_nodes = [node.strip() for node in entry_nodes if str(node).strip()]

    if not after_node or not entry_nodes:
        print("Downstream validation failed: invalid after-node or entry-nodes config.")
        return 6

    # Prefer ticker-specific edges when identifiers are available.
    def _is_ticker_match(event: dict) -> bool:
        identifier = str(event.get("identifier") or "").upper().strip()
        if not ticker_upper:
            return True
        if not identifier:
            return True
        return identifier == ticker_upper

    after_indices: list[int] = []
    for index, event in enumerate(events):
        if str(event.get("node_id") or "") == after_node and _is_ticker_match(event):
            after_indices.append(index)

    pivot_index = after_indices[-1] if after_indices else -1
    print(f"downstream_after_node={after_node}")
    print(f"downstream_entry_nodes={entry_nodes}")
    print(f"downstream_ticker_filter={ticker_upper or '<none>'}")
    print(f"after_node_last_index={pivot_index}")

    if pivot_index < 0:
        print("Downstream validation failed: after-node never appeared in run events.")
        return 7

    entry_hit_after_index = -1
    entry_hit_index = -1
    entry_hit_node = ""
    entry_hit_type = ""
    for after_index in after_indices:
        for index, event in enumerate(events):
            if index <= after_index:
                continue
            if not _is_ticker_match(event):
                continue
            node_id = str(event.get("node_id") or "")
            if node_id in entry_nodes:
                entry_hit_after_index = after_index
                entry_hit_index = index
                entry_hit_node = node_id
                entry_hit_type = str(event.get("type") or "")
                break
        if entry_hit_index >= 0:
            break

    if entry_hit_index < 0:
        print(
            "Downstream validation failed: none of the expected entry nodes "
            "appeared after the market node."
        )
        return 8

    print(
        "downstream_entry_hit="
        f"node:{entry_hit_node} type:{entry_hit_type} "
        f"after_index:{entry_hit_after_index} entry_index:{entry_hit_index}"
    )
    return 0


def _default_contract_fields_from_analysts(analysts: list[str]) -> list[str]:
    mapping = {
        "market": "market_report_structured",
        "social": "sentiment_report_structured",
        "news": "news_report_structured",
        "fundamentals": "fundamentals_report_structured",
    }
    fields: list[str] = []
    for analyst in analysts:
        key = mapping.get(str(analyst).strip().lower())
        if key and key not in fields:
            fields.append(key)
    return fields


def _validate_checkpoint_contract_fields(
    *,
    run_id: str,
    ticker: str,
    date: str,
    required_fields: list[str],
    require_nonempty: bool,
) -> int:
    checkpoint_path = _find_latest_analysts_checkpoint(
        run_id=run_id,
        ticker=ticker,
        date=date,
    )
    if checkpoint_path is None:
        print("Analysts checkpoint not found for contract validation.")
        return 9

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    print(f"Analysts checkpoint: {checkpoint_path}")
    missing: list[str] = []
    empty: list[str] = []
    for field in required_fields:
        if field not in payload:
            missing.append(field)
            continue
        if require_nonempty and not payload.get(field):
            empty.append(field)

    print(f"required_contract_fields={required_fields}")
    print(f"missing_contract_fields={missing}")
    print(f"empty_contract_fields={empty}")
    if missing:
        return 10
    if empty:
        return 11
    return 0


def _validate_bypass_summary_flow(
    *,
    base_url: str,
    run_id: str,
    ticker: str,
    required_analyst_nodes: list[str],
    forbidden_nodes: list[str],
    bull_node: str = "Bull Researcher",
) -> int:
    run = _api_get(base_url, run_id)
    events = list(run.get("events") or [])
    ticker_upper = str(ticker or "").upper().strip()

    def _matches_ticker(event: dict) -> bool:
        ident = str(event.get("identifier") or "").upper().strip()
        if not ticker_upper:
            return True
        if not ident:
            return True
        return ident == ticker_upper

    # Node presence map for ticker-scoped flow.
    seen_nodes: list[str] = []
    for event in events:
        if not _matches_ticker(event):
            continue
        node_id = str(event.get("node_id") or "").strip()
        if node_id:
            seen_nodes.append(node_id)

    # Ensure Bull Researcher is entered.
    bull_index = -1
    for idx, event in enumerate(events):
        if not _matches_ticker(event):
            continue
        if str(event.get("node_id") or "") == bull_node:
            bull_index = idx
            break
    print(f"bypass_flow_bull_index={bull_index}")
    if bull_index < 0:
        print("Bypass flow validation failed: Bull Researcher node not observed.")
        return 12

    # Ensure required analysts appear before bull.
    missing_analysts: list[str] = []
    for node in required_analyst_nodes:
        found = any(
            str(event.get("node_id") or "") == node
            and _matches_ticker(event)
            and idx < bull_index
            for idx, event in enumerate(events)
        )
        if not found:
            missing_analysts.append(node)
    print(f"required_analyst_nodes={required_analyst_nodes}")
    print(f"missing_analyst_nodes_before_bull={missing_analysts}")
    if missing_analysts:
        return 13

    # Ensure forbidden summary nodes do not appear before bull.
    hit_forbidden: list[str] = []
    for node in forbidden_nodes:
        found = any(
            str(event.get("node_id") or "") == node
            and _matches_ticker(event)
            and idx < bull_index
            for idx, event in enumerate(events)
        )
        if found:
            hit_forbidden.append(node)
    print(f"forbidden_nodes_before_bull={forbidden_nodes}")
    print(f"forbidden_nodes_hit_before_bull={hit_forbidden}")
    if hit_forbidden:
        print("Bypass flow validation failed: forbidden summary node(s) observed.")
        return 14

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
    parser.add_argument(
        "--validate-market-checkpoint",
        action="store_true",
        help="Validate market analysts checkpoint artifact for fallback/structured fields.",
    )
    parser.add_argument(
        "--market-require-structured",
        action="store_true",
        help="When validating market checkpoint, require market_report_structured.",
    )
    parser.add_argument(
        "--market-required-fields",
        default="status,contract_version,macro_regime",
        help="Comma-separated required keys in market_report_structured.",
    )
    parser.add_argument(
        "--allow-macro-fallback",
        action="store_true",
        help="Allow macro_regime_report == market_report in market checkpoint validation.",
    )
    parser.add_argument(
        "--validate-downstream-entry",
        action="store_true",
        help="Validate that downstream node entry occurs after the market node.",
    )
    parser.add_argument(
        "--downstream-after-node",
        default="Market Analyst",
        help="Node that must appear before downstream entry nodes.",
    )
    parser.add_argument(
        "--downstream-entry-nodes",
        default="Bull Researcher",
        help="Comma-separated downstream nodes expected after the after-node.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=30.0,
        help="Emit periodic progress lines while run stays in-progress.",
    )
    parser.add_argument(
        "--stall-seconds",
        type=float,
        default=180.0,
        help="If no new events arrive for this long while status=running, emit stall diagnostics. Set <=0 to disable.",
    )
    parser.add_argument(
        "--exit-on-stall",
        action="store_true",
        help="Exit with code 125 when stall threshold is reached.",
    )
    parser.add_argument(
        "--stop-on-stall",
        action="store_true",
        help="Request run stop when stall threshold is reached.",
    )
    parser.add_argument(
        "--validate-bypass-summary-flow",
        action="store_true",
        help="Validate analysts flow enters Bull Researcher without running summary node(s) first.",
    )
    parser.add_argument(
        "--required-analyst-nodes",
        default="",
        help="Comma-separated analyst node IDs expected before Bull Researcher. Default inferred from --analysts.",
    )
    parser.add_argument(
        "--forbidden-nodes-before-bull",
        default="Research Packet Summary",
        help="Comma-separated node IDs that must not appear before Bull Researcher.",
    )
    parser.add_argument(
        "--validate-analyst-contracts",
        action="store_true",
        help="Validate analysts checkpoint contains required structured contract fields.",
    )
    parser.add_argument(
        "--required-contract-fields",
        default="",
        help="Comma-separated contract fields expected in analysts checkpoint. Default inferred from --analysts.",
    )
    parser.add_argument(
        "--allow-empty-contract-fields",
        action="store_true",
        help="Allow required contract fields to be present but empty.",
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
    last_heartbeat = started
    last_progress = started
    stall_reported = False
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
        new_events = len(events) - seen
        seen = len(events)
        now = time.time()
        if new_events > 0:
            last_progress = now
            stall_reported = False

        if status in {"completed", "failed"}:
            print(f"final_status={status}")
            error = run.get("error")
            if error:
                print(f"error={error}")
            _write_artifact(args.base_url, run_id, args.write_run_json)
            if args.validate_news_prompt:
                result = _validate_news_prompt(args.base_url, run_id)
                if result != 0:
                    return result
            if args.validate_market_checkpoint:
                result = _validate_market_checkpoint(
                    run_id=run_id,
                    ticker=args.ticker,
                    date=args.date,
                    require_structured=args.market_require_structured,
                    required_fields=_parse_csv(args.market_required_fields),
                    disallow_macro_fallback=not args.allow_macro_fallback,
                )
                if result != 0:
                    return result
            if args.validate_downstream_entry:
                result = _validate_downstream_entry(
                    base_url=args.base_url,
                    run_id=run_id,
                    ticker=args.ticker,
                    after_node=args.downstream_after_node,
                    entry_nodes=_parse_csv(args.downstream_entry_nodes),
                )
                if result != 0:
                    return result
            if args.validate_bypass_summary_flow:
                required_nodes = _parse_csv(args.required_analyst_nodes)
                if not required_nodes:
                    required_nodes = [
                        f"{analyst.capitalize()} Analyst" for analyst in analysts if analyst
                    ]
                result = _validate_bypass_summary_flow(
                    base_url=args.base_url,
                    run_id=run_id,
                    ticker=args.ticker,
                    required_analyst_nodes=required_nodes,
                    forbidden_nodes=_parse_csv(args.forbidden_nodes_before_bull),
                )
                if result != 0:
                    return result
            if args.validate_analyst_contracts:
                required_fields = _parse_csv(args.required_contract_fields)
                if not required_fields:
                    required_fields = _default_contract_fields_from_analysts(analysts)
                result = _validate_checkpoint_contract_fields(
                    run_id=run_id,
                    ticker=args.ticker,
                    date=args.date,
                    required_fields=required_fields,
                    require_nonempty=not args.allow_empty_contract_fields,
                )
                if result != 0:
                    return result
            return 0

        if args.heartbeat_seconds > 0 and (now - last_heartbeat) >= args.heartbeat_seconds:
            elapsed = int(now - started)
            last_node = str((events[-1] or {}).get("node_id") or "") if events else ""
            last_type = str((events[-1] or {}).get("type") or "") if events else ""
            print(
                f"heartbeat elapsed={elapsed}s status={status} events={len(events)} "
                f"last={last_node}:{last_type}"
            )
            last_heartbeat = now

        if (
            args.stall_seconds > 0
            and status == "running"
            and not stall_reported
            and (now - last_progress) >= args.stall_seconds
        ):
            idle = int(now - last_progress)
            elapsed = int(now - started)
            print(
                f"stall_detected idle={idle}s elapsed={elapsed}s events={len(events)} "
                f"last_event=({_last_event_brief(events)})"
            )
            stall_reported = True
            if args.stop_on_stall:
                response = requests.post(
                    f"{args.base_url}/api/run/{run_id}/stop",
                    timeout=30,
                )
                print(
                    "stall_stop_requested "
                    f"status={response.status_code} response={response.text}"
                )
            _write_artifact(args.base_url, run_id, args.write_run_json)
            if args.exit_on_stall:
                return 125

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
                result = _validate_news_prompt(args.base_url, run_id)
                if result != 0:
                    return result
            if args.validate_market_checkpoint:
                result = _validate_market_checkpoint(
                    run_id=run_id,
                    ticker=args.ticker,
                    date=args.date,
                    require_structured=args.market_require_structured,
                    required_fields=_parse_csv(args.market_required_fields),
                    disallow_macro_fallback=not args.allow_macro_fallback,
                )
                if result != 0:
                    return result
            if args.validate_downstream_entry:
                result = _validate_downstream_entry(
                    base_url=args.base_url,
                    run_id=run_id,
                    ticker=args.ticker,
                    after_node=args.downstream_after_node,
                    entry_nodes=_parse_csv(args.downstream_entry_nodes),
                )
                if result != 0:
                    return result
            if args.validate_bypass_summary_flow:
                required_nodes = _parse_csv(args.required_analyst_nodes)
                if not required_nodes:
                    required_nodes = [
                        f"{analyst.capitalize()} Analyst" for analyst in analysts if analyst
                    ]
                result = _validate_bypass_summary_flow(
                    base_url=args.base_url,
                    run_id=run_id,
                    ticker=args.ticker,
                    required_analyst_nodes=required_nodes,
                    forbidden_nodes=_parse_csv(args.forbidden_nodes_before_bull),
                )
                if result != 0:
                    return result
            if args.validate_analyst_contracts:
                required_fields = _parse_csv(args.required_contract_fields)
                if not required_fields:
                    required_fields = _default_contract_fields_from_analysts(analysts)
                result = _validate_checkpoint_contract_fields(
                    run_id=run_id,
                    ticker=args.ticker,
                    date=args.date,
                    required_fields=required_fields,
                    require_nonempty=not args.allow_empty_contract_fields,
                )
                if result != 0:
                    return result
            return 124

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
