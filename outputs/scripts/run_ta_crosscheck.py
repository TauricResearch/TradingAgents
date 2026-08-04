"""TradingAgents AI 交叉验证：对 000001.SZ 跑多 agent 分析，与量化信号对照。"""

import os
from pathlib import Path
from dotenv import load_dotenv

# override=True：.env 里的 NO_PROXY 必须覆盖 shell 的值，否则讯飞 .com 域名
# 会被 Clash 代理劫持，大 prompt 经代理转发时 hang。
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
# .env 已配 GLM-5.1，config 会自动带上 provider/model
print(
    f"provider={config.get('llm_provider')} deep={config.get('deep_think_llm')} quick={config.get('quick_think_llm')}"
)
print(f"output_language={config.get('output_language')}")

ta = TradingAgentsGraph(config=config, debug=False)
# 000001.SZ 平安银行，分析日期取最近交易日
state, decision = ta.propagate("000001.SZ", "2026-07-31")
print("\n=== AI 决策 ===")
print(decision)
# 落盘
from pathlib import Path

out = Path(__file__).resolve().parent.parent / "reports" / "ta_crosscheck_000001.md"
out.write_text(
    f"# TradingAgents AI 交叉验证 000001.SZ @ 2026-07-31\n\n## 量化结论（v2 T+1优化版）\n金叉死叉最优 fast=3/slow=120：总收益 -1.00%，夏普 0.064，相对买入持有（-34.55%）少亏 33.5%，最大回撤 -24.9%。\n\n## AI 决策\n\n{decision}\n",
    encoding="utf-8",
)
print(f"\n-> {out}")
