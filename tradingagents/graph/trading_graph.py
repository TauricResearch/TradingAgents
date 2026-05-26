"""
交易图编排器（Trading Graph Orchestrator）

在项目中的角色：
  - 整个 TradingAgents 系统的「总指挥」—— 负责组装、编译、执行 LangGraph 工作流
  - 是唯一对外暴露的高层 API 入口：propagate(company_name, trade_date)
  - 连接了系统中所有子系统：LLM 客户端、工具节点、状态管理、记忆日志、检查点恢复

架构层次：
  ┌─────────────────────────────────────────────┐
  │  CLI / 用户代码                               │
  │    ↓ 调用 propagate()                        │
  ├─────────────────────────────────────────────┤
  │  TradingAgentsGraph（本文件）                 │
  │    ├── 初始化 LLM（deep / quick 两套模型）     │
  │    ├── 创建 ToolNode（market/social/news/..） │
  │    ├── 委托 GraphSetup 构建 LangGraph 有向图   │
  │    ├── 编译 graph（可选 checkpointer 持久化）   │
  │    └── 执行 → 日志记录 → 反思存储              │
  ├─────────────────────────────────────────────┤
  │  子系统（组合模式）                            │
  │    ├── GraphSetup     → 图结构定义（节点+边）    │
  │    ├── ConditionalLogic → 条件路由（辩论轮次控制）│
  │    ├── Propagator      → 初始状态构建           │
  │    ├── Reflector       → 决策反思（事后复盘）     │
  │    ├── SignalProcessor → 信号提取（BUY/HOLD/SELL）│
  │    └── TradingMemoryLog → 跨轮次记忆            │
  └─────────────────────────────────────────────┘

数据流：
  输入: company_name + trade_date + asset_type
    → _resolve_pending_entries() [处理上次未完成的决策]
    → _run_graph() [执行完整工作流]
       → create_initial_state() [注入历史记忆上下文]
       → graph.invoke(stream) [LangGraph 驱动所有节点]
       → _log_state() [持久化到 JSON]
       → memory_log.store_decision() [存入待反思队列]
    → process_signal() [提取最终交易信号]
  输出: (final_state, signal)
"""

# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """交易 Agent 系统的主编排器 —— 组装并驱动整个 LangGraph 工作流。

    生命周期：
        1. __init__() → 创建 LLM、工具节点、子组件，编译 LangGraph workflow
        2. propagate()  → 对外主入口：接收公司+日期，执行完整决策流水线
        3. 内部调用链：resolve_pending → run_graph → log_state → store_decision

    双模型策略：
        - deep_thinking_llm: 用于需要深度推理的场景（辩论 judge、最终决策）
        - quick_thinking_llm: 用于轻量任务（初步分析、信号提取）
        通过 config 的 deep_think_llm / quick_think_llm 字段分别配置

    容错机制：
        - checkpointer: 启用后可在崩溃时从最后成功的节点恢复
        - _resolve_pending_entries: 每次运行前先处理上次未完成的决策（计算收益+反思）
    """

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """初始化交易图的所有组件。

        Args:
            selected_analysts: 要启用的分析师类型列表，控制哪些分析节点被加入图。
                默认4路全开（market/social/news/fundamentals），可裁剪以节省 token。
            debug: 调试模式。开启后用 graph.stream() 逐节点输出消息，
                关闭时用 graph.invoke() 一次性返回最终状态。
            config: 配置字典。为 None 时使用 DEFAULT_CONFIG。
            callbacks: LangChain 回调处理器列表（用于追踪 LLM 调用/工具统计等）。
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # 将配置写入全局单例，供下层工具函数读取
        set_config(self.config)

        # 确保缓存和结果目录存在
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # 根据不同的 LLM provider 注入特定的推理参数
        # 例如 Google 需要 thinking_level，OpenAI 需要 reasoning_effort
        llm_kwargs = self._get_provider_kwargs()

        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        # 创建两套 LLM 客户端：深度推理 + 快速推理
        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()

        # 记忆日志系统：跨轮次存储决策和反思，避免重复犯错
        self.memory_log = TradingMemoryLog(self.config)

        # 按数据源分组创建 ToolNode —— 每个 ToolNode 是一个 LangGraph 节点，
        # 负责执行对应类别的工具调用（如 get_stock_data, get_fundamentals 等）
        self.tool_nodes = self._create_tool_nodes()

        # 初始化各子系统组件（组合模式）
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # 运行时状态跟踪
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date -> full state dict

        # 构建并编译 LangGraph 有向图（节点+边的拓扑结构在 GraphSetup 中定义）
        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """根据 LLM provider 类型返回特定的推理参数。

        不同厂商的「深度推理」模式参数名不同：
          - Google  → thinking_level
          - OpenAI  → reasoning_effort
          - Anthropic → effort

        Returns:
            包含 provider 特定参数的字典，无匹配时返回空字典
        """
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """按数据源类别创建 LangGraph ToolNode 分组。

        每个 ToolNode 封装了一组同类的数据获取工具（都是 @tool 装饰的函数）。
        当 LLM 在分析师节点中发起 tool_call 时，LangGraph 会根据工具名称路由到
        对应的 ToolNode 执行。

        分组设计的原因：
          - 不同分析师节点需要不同的工具集（基本面分析师不需要 get_news）
          - 权限和速率限制可以按组管理
          - 图的边可以按组连接，结构更清晰

        Returns:
            字典 key 为类别名，value 为封装了对应工具列表的 ToolNode 实例
        """
        return {
            "market": ToolNode(
                [
                    # 股票数据工具
                    get_stock_data,
                    # 技术指标工具
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # 社交媒体新闻工具
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # 新闻工具和内部交易信息工具
                    get_news,
                    # 全球新闻工具
                    get_global_news,
                    # 内部交易新闻工具
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # 基本面分析工具
                    get_fundamentals,
                    # 资产负债表工具
                    get_balance_sheet,
                    # 现金流量表工具
                    get_cashflow,
                    # 利润表表工具
                    get_income_statement,
                ]
            ),
        }

    def _resolve_benchmark(self, ticker: str) -> str:
        """为给定标的解析用于 Alpha 计算的基准指数 ticker。

        解析优先级：
          1. config 中显式设置的 benchmark_ticker（最高优先级，覆盖一切）
          2. 根据 ticker 的交易所后缀匹配 benchmark_map（如 .T → 东证指数）
          3. 兜底：无后缀或无法识别时返回 SPY（美股默认基准）

        为什么需要这个？
          - 原始收益率（raw return）不区分市场涨跌 —— 大盘涨 5%，个股涨 3% 其实是跑输
          - Alpha = raw_return - benchmark_return，衡量「超额收益」
          - 不同市场的股票需要用对应市场的基准（日本 → TOPIX，美国 → S&P500）

        Args:
            ticker: 股票/加密货币代码（如 "AAPL", "7203.T"）

        Returns:
            基准指数的 ticker 字符串
        """
        explicit = self.config.get("benchmark_ticker")
        if explicit:
            return explicit
        benchmark_map = self.config.get("benchmark_map", {})
        ticker_upper = ticker.upper()
        for suffix, benchmark in benchmark_map.items():
            if suffix and ticker_upper.endswith(suffix.upper()):
                return benchmark
        return benchmark_map.get("", "SPY")

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5,
        benchmark: str = "SPY",
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """获取标的在 trade_date 之后 holding_days 天的实际收益率。

        通过 yfinance 拉取历史价格数据，计算：
          - raw_return: 标的的原始收益率
          - alpha_return: 相对基准的超额收益率（raw - benchmark）
          - actual_holding_days: 实际计算用的天数（可能因周末/假期 < holding_days）

        Args:
            ticker: 标的代码
            trade_date: 交易决策日期（YYYY-MM-DD 格式）
            holding_days: 持仓天数，默认5天
            benchmark: 基准指数代码

        Returns:
            (raw_return, alpha_return, actual_days) 三元组，
            数据不可用时返回 (None, None, None)
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            # 多取7天缓冲区，覆盖周末和节假日
            end = start + timedelta(days=holding_days + 7)
            end_str = end.strftime("%Y-%m-%d")

            stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
            bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

            if len(stock) < 2 or len(bench) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
            raw = float(
                (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
                / stock["Close"].iloc[0]
            )
            bench_ret = float(
                (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
                / bench["Close"].iloc[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
                ticker, trade_date, benchmark, e,
            )
            return None, None, None

    def _resolve_pending_entries(self, ticker: str) -> None:
        """处理同一 ticker 上次运行遗留的未完成决策条目。

        这是系统「反思闭环」的核心入口。每次 propagate() 执行前先调用此方法：

        工作流程：
          1. 从 memory_log 中取出该 ticker 所有 pending 状态的决策记录
          2. 对每条记录调用 _fetch_returns() 拉取实际收盘数据
          3. 用 Reflector 生成决策反思（"当时说 BUY 结果跌了 3%，原因是什么"）
          4. 批量写入 memory_log（原子操作，避免部分写入）

        设计权衡：
          - 只处理同 ticker 的 pending 条目 —— 不同 ticker 的条目留到该 ticker 下次运行时处理
          - 价格数据不可用的条目跳过不删除 —— 下次运行再重试

        Args:
            ticker: 要处理的标的代码
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        benchmark = self._resolve_benchmark(ticker)
        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(
                ticker, entry["date"], benchmark=benchmark,
            )
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date, asset_type: str = "stock"):
        """对外主入口 —— 对指定公司在指定日期执行完整交易决策流水线。

        这是整个系统唯一的「一键运行」方法。调用方（CLI / 回测引擎 / API）只需传入
        公司名+日期，内部自动完成：反思处理 → 图执行 → 日志记录 → 信号提取。

        完整调用链：
            propagate()
              → _resolve_pending_entries()   # 处理上次遗留的待反思决策
              → [可选] 重新编译图 + 注入 checkpointer（崩溃恢复支持）
              → _run_graph()                 # 执行 LangGraph 工作流
                → create_initial_state()     # 构建初始状态（注入历史记忆）
                → graph.invoke/stream()      # 驱动所有节点运行
                → _log_state()               # 持久化最终状态到 JSON
                → store_decision()           # 存入 memory_log 等待下次反思
              → process_signal()             # 从最终决策文本中提取 BUY/HOLD/SELL

        Args:
            company_name: 目标公司 ticker 或名称（如 "AAPL"）
            trade_date: 交易日期字符串（YYYY-MM-DD 格式）
            asset_type: 资产类型，"stock"（默认）或 "crypto"

        Returns:
            (final_state, signal) 元组：
              - final_state: LangGraph 最终状态字典（包含所有报告和决策）
              - signal: 提取后的核心交易信号字符串
        """
        self.ticker = company_name

        # 先处理该 ticker 上次运行遗留的 pending 决策（计算收益 + 反思）
        self._resolve_pending_entries(company_name)

        # 如果用户启用了检查点功能，用 SqliteSaver 重新编译 graph
        # 这样崩溃后再次调用同一 ticker+date 可以从断点恢复
        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s", step, company_name, trade_date
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            return self._run_graph(company_name, trade_date, asset_type=asset_type)
        finally:
            # 无论成功还是异常，都要清理 checkpointer 上下文管理器
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                # 恢复无 checkpointer 的编译版本，避免影响后续调用
                self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock"):
        """执行 LangGraph 工作流并处理结果持久化。

        核心步骤：
          1. 从 memory_log 获取历史上下文（past_context），注入初始状态
             → 这让 Agent 能看到「这个股票之前怎么判的、结果如何」
          2. 构建 LangGraph 调用参数（含 thread_id 用于 checkpointer 恢复）
          3. 执行图：debug 模式用 stream（逐节点输出），正常模式用 invoke（一次性返回）
          4. 记录最终状态到磁盘 JSON 文件
          5. 将本次决策存入 memory_log 的 pending 队列（等下次同 ticker 运行时反思）
          6. 成功后清除检查点文件（避免残留脏数据）

        Args:
            company_name: 目标公司标识
            trade_date: 交易日期
            asset_type: 资产类型

        Returns:
            (final_state, processed_signal) 元组
        """
        # 从记忆日志获取历史上下文，注入到 state["past_context"]
        # 下游的 PM（Portfolio Manager）节点会读取此字段做参考
        past_context = self.memory_log.get_past_context(company_name)
        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, asset_type=asset_type, past_context=past_context
        )
        args = self.propagator.get_graph_args()

        # 注入 thread_id：同一 ticker+date 复用同一会话，不同 date 开新会话
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if self.debug:
            # debug 模式：逐节点流式输出，可实时观察每个节点的消息
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            # 将 per-node delta 合并为完整 final_state，与 invoke 路径的输出格式一致
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            # 正常模式：一次性 invoke，只返回最终状态
            final_state = self.graph.invoke(init_agent_state, **args)

        # 缓存当前状态，供外部访问和反思使用
        self.curr_state = final_state

        # 持久化到磁盘 JSON 文件
        self._log_state(trade_date, final_state)

        # 存入 memory_log 的 pending 队列 —— 不立即反思，
        # 等下次同 ticker 运行时有了实际收盘数据再做
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        # 成功完成后清除检查点标记，避免残留导致下次误恢复
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """将最终状态持久化到磁盘 JSON 文件。

        文件路径结构：
            {results_dir}/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json

        选取写入的字段是「决策关键路径」上的字段，过滤了中间过程数据（如 messages）。
        每个日期一个文件，同一 ticker 的多次运行按日期追加到 log_states_dict（内存索引）。

        安全措施：
          - safe_ticker_component() 清理 ticker 中的特殊字符，防止路径遍历攻击
          - 目录不存在时自动创建

        Args:
            trade_date: 交易日期
            final_state: LangGraph 执行完毕后的最终完整状态字典
        """
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # 防止 ticker 含特殊字符导致路径逃逸（如 "../" 路径遍历攻击）
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def process_signal(self, full_signal):
        """从 LLM 生成的最终决策文本中提取标准化的交易信号。

        LLM 输出的决策文本可能包含各种格式（"FINAL TRANSACTION PROPOSAL: **BUY**"、
        "建议买入"、"I recommend BUY" 等），此方法委托 SignalProcessor 将其统一为
        标准化的信号格式。

        Args:
            full_signal: LLM 输出的原始决策文本

        Returns:
            标准化后的交易信号字符串
        """
        return self.signal_processor.process_signal(full_signal)
