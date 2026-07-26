"""Immutable Phase 3 China public-fund domain records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from tradingagents.domain import EvidenceField


class VehicleType(StrEnum):
    OPEN_END = "open_end"
    ETF_FEEDER = "etf_feeder"
    INDEX_FEEDER = "index_feeder"
    LOF = "lof"
    OTHER = "other"


class StrategyType(StrEnum):
    ACTIVE_EQUITY = "active_equity"
    ACTIVE_MIXED = "active_mixed"
    INDEX = "index"
    BOND = "bond"
    MONEY = "money"
    FOF = "fof"
    OTHER = "other"


class MarketScope(StrEnum):
    MAINLAND = "mainland"
    HONG_KONG = "hong_kong"
    GLOBAL = "global"
    QDII = "qdii"


class ShareClass(StrEnum):
    A = "A"
    C = "C"
    OTHER = "other"


class FundAction(StrEnum):
    SUBSCRIBE = "subscribe"
    HOLD = "hold"
    REDEEM_PARTIAL = "redeem_partial"
    REDEEM_ALL = "redeem_all"
    CONVERT = "convert"


@dataclass(frozen=True)
class ChinaFundIdentity:
    code: str
    display_name: str
    share_class: ShareClass
    vehicle_type: VehicleType
    strategy_type: StrategyType
    market_scope: MarketScope
    parent_product_id: str | None = None
    currency: str = "CNY"
    status: str = "active"
    manager_name: str | None = None
    fund_company: str | None = None
    tags: tuple[str, ...] = ()
    evidence: tuple[EvidenceField, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_qdii(self) -> bool:
        return self.market_scope == MarketScope.QDII

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NavPoint:
    date: str
    nav: str
    accumulated_nav: str | None = None


@dataclass(frozen=True)
class TransactionStatus:
    subscription: str
    redemption: str
    observed_at: str
    subscription_limit: str | None = None


@dataclass(frozen=True)
class FeeRule:
    action: str
    condition: str
    rate: str
    source_note: str = "approximate"


@dataclass(frozen=True)
class Holding:
    code: str | None
    name: str
    weight: str | None
    disclosure_date: str | None


@dataclass(frozen=True)
class Benchmark:
    disclosed_text: str | None
    components: tuple[dict[str, str], ...] = ()
    selected_code: str | None = None
    selected_name: str | None = None
    user_override: str | None = None


@dataclass(frozen=True)
class ChinaFundSnapshot:
    identity: ChinaFundIdentity
    analysis_date: str
    retrieved_at: str
    nav_history: tuple[NavPoint, ...] = ()
    transaction_status: TransactionStatus | None = None
    fees: tuple[FeeRule, ...] = ()
    manager: dict[str, Any] = field(default_factory=dict)
    holdings: tuple[Holding, ...] = ()
    sector_allocation: dict[str, str] = field(default_factory=dict)
    asset_allocation: dict[str, str] = field(default_factory=dict)
    benchmark: Benchmark | None = None
    qdii_context: dict[str, Any] = field(default_factory=dict)
    metrics: tuple[dict[str, Any], ...] = ()
    evidence: tuple[EvidenceField, ...] = ()
    warnings: tuple[str, ...] = ()
    capability_status: dict[str, str] = field(default_factory=dict)
    trust: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FundEvaluation:
    code: str
    action: FundAction
    allowed_actions: tuple[FundAction, ...]
    blocked_actions: dict[str, tuple[str, ...]]
    executable: bool
    confidence: str
    reason: str
    amount: str | None = None
    unit_fraction: str | None = None
    sales_platform: str | None = None
    conversion_supported: bool = False
    target_code: str | None = None
    expected_horizon: str = "medium_term"
    supporting_evidence: tuple[str, ...] = ()
    opposing_evidence: tuple[str, ...] = ()
    friction: tuple[dict[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
