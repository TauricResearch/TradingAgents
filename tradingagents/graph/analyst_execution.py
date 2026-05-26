"""
分析师执行编排器 —— 定义分析师节点的拓扑结构和运行时追踪

在项目中的角色：
  - 为 4 类分析师（市场/情绪/新闻/基本面）定义统一的节点规格
  - 构建可配置的执行计划（支持选择哪些分析师参与分析）
  - 追踪分析师的墙钟时间（wall time），用于性能监控和调试

核心概念：
  - AnalystNodeSpec：单个分析师的完整规格（Agent节点 + 清理节点 + 工具节点 + 报告键）
  - AnalystExecutionPlan：一次运行的完整执行计划（包含选定的分析师列表和并发限制）
  - AnalystWallTimeTracker：运行时追踪器，记录每个分析师的开始/结束时间

调用链：
  trading_graph._build_graph()
    → build_analyst_execution_plan()  ← 构建计划
    → get_initial_analyst_node()      ← 获取入口节点
    → AnalystWallTimeTracker          ← 创建追踪器实例
    → sync_analyst_tracker_from_chunk() ← 流式输出时同步状态

设计决策：
  - 使用 frozen dataclass 确保规格不可变（防止运行时意外修改）
  - 将节点名称集中管理，避免硬编码散落在各处
  - 支持并发控制（concurrency_limit），未来可扩展并行执行
"""

from dataclasses import dataclass
from time import monotonic
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class AnalystNodeSpec:
    """单个分析师节点的完整规格定义。

    每个分析师在 LangGraph 图中需要 4 个组件：
    - agent_node：LLM Agent 执行分析的节点（如 "Market Analyst"）
    - clear_node：消息清理节点（在 Agent 执行前清空上下文）
    - tool_node：该分析师可用的工具集合节点（如 "tools_market"）
    - report_key：该分析师产出报告在 state 中的存储键名（如 "market_report"）

    为什么需要 clear_node？
      - LangGraph 的 state 是累积式的（messages 列表不断增长）
      - 每个 Agent 只需要看到自己的工具调用结果
      - clear_node 在 Agent 执行前截断 messages，避免 token 浪费

    frozen=True 的原因：
      - 规格是静态配置，不应该被修改
      - 可以安全地用作字典 key 或放入 set
      - 防止运行时意外修改导致图结构不一致
    """
    key: str           # 内部标识符（如 "market"、"fundamentals"）
    agent_node: str    # LangGraph 中 Agent 节点的显示名称
    clear_node: str    # 消息清理节点的显示名称
    tool_node: str     # 工具集合节点的显示名称
    report_key: str    # 该分析师报告在 AgentState 中的字段名


@dataclass(frozen=True)
class AnalystExecutionPlan:
    """一次完整分析任务的执行计划。

    包含两部分信息：
    - specs：本次要执行的分析师列表（有序，决定执行顺序）
    - concurrency_limit：并发限制（当前固定为 1，即串行执行）

    并发控制的现状与未来：
      - 当前实现：所有分析师串行执行（concurrency_limit=1）
      - 设计预留：支持未来改为并行执行（设置 concurrency_limit > 1）
      - 并行化的前提：各分析师之间无数据依赖（目前满足）

    典型用法：
        plan = build_analyst_execution_plan(["market", "news", "fundamentals"])
        # plan.specs = [market_spec, news_spec, fundamentals_spec]
        # plan.concurrency_limit = 1
    """
    specs: List[AnalystNodeSpec]   # 选定参与的分析师规格列表
    concurrency_limit: int         # 最大并发数（>=1）


# ──────────────────────────────────────────────
# 预定义的 4 类分析师节点规格
# ──────────────────────────────────────────────
# 这是系统中唯一的"分析师注册表"，新增分析师只需在此添加一行。
# 所有其他代码通过 key 查找此表获取完整的节点规格。

ANALYST_NODE_SPECS: Dict[str, AnalystNodeSpec] = {
    # 市场分析师 —— 技术面 + 价格数据分析
    # 工具：get_stock_data, get_indicators
    # 输出：state["market_report"]
    "market": AnalystNodeSpec(
        key="market",
        agent_node="Market Analyst",
        clear_node="Msg Clear Market",
        tool_node="tools_market",
        report_key="market_report",
    ),

    # 情绪分析师 —— 社交媒体 + 市场情绪分析
    # 注意：key 保持 "social" 是为了向后兼容旧配置文件，
    # 但实际标签已改名为 "Sentiment Analyst"（v0.2.5 重命名）
    # 工具：get_news（社交媒体相关新闻）
    # 输出：state["sentiment_report"]
    "social": AnalystNodeSpec(
        key="social",                     # 内部 key 不变（兼容性）
        agent_node="Sentiment Analyst",    # 显示名称更新（语义更准确）
        clear_node="Msg Clear Sentiment",
        tool_node="tools_social",
        report_key="sentiment_report",
    ),

    # 新闻分析师 —— 新闻事件 + 宏观经济影响
    # 工具：get_news, get_global_news, get_insider_transactions
    # 输出：state["news_report"]
    "news": AnalystNodeSpec(
        key="news",
        agent_node="News Analyst",
        clear_node="Msg Clear News",
        tool_node="tools_news",
        report_key="news_report",
    ),

    # 基本面分析师 —— 财务报表 + 公司估值
    # 工具：get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement
    # 输出：state["fundamentals_report"]
    "fundamentals": AnalystNodeSpec(
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        clear_node="Msg Clear Fundamentals",
        tool_node="tools_fundamentals",
        report_key="fundamentals_report",
    ),
}


def build_analyst_execution_plan(
    selected_analysts: Iterable[str],
    concurrency_limit: int = 1,
) -> AnalystExecutionPlan:
    """根据用户选择的分析师列表构建执行计划。

    Args:
        selected_analysts: 要启用的分析师 key 列表（如 ["market", "news"]）
            支持的值："market", "social", "news", "fundamentals"
            顺序决定执行顺序（先 market，再 news...）
        concurrency_limit: 并发上限，默认 1（串行执行）

    Returns:
        包含选定分析师规格和并发限制的执行计划

    Raises:
        ValueError: 如果 concurrency_limit < 1
        ValueError: 如果传入未知的 analyst key
        ValueError: 如果 selected_analysts 为空

    示例：
        >>> plan = build_analyst_execution_plan(["market", "fundamentals"])
        >>> [s.key for s in plan.specs]
        ['market', 'fundamentals']
    """
    if concurrency_limit < 1:
        raise ValueError("analyst concurrency limit must be >= 1")

    specs: List[AnalystNodeSpec] = []
    for analyst_key in selected_analysts:
        spec = ANALYST_NODE_SPECS.get(analyst_key)
        if spec is None:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        specs.append(spec)

    if not specs:
        raise ValueError("at least one analyst must be selected")

    return AnalystExecutionPlan(specs=specs, concurrency_limit=concurrency_limit)


def get_initial_analyst_node(plan: AnalystExecutionPlan) -> str:
    """获取执行计划中第一个分析师的 Agent 节点名称。

    这是图的入口点 —— graph.invoke() 后首先进入此节点。

    Args:
        plan: 已构建的执行计划

    Returns:
        第一个分析师的 agent_node 名称（如 "Market Analyst"）
    """
    return plan.specs[0].agent_node


class AnalystWallTimeTracker:
    """分析师墙钟时间追踪器。

    用于监控每个分析师的实际运行耗时（非 CPU 时间）。
    
    核心用途：
      - 性能调优：识别哪个分析师最慢（通常是与 LLM 交互的时间）
      - 成本估算：结合 LLM 定价计算每次运行的成本
      - 调试诊断：超时或异常时定位瓶颈

    时间测量方式：
      - 使用 time.monotonic()（单调时钟），不受系统时间调整影响
      - 记录的是"墙钟时间"（包括等待 LLM 响应的时间）
      - 不是 CPU 时间（不反映实际的计算开销）

    线程安全性：
      - 当前设计假设单线程使用（LangGraph 默认单线程执行）
      - 如需多线程需加锁保护 _started_at 和 _wall_times
    """

    def __init__(self, plan: AnalystExecutionPlan):
        """初始化追踪器。

        Args:
            plan: 要追踪的执行计划（用于知道有哪些分析师）
        """
        self.plan = plan
        self._started_at: Dict[str, float] = {}   # analyst_key → 开始时间戳
        self._wall_times: Dict[str, float] = {}    # analyst_key → 耗时（秒）

    def mark_started(self, analyst_key: str, started_at: Optional[float] = None) -> None:
        """标记某个分析师开始执行。

        只记录首次开始时间（忽略重复调用）。
        这是因为同一个分析师可能在流式输出中被多次"标记开始"。

        Args:
            analyst_key: 分析师的内部 key（如 "market"）
            started_at: 开始时间戳，默认使用当前 monotonic 时间
        """
        if analyst_key not in ANALYST_NODE_SPECS:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        # setdefault 保证只记录第一次（后续调用不会覆盖）
        self._started_at.setdefault(analyst_key, monotonic() if started_at is None else started_at)

    def mark_completed(
        self,
        analyst_key: str,
        completed_at: Optional[float] = None,
    ) -> None:
        """标记某个分析师执行完成。

        只记录首次完成时间（忽略重复调用）。
        必须先调用 mark_started() 否则不记录（避免无效数据）。

        Args:
            analyst_key: 分析师的内部 key
            completed_at: 完成时间戳，默认使用当前 monotonic 时间
        """
        if analyst_key not in ANALYST_NODE_SPECS:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        # 已完成则跳过（幂等操作）
        if analyst_key in self._wall_times:
            return
        started_at = self._started_at.get(analyst_key)
        if started_at is None:
            return
        finished_at = monotonic() if completed_at is None else completed_at
        # max(0.0, ...) 防止负数（理论上不会发生，但防御性编程）
        self._wall_times[analyst_key] = max(0.0, finished_at - started_at)

    def get_wall_times(self) -> Dict[str, float]:
        """获取所有已完成分析师的耗时字典。

        Returns:
            {analyst_key: duration_seconds} 字典
            未完成的分析师不在返回结果中
        """
        return dict(self._wall_times)

    def format_summary(self) -> str:
        """格式化耗时摘要用于日志输出。

        格式示例：
            "Analyst wall time: Market 12.34s | News 8.56s"
            "Analyst wall time: pending"（如果还没有完成的）

        Returns:
            人类可读的耗时摘要字符串
        """
        parts = []
        for spec in self.plan.specs:
            duration = self._wall_times.get(spec.key)
            if duration is not None:
                # 移除 "Analyst" 后缀，让标签更简洁（"Market" 而不是 "Market Analyst"）
                label = spec.agent_node.removesuffix(" Analyst")
                parts.append(f"{label} {duration:.2f}s")
        if not parts:
            return "Analyst wall time: pending"
        return "Analyst wall time: " + " | ".join(parts)


def sync_analyst_tracker_from_chunk(
    tracker: AnalystWallTimeTracker,
    chunk: Dict[str, str],
    now: Optional[float] = None,
) -> None:
    """从 LangGraph 流式输出的 chunk 更新追踪器状态。

    当使用 stream_mode="updates" 时，LangGraph 会周期性地输出 state chunks。
    此函数根据 chunk 中是否包含某分析师的报告来判断其执行状态：

    判断逻辑：
      1. 如果 chunk 中有某分析师的报告（report_key 存在且非空）
         → 该分析师已完成（标记开始+结束都在当前时刻）
      
      2. 如果没有找到任何正在执行的分析师
         → 第一个尚未完成的分析师被认为是"当前正在执行的"
         → 标记其开始时间为当前时刻

    为什么这样设计？
      - LangGraph 的 stream 输出是离散的快照，不是连续事件流
      - 我们无法精确知道"何时开始"，只能推断"大概什么时候"
      - 对于性能统计来说，这种近似已经足够准确

    Args:
        tracker: 已初始化的追踪器实例
        chunk: LangGraph 输出的 state chunk（dict）
        now: 当前时间戳，默认使用 monotonic()

    示例 chunk：
        {"market_report": "...", "sentiment_report": None}
        → market 已完成，sentiment 正在执行
    """
    current_time = monotonic() if now is None else now
    active_found = False

    for spec in tracker.plan.specs:
        # 检查该分析师的报告是否已在 chunk 中出现
        has_report = bool(chunk.get(spec.report_key))

        if has_report:
            # 报告存在 → 该分析师已完成
            # 同时标记开始和结束（因为我们不知道精确的开始时间）
            tracker.mark_started(spec.key, started_at=current_time)
            tracker.mark_completed(spec.key, completed_at=current_time)
            continue

        # 还没找到"正在执行"的分析师 → 认为第一个没报告的就是当前活跃的
        if not active_found:
            tracker.mark_started(spec.key, started_at=current_time)
            active_found = True
