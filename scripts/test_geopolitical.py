#!/usr/bin/env python3
"""
临时脚本：用 DeepSeek V4 Flash 获取当前全球新闻并分析国际形势热点。
独立运行，不依赖项目 Graph 执行流。

Usage:
    python scripts/test_geopolitical.py

Output:
    reports/geopolitical_report_<date>.md
"""

import os
import sys
import json
from datetime import datetime, timedelta

# 确保能从项目根目录导入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tradingagents.dataflows.yfinance_news import get_global_news_yfinance
from tradingagents.llm_clients.factory import create_llm_client

CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "reports", f"geopolitical_report_{CURRENT_DATE}.md")


def check_env():
    """检查必要环境变量。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        # 尝试从 .env 加载
        env_path = os.path.join(PROJECT_ROOT, ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPSEEK_API_KEY="):
                        os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
                        api_key = os.environ["DEEPSEEK_API_KEY"]
                        break
    if not api_key:
        print("❌ 未设置 DEEPSEEK_API_KEY 环境变量")
        print("   请先 export DEEPSEEK_API_KEY=your_key 或在 .env 中配置")
        sys.exit(1)


def fetch_news() -> str:
    """拉取最近 7 天的全球宏观新闻。"""
    lookback = 7
    start = (datetime.strptime(CURRENT_DATE, "%Y-%m-%d") - timedelta(days=lookback)).strftime("%Y-%m-%d")
    print(f"  [FETCH] Period: {start} ~ {CURRENT_DATE} ({lookback}-day lookback)")

    news = get_global_news_yfinance(
        curr_date=CURRENT_DATE,
        look_back_days=lookback,
        limit=50,
    )

    if not news or "No global news found" in news or "Error" in news:
        print(f"  [WARN] Global news API returned no data:\n{news[:500]}")
        print("  [WARN] Falling back to model knowledge (no news context)")
        return ""

    # 粗略统计文章数
    article_count = news.count("### ")
    print(f"  [OK] Fetched ~{article_count} articles")
    return news


def analyze_geopolitics(llm, news_block: str) -> str:
    """调用 LLM 分析国际形势热点。"""
    if news_block:
        prompt = f"""You are a geopolitical risk analyst for a quantitative trading firm. Today's date is {CURRENT_DATE}.

Below is a batch of recent global news headlines covering the past 7 days. Analyze them and produce a structured geopolitical risk assessment.

## Instructions
1. Identify the **5-10 most significant geopolitical hot topics** currently unfolding.
2. For each topic, provide:
   - **Title** — short label
   - **Description** — what is happening (2-3 sentences)
   - **Risk Level** — 🔴 High / 🟡 Medium / 🟢 Low
   - **Trend** — Escalating / Stable / De-escalating
   - **Market Transmission Channel** — how this affects markets (e.g. oil prices, supply chain, safe-haven flows, sector rotation, currency moves, etc.)
3. Assign an **Overall Global Geopolitical Risk Rating** (🔴 High / 🟡 Medium / 🟢 Low) with a brief rationale.
4. Identify **key risks to monitor** in the coming week.

## Recent Global News (past 7 days)
{news_block}

## Output Format
Output your analysis in clean markdown."""

        print("  [ANALYZE] Analyzing geopolitical hot topics...")
    else:
        # 没有新闻时的降级方案：让 LLM 凭知识回答
        prompt = f"""You are a geopolitical risk analyst for a quantitative trading firm. Today's date is {CURRENT_DATE}.

Unfortunately, the news feed returned no data for the current period. Based on your training knowledge up to your cutoff date, provide the best estimate of what geopolitical hot topics are likely relevant:

1. What geopolitical risks would you flag given the current date?
2. What are the typical ongoing geopolitical flash points that a trading desk should monitor?
3. Assign a provisional risk rating.

Be honest about what you know vs. what you are extrapolating.

## Output Format
Output your analysis in clean markdown with a clear disclaimer about any data limitations."""

        print("  [ANALYZE] No news data, using model knowledge (fallback mode)...")

    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return content


def save_report(content: str):
    """保存分析报告为 markdown 文件。"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# 国际形势风险评估报告\n\n")
        f.write(f"- **分析日期**: {CURRENT_DATE}\n")
        f.write(f"- **模型**: DeepSeek V4 Flash\n")
        f.write(f"- **数据源**: Yahoo Finance Global News\n")
        f.write(f"- **新闻回溯**: 7 天\n\n")
        f.write("---\n\n")
        f.write(content)

    print(f"\n  [OK] Report saved: {OUTPUT_FILE}")


def main():
    print("=" * 60)
    print("  Geopolitical Analysis -- DeepSeek V4 Flash")
    print("=" * 60)
    print()

    # Step 1: 环境检查
    print("[1/4] Check environment variables...")
    check_env()
    print("  [OK] DEEPSEEK_API_KEY is set")
    print()

    # Step 2: 拉取新闻
    print("[2/4] Fetch global news...")
    news_block = fetch_news()
    print()

    # Step 3: 创建 LLM 客户端
    print("[3/4] Initialize DeepSeek V4 Flash...")
    try:
        client = create_llm_client(
            provider="deepseek",
            model="deepseek-v4-flash",
        )
        llm = client.get_llm()
        print("  [OK] LLM client ready")
    except Exception as e:
        print(f"  [FAIL] Create LLM client failed: {e}")
        sys.exit(1)
    print()

    # Step 4: 分析
    print("[4/4] Analyze geopolitical hot topics...")
    try:
        content = analyze_geopolitics(llm, news_block)
        save_report(content)
    except Exception as e:
        print(f"  [FAIL] Analysis failed: {e}")
        # 保存错误信息
        with open(OUTPUT_FILE.replace(".md", "_error.md"), "w") as f:
            f.write(f"# Error\n\nAnalysis failed: {e}\n")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
