from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is optional for this runner
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cli.main import save_report_to_disk
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from automation.market_data import (
    configure_yfinance_cache,
    fetch_daily_close_history,
    has_price_data,
    resolve_data_symbol,
)
from automation.pdf import write_investment_pdf
from automation.signals import build_signal, write_signal


LOG = logging.getLogger("tradingagents.automation")


def main() -> int:
    args = _parse_args()
    if load_dotenv:
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / ".env.enterprise", override=False)
    configure_yfinance_cache(ROOT / ".yfinance_cache")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not config_path.exists() and config_path.name == "config.json":
        config_path = config_path.with_name("config.json.example")
    automation_config = _load_json(config_path)

    analysis_date = args.analysis_date or date.today().isoformat()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = ROOT / automation_config.get("results_root", "reports/scheduled") / analysis_date / run_id
    log_path = output_root / "run.log"
    _setup_logging(log_path)

    tickers = args.tickers or automation_config["tickers"]
    LOG.info("Starting scheduled analysis date=%s tickers=%s", analysis_date, ",".join(tickers))

    failures = 0
    for ticker in tickers:
        try:
            _run_ticker(ticker=ticker, analysis_date=analysis_date, run_root=output_root, automation_config=automation_config)
        except Exception as exc:
            failures += 1
            LOG.error("Ticker %s failed: %s\n%s", ticker, exc, traceback.format_exc())

    LOG.info("Finished scheduled analysis failures=%s output=%s", failures, output_root)
    return 1 if failures == len(tickers) else 0


def _run_ticker(*, ticker: str, analysis_date: str, run_root: Path, automation_config: dict[str, Any]) -> None:
    symbol = resolve_data_symbol(ticker, automation_config.get("ticker_aliases"))
    has_data, data_message = has_price_data(symbol.data_symbol)
    if not has_data:
        _write_skipped_ticker(run_root / ticker, ticker=ticker, data_symbol=symbol.data_symbol, reason=data_message)
        LOG.warning("Skipping %s: %s", ticker, data_message)
        return

    LOG.info("Running TradingAgents for %s using data_symbol=%s", ticker, symbol.data_symbol)
    ta_config = DEFAULT_CONFIG.copy()
    ta_config.update(
        {
            "llm_provider": automation_config.get("llm_provider", ta_config["llm_provider"]),
            "quick_think_llm": automation_config.get("quick_think_llm", ta_config["quick_think_llm"]),
            "deep_think_llm": automation_config.get("deep_think_llm", ta_config["deep_think_llm"]),
            "max_debate_rounds": automation_config.get("max_debate_rounds", ta_config["max_debate_rounds"]),
            "max_risk_discuss_rounds": automation_config.get("max_risk_discuss_rounds", ta_config["max_risk_discuss_rounds"]),
            "output_language": automation_config.get("output_language", ta_config["output_language"]),
            "checkpoint_enabled": automation_config.get("checkpoint_enabled", True),
            "results_dir": str(run_root / "_state_logs"),
        }
    )

    graph = TradingAgentsGraph(
        selected_analysts=automation_config.get("selected_analysts", ["market", "news"]),
        debug=True,
        config=ta_config,
    )
    final_state, decision = graph.propagate(symbol.data_symbol, analysis_date)
    LOG.info("TradingAgents decision for %s: %s", symbol.data_symbol, decision)

    ticker_dir = run_root / ticker
    report_path = save_report_to_disk(final_state, ticker, ticker_dir)
    signal = build_signal(
        ticker=ticker,
        analysis_date=analysis_date,
        final_state=final_state,
        report_path=report_path,
        risk_config=automation_config.get("risk", {}),
        market_symbol=symbol.data_symbol,
    )
    signal_path = write_signal(signal, ticker_dir / "signal.json")
    markdown = report_path.read_text(encoding="utf-8")
    pdf_path = write_investment_pdf(
        markdown,
        ticker_dir / "complete_report.pdf",
        title=f"Trading Analysis Report: {ticker}",
        signal=signal.to_dict(),
        price_history=fetch_daily_close_history(symbol.data_symbol),
    )
    LOG.info("Saved %s report=%s pdf=%s signal=%s", ticker, report_path, pdf_path, signal_path)


def _write_skipped_ticker(ticker_dir: Path, *, ticker: str, data_symbol: str, reason: str) -> None:
    ticker_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "ticker": ticker,
        "data_symbol": data_symbol,
        "status": "skipped",
        "reason": reason,
        "next_action": (
            "Configure automation/config.json ticker_aliases with a data_symbol "
            "that has OHLCV coverage, or add a non-yfinance data provider."
        ),
    }
    (ticker_dir / "skipped.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled TradingAgents analysis.")
    parser.add_argument("--config", default="automation/config.json", help="Path to automation JSON config.")
    parser.add_argument("--analysis-date", default=None, help="Analysis date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--tickers", nargs="*", default=None, help="Optional ticker override.")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
