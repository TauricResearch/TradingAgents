"""每日股票分析排程器 — 本地執行版

設定方式：
  1. 編輯下方 ── 使用者設定 ── 區塊，填入你的本地模型資訊與股票清單
  2. 雙擊 run_now.bat 立即執行一次
     或雙擊 start_scheduler.bat 啟動每天早上 06:00 自動執行

報告輸出位置：reports\{股票代號}\{日期}\
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import schedule
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

load_dotenv()

# ════════════════════════════════════════════════════════════════
# ── 使用者設定（依照你的環境修改這裡）
# ════════════════════════════════════════════════════════════════

# 每天執行時間（24 小時制）
RUN_AT = "06:00"

# 要分析的股票清單
STOCKS = [
    "NVDA",
    "TSLA",
    "AAPL",
    "MSFT",
    "AMZN",
]

# 報告存放資料夾（相對於此腳本的位置）
REPORTS_DIR = Path(__file__).parent / "reports"

# 本地模型設定
# Ollama 範例：provider="openai", backend_url="http://localhost:11434/v1", model="llama3"
# LM Studio 範例：provider="openai", backend_url="http://localhost:1234/v1", model="你的模型名稱"
LLM_PROVIDER   = "openai"
BACKEND_URL    = "http://localhost:11434/v1"   # ← 改成你的本地伺服器位址
DEEP_THINK_LLM = "llama3"                      # ← 改成你的模型名稱
QUICK_THINK_LLM = "llama3"                     # ← 可與上方相同或使用較小模型

MAX_DEBATE_ROUNDS = 1

# ════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

_SIGNAL_COLOR = {
    "Buy":         "#1e8449",
    "Overweight":  "#2ecc71",
    "Hold":        "#d4ac0d",
    "Underweight": "#e67e22",
    "Sell":        "#c0392b",
}

_SECTIONS = [
    ("市場分析 Market Analysis",        "market_report"),
    ("情緒分析 Sentiment Analysis",      "sentiment_report"),
    ("新聞分析 News Analysis",           "news_report"),
    ("基本面分析 Fundamentals",          "fundamentals_report"),
    ("投資計畫 Investment Plan",         "investment_plan"),
    ("交易決策 Trader Decision",         "trader_investment_plan"),
    ("最終決策 Final Trade Decision",    "final_trade_decision"),
]


def _build_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"]    = LLM_PROVIDER
    cfg["backend_url"]     = BACKEND_URL
    cfg["deep_think_llm"]  = DEEP_THINK_LLM
    cfg["quick_think_llm"] = QUICK_THINK_LLM
    cfg["max_debate_rounds"] = MAX_DEBATE_ROUNDS
    cfg["checkpoint_enabled"] = True
    cfg["data_vendors"] = {
        "core_stock_apis":      "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data":     "yfinance",
        "news_data":            "yfinance",
    }
    return cfg


def _generate_pdf(ticker: str, trade_date: str, state: dict, signal: str) -> Path:
    out_dir = REPORTS_DIR / ticker / trade_date
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{ticker}_{trade_date}.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    base  = getSampleStyleSheet()
    title = ParagraphStyle("T", parent=base["Heading1"], fontSize=18, spaceAfter=4)
    sig   = ParagraphStyle("S", parent=base["Normal"], fontSize=13,
                           textColor=colors.HexColor(_SIGNAL_COLOR.get(signal, "#1a5276")),
                           spaceAfter=8)
    h2    = ParagraphStyle("H", parent=base["Heading2"], fontSize=12, spaceAfter=4)
    body  = ParagraphStyle("B", parent=base["Normal"], fontSize=9, leading=14, spaceAfter=6)

    story = [
        Paragraph(f"TradingAgents — {ticker}", title),
        Paragraph(f"日期 {trade_date} &nbsp;|&nbsp; 信號 <b>{signal}</b>", sig),
        HRFlowable(width="100%", thickness=1, color=colors.grey),
        Spacer(1, 4*mm),
    ]

    for section_title, key in _SECTIONS:
        content = state.get(key, "")
        if not content or not content.strip():
            continue
        story.append(Paragraph(section_title, h2))
        safe = (content
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>"))
        story.append(Paragraph(safe, body))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 3*mm))

    doc.build(story)
    log.info("已儲存 PDF：%s", pdf_path)
    return pdf_path


def run_analysis() -> None:
    trade_date = datetime.now().strftime("%Y-%m-%d")
    log.info("═══ 開始分析：%s ═══", trade_date)

    cfg = _build_config()
    ta  = TradingAgentsGraph(debug=False, config=cfg)

    results = []
    for ticker in STOCKS:
        log.info("分析中：%s …", ticker)
        try:
            final_state, signal = ta.propagate(ticker, trade_date)
            pdf = _generate_pdf(ticker, trade_date, final_state, signal)
            results.append((ticker, signal, str(pdf)))
            log.info("%s → %s", ticker, signal)
        except Exception as exc:
            log.error("%s 失敗：%s", ticker, exc, exc_info=True)
            results.append((ticker, "ERROR", str(exc)))

    log.info("═══ 分析摘要 ═══")
    for ticker, signal, info in results:
        log.info("  %-8s %s", ticker, signal)
    log.info("報告位置：%s", REPORTS_DIR.resolve())
    log.info("════════════════")


def main() -> None:
    import sys
    # 傳入 --now 參數可立即執行一次
    if "--now" in sys.argv:
        run_analysis()
        return

    log.info("排程器啟動。每天 %s 自動執行。按 Ctrl+C 停止。", RUN_AT)
    schedule.every().day.at(RUN_AT).do(run_analysis)
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
