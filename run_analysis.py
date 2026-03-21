"""
TradingAgents 分析脚本
用途：对持仓标的（NVDA / VOO）进行多 Agent 分析
用法：
  python run_analysis.py NVDA                          # 分析 NVDA，使用今日日期
  python run_analysis.py VOO                           # 分析 VOO
  python run_analysis.py NVDA 2026-03-20               # 指定日期
  python run_analysis.py NVDA 2026-03-20 "中东地缘冲突..."  # 注入自定义分析视角
"""

import sys
import os
import time
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ── 配置 ────────────────────────────────────────────────────────────────────
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-2.5-flash"
config["quick_think_llm"] = "gemini-2.5-flash"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
}

# ── 入参解析 ─────────────────────────────────────────────────────────────────
ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
analysis_date = sys.argv[2] if len(sys.argv) > 2 else str(date.today())
user_context = sys.argv[3] if len(sys.argv) > 3 else ""

# 如果没有传入上下文，交互式询问
if not user_context and sys.stdin.isatty():
    print("\n💬 是否有自定义分析视角？（直接回车跳过）")
    print("   例：当前主导美股的核心因素是中东地缘冲突，请重点考虑此风险")
    user_context = input("   > ").strip()

print(f"\n{'='*60}")
print(f"🤖 TradingAgents 多 Agent 分析")
print(f"   标的：{ticker}")
print(f"   日期：{analysis_date}")
print(f"   模型：Gemini 2.5 Flash")
if user_context:
    print(f"   用户视角：{user_context[:60]}{'...' if len(user_context) > 60 else ''}")
print(f"{'='*60}\n")

# ── 执行分析（带 retry）────────────────────────────────────────────────────────
MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        print(f"[尝试 {attempt}/{MAX_RETRIES}]")
        ta = TradingAgentsGraph(
            selected_analysts=["market", "social", "news", "fundamentals"],
            debug=False,
            config=config,
        )
        final_state, decision = ta.propagate(ticker, analysis_date, user_context)
        break
    except Exception as e:
        print(f"⚠️  第 {attempt} 次失败: {type(e).__name__}: {str(e)[:120]}")
        if attempt < MAX_RETRIES:
            wait = 10 * attempt
            print(f"   等待 {wait}s 后重试...")
            time.sleep(wait)
        else:
            print("❌ 全部重试失败，退出。")
            sys.exit(1)

# ── 输出结果 ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"📊 {ticker} 最终决策（{analysis_date}）：{decision}")
print(f"{'='*60}\n")

# 保存完整报告
output_dir = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, f"{ticker}_{analysis_date}.txt")

with open(output_file, "w", encoding="utf-8") as f:
    f.write(f"标的：{ticker}\n日期：{analysis_date}\n最终决策：{decision}\n")
    if user_context:
        f.write(f"用户视角：{user_context}\n")
    f.write("\n" + "="*60 + "\n")

    f.write("【交易员决策报告】\n")
    f.write(str(final_state.get("trader_investment_plan", "N/A")))
    f.write("\n\n" + "="*60 + "\n")

    debate = final_state.get("investment_debate_state", {})
    f.write("【多空辩论结论】\n")
    f.write(str(debate.get("judge_decision", "N/A")))
    f.write("\n\n" + "="*60 + "\n")

    risk = final_state.get("risk_debate_state", {})
    f.write("【风控审核结论】\n")
    f.write(str(risk.get("judge_decision", "N/A")))
    f.write("\n\n" + "="*60 + "\n")

    f.write("【最终决策原文】\n")
    f.write(str(final_state.get("final_trade_decision", "N/A")))

print(f"✅ 完整报告已保存：{output_file}")
