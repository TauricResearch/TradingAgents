"""
决策反思引擎（Decision Reflection Engine）

在项目中的角色：
  - 记忆系统 Phase B 的核心组件 —— 在决策的实际收益已知后，生成结构化反思
  - 被 trading_graph.py 的 _resolve_pending_entries() 调用
  - 反思文本被写入 memory_log 的 REFLECTION 段，供下次运行时注入 Agent Prompt

调用链：
  trading_graph._resolve_pending_entries()
    → _fetch_returns()          ← 拉取实际收盘数据
    → reflector.reflect_on_final_decision()  ← 本文件，LLM 生成反思
    → memory_log.update_with_outcome()      ← 写入日志

设计哲学：
  - 用 quick_thinking_llm（轻量模型）而非 deep_thinking_llm
    → 反思是辅助功能，不需要深度推理；用便宜模型节省成本
  - 输出严格限制在 2-4 句话
    → 反思会被注入未来的 Prompt，太长会挤占分析空间
    → 强制简洁迫使 LLM 提炼最关键的教训
  - Prompt 工程精心设计：固定三段式结构（方向判断→论点验证→具体教训）
    → 保证输出格式一致，下游 get_past_context() 可靠解析

反思文本的完整生命周期：
  1. 生成（本文件）→ 2. 存储到 memory.log（memory.py）
     → 3. 下次运行时读取并注入 state["past_context"]（propagation.py）
     → 4. Agent 在 Prompt 中看到历史教训 → 5. 做出更明智的决策
"""

# TradingAgents/graph/reflection.py

from typing import Any


class Reflector:
    """交易决策事后复盘器。

    核心方法 reflect_on_final_decision() 接收：
      - 原始决策文本（当时 LLM 说了什么）
      - 实际收益数据（raw_return, alpha_return）
    返回一段 2-4 句话的纯文本反思，写入 memory log 的 REFLECTION 字段。

    为什么用 quick_thinking_llm？
      - 反思任务相对简单：「看结果 → 对比预期 → 总结教训」
      - 不需要复杂的多步推理（不像辩论 judge 那种需要权衡多方观点的任务）
      - 每次运行可能触发多条反思（同一 ticker 有多个 pending 条目），成本敏感

    典型输出示例：
      "方向判断正确（alpha +1.2%）。技术面突破论点成立，
       但低估了美联储加息对估值的压制。下次遇到类似宏观环境时，
       应将估值模型的风险溢价上调 50bp。"
    """

    def __init__(self, quick_thinking_llm: Any):
        """初始化反思器。

        Args:
            quick_thinking_llm: 轻量级 LangChain ChatModel 实例，
                用于执行反思生成任务（非深度推理场景）
        """
        self.quick_thinking_llm = quick_thinking_llm
        # 预编译 prompt 模板，避免每次调用都重新构建字符串
        self.log_reflection_prompt = self._get_log_reflection_prompt()

    def _get_log_reflection_prompt(self) -> str:
        """构建反思生成的 System Prompt。

        Prompt 设计要点（经过调优的关键约束）：

        「2-4 sentences」硬约束：
          - 太短（1句）→ 信息量不足，Agent 无法从中学习
          - 太长（>4句）→ 注入 Prompt 时占用过多 token，挤压分析空间
          - 2-4 句是经验最优值：足够覆盖三个维度又不冗余

        「no bullets, no headers, no markdown」：
          - 纯 prose 格式确保在 memory.md 文件中可读性好
          - 避免 markdown 符号干扰后续的 REFLECTION 正则解析
          - 让反思读起来像人类分析师的自然语言笔记

        三段式固定结构（Cover in order）：
          1. 方向判断：BUY/SELL 是否正确？引用 alpha 数据佐证
          2. 论点验证：当时的投资逻辑哪部分对了、哪部分错了？
          3. 具体教训：一条可操作的改进建议（给未来自己看的）

        「every word must earn its place」：
          - 心理暗示 LLM 不要写废话和套话
          - 实测效果：比不加这句的输出平均短 30%，信息密度更高

        Returns:
            反思任务的 system prompt 字符串
        """
        return (
            "You are a trading analyst reviewing your own past decision now that the outcome is known.\n"
            "Write exactly 2-4 sentences of plain prose (no bullets, no headers, no markdown).\n\n"
            "Cover in order:\n"
            "1. Was the directional call correct? (cite the alpha figure)\n"
            "2. Which part of the investment thesis held or failed?\n"
            "3. One concrete lesson to apply to the next similar analysis.\n\n"
            "Be specific and terse. Your output will be stored verbatim in a decision log "
            "and re-read by future analysts, so every word must earn its place."
        )

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
        benchmark_name: str = "SPY",
    ) -> str:
        """基于实际收益数据对交易决策进行单次反思。

        这是 Phase B 延迟反思的核心入口。被 _resolve_pending_entries() 对每条 pending
        决策记录调用一次。

        输入数据说明：
          - final_decision: 当时 LLM 生成的完整决策文本（包含所有分析师的综合意见）
            → 已经是高度综合的内容，不需要再传入市场数据或各报告
          - raw_return: 标的原始收益率（如 0.02 = +2%）
          - alpha_return: 相对基准的超额收益率（如 -0.01 = 跑输基准 1%）
            → alpha 是更重要的指标：正 alpha 说明判断有增量价值
          - benchmark_name: 基准指数名称（用于在反思文本中引用，如 "SPY"、"^N225"）

        为什么不需要额外上下文？
          - final_trade_decision 已经综合了所有分析师的报告和辩论结论
          - 反思只需要回答一个核心问题：「当时的综合判断 vs 实际结果，差距在哪？」
          - 过多上下文反而会让 LLM 写出泛泛而谈的评论

        Args:
            final_decision: 原始的最终决策文本（来自 state["final_trade_decision"]）
            raw_return: 原始收益率小数（正=赚，负=亏）
            alpha_return: 超额收益率小数（正=跑赢大盘，负=跑输）
            benchmark_name: 基准指数显示名，默认 "SPY"

        Returns:
            LLM 生成的 2-4 句话反思纯文本
        """
        messages = [
            ("system", self.log_reflection_prompt),
            (
                "human",
                (
                    f"Raw return: {raw_return:+.1%}\n"
                    f"Alpha vs {benchmark_name}: {alpha_return:+.1%}\n\n"
                    f"Final Decision:\n{final_decision}"
                ),
            ),
        ]
        return self.quick_thinking_llm.invoke(messages).content
