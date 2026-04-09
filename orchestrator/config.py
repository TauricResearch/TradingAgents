from dataclasses import dataclass, field


@dataclass
class OrchestratorConfig:
    quant_backtest_path: str = "/Users/chenshaojie/Downloads/quant_backtest"
    trading_agents_config: dict = field(default_factory=dict)
    quant_weight_cap: float = 0.8   # quant 置信度上限
    llm_weight_cap: float = 0.9     # llm 置信度上限
    llm_batch_days: int = 7         # LLM 每隔几天运行一次（节省 API）
    cache_dir: str = "orchestrator/cache"  # LLM 信号缓存目录
