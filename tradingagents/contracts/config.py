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
    max_same_direction_positions: int = Field(
        default=2, ge=1,
        description="Concentration limit: at most this many concurrent open "
        "positions on the same side (BUY/SELL), so correlated entries can't "
        "stack the whole book onto one directional thesis.",
    )
    max_orders_per_day: int = Field(
        default=24, ge=1,
        description="Cap on new entries per UTC day, enforced in every mode "
        "(paper included) — live arming adds its own stricter cap.",
    )
    circuit_breaker_consecutive_losses: int = Field(
        default=3, ge=1, description="Halt new entries after this many consecutive losses."
    )


class LiveRiskLimits(ContractModel):
    """Additional hard limits that apply when real capital is armed
    (go-live Phase 3). Deterministic gates only — no override path exists.

    Contract defaults are deliberately conservative; the Phase-4
    ``live.yaml`` loader additionally requires every one of these to be
    written out explicitly by a human (no silent defaults in production).
    """

    live_max_account_allocation_pct: float = Field(
        default=5.0, gt=0, le=100,
        description="Ceiling on TOTAL notional across open positions as a "
                    "percentage of venue-reported equity.")
    max_notional_per_trade: float = Field(
        default=1_000.0, gt=0,
        description="Absolute notional cap (quote currency) per entry.")
    max_orders_per_hour: int = Field(default=6, ge=1)
    max_orders_per_day: int = Field(default=24, ge=1)
    daily_loss_limit_pct: float = Field(default=2.0, gt=0, le=100)
    weekly_loss_limit_pct: float = Field(default=5.0, gt=0, le=100)
    max_drawdown_from_hwm_pct: float = Field(default=10.0, gt=0, le=100)
    venue_error_cooldown_seconds: float = Field(default=300.0, ge=0)
    venue_error_burst_threshold: int = Field(
        default=3, ge=1,
        description="Venue errors within the cooldown window that trigger "
                    "an entry cooldown.")
    max_spread_bps: float = Field(
        default=25.0, gt=0,
        description="Reject entries when the quoted bid/ask spread exceeds "
                    "this (execution would start underwater).")
    market_order_notional_cap: float = Field(
        default=500.0, gt=0,
        description="Above this notional, market orders are converted to "
                    "limit orders with max_cross_bps tolerance.")
    max_cross_bps: float = Field(default=10.0, gt=0)
    max_leverage: float = Field(default=1.0, ge=1)
    i_understand_leverage_multiplies_losses: bool = Field(
        default=False,
        description="Must be explicitly true to set max_leverage above 1.")

    @model_validator(mode="after")
    def _leverage_needs_explicit_acknowledgement(self):
        if (self.max_leverage > 1
                and not self.i_understand_leverage_multiplies_losses):
            raise ValueError(
                "max_leverage > 1 requires "
                "i_understand_leverage_multiplies_losses=true — leverage "
                "multiplies losses as well as gains"
            )
        return self


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
    event_block_hours: float = Field(
        default=4.0, ge=0, le=48,
        description=(
            "No NEW entries within this many hours before a major scheduled "
            "release (FOMC/CPI/NFP...). 0 disables the event gate. Exits are "
            "never blocked."
        ),
    )

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
