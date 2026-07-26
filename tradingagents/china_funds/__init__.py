"""China public-fund identity, provider, trust, and action services."""

from .actions import evaluate_actions
from .cache import CachedChinaFundProvider
from .catalog import ACCEPTANCE_CATALOG, search_catalog
from .domain import (
    ChinaFundIdentity,
    ChinaFundSnapshot,
    FundAction,
    FundEvaluation,
    MarketScope,
    ShareClass,
    StrategyType,
    VehicleType,
)
from .eastmoney import EastmoneyFundProvider
from .service import AmbiguousFundError, ChinaFundService, FundNotFoundError, default_registry
from .synthetic import SyntheticChinaFundProvider

__all__ = [
    "ACCEPTANCE_CATALOG",
    "AmbiguousFundError",
    "CachedChinaFundProvider",
    "ChinaFundIdentity",
    "ChinaFundService",
    "ChinaFundSnapshot",
    "EastmoneyFundProvider",
    "FundAction",
    "FundEvaluation",
    "FundNotFoundError",
    "MarketScope",
    "ShareClass",
    "StrategyType",
    "SyntheticChinaFundProvider",
    "VehicleType",
    "evaluate_actions",
    "default_registry",
    "search_catalog",
]
