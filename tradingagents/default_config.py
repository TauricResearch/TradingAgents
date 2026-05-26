"""
全局默认配置 —— 系统所有可调参数的单一真实来源（Single Source of Truth）

在项目中的角色：
  - 定义所有模块的默认配置值
  - 支持环境变量覆盖（无需修改代码即可调整参数）
  - 支持运行时动态覆盖（set_config()）

设计原则：
  - 集中式管理：所有配置在此文件，避免散落在各处
  - 环境变量优先：TRADINGAGENTS_* 环境变量可覆盖任何配置项
  - 类型安全：自动根据默认值类型转换环境变量值

配置层级优先级（从低到高）：
  1. DEFAULT_CONFIG（本文件的硬编码默认值）
  2. .env 文件或 shell 环境变量（TRADINGAGENTS_*）
  3. set_config() 运行时覆盖（程序化设置）

使用方式：

  方式 1：直接导入使用
    from tradingagents.default_config import DEFAULT_CONFIG
    llm_model = DEFAULT_CONFIG["deep_think_llm"]

  方式 2：通过 config.py 接口（推荐）
    from tradingagents.dataflows.config import get_config, set_config
    config = get_config()
    set_config({"max_debate_rounds": 3})

  方式 3：环境变量覆盖
    export TRADINGAGENTS_MAX_DEBATE_ROUNDS=3
    # 或在 .env 文件中：TRADINGAGENTS_MAX_DEBATE_ROUNDS=3

目录结构约定：
  ~/.tradingagents/
  ├── logs/           # 运行结果日志
  ├── cache/          # 数据缓存
  └── memory/         # 记忆日志（trading_memory.md）
"""

import os

# 用户主目录下的项目根目录
_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# ──────────────────────────────────────────────
# 环境变量 → 配置键 映射表
# ──────────────────────────────────────────────
# 要新增一个可通过环境变量覆盖的配置项，只需在此添加一行映射。
# 无需修改入口脚本或其他代码。

# 格式：{环境变量名: 配置字典键名}
_ENV_OVERRIDES = {
    # LLM 相关
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",         # LLM 提供商（openai/anthropic/google）
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",       # 深度思考模型名称
    "TRADINGAGENTS_QUICK_THINK_LLM":      "quick_think_llm",      # 快速思考模型名称
    "TRADINGAGENTS_LLM_BACKEND_URL":      "backend_url",          # LLM API 自定义端点
    "TRADINGAGENTS_OUTPUT_LANGUAGE":      "output_language",      # 输出语言（English/Chinese）

    # 辩论和讨论控制
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",    # 投资辩论最大轮次
    "TRADINGAGENTS_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",  # 风险讨论最大轮次

    # 功能开关
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",   # 是否启用检查点（崩溃恢复）

    # 基准指数
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",     # 全局基准指数（覆盖自动检测）
}


def _coerce(value: str, reference):
    """将环境变量字符串转换为与默认值匹配的类型。

    类型推断逻辑：
      - 如果默认值是 bool → 解析为布尔值（支持 true/false/yes/no/1/0）
      - 如果默认值是 int → 转换为整数
      - 如果默认值是 float → 转换为浮点数
      - 其他情况 → 保持字符串

    为什么需要类型强制？
      - 环境变量永远是字符串类型
      - 但配置值可能是 int、bool、float 等
      - 需要根据默认值的类型进行智能转换

    Args:
        value: 环境变量的原始字符串值
        reference: 配置项的默认值（用于推断目标类型）

    Returns:
        转换后的正确类型值
    """
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """将 TRADINGAGENTS_* 环境变量应用到配置字典。

    遍历 _ENV_OVERRIDES 映射表，对每个已设置的环境变量：
      1. 从 os.environ 读取原始值
      2. 使用 _coerce() 转换为正确的类型
      3. 覆盖 config 中对应的键

    Args:
        config: 待修改的配置字典（原地修改）

    Returns:
        修改后的同一个配置字典（方便链式调用）
    """
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    # ──────────────────────────────────────────
    # 目录路径配置
    # ──────────────────────────────────────────
    
    # 项目根目录（当前文件所在目录）
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    
    # 运行结果输出目录
    # 默认：~/.tradingagents/logs/
    # 可通过环境变量 TRADINGAGENTS_RESULTS_DIR 覆盖
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    
    # 数据缓存目录（API 响应缓存，避免重复请求）
    # 默认：~/.tradingagents/cache/
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    
    # 记忆日志路径（存储历史决策和反思）
    # 默认：~/.tradingagents/memory/trading_memory.md
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    
    # 记忆日志条目上限（None = 不限制）
    # 设置后，超过限制时自动删除最旧的已解决条目（pending 条目不受影响）
    "memory_log_max_entries": None,

    # ──────────────────────────────────────────
    # LLM 配置
    # ──────────────────────────────────────────
    
    # LLM 提供商标识符
    # 可选值："openai" | "anthropic" | "google" | "openai_compatible"
    "llm_provider": "openai",
    
    # 深度思考模型 —— 用于复杂推理任务
    # 适用场景：辩论裁判、最终交易决策、复杂分析
    # 当前默认：gpt-5.4（可根据需求更换）
    "deep_think_llm": "gpt-5.4",
    
    # 快速思考模型 —— 用于简单任务
    # 适用场景：决策反思、格式化、轻量级分析
    # 选择更便宜的模型以节省成本
    "quick_think_llm": "gpt-5.4-mini",
    
    # LLM API 自定义端点 URL
    # None 表示使用各提供商的默认端点：
    #   OpenAI: api.openai.com
    #   Anthropic: api.anthropic.com
    #   Google: generativelanguage.googleapis.com
    # 
    # 使用场景：代理服务器、私有部署、兼容接口
    "backend_url": None,
    
    # 各提供商特定的"思考"模式配置
    # 不同提供商对"深度推理"的实现不同，这里统一抽象
    
    # Google Gemini 的 thinking level
    # 可选值：None（禁用）| "high" | "minimal"
    "google_thinking_level": None,
    
    # OpenAI 的 reasoning effort
    # 可选值：None（禁用）| "low" | "medium" | "high"
    "openai_reasoning_effort": None,
    
    # Anthropic 的 extended thinking effort
    # 可选值：None（禁用）| "low" | "medium" | "high"
    "anthropic_effort": None,

    # ──────────────────────────────────────────
    # 检查点和崩溃恢复
    # ──────────────────────────────────────────
    
    # 是否启用 LangGraph 检查点机制
    # True：每个节点执行后保存状态，崩溃时可从断点恢复
    # False：不保存状态，内存占用更低但无法恢复
    "checkpoint_enabled": False,

    # ──────────────────────────────────────────
    # 输出语言配置
    # ──────────────────────────────────────────
    
    # 分析师报告和最终决策的输出语言
    # 注意：Agent 内部辩论始终使用英文（保证推理质量）
    # 只有面向用户的输出才受此配置影响
    "output_language": "English",

    # ──────────────────────────────────────────
    # 辩论和讨论控制
    # ──────────────────────────────────────────
    
    # 投资辩论（Investment Debate）最大轮次
    # Bull vs Bear 各发言 N 轮 = 总共 2N 轮
    # 值越大 → 分析越深入但 token 消耗越高、耗时越长
    # 推荐：1-3（生产环境），3-5（研究环境）
    "max_debate_rounds": 1,
    
    # 风险讨论（Risk Discussion）最大轮次
    # Aggressive vs Conservative vs Neutral 三方各发言 N 轮
    # 值越大 → 风险评估越全面但成本越高
    "max_risk_discuss_rounds": 1,
    
    # LangGraph 最大递归深度限制
    # 防止无限循环（如条件边总是返回同一节点）
    # 设得太小可能导致正常流程被中断
    "max_recur_limit": 100,
    
    # 分析师并发数（当前固定为 1，未来可扩展并行）
    "analyst_concurrency_limit": 1,

    # ──────────────────────────────────────────
    # 新闻和数据获取参数
    # ──────────────────────────────────────────
    
    # 单只股票的最大新闻文章数量
    # 影响：token 消耗和信息完整性的权衡
    # 增大 → 更全面的信息但更多 token
    # 减少 → 更快更便宜但可能遗漏重要信息
    "news_article_limit": 20,
    
    # 全球宏观新闻的最大文章数量
    "global_news_article_limit": 10,
    
    # 宏观新闻回溯天数
    # 决定 get_global_news 查询多长时间范围内的新闻
    "global_news_lookback_days": 7,
    
    # 全球新闻搜索关键词列表
    # 用于 get_global_news 的查询模板
    # 可自定义以扩展地理或行业覆盖范围
    # 每个关键词会生成独立的搜索请求
    "global_news_queries": [
        "Federal Reserve interest rates inflation",        # 美联储 + 利率 + 通胀
        "S&P 500 earnings GDP economic outlook",            # 标普500 + 盈利 + GDP
        "geopolitical risk trade war sanctions",            # 地缘政治 + 贸易战 + 制裁
        "ECB Bank of England BOJ central bank policy",      # 央行政策（欧/英/日）
        "oil commodities supply chain energy",              # 大宗商品 + 供应链 + 能源
    ],

    # ──────────────────────────────────────────
    # 数据供应商配置
    # ──────────────────────────────────────────
    
    # 类别级供应商配置（该类别下所有工具的默认供应商）
    # 优先级低于 tool_vendors（工具级配置会覆盖此配置）
    "data_vendors": {
        "core_stock_apis": "yfinance",       # OHLCV 数据：yfinance（免费）/ alpha_vantage
        "technical_indicators": "yfinance",  # 技术指标：yfinance（需计算）/ alpha_vantage（内置）
        "fundamental_data": "yfinance",      # 基本面数据：同上
        "news_data": "yfinance",             # 新闻数据：同上
    },
    
    # 工具级供应商配置（优先级最高，覆盖类别级配置）
    # 用法示例：让某个特定工具使用不同的供应商
    "tool_vendors": {
        # "get_stock_data": "alpha_vantage",  # 仅股票数据用 Alpha Vantage
    },

    # ──────────────────────────────────────────
    # 反思层基准指数配置
    # ──────────────────────────────────────────
    
    # 全局基准指数（可选）
    # 设置后将忽略 benchmark_map 的自动检测逻辑
    # 所有股票都与此基准比较计算 alpha
    "benchmark_ticker": None,
    
    # 基准指数自动检测映射表
    # 根据股票代码的后缀自动选择对应市场的基准指数
    # 例如：AAPL（无后缀）→ SPY；RELIANCE.NS → ^NSEI
    "benchmark_map": {
        ".NS":  "^NSEI",    # 印度国家证券交易所（Nifty 50）
        ".BO":  "^BSESN",   # 孟买证券交易所（Sensex）
        ".T":   "^N225",    # 日本东京交易所（日经 225）
        ".HK":  "^HSI",     # 香港交易所（恒生指数）
        ".L":   "^FTSE",    # 英国伦敦交易所（富时 100）
        ".TO":  "^GSPTSE",  # 加拿大多伦多交易所（TSX 综合指数）
        ".AX":  "^AXJO",    # 澳大利亚 ASX（ASX 200）
        "":     "SPY",      # 美国（无后缀，默认标普 500 ETF）
    },
})
