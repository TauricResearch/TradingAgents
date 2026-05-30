import copy
import json
import os
import traceback
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", str(WORKSPACE / ".tmp_cache"))
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", str(WORKSPACE / "reports" / "_runtime_logs"))

from dotenv import load_dotenv

from cli.main import save_report_to_disk
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main():
    load_dotenv(WORKSPACE / ".env", override=True)
    load_dotenv(WORKSPACE / ".env.enterprise", override=False)

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = "mimo"
    config["backend_url"] = "https://token-plan-sgp.xiaomimimo.com/anthropic"
    config["quick_think_llm"] = "mimo-v2.5"
    config["deep_think_llm"] = "mimo-v2.5-pro"
    config["output_language"] = "Chinese"
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["checkpoint_enabled"] = False
    config["data_vendors"].update(
        {
            "news_data": "tavily,yfinance,alpha_vantage",
            "core_stock_apis": "yfinance,tushare,akshare,alpha_vantage",
            "fundamental_data": "yfinance,tushare,akshare,alpha_vantage",
        }
    )

    ticker = "002396.SZ"
    trade_date = "2026-05-07"
    graph = TradingAgentsGraph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        config=config,
        debug=False,
    )

    result = {
        "ticker": ticker,
        "trade_date": trade_date,
        "provider": "mimo",
        "quick_model": "mimo-v2.5",
        "deep_model": "mimo-v2.5-pro",
        "status": "unknown",
    }

    try:
        final_state, decision = graph.propagate(ticker, trade_date)
        save_path = Path.cwd() / "reports" / "002396.SZ_20260508_mimo_gate_test"
        report_path = save_report_to_disk(final_state, ticker, save_path)
        result.update(
            {
                "status": "completed",
                "decision": decision,
                "report_path": str(report_path),
                "evidence_status": final_state.get("evidence_status"),
                "evidence_report": final_state.get("evidence_report"),
                "final_trade_decision": final_state.get("final_trade_decision"),
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "stopped",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc().splitlines()[-8:],
            }
        )

    out_path = Path.cwd() / "reports" / "002396.SZ_20260508_mimo_gate_test_result.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
