"""ProConfig: typed run configuration for the Pro pipeline.

Safety posture (Constraint 5) is structural, not conventional: the default
mode is paper, and a live-mode config cannot be constructed unless live
trading is explicitly enabled AND human approval remains on. There is no
flag combination that yields unattended live execution.

``to_legacy_config()`` bridges to the existing dict-based ``DEFAULT_CONFIG``
so the original stock workflow keeps running untouched (Constraint 6)."""

from __future__ import annotations

import copy

from pydantic import Field, model_validator

from tradingagents.contracts.base import ContractModel
from tradingagents.contracts.enums import DEFAULT_SYMBOLS, AgentTeam, AssetClass, TradingMode


class RiskLimits(ContractModel):
    """Hard limits enforced by deterministic risk code; LLMs only explain them."""

    max_risk_per_trade_pct: float = Field(default=1.0, gt=0, le=5)
    max_position_pct_equity: float = Field(default=10.0, gt=0, le=100)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=100)
    max_drawdown_pct: float = Field(default=15.0, gt=0, le=100)
    max_leverage: float = Field(default=1.0, ge=1)
    max_open_positions: int = Field(default=3, ge=1)
    circuit_breaker_consecutive_losses: int = Field(
        default=3, ge=1, description="Halt new entries after this many consecutive losses."
    )


class ModelRouting(ContractModel):
    """Which LLM serves which tier/team.

    Defaults mirror the base repo's DEFAULT_CONFIG so a ProConfig with no
    overrides behaves exactly like a stock run of the original framework.
    """

    llm_provider: str = "openai"
    deep_think_llm: str = "gpt-5.5"
    quick_think_llm: str = "gpt-5.4-mini"
    team_overrides: dict[AgentTeam, str] = Field(
        default_factory=dict,
        description="Optional per-team model override, e.g. {'risk': 'gpt-5.5'}.",
    )
    require_pinned_models: bool = Field(
        default=False,
        description=(
            "Refuse floating model aliases (AI-07): every model ID must carry "
            "a date stamp (YYYY-MM-DD or YYYYMMDD suffix) so provider-side "
            "model swaps cannot silently change behavior under an eval gate. "
            "Set for paper/live deployments; leave off for dev and providers "
            "without dated aliases (accepting that risk explicitly)."
        ),
    )

    def all_model_ids(self) -> list[str]:
        return [self.quick_think_llm, self.deep_think_llm,
                *self.team_overrides.values()]

    def model_for(self, team: AgentTeam, deep: bool = False) -> str:
        return self.team_overrides.get(
            team, self.deep_think_llm if deep else self.quick_think_llm
        )


class ProConfig(ContractModel):
    asset: AssetClass
    symbol: str | None = Field(
        default=None, description="Broker-style symbol; defaults per asset (XAUUSD / BTC-USD)."
    )
    mode: TradingMode = TradingMode.PAPER
    live_trading_enabled: bool = Field(
        default=False, description="Must be explicitly set to even construct a live config."
    )
    require_human_approval: bool = Field(
        default=True, description="Human-approval graph node; cannot be disabled in live mode."
    )
    risk: RiskLimits = Field(default_factory=RiskLimits)
    models: ModelRouting = Field(default_factory=ModelRouting)
    max_debate_rounds: int = Field(default=1, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=10)

    @model_validator(mode="after")
    def _default_symbol_and_live_guard(self) -> ProConfig:
        if self.symbol is None:
            object.__setattr__(self, "symbol", DEFAULT_SYMBOLS[self.asset])
        if self.mode is TradingMode.LIVE:
            if not self.live_trading_enabled:
                raise ValueError(
                    "mode=live requires live_trading_enabled=True (live execution ships disabled)"
                )
            if not self.require_human_approval:
                raise ValueError("live mode cannot disable the human-approval node")
        return self

    def to_legacy_config(self) -> dict:
        """Merge Pro settings over the base framework's DEFAULT_CONFIG dict.

        Imported lazily so the contracts package stays importable without the
        framework's heavier dependency chain (used by tests and tooling).
        """
        from tradingagents.default_config import DEFAULT_CONFIG

        config = copy.deepcopy(DEFAULT_CONFIG)
        config.update(
            {
                "llm_provider": self.models.llm_provider,
                "deep_think_llm": self.models.deep_think_llm,
                "quick_think_llm": self.models.quick_think_llm,
                "max_debate_rounds": self.max_debate_rounds,
                "max_risk_discuss_rounds": self.max_risk_discuss_rounds,
            }
        )
        return config
