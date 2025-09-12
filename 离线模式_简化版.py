#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingAgents 离线模式 - 简化版
当网络连接有问题时，使用模拟数据进行分析
"""

import os
import sys
import json
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def create_offline_config():
    """创建离线模式配置"""
    return {
        "llm_provider": "offline",
        "deep_think_llm": "offline-model",
        "quick_think_llm": "offline-model",
        "backend_url": "offline",
        "online_tools": False,
        "max_recur_limit": 10,
        "request_timeout": 30,
        "max_retries": 1,
    }

def simulate_analysis(ticker, analysis_date):
    """模拟分析过程"""
    print(f"🔍 离线模式分析: {ticker} ({analysis_date})")
    print("=" * 50)
    
    # 模拟各个分析阶段
    stages = [
        "📊 市场分析师 - 技术指标分析",
        "📰 新闻分析师 - 新闻情绪分析", 
        "📈 基本面分析师 - 财务数据分析",
        "🔍 研究团队 - 投资决策讨论",
        "💼 交易团队 - 交易计划制定",
        "⚠️ 风险管理 - 风险评估",
        "📋 投资组合管理 - 最终决策"
    ]
    
    for i, stage in enumerate(stages, 1):
        print(f"\n{i}. {stage}")
        print("   ✅ 分析完成")
        
        # 模拟处理时间
        import time
        time.sleep(0.5)
    
    # 生成模拟报告
    report = f"""
# {ticker} 股票分析报告
**分析日期**: {analysis_date}
**分析模式**: 离线模拟

## 📊 市场分析
- 技术指标显示{ticker}处于上升趋势
- RSI指标为65，接近超买区域
- MACD显示正动量
- 布林带显示价格在正常区间内

## 📰 新闻情绪
- 整体情绪偏向积极
- 主要新闻关注AI和科技发展
- 分析师评级多数为买入

## 📈 基本面分析
- 营收增长稳定
- 利润率保持健康水平
- 现金流充裕
- 债务水平合理

## 🔍 投资建议
基于离线模拟分析，建议：

**最终决策**: **HOLD** (持有)

**理由**:
1. 技术指标显示上升趋势但接近阻力位
2. 基本面稳健但估值偏高
3. 建议等待更好的入场时机

**风险提示**:
- 市场波动性较高
- 宏观经济不确定性
- 行业竞争加剧

---
*此报告基于离线模拟数据生成，仅供参考*
"""
    
    return report

def main():
    """主函数"""
    print("🚀 TradingAgents 离线模式")
    print("=" * 50)
    
    # 获取用户输入
    ticker = input("请输入股票代码 (默认: NVDA): ").strip() or "NVDA"
    analysis_date = input("请输入分析日期 (默认: 2024-05-10): ").strip() or "2024-05-10"
    
    try:
        # 执行模拟分析
        report = simulate_analysis(ticker, analysis_date)
        
        # 保存报告
        results_dir = f"results/{ticker}/{analysis_date}"
        os.makedirs(results_dir, exist_ok=True)
        
        report_file = os.path.join(results_dir, "offline_analysis_report.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"\n📄 报告已保存到: {report_file}")
        print("\n" + "=" * 50)
        print(report)
        
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断分析")
    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {e}")

if __name__ == "__main__":
    main()
