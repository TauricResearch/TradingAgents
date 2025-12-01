from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import questionary
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.services.account import AccountService, AccountSnapshot
from tradingagents.services.auto_trade import AutoTradeResult, AutoTradeService
from tradingagents.services.autopilot_worker import AutopilotWorker
from tradingagents.services.autopilot_broker import AutopilotBroker
from tradingagents.services.realtime_broker import RealtimeBroker
from tradingagents.services.realtime_news_broker import RealtimeNewsBroker
from tradingagents.services.hypothesis_store import HypothesisStore


console = Console()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = DEFAULT_CONFIG.copy()
    console.print(Panel("[bold]TradingAgents CLI[/bold]\nConnect to Alpaca MCP and manage auto-trading.", title="TradingAgents", expand=False))

    autopilot_requested = "--autopilot" in sys.argv or bool(config.get("autopilot", {}).get("enabled"))
    if "--autopilot" in sys.argv:
        sys.argv.remove("--autopilot")

    results_root = Path(config.get("results_dir", "./results")).resolve()
    hypothesis_store = HypothesisStore(results_root / "hypotheses")
    realtime_state: Dict[str, Any] = {}
    news_state: Dict[str, Any] = {}

    account_service = AccountService(config.get("alpaca_mcp", {}))
    snapshot = _refresh_account_snapshot(account_service)

    graph = TradingAgentsGraph(debug=False, config=config, skip_initial_probes=True)
    auto_trader = AutoTradeService(config=config, graph=graph)
    autopilot_worker = AutopilotWorker(results_root, auto_trader, account_service)
    autopilot_broker = AutopilotBroker(hypothesis_store, autopilot_worker)

    if autopilot_requested:
        _run_autopilot_loop(
            config,
            snapshot,
            auto_trader,
            hypothesis_store,
            autopilot_worker,
            autopilot_broker,
            realtime_state,
            news_state,
            account_service,
        )
        return

    if not sys.stdin.isatty():
        console.print(
            "Detected non-interactive environment. Running auto-trade once and exiting.",
            style="yellow",
        )
        _execute_auto_trade(auto_trader, snapshot, hypothesis_store)
        return

    while True:
        choice = questionary.select(
            "Select an option",
            choices=[
                "Refresh Alpaca snapshot",
                "Show account summary",
                "Show positions",
                "Show recent orders",
                "Show hypotheses",
                "Run auto-trade",
                "Simulate hypothesis event",
                "Process autopilot events",
                "Run price-alert poll",
                "Start realtime broker",
                "Start news broker",
                "Exit",
            ],
        ).ask()

        if choice is None or choice == "Exit":
            console.print("Goodbye!")
            break

        if choice == "Refresh Alpaca snapshot":
            snapshot = _refresh_account_snapshot(account_service)
        elif choice == "Show account summary":
            _render_account_summary(snapshot)
        elif choice == "Show positions":
            _render_positions(snapshot)
        elif choice == "Show recent orders":
            _render_orders(snapshot)
        elif choice == "Show hypotheses":
            _render_hypotheses(hypothesis_store)
        elif choice == "Run auto-trade":
            _execute_auto_trade(auto_trader, snapshot, hypothesis_store)
        elif choice == "Simulate hypothesis event":
            _simulate_hypothesis_event(hypothesis_store, autopilot_worker)
        elif choice == "Process autopilot events":
            _process_autopilot_events(autopilot_worker)
        elif choice == "Run price-alert poll":
            _run_price_alert_poll(autopilot_broker)
        elif choice == "Start realtime broker":
            _start_realtime_broker(config, hypothesis_store, autopilot_worker, realtime_state)
        elif choice == "Start news broker":
            _start_news_broker(config, hypothesis_store, autopilot_worker, news_state)


def _refresh_account_snapshot(account_service: AccountService) -> AccountSnapshot:
    console.print("Connecting to Alpaca MCP …", style="bold cyan")
    try:
        snapshot = account_service.refresh()
    except RuntimeError as exc:
        console.print(str(exc), style="red")
        raise SystemExit(1)

    console.print(
        f"Snapshot fetched at {snapshot.fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        style="green",
    )
    _render_account_summary(snapshot)
    return snapshot


def _render_account_summary(snapshot: AccountSnapshot) -> None:
    table = Table(title="Account Summary", box=None)
    table.add_column("Field", justify="left", style="cyan")
    table.add_column("Value", justify="right", style="magenta")

    for key, label in [
        ("account_id", "Account ID"),
        ("status", "Status"),
        ("currency", "Currency"),
        ("buying_power", "Buying Power"),
        ("cash", "Cash"),
        ("portfolio_value", "Portfolio Value"),
        ("equity", "Equity"),
        ("long_market_value", "Long Market Value"),
        ("short_market_value", "Short Market Value"),
        ("pattern_day_trader", "Pattern Day Trader"),
        ("day_trades_remaining", "Day Trades Remaining"),
    ]:
        value = snapshot.account.get(key)
        if value is not None:
            table.add_row(label, str(value))

    console.print(table)


def _render_positions(snapshot: AccountSnapshot) -> None:
    if not snapshot.positions:
        console.print("No open positions.")
        return

    table = Table(title="Open Positions", box=None)
    table.add_column("Symbol", style="cyan")
    table.add_column("Quantity", justify="right")
    table.add_column("Market Value", justify="right")
    table.add_column("Cost Basis", justify="right")

    for position in snapshot.positions:
        table.add_row(
            str(position.get("symbol") or position.get("symbol:") or ""),
            str(position.get("quantity") or position.get("qty") or ""),
            str(position.get("market_value") or ""),
            str(position.get("cost_basis") or ""),
        )

    console.print(table)


def _render_orders(snapshot: AccountSnapshot) -> None:
    if not snapshot.orders:
        console.print("No recent orders.")
        return

    table = Table(title="Recent Orders", box=None)
    table.add_column("Order ID")
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Qty")
    table.add_column("Status")

    for order in snapshot.orders:
        table.add_row(
            str(order.get("order_id") or order.get("id") or ""),
            str(order.get("symbol") or ""),
            str(order.get("side") or ""),
            str(order.get("qty") or order.get("quantity") or ""),
            str(order.get("status") or ""),
        )

    console.print(table)


def _render_hypotheses(store: HypothesisStore) -> None:
    records = store.list()
    if not records:
        console.print("No stored hypotheses yet.", style="yellow")
        return

    table = Table(title="Stored Hypotheses", box=None)
    table.add_column("ID", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Status")
    table.add_column("Action")
    table.add_column("Priority", justify="right")
    table.add_column("Next Step")
    table.add_column("Created", style="dim")

    display_limit = 15
    for record in records[:display_limit]:
        next_step = record.next_open_step()
        next_desc = next_step.description if next_step else "<complete>"
        created = record.created_at.split("T")[0]
        table.add_row(
            record.id[-6:],
            record.ticker,
            record.status,
            record.action,
            f"{record.priority:.2f}",
            next_desc,
            created,
        )

    console.print(table)
    remaining = len(records) - display_limit
    if remaining > 0:
        console.print(f"(+{remaining} more stored hypotheses)", style="dim")


def _simulate_hypothesis_event(store: HypothesisStore, worker: AutopilotWorker) -> None:
    records = store.list()
    if not records:
        console.print("No hypotheses to simulate events for.", style="yellow")
        return

    record_choices = [
        questionary.Choice(
            title=f"{record.ticker} ({record.status}) – id {record.id[-6:]}",
            value=record.id,
        )
        for record in records[:25]
    ]
    hypothesis_id = questionary.select("Select hypothesis", choices=record_choices).ask()
    if not hypothesis_id:
        return

    event_type = questionary.select(
        "Select event type",
        choices=["price_threshold", "news", "heartbeat", "manual"],
    ).ask()
    if not event_type:
        return

    payload_text = questionary.text(
        "Optional JSON payload (press Enter to skip)",
        default="",
    ).ask() or ""
    payload = {}
    if payload_text.strip():
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            console.print("Invalid JSON payload; storing empty payload instead.", style="yellow")

    event = worker.enqueue_event(hypothesis_id, event_type, payload)
    console.print(
        f"Enqueued {event.event_type} event for hypothesis {hypothesis_id[-6:]}",
        style="green",
    )


def _process_autopilot_events(worker: AutopilotWorker) -> None:
    processed = worker.process_all()
    if not processed:
        console.print("No autopilot events queued.", style="yellow")
        return

    table = Table(title="Autopilot Event Processing", box=None)
    table.add_column("Event ID", style="dim")
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Message")

    for result in processed:
        table.add_row(
            result.event.id[-8:],
            result.event.hypothesis_id[-6:],
            result.event.event_type,
            result.status,
            result.message,
        )

    console.print(table)


def _resolve_premarket_window(value: Any) -> int:
    candidates = [os.getenv("AUTOPILOT_PREMARKET_MINUTES"), value, 30]
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        try:
            minutes = int(candidate)
        except (TypeError, ValueError):
            continue
        return max(minutes, 0)
    return 0


def _run_price_alert_poll(broker: AutopilotBroker) -> None:
    outcomes = broker.poll_once()
    if not outcomes:
        console.print("No price triggers fired during this poll.", style="yellow")
        return
    table = Table(title="Price Trigger Poll", box=None)
    table.add_column("Event ID", style="dim")
    table.add_column("Result")
    for event_id, message in outcomes.items():
        table.add_row(event_id[-8:], message)
    console.print(table)
    console.print("Processing newly queued events …", style="dim")
    _process_autopilot_events(broker.worker)


def _start_realtime_broker(
    config: Dict[str, Any],
    store: HypothesisStore,
    worker: AutopilotWorker,
    state: Dict[str, Any],
) -> None:
    if state.get("thread") and state["thread"].is_alive():
        console.print("Realtime broker already running.", style="yellow")
        return

    api_key = os.getenv("APCA_API_KEY_ID") or config.get("market_data", {}).get("api_key")
    secret_key = os.getenv("APCA_API_SECRET_KEY") or config.get("market_data", {}).get("secret_key")
    feed = (config.get("market_data", {}) or {}).get("feed", "iex")
    if not api_key or not secret_key:
        console.print("Set APCA_API_KEY_ID / APCA_API_SECRET_KEY env vars to use realtime broker.", style="red")
        return

    try:
        broker = RealtimeBroker(store, worker, api_key, secret_key, feed=feed)
    except RuntimeError as exc:
        console.print(str(exc), style="red")
        return

    def _run():
        broker.run_forever()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    state["thread"] = thread
    state["broker"] = broker
    console.print("Realtime broker started in background thread.", style="green")


def _start_news_broker(
    config: Dict[str, Any],
    store: HypothesisStore,
    worker: AutopilotWorker,
    state: Dict[str, Any],
) -> None:
    thread = state.get("thread")
    if thread and thread.is_alive():
        console.print("News broker already running.", style="yellow")
        return

    api_key = os.getenv("APCA_API_KEY_ID") or config.get("market_data", {}).get("api_key")
    secret_key = os.getenv("APCA_API_SECRET_KEY") or config.get("market_data", {}).get("secret_key")
    url = (config.get("market_data", {}) or {}).get("news_stream_url")
    if not api_key or not secret_key:
        console.print("Set APCA_API_KEY_ID / APCA_API_SECRET_KEY to use news broker.", style="red")
        return

    broker = RealtimeNewsBroker(store, worker, api_key, secret_key, url=url)
    try:
        broker.start()
    except Exception as exc:  # pragma: no cover - network bootstrap errors
        console.print(f"Failed to start news broker: {exc}", style="red")
        return

    state["broker"] = broker
    state["thread"] = broker._thread
    console.print("News broker started in background thread.", style="green")


def _execute_auto_trade(
    auto_trader: AutoTradeService,
    snapshot: AccountSnapshot,
    hypothesis_store: HypothesisStore,
    *,
    compact: bool = False,
    skip_if_market_closed: bool = False,
    allow_market_closed: bool = False,
) -> bool:
    should_skip = skip_if_market_closed and bool(
        (auto_trader.config.get("auto_trade", {}) or {}).get("skip_when_market_closed", True)
    )
    if should_skip:
        is_open, reason = _market_is_open(auto_trader)
        if not is_open:
            suffix = f" ({reason})" if reason else ""
            console.print(f"Skipping auto-trade: market is closed{suffix}.", style="yellow")
            return False

    console.print("Running auto-trade …", style="bold cyan")
    try:
        result = auto_trader.run(snapshot, allow_market_closed=allow_market_closed)
    except Exception as exc:  # pragma: no cover - surfaced to CLI
        console.print(f"Auto-trade failed: {exc}", style="red")
        logging.exception("Auto-trade failed")
        return False
    _render_auto_trade_result(result, compact=compact)
    results_dir = Path(auto_trader.config.get("results_dir", "./results"))
    _persist_auto_trade_result(result, results_dir)
    new_records = hypothesis_store.record_result(result)
    if new_records:
        console.print(f"Recorded {len(new_records)} hypothesis{'es' if len(new_records) != 1 else ''} for autopilot follow-up.", style="green")
    return True


def _render_auto_trade_result(result: AutoTradeResult, *, compact: bool = False) -> None:
    console.rule("Auto-Trade Result")
    focus = ", ".join(result.focus_tickers) or "<none>"
    console.print(
        f"Focus tickers: {focus}\n"
        f"Buying Power: ${result.account_snapshot.buying_power():,.0f}\n"
        f"Cash: ${result.account_snapshot.cash():,.0f}"
    )
    skip_reason = (result.raw_state or {}).get("skip_reason") if result.raw_state is not None else None
    if skip_reason:
        console.print(skip_reason, style="yellow")

    if compact:
        if not result.decisions:
            console.print("No decisions produced.", style="yellow")
            return
        table = Table(title="Decisions", box=None)
        table.add_column("Ticker", style="cyan")
        table.add_column("Action", style="magenta")
        table.add_column("Next", overflow="fold")
        for decision in result.decisions:
            action = (decision.final_decision or decision.immediate_action or "hold").upper()
            next_hint = decision.sequential_plan.next_decision or decision.sequential_plan.notes or decision.final_notes or "<pending>"
            table.add_row(decision.ticker, action, next_hint)
        console.print(table)
        return

    transcript = (result.raw_state or {}).get("responses_transcript") if result.raw_state is not None else None
    if transcript:
        console.rule("Narrative")
        for idx, entry in enumerate(transcript, 1):
            console.print(f"[bold]Step {idx}: [/bold]{entry}")
        console.rule("Decisions")

    if not result.decisions:
        console.print("No decisions produced.", style="yellow")
        return

    for decision in result.decisions:
        header = f"[bold]{decision.ticker}[/bold] – action: [cyan]{decision.immediate_action.upper()}[/cyan]"
        table = Table(title=header, box=None)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")

        required = decision.hypothesis.get("required_analysts", [])
        plan_next = (
            decision.sequential_plan.next_decision.upper()
            if decision.sequential_plan.next_decision
            else "<none>"
        )
        table.add_row("Priority", f"{decision.priority:.2f}")
        table.add_row("Required Analysts", ", ".join(required) or "<none>")
        table.add_row("Plan Actions", " → ".join(decision.sequential_plan.actions) or "<none>")
        table.add_row("Plan Next Decision", plan_next)
        table.add_row("Action Queue", " → ".join(decision.action_queue or []) or "<none>")
        table.add_row("Planner Notes", decision.sequential_plan.notes or "<none>")
        table.add_row("Final Decision", decision.final_decision or "<pending>")
        table.add_row("Trader Plan", decision.trader_plan or "<none>")

        console.print(table)

        if decision.sequential_plan.reasoning:
            console.print(Text("Reasoning:", style="bold underline"))
            for idx, step in enumerate(decision.sequential_plan.reasoning, 1):
                console.print(f"  {idx}. {step}")

        if decision.final_notes:
            console.print(Text("Final Notes:", style="bold underline"))
            console.print(decision.final_notes)

        console.print()


def _persist_auto_trade_result(result: AutoTradeResult, results_dir: Path) -> None:
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        path = results_dir / f"auto_trade_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(result.summary(), handle, indent=2)
        console.print(f"Saved auto-trade summary to {path}", style="green")
    except Exception as exc:  # pragma: no cover - persistence best effort
        console.print(f"Failed to persist auto-trade summary: {exc}", style="red")


def _run_autopilot_loop(
    config: Dict[str, Any],
    snapshot: AccountSnapshot,
    auto_trader: AutoTradeService,
    hypothesis_store: HypothesisStore,
    autopilot_worker: AutopilotWorker,
    autopilot_broker: AutopilotBroker,
    realtime_state: Dict[str, Any],
    news_state: Dict[str, Any],
    account_service: AccountService,
) -> None:
    autopilot_cfg = config.get("autopilot", {}) or {}
    event_interval = max(int(autopilot_cfg.get("event_loop_interval_seconds", 10)), 1)
    price_poll_interval = max(int(autopilot_cfg.get("price_poll_interval_seconds", 60)), event_interval)
    seed_run = bool(autopilot_cfg.get("auto_trade_on_start", True))
    premarket_window = _resolve_premarket_window(autopilot_cfg.get("pre_market_research_minutes"))

    console.print("Autopilot mode enabled. Press Ctrl+C to stop.", style="bold cyan")

    latest_snapshot = snapshot
    pending_market_open_run = False
    premarket_marker: Optional[str] = None

    def _refresh_snapshot() -> Optional[AccountSnapshot]:
        nonlocal latest_snapshot
        try:
            snap = account_service.refresh()
            latest_snapshot = snap
            return snap
        except Exception as exc:
            console.print(f"Failed to refresh account snapshot: {exc}", style="red")
            return None

    def _refresh_snapshot_if_needed(force: bool = False) -> Optional[AccountSnapshot]:
        nonlocal latest_snapshot, market_is_open, market_status
        if not force and not market_is_open and not _within_premarket(market_status, premarket_window):
            return latest_snapshot
        snap = _refresh_snapshot()
        return snap

    heartbeat_interval = max(event_interval, 30)
    market_check_interval = max(price_poll_interval, 60)
    market_status = _get_market_status(auto_trader)
    last_market_check = time.time()
    market_is_open = bool(market_status.get("is_open"))
    next_market_check_delay = market_check_interval

    if seed_run:
        if market_is_open:
            snap = _refresh_snapshot_if_needed(force=True)
            if snap:
                ran = _execute_auto_trade(
                    auto_trader,
                    snap,
                    hypothesis_store,
                    compact=True,
                    skip_if_market_closed=False,
                    allow_market_closed=False,
                )
                pending_market_open_run = not ran
        else:
            pending_market_open_run = True
            reason = market_status.get("clock_text") or market_status.get("reason") or "market closed"
            console.print(f"Initial run skipped: {reason}.", style="yellow")
            if premarket_window > 0 and _should_run_premarket(market_status, premarket_window):
                snap = _refresh_snapshot_if_needed(force=True)
                if snap and _execute_auto_trade(
                    auto_trader,
                    snap,
                    hypothesis_store,
                    compact=True,
                    skip_if_market_closed=False,
                    allow_market_closed=True,
                ):
                    premarket_marker = market_status.get("next_open")
                    console.print(
                        "Pre-market research run completed; awaiting opening bell.",
                        style="dim",
                    )
    else:
        console.print("Skipping initial auto-trade seed (auto_trade_on_start=false).", style="yellow")

    _start_realtime_broker(config, hypothesis_store, autopilot_worker, realtime_state)
    _start_news_broker(config, hypothesis_store, autopilot_worker, news_state)

    last_price_poll = 0.0
    last_signature = ""
    last_heartbeat = 0.0
    events_since_heartbeat = 0
    console.print(
        f"Entering autopilot loop (event every {event_interval}s, price poll every {price_poll_interval}s)…",
        style="dim",
    )

    try:
        while True:
            events_since_heartbeat += _drain_autopilot_queue(autopilot_worker)

            records = hypothesis_store.list()
            signature = _hypothesis_signature(records)
            if signature != last_signature:
                last_signature = signature
                _refresh_stream_registrations(realtime_state, news_state, records)

            now = time.time()
            if now - last_price_poll >= price_poll_interval:
                events_since_heartbeat += _poll_price_alerts_quiet(
                    autopilot_broker,
                    autopilot_worker,
                    market_open=bool(market_status.get("is_open")),
                )
                last_price_poll = now

            if now - last_heartbeat >= heartbeat_interval:
                stats = _collect_stream_stats(realtime_state, news_state)
                _print_autopilot_heartbeat(events_since_heartbeat, stats)
                events_since_heartbeat = 0
                last_heartbeat = now

            if now - last_market_check >= next_market_check_delay:
                market_status = _get_market_status(auto_trader)
                last_market_check = now
                is_open = bool(market_status.get("is_open"))
                next_market_check_delay = market_check_interval if is_open else max(market_check_interval * 5, 300)
                market_is_open = is_open
                if is_open:
                    if pending_market_open_run:
                        snap = _refresh_snapshot_if_needed(force=True)
                        if snap and _execute_auto_trade(
                            auto_trader,
                            snap,
                            hypothesis_store,
                            compact=True,
                            skip_if_market_closed=False,
                            allow_market_closed=False,
                        ):
                            pending_market_open_run = False
                            premarket_marker = None
                else:
                    pending_market_open_run = True
                    if premarket_window > 0 and _should_run_premarket(market_status, premarket_window):
                        marker = market_status.get("next_open")
                        if marker and marker != premarket_marker:
                            snap = _refresh_snapshot()
                            if snap and _execute_auto_trade(
                                auto_trader,
                                snap,
                                hypothesis_store,
                                compact=True,
                                skip_if_market_closed=False,
                                allow_market_closed=True,
                            ):
                                console.print(
                                    "Pre-market research run completed; awaiting opening bell.",
                                    style="dim",
                                )
                                premarket_marker = marker

            time.sleep(event_interval)
    except KeyboardInterrupt:
        console.print("Autopilot loop stopped by user request.", style="yellow")


def _drain_autopilot_queue(worker: AutopilotWorker) -> int:
    try:
        processed = worker.process_all()
    except Exception as exc:  # pragma: no cover - best effort logging
        console.print(f"Autopilot event processing failed: {exc}", style="red")
        return 0

    if not processed:
        return 0

    table = Table(title="Autopilot Updates", box=None)
    table.add_column("Hypothesis", style="cyan")
    table.add_column("Event")
    table.add_column("Status", style="green")
    table.add_column("Message", style="magenta")

    max_rows = 10
    for item in processed[:max_rows]:
        hypothesis = item.event.hypothesis_id[-6:]
        table.add_row(
            hypothesis,
            item.event.event_type,
            item.status,
            item.message,
        )

    console.print(table)
    if len(processed) > max_rows:
        console.print(f"(+{len(processed) - max_rows} more events)", style="dim")

    return len(processed)


def _refresh_stream_registrations(
    realtime_state: Dict[str, Any],
    news_state: Dict[str, Any],
    records: List[Any],
) -> None:
    broker = realtime_state.get("broker")
    if broker is not None:
        try:
            registered = broker.refresh_triggers(records, reset=True)
            if registered:
                console.print(f"Realtime broker tracking {registered} trigger(s).", style="dim")
        except Exception as exc:  # pragma: no cover - best effort logging
            console.print(f"Realtime broker refresh failed: {exc}", style="red")

    news_broker = news_state.get("broker")
    if news_broker is not None:
        try:
            watchers = news_broker.refresh_watchers(records)
            if watchers:
                console.print(f"News broker monitoring {watchers} symbol-link(s).", style="dim")
        except Exception as exc:  # pragma: no cover - best effort logging
            console.print(f"News broker refresh failed: {exc}", style="red")


def _collect_stream_stats(
    realtime_state: Dict[str, Any],
    news_state: Dict[str, Any],
) -> Dict[str, Any]:
    price_thread = realtime_state.get("thread")
    price_connected = bool(price_thread and getattr(price_thread, "is_alive", lambda: False)())
    price_symbols = 0
    price_triggers = 0
    broker = realtime_state.get("broker")
    if broker is not None:
        lock = getattr(broker, "_lock", None)
        context = lock or nullcontext()
        with context:
            trigger_map = getattr(broker, "triggers", {}) or {}
            price_symbols = len(trigger_map)
            price_triggers = sum(len(bucket) for bucket in trigger_map.values())

    news_thread = news_state.get("thread")
    news_connected = bool(news_thread and getattr(news_thread, "is_alive", lambda: False)())
    news_symbols = 0
    news_broker = news_state.get("broker")
    if news_broker is not None:
        lock = getattr(news_broker, "_lock", None)
        context = lock or nullcontext()
        with context:
            watchers = getattr(news_broker, "watchers", {}) or {}
            news_symbols = len(watchers)

    return {
        "price_connected": price_connected,
        "price_symbols": price_symbols,
        "price_triggers": price_triggers,
        "news_connected": news_connected,
        "news_symbols": news_symbols,
    }


def _print_autopilot_heartbeat(events_processed: int, stats: Dict[str, Any]) -> None:
    price_status = "connected" if stats.get("price_connected") else "idle"
    news_status = "connected" if stats.get("news_connected") else "idle"
    message = (
        f"[dim]Heartbeat – events:{events_processed} | price stream {price_status} "
        f"({stats.get('price_symbols', 0)} symbols, {stats.get('price_triggers', 0)} triggers) "
        f"| news stream {news_status} ({stats.get('news_symbols', 0)} symbols).[/dim]"
    )
    console.print(message)


def _hypothesis_signature(records: List[Any]) -> str:
    if not records:
        return ""
    parts = [f"{getattr(rec, 'id', '')}:{getattr(rec, 'updated_at', '')}:{getattr(rec, 'status', '')}:{getattr(rec, 'action', '')}" for rec in records]
    return "|".join(parts)


def _poll_price_alerts_quiet(
    broker: AutopilotBroker,
    worker: AutopilotWorker,
    *,
    market_open: bool,
) -> int:
    if not market_open:
        return 0
    try:
        outcomes = broker.poll_once()
    except Exception as exc:  # pragma: no cover - best effort logging
        console.print(f"Price alert poll failed: {exc}", style="red")
        return 0

    if not outcomes:
        return 0

    table = Table(title="Price Trigger Alerts", box=None)
    table.add_column("Event", style="cyan")
    table.add_column("Message", style="magenta")
    for event_id, message in outcomes.items():
        table.add_row(event_id[-8:], message)
    console.print(table)

    # Process the events immediately so hypotheses update promptly.
    return _drain_autopilot_queue(worker)


def _market_is_open(auto_trader: AutoTradeService) -> (bool, Optional[str]):
    checker = getattr(auto_trader.graph, "check_market_status", None)
    if not callable(checker):
        return True, None
    try:
        status = checker() or {}
    except Exception:
        return True, None

    is_open = status.get("is_open")
    if is_open:
        return True, None
    reason = status.get("clock_text") or status.get("reason")
    return False, reason


def _get_market_status(auto_trader: AutoTradeService) -> Dict[str, Any]:
    checker = getattr(auto_trader.graph, "check_market_status", None)
    if not callable(checker):
        return {"is_open": True, "reason": "clock_unavailable"}
    try:
        return checker() or {}
    except Exception as exc:
        console.print(f"Failed to fetch market status: {exc}", style="red")
        return {"is_open": False, "reason": "clock_error"}


def _should_run_premarket(status: Dict[str, Any], window_minutes: int) -> bool:
    if window_minutes <= 0:
        return False
    next_open = _parse_market_time(status.get("next_open"))
    if not next_open:
        return False
    current = _parse_market_time(status.get("current_time"))
    if current is None:
        current = datetime.now(timezone.utc)
    now_utc = current.astimezone(timezone.utc)
    target = next_open.astimezone(timezone.utc)
    minutes = (target - now_utc).total_seconds() / 60
    return 0 <= minutes <= window_minutes


def _within_premarket(status: Dict[str, Any], window_minutes: int) -> bool:
    if not window_minutes:
        return False
    return _should_run_premarket(status, window_minutes)


def _parse_market_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if "T" not in text and " " in text:
        text = text.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


if __name__ == "__main__":
    main()
