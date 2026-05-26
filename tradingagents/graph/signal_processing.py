"""
信号处理器 —— 从 Portfolio Manager 决策中提取 5 级评级

在项目中的角色：
  - 作为交易信号提取的统一入口
  - 将 LLM 生成的自然语言决策转换为标准化评级
  - 为下游系统（如交易执行、日志记录）提供结构化输出

设计演进：
  - 早期版本：使用 LLM 进行二次解析提取评级
  - 当前版本：PM 输出采用结构化格式，直接用正则解析即可
  - 保留 LLM 参数是为了向后兼容旧代码

核心逻辑：
  - PM 的决策通过 structured output 生成，保证包含 "**Rating**: X" 标签
  - 使用 rating.py 中的确定性启发式解析器，无需额外 LLM 调用
  - 零 token 消耗，毫秒级响应
"""

from __future__ import annotations

from typing import Any

from tradingagents.agents.utils.rating import parse_rating


class SignalProcessor:
    """从 Portfolio Manager 决策中读取 5 级评级。

    核心能力：
      - 接收 PM 生成的 markdown 格式决策文本
      - 提取标准化评级（Buy/Overweight/Hold/Underweight/Sell）
      - 输出可直接用于下游系统的结构化信号

    输入输出示例：
      输入："FINAL TRANSACTION PROPOSAL: **BUY**\nRating: **Buy**\n分析：..."
      输出："Buy"
    """

    def __init__(self, quick_thinking_llm: Any = None):
        """初始化信号处理器。

        Args:
            quick_thinking_llm: 轻量级 LLM 实例（向后兼容保留参数）
                - 当前版本不再使用此参数
                - PM 的结构化输出保证评级可通过正则解析
                - 保留此参数是为了不破坏旧代码的调用接口
        """
        # 保存引用以保持接口兼容性，实际不使用
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """从完整决策文本中提取标准化评级。

        调用链：
          PortfolioManager 输出 → process_signal() → parse_rating() → 评级

        Args:
            full_signal: Portfolio Manager 生成的完整决策文本（markdown 格式）

        Returns:
            标准化的 5 级评级之一：Buy / Overweight / Hold / Underweight / Sell
            如果未找到评级，返回默认值 "Hold"
        """
        # 委托给 rating.py 中的解析器
        # 该解析器实现了两阶段策略：先找明确标签，再扫描自由文本
        return parse_rating(full_signal)
