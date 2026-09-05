"""Curated, point-in-time game-company universe for A-share research."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GameEvidenceType(str, Enum):
    FILING = "filing"
    COMPANY_RELEASE = "company_release"
    OFFICIAL_PRODUCT_SITE = "official_product_site"


class GameEntityRole(str, Enum):
    LISTED_COMPANY = "listed_company"
    GAME_BUSINESS = "game_business"
    DEVELOPER_PUBLISHER = "developer_publisher"


class GameProductStatus(str, Enum):
    LIVE = "live"
    PIPELINE = "pipeline"
    LEGACY_LIVE = "legacy_live"


class GameCatalystCategory(str, Enum):
    LAUNCH = "launch"
    OVERSEAS_LAUNCH = "overseas_launch"
    LIVE_OPERATIONS = "live_operations"
    PRODUCT_PIPELINE = "product_pipeline"


class GameCatalystStatus(str, Enum):
    UPCOMING = "upcoming"
    COMPLETED = "completed"
    ONGOING = "ongoing"
    UNDATED = "undated"


class GameEvidence(BaseModel):
    """One source supporting a curated company, entity, product, or catalyst fact."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str = Field(min_length=1)
    evidence_type: GameEvidenceType
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    available_as_of: date
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GameBusinessEntity(BaseModel):
    """A listed company or operating entity in the game-company graph."""

    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: GameEntityRole
    relationship: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    known_as_of: date
    evidence_ids: list[str] = Field(default_factory=list)


class GameProduct(BaseModel):
    """One material live or pipeline title linked to an operating entity."""

    model_config = ConfigDict(frozen=True)

    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    operator_entity_id: str = Field(min_length=1)
    status: GameProductStatus
    known_as_of: date
    aliases: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class GameCatalyst(BaseModel):
    """A product event worth tracking, separate from any investment signal."""

    model_config = ConfigDict(frozen=True)

    catalyst_id: str = Field(min_length=1)
    category: GameCatalystCategory
    title: str = Field(min_length=1)
    known_as_of: date
    product_id: str | None = None
    event_date: date | None = None
    ongoing: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class GameCompanyProfile(BaseModel):
    """Curated source record for one A-share game company."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    research_focus: list[str] = Field(default_factory=list)
    entities: list[GameBusinessEntity] = Field(default_factory=list)
    products: list[GameProduct] = Field(default_factory=list)
    catalysts: list[GameCatalyst] = Field(default_factory=list)
    evidence: list[GameEvidence] = Field(default_factory=list)


class GameCatalystView(BaseModel):
    """Catalyst plus status derived for the requested point in time."""

    model_config = ConfigDict(frozen=True)

    catalyst: GameCatalyst
    status: GameCatalystStatus


class GameResearchSnapshot(BaseModel):
    """Point-in-time game-company view rendered by the cockpit."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of_date: date
    available: bool
    company_name: str | None = None
    research_focus: list[str] = Field(default_factory=list)
    entities: list[GameBusinessEntity] = Field(default_factory=list)
    products: list[GameProduct] = Field(default_factory=list)
    catalysts: list[GameCatalystView] = Field(default_factory=list)
    evidence: list[GameEvidence] = Field(default_factory=list)
    live_product_count: int = Field(default=0, ge=0)
    pipeline_product_count: int = Field(default=0, ge=0)


def list_game_universe_symbols() -> list[str]:
    """Return symbols with curated game-company coverage."""

    return sorted(_GAME_UNIVERSE)


def build_game_research_snapshot(
    symbol: str,
    *,
    as_of_date: date | None = None,
) -> GameResearchSnapshot:
    """Return only facts which were known by the requested date."""

    normalized_symbol = symbol.strip().upper()
    reference_date = as_of_date or date.today()
    profile = _GAME_UNIVERSE.get(normalized_symbol)
    if profile is None:
        return GameResearchSnapshot(
            symbol=normalized_symbol,
            as_of_date=reference_date,
            available=False,
        )

    evidence = [item for item in profile.evidence if item.available_as_of <= reference_date]
    evidence_ids = {item.evidence_id for item in evidence}
    entities = [
        item
        for item in profile.entities
        if item.known_as_of <= reference_date and _has_available_evidence(item.evidence_ids, evidence_ids)
    ]
    entity_ids = {item.entity_id for item in entities}
    products = [
        item
        for item in profile.products
        if item.known_as_of <= reference_date
        and item.operator_entity_id in entity_ids
        and _has_available_evidence(item.evidence_ids, evidence_ids)
    ]
    product_ids = {item.product_id for item in products}
    catalysts = [
        GameCatalystView(catalyst=item, status=_catalyst_status(item, reference_date))
        for item in profile.catalysts
        if item.known_as_of <= reference_date
        and (item.product_id is None or item.product_id in product_ids)
        and _has_available_evidence(item.evidence_ids, evidence_ids)
    ]
    live_statuses = {GameProductStatus.LIVE, GameProductStatus.LEGACY_LIVE}
    return GameResearchSnapshot(
        symbol=normalized_symbol,
        as_of_date=reference_date,
        available=bool(entities or products or catalysts),
        company_name=profile.company_name if evidence else None,
        research_focus=profile.research_focus if evidence else [],
        entities=entities,
        products=products,
        catalysts=catalysts,
        evidence=evidence,
        live_product_count=sum(item.status in live_statuses for item in products),
        pipeline_product_count=sum(item.status == GameProductStatus.PIPELINE for item in products),
    )


def _has_available_evidence(required: list[str], available: set[str]) -> bool:
    return not required or any(item in available for item in required)


def _catalyst_status(catalyst: GameCatalyst, as_of_date: date) -> GameCatalystStatus:
    if catalyst.ongoing:
        return GameCatalystStatus.ONGOING
    if catalyst.event_date is None:
        return GameCatalystStatus.UNDATED
    if catalyst.event_date <= as_of_date:
        return GameCatalystStatus.COMPLETED
    return GameCatalystStatus.UPCOMING


_PERFECT_WORLD_RELEASE = GameEvidence(
    evidence_id="perfect-world-2025-results",
    evidence_type=GameEvidenceType.COMPANY_RELEASE,
    title="完美世界发布2025年报及2026一季报",
    source_url="https://www.wanmei.com/wmnews/wmnews2026/20260428/261966.shtml",
    available_as_of=date(2026, 4, 28),
)
_PERFECT_WORLD_SITE = GameEvidence(
    evidence_id="perfect-world-company-site",
    evidence_type=GameEvidenceType.COMPANY_RELEASE,
    title="完美世界官方网站",
    source_url="https://www.wanmei.com/",
    available_as_of=date(2026, 4, 28),
)
_CENTURY_FORECAST = GameEvidence(
    evidence_id="century-huatong-2025-forecast",
    evidence_type=GameEvidenceType.FILING,
    title="世纪华通2025年度业绩预告",
    source_url=(
        "https://disc.static.szse.cn/disc/disk03/finalpage/2026-01-30/"
        "f3597cda-d7f6-4dc7-8a2f-cff71524ed37.PDF"
    ),
    available_as_of=date(2026, 1, 30),
)
_CENTURY_GAMES_SITE = GameEvidence(
    evidence_id="century-games-products",
    evidence_type=GameEvidenceType.OFFICIAL_PRODUCT_SITE,
    title="Century Games official product catalog",
    source_url="https://www.centurygames.com/games/",
    available_as_of=date(2026, 7, 12),
)


def _product(
    product_id: str,
    name: str,
    entity_id: str,
    status: GameProductStatus,
    known_as_of: date,
    evidence_id: str,
    *,
    aliases: list[str] | None = None,
    genres: list[str] | None = None,
    platforms: list[str] | None = None,
    markets: list[str] | None = None,
) -> GameProduct:
    return GameProduct(
        product_id=product_id,
        name=name,
        operator_entity_id=entity_id,
        status=status,
        known_as_of=known_as_of,
        aliases=aliases or [],
        genres=genres or [],
        platforms=platforms or [],
        markets=markets or [],
        evidence_ids=[evidence_id],
    )


_GAME_UNIVERSE = {
    "002624": GameCompanyProfile(
        symbol="002624",
        company_name="完美世界股份有限公司",
        research_focus=["MMORPG长线运营", "二次元产品", "全球发行", "新品上线兑现"],
        evidence=[_PERFECT_WORLD_RELEASE, _PERFECT_WORLD_SITE],
        entities=[
            GameBusinessEntity(
                entity_id="perfect-world-listed",
                name="完美世界股份有限公司",
                role=GameEntityRole.LISTED_COMPANY,
                relationship="A股上市公司，股票代码002624",
                known_as_of=date(2026, 4, 28),
                evidence_ids=[_PERFECT_WORLD_SITE.evidence_id],
            ),
            GameBusinessEntity(
                entity_id="perfect-world-games",
                name="完美世界游戏业务",
                role=GameEntityRole.GAME_BUSINESS,
                relationship="上市公司游戏研发与发行板块",
                known_as_of=date(2026, 4, 28),
                evidence_ids=[_PERFECT_WORLD_RELEASE.evidence_id],
            ),
        ],
        products=[
            _product(
                "perfect-world-international",
                "完美世界国际版",
                "perfect-world-games",
                GameProductStatus.LEGACY_LIVE,
                date(2026, 4, 28),
                _PERFECT_WORLD_RELEASE.evidence_id,
                genres=["MMORPG"],
                platforms=["PC"],
                markets=["中国", "海外"],
            ),
            _product(
                "zhu-xian-world",
                "诛仙世界",
                "perfect-world-games",
                GameProductStatus.LIVE,
                date(2026, 4, 28),
                _PERFECT_WORLD_RELEASE.evidence_id,
                genres=["MMORPG"],
                platforms=["PC"],
                markets=["中国"],
            ),
            _product(
                "zhu-xian-2",
                "诛仙2",
                "perfect-world-games",
                GameProductStatus.LIVE,
                date(2026, 4, 28),
                _PERFECT_WORLD_RELEASE.evidence_id,
                genres=["MMORPG"],
                platforms=["Mobile"],
                markets=["中国"],
            ),
            _product(
                "persona-5-x",
                "女神异闻录：夜幕魅影",
                "perfect-world-games",
                GameProductStatus.LIVE,
                date(2026, 4, 28),
                _PERFECT_WORLD_RELEASE.evidence_id,
                aliases=["Persona 5: The Phantom X", "P5X"],
                genres=["RPG", "二次元"],
                platforms=["Mobile", "PC"],
                markets=["中国", "日本", "欧美", "东南亚"],
            ),
            _product(
                "neverness-to-everness",
                "异环",
                "perfect-world-games",
                GameProductStatus.LIVE,
                date(2026, 4, 28),
                _PERFECT_WORLD_RELEASE.evidence_id,
                aliases=["Neverness to Everness", "NTE"],
                genres=["开放世界RPG", "二次元"],
                platforms=["Mobile", "PC", "PlayStation 5", "Mac"],
                markets=["中国", "海外"],
            ),
            *[
                _product(
                    f"perfect-world-pipeline-{index}",
                    name,
                    "perfect-world-games",
                    GameProductStatus.PIPELINE,
                    date(2026, 4, 28),
                    _PERFECT_WORLD_RELEASE.evidence_id,
                    markets=["待披露"],
                )
                for index, name in enumerate(
                    ["梦幻新诛仙：轻享", "代号普洱", "代号MT1", "代号J1", "代号F", "代号U1", "代号ZH"],
                    start=1,
                )
            ],
        ],
        catalysts=[
            GameCatalyst(
                catalyst_id="nte-cn-launch",
                category=GameCatalystCategory.LAUNCH,
                title="《异环》国服公测",
                product_id="neverness-to-everness",
                known_as_of=date(2026, 4, 28),
                event_date=date(2026, 4, 23),
                evidence_ids=[_PERFECT_WORLD_RELEASE.evidence_id],
            ),
            GameCatalyst(
                catalyst_id="nte-overseas-launch",
                category=GameCatalystCategory.OVERSEAS_LAUNCH,
                title="《异环》海外多平台上线",
                product_id="neverness-to-everness",
                known_as_of=date(2026, 4, 28),
                event_date=date(2026, 4, 29),
                evidence_ids=[_PERFECT_WORLD_RELEASE.evidence_id],
            ),
            GameCatalyst(
                catalyst_id="perfect-world-pipeline",
                category=GameCatalystCategory.PRODUCT_PIPELINE,
                title="储备项目测试、定档与版号进展",
                known_as_of=date(2026, 4, 28),
                evidence_ids=[_PERFECT_WORLD_RELEASE.evidence_id],
            ),
        ],
    ),
    "002602": GameCompanyProfile(
        symbol="002602",
        company_name="浙江世纪华通集团股份有限公司",
        research_focus=["全球SLG", "长线运营", "出海收入", "多产品接力"],
        evidence=[_CENTURY_FORECAST, _CENTURY_GAMES_SITE],
        entities=[
            GameBusinessEntity(
                entity_id="century-huatong-listed",
                name="浙江世纪华通集团股份有限公司",
                role=GameEntityRole.LISTED_COMPANY,
                relationship="A股上市公司，股票代码002602",
                known_as_of=date(2026, 1, 30),
                evidence_ids=[_CENTURY_FORECAST.evidence_id],
            ),
            GameBusinessEntity(
                entity_id="century-games",
                name="点点互动（Century Games）",
                role=GameEntityRole.DEVELOPER_PUBLISHER,
                relationship="上市公司海外游戏研发与发行主体",
                aliases=["点点互动", "Century Games"],
                known_as_of=date(2026, 1, 30),
                evidence_ids=[_CENTURY_FORECAST.evidence_id],
            ),
        ],
        products=[
            _product(
                "whiteout-survival",
                "Whiteout Survival",
                "century-games",
                GameProductStatus.LIVE,
                date(2026, 1, 30),
                _CENTURY_FORECAST.evidence_id,
                aliases=["无尽冬日"],
                genres=["SLG", "生存模拟"],
                platforms=["Mobile"],
                markets=["全球", "中国"],
            ),
            _product(
                "kingshot",
                "Kingshot",
                "century-games",
                GameProductStatus.LIVE,
                date(2026, 1, 30),
                _CENTURY_FORECAST.evidence_id,
                genres=["SLG", "中世纪生存"],
                platforms=["Mobile"],
                markets=["全球"],
            ),
            *[
                _product(
                    product_id,
                    name,
                    "century-games",
                    GameProductStatus.LIVE,
                    date(2026, 7, 12),
                    _CENTURY_GAMES_SITE.evidence_id,
                    genres=genres,
                    platforms=["Mobile"],
                    markets=["全球"],
                )
                for product_id, name, genres in [
                    ("tasty-travels", "Tasty Travels: Merge Game", ["Merge", "休闲"]),
                    ("truck-star", "Truck Star", ["Match-3", "模拟经营"]),
                    ("family-farm-adventure", "Family Farm Adventure", ["农场模拟", "冒险"]),
                ]
            ],
        ],
        catalysts=[
            GameCatalyst(
                catalyst_id="century-slg-live-ops",
                category=GameCatalystCategory.LIVE_OPERATIONS,
                title="《Whiteout Survival》与《Kingshot》全球长线运营表现",
                known_as_of=date(2026, 1, 30),
                ongoing=True,
                evidence_ids=[_CENTURY_FORECAST.evidence_id],
            ),
            GameCatalyst(
                catalyst_id="century-new-product-validation",
                category=GameCatalystCategory.PRODUCT_PIPELINE,
                title="新SLG与休闲产品的测试和商业化验证",
                known_as_of=date(2026, 1, 30),
                evidence_ids=[_CENTURY_FORECAST.evidence_id],
            ),
        ],
    ),
}
