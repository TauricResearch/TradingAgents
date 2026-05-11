"""Mini validation: does the new Traditional Chinese prompt actually produce Traditional output?

Uses the project's own LLM client + prompt instruction so this verifies the
exact code path that ran in production. Sends a single small chat request
to DeepSeek via OpenRouter (same provider the user picked) and tallies
unambiguously-Simplified vs unambiguously-Traditional characters.

Cost: roughly $0.001-0.005. Cheaper than retrying a full analysis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure we use the local source tree, not any installed copy
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.llm_clients import create_llm_client
from tradingagents.runtime import set_runtime_config

# Characters that exist ONLY in Simplified (not used in modern Traditional).
# Each entry has a distinct Traditional counterpart. Characters that look the
# same in both scripts (e.g. 整, 跌, 步) are intentionally excluded — including
# them produces false positives.
SIMPLIFIED_ONLY = set(
    "数据软义严经续应这时间个实现国风险评级见关价决议项营销论报"
    "类设资产业边际维仓财务历长调询确认护备测试运营错误"
    "动态结构观点说赞优势协议预计划买卖涨赔赚总额详细进选择"
)

# Characters that exist ONLY in modern Traditional Chinese (not in mainland Simplified).
TRADITIONAL_ONLY = set(
    "數據軟義嚴經續應這時間個實現國風險評級見關價決議項營銷論報"
    "類設資產業邊際維倉財務歷長調詢確認護備測試運營錯誤"
    "動態結構觀點說讚優勢協議預計劃買賣漲賠賺總額詳細進選擇"
)


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("FAIL: OPENROUTER_API_KEY not loaded from .env")
        return 1

    # Apply the runtime config the same way the CLI does.
    set_runtime_config({"output_language": "Traditional Chinese"}, scope="context")

    instruction = get_language_instruction()
    print("Resolved instruction:")
    print(f"  {instruction.strip()}")
    print()

    # Build a system prompt mirroring how analysts use it.
    system_prompt = (
        "You are a financial analyst summarizing a single stock for a trader. "
        "Write 1 short paragraph (60-120 words) covering the company's business, "
        "recent price action, and one risk."
        + instruction
    )
    user_prompt = "Summarize Apple Inc. (AAPL)."

    # Use deepseek/deepseek-chat via OpenRouter — cheapest stable variant.
    client = create_llm_client(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
    )
    llm = client.get_llm()

    print("Calling deepseek/deepseek-chat via OpenRouter...")
    response = llm.invoke(
        [{"role": "system", "content": system_prompt},
         {"role": "user", "content": user_prompt}]
    )
    text = response.content if hasattr(response, "content") else str(response)
    if isinstance(text, list):  # some clients return list-of-parts
        text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)

    print()
    print("--- LLM response ---")
    print(text)
    print("--- end response ---")
    print()

    s_chars = [c for c in text if c in SIMPLIFIED_ONLY]
    t_chars = [c for c in text if c in TRADITIONAL_ONLY]
    s_unique = sorted(set(s_chars))
    t_unique = sorted(set(t_chars))

    print(f"Simplified-only character occurrences: {len(s_chars)}  unique: {len(s_unique)}")
    if s_unique:
        print(f"  Found: {''.join(s_unique)}")
    print(f"Traditional-only character occurrences: {len(t_chars)}  unique: {len(t_unique)}")
    if t_unique:
        print(f"  Found: {''.join(t_unique)}")
    print()

    if len(s_chars) == 0 and len(t_chars) > 0:
        print("VERDICT: PASS — output is Traditional Chinese, no Simplified contamination.")
        return 0
    if len(s_chars) > 0 and len(t_chars) == 0:
        print("VERDICT: FAIL — output is Simplified Chinese; the prompt instruction was ignored.")
        return 2
    if len(s_chars) == 0 and len(t_chars) == 0:
        print("VERDICT: INCONCLUSIVE — no marker characters found "
              "(response may be too short or in English).")
        return 3
    print(f"VERDICT: PARTIAL — mixed output. Simplified: {len(s_chars)}, Traditional: {len(t_chars)}")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
