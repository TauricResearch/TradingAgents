import argparse
import datetime
from pathlib import Path
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
# 引入原版CLI自带的保存报告的方法
from cli.main import save_report_to_disk

def parse_args():
    parser = argparse.ArgumentParser(description="Run TradingAgents Analysis via Command Line")
    
    parser.add_argument("-t", "--ticker", type=str, required=True,
                        help="分析的股票代码（如 NVDA, MU）")
    
    parser.add_argument("-d", "--date", type=str, default=datetime.datetime.now().strftime("%Y-%m-%d"),
                        help="分析日期（格式 YYYY-MM-DD），默认是当天")
    
    parser.add_argument("-a", "--analysts", type=str, default="market,social,news,fundamentals",
                        help="分析师列表，用逗号分隔（可选值: market, social, news, fundamentals）。默认全部包括。")
    
    parser.add_argument("--depth", type=int, default=1, choices=[1, 2, 3, 4, 5],
                        help="研究深度/辩论轮数（推荐 1, 3 或 5），默认使用1")
    
    parser.add_argument("-p", "--provider", type=str, default="google",
                        choices=["openai", "anthropic", "google", "openrouter", "ollama", "xai"],
                        help="LLM 提供商，默认是 google")
    
    parser.add_argument("--shallow-model", type=str, default="gemini-3.1-flash-lite-preview",
                        help="指定用于快速思考的模型，默认是 gemini-3.1-flash-lite-preview")
    
    parser.add_argument("--deep-model", type=str, default="gemini-3.1-pro-preview",
                        help="指定用于深度推理的模型，默认是 gemini-3.1-pro-preview")
    
    parser.add_argument("-n", "--non-interactive", action="store_true", required=True,
                        help="必须加上此参数以确认非交互模式运行")

    return parser.parse_args()

def main():
    load_dotenv()
    args = parse_args()

    print(f"\n[System] Starting analysis for {args.ticker} on {args.date} (Non-Interactive Mode)")

    valid_analyst_keys = ["market", "social", "news", "fundamentals"]
    selected_analysts = [
        a.strip().lower() for a in args.analysts.split(",") 
        if a.strip().lower() in valid_analyst_keys
    ]

    if not selected_analysts:
        print("[Error] No valid analysts selected. Please check your --analysts argument.")
        return

    print(f"[System] Selected Analysts: {', '.join(selected_analysts)}")

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = args.provider
    config["quick_think_llm"] = args.shallow_model
    config["deep_think_llm"] = args.deep_model
    config["max_debate_rounds"] = args.depth
    config["max_risk_discuss_rounds"] = args.depth

    print(f"[System] LLM Provider: {args.provider}")
    print(f"[System] Shallow Model: {args.shallow_model} | Deep Model: {args.deep_model}")
    print(f"[System] Research Depth: {args.depth}")

    print("\n[System] Initializing Trading Agents Graph...")
    ta = TradingAgentsGraph(selected_analysts, debug=False, config=config)

    print("\n[System] Propagating analysis... (This may take a while depending on depth and models)")
    try:
        # 获取包含所有过程记录的 final_state
        final_state, decision = ta.propagate(args.ticker, args.date)
        
        print("\n" + "="*50)
        print("FINAL TRADING DECISION")
        print("="*50)
        print(decision)
        print("="*50)

        # ====== 使用原版完整的方法保存报告 ======
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # 存放在项目根目录下的 reports 文件夹，按股票和时间分类
        save_dir = Path.cwd() / "reports" / f"{args.ticker}_{timestamp}"
        
        report_file = save_report_to_disk(final_state, args.ticker, save_dir)
        print(f"\n[System] Complete reports successfully saved to: {save_dir.resolve()}")
        print(f"[System] Aggregated report file: {report_file.name}")

    except Exception as e:
        print(f"\n[Error] Analysis failed: {e}")

if __name__ == "__main__":
    main()
