"""Confirmed Phase 3 acceptance catalog and deterministic name search."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .domain import MarketScope, ShareClass, StrategyType, VehicleType


@dataclass(frozen=True)
class CatalogEntry:
    code: str
    name: str
    vehicle_type: VehicleType
    strategy_type: StrategyType
    market_scope: MarketScope
    share_class: ShareClass
    sector: str
    parent_product_id: str | None = None
    aliases: tuple[str, ...] = ()


def _entry(
    code: str,
    name: str,
    *,
    strategy: StrategyType = StrategyType.ACTIVE_MIXED,
    vehicle: VehicleType = VehicleType.OPEN_END,
    scope: MarketScope = MarketScope.MAINLAND,
    share: ShareClass = ShareClass.C,
    sector: str,
    parent: str | None = None,
    aliases: tuple[str, ...] = (),
) -> CatalogEntry:
    return CatalogEntry(code, name, vehicle, strategy, scope, share, sector, parent, aliases)


ACCEPTANCE_CATALOG: tuple[CatalogEntry, ...] = (
    _entry(
        "026539",
        "融通科技臻选混合C",
        sector="Technology / AI",
        aliases=("融通科技臻选混合发起式C",),
    ),
    _entry("017811", "东方人工智能主题混合C", sector="Technology / AI"),
    _entry("021383", "博时科技驱动混合C", sector="Technology / AI"),
    _entry("026211", "平安科技精选混合C", sector="Technology / AI"),
    _entry("016874", "广发远见智选混合C", sector="Technology / AI"),
    _entry(
        "012734",
        "易方达人工智能ETF联接C",
        vehicle=VehicleType.ETF_FEEDER,
        strategy=StrategyType.INDEX,
        sector="Technology / AI",
    ),
    _entry(
        "026790",
        "中欧上证科创板人工智能指数C",
        vehicle=VehicleType.INDEX_FEEDER,
        strategy=StrategyType.INDEX,
        sector="Technology / AI",
    ),
    _entry(
        "020483",
        "中欧中证芯片产业指数C",
        vehicle=VehicleType.INDEX_FEEDER,
        strategy=StrategyType.INDEX,
        sector="Technology / AI",
    ),
    _entry("257070", "国联安优选行业混合", share=ShareClass.OTHER, sector="Communications"),
    _entry(
        "020900",
        "天弘中证全指通信设备指数C",
        vehicle=VehicleType.INDEX_FEEDER,
        strategy=StrategyType.INDEX,
        sector="Communications",
    ),
    _entry("015790", "永赢高端装备智选混合C", sector="Manufacturing / Equipment"),
    _entry(
        "003516",
        "国泰融安多策略灵活配置混合A",
        share=ShareClass.A,
        sector="Balanced / Multi-strategy",
    ),
    _entry(
        "016453",
        "南方纳斯达克100指数(QDII)C",
        vehicle=VehicleType.INDEX_FEEDER,
        strategy=StrategyType.INDEX,
        scope=MarketScope.QDII,
        sector="US / QDII",
    ),
    _entry(
        "040046",
        "华安纳斯达克100ETF联接(QDII)A",
        vehicle=VehicleType.ETF_FEEDER,
        strategy=StrategyType.INDEX,
        scope=MarketScope.QDII,
        share=ShareClass.A,
        sector="US / QDII",
    ),
    _entry(
        "021277",
        "广发全球精选股票(QDII)C",
        strategy=StrategyType.ACTIVE_EQUITY,
        scope=MarketScope.QDII,
        sector="US / QDII",
    ),
    _entry(
        "019172",
        "摩根纳斯达克100指数(QDII)A",
        vehicle=VehicleType.INDEX_FEEDER,
        strategy=StrategyType.INDEX,
        scope=MarketScope.QDII,
        share=ShareClass.A,
        sector="US / QDII",
    ),
    _entry(
        "012920",
        "易方达全球成长精选混合(QDII)A",
        scope=MarketScope.QDII,
        share=ShareClass.A,
        sector="US / QDII",
        parent="ef-global-growth",
    ),
    _entry(
        "012922",
        "易方达全球成长精选混合(QDII)C",
        scope=MarketScope.QDII,
        sector="US / QDII",
        parent="ef-global-growth",
    ),
    _entry("018147", "建信新兴市场优选混合(QDII)C", scope=MarketScope.QDII, sector="US / QDII"),
    _entry(
        "013127",
        "汇添富恒生科技ETF联接(QDII)A",
        vehicle=VehicleType.ETF_FEEDER,
        strategy=StrategyType.INDEX,
        scope=MarketScope.QDII,
        share=ShareClass.A,
        sector="Hong Kong Technology",
    ),
)

CATALOG_BY_CODE = {item.code: item for item in ACCEPTANCE_CATALOG}


def normalize_name(value: str) -> str:
    return re.sub(r"[\s（）()\-_/·]", "", value).casefold()


def search_catalog(query: str) -> list[CatalogEntry]:
    query = query.strip()
    if re.fullmatch(r"\d{6}", query):
        value = CATALOG_BY_CODE.get(query)
        return [value] if value else []
    normalized = normalize_name(query)
    if not normalized:
        return []
    exact: list[CatalogEntry] = []
    partial: list[CatalogEntry] = []
    for item in ACCEPTANCE_CATALOG:
        names = (item.name, *item.aliases)
        if any(normalize_name(name) == normalized for name in names):
            exact.append(item)
        elif any(normalized in normalize_name(name) for name in names):
            partial.append(item)
    return exact or partial
