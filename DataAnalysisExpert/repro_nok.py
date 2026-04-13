import asyncio
import json

from agent_os.backend.services.langgraph_engine import LangGraphEngine
from agent_os.backend.services.scanner_context import build_scanner_context_packet
from agent_os.backend.services.run_helpers import analysis_status
from tradingagents.portfolio.store_factory import create_report_store
from tradingagents.report_paths import generate_run_id, get_ticker_dir


SOURCE_RUN_ID = "01KP40Z636JA4MP5Y35YX4RMXA"
DATE = "2026-04-13"
TICKER = "NOK"


async def main() -> None:
    engine = LangGraphEngine()
    source_store = create_report_store(run_id=SOURCE_RUN_ID)
    scan_state = engine._load_scan_state(root_run_id=SOURCE_RUN_ID, date=DATE, store=source_store)
    scanner_packet = build_scanner_context_packet(scan_state, TICKER)

    new_run_id = generate_run_id()
    print(f"REPRO_RUN_ID={new_run_id}")
    print(f"SCANNER_PACKET_LEN={len(scanner_packet)}")

    async def run_once(execution_key: str, *, resume_from_latest_snapshot: bool = False) -> Exception | None:
        async for event in engine.run_pipeline(
            execution_key,
            {
                "ticker": TICKER,
                "date": DATE,
                "run_id": new_run_id,
                "portfolio_context": "candidate",
                "scanner_context_packet": scanner_packet,
                "_execution_key": execution_key,
                "resume_from_latest_snapshot": resume_from_latest_snapshot,
            },
        ):
            event_type = event.get("type")
            node_id = event.get("node_id")
            if event_type == "log":
                print(f"LOG::{event.get('message', '')}")
            elif event_type == "result" and node_id in {
                "Research Manager",
                "Trader",
                "Risk Synthesis",
                "Portfolio Manager",
            }:
                metrics = event.get("metrics") or {}
                response_len = len(str(event.get("response") or ""))
                print(
                    f"NODE::{node_id}::latency_ms={metrics.get('latency_ms')}::response_len={response_len}"
                )
        return None

    try:
        await run_once(f"{new_run_id}:pipeline:{TICKER}")
    except Exception as exc:  # noqa: BLE001
        print(f"EXCEPTION::{type(exc).__name__}::{exc}")

    store = create_report_store(run_id=new_run_id)
    analysis = store.load_analysis(DATE, TICKER) or {}
    snapshot = store.load_latest_pipeline_node_snapshot(DATE, TICKER) or {}
    ticker_dir = get_ticker_dir(DATE, TICKER, new_run_id) / "report"
    files = sorted(path.name for path in ticker_dir.glob("*.json")) if ticker_dir.exists() else []

    summary = {
        "analysis_status": analysis_status(analysis) if analysis else None,
        "analysis_keys": sorted(list(analysis.keys()))[:20] if analysis else [],
        "latest_snapshot_node": snapshot.get("node_name"),
        "latest_snapshot_phase": snapshot.get("resume_phase"),
        "snapshot_status": snapshot.get("analysis_status"),
        "report_dir": str(ticker_dir),
        "json_artifacts": files,
    }
    print("SUMMARY::" + json.dumps(summary))


if __name__ == "__main__":
    asyncio.run(main())