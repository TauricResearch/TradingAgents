from dataclasses import dataclass, field

from orchestrator.contracts.config_loader import normalize_orchestrator_fields


@dataclass
class OrchestratorConfig:
    # Must be set to the local quant backtest output directory before use
    quant_backtest_path: str = ""
    trading_agents_config: dict = field(default_factory=dict)
    quant_weight_cap: float = 0.8   # quant 置信度上限
    llm_weight_cap: float = 0.9     # llm 置信度上限
    llm_batch_days: int = 7         # LLM 每隔几天运行一次（节省 API）
    cache_dir: str = "orchestrator/cache"  # LLM 信号缓存目录
    llm_solo_penalty: float = 0.7   # LLM 单轨时的置信度折扣
    quant_solo_penalty: float = 0.8  # Quant 单轨时的置信度折扣

    def __post_init__(self) -> None:
        normalized = normalize_orchestrator_fields(
            {
                "quant_backtest_path": self.quant_backtest_path,
                "trading_agents_config": self.trading_agents_config,
                "quant_weight_cap": self.quant_weight_cap,
                "llm_weight_cap": self.llm_weight_cap,
                "llm_batch_days": self.llm_batch_days,
                "cache_dir": self.cache_dir,
                "llm_solo_penalty": self.llm_solo_penalty,
                "quant_solo_penalty": self.quant_solo_penalty,
            }
        )
        for key, value in normalized.items():
            setattr(self, key, value)
