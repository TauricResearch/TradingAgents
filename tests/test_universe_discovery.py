from tradingagents.research_platform.research_settings import ResearchSettings, SectorRule
from tradingagents.research_platform.universe_discovery import TushareUniverseDiscovery


class FakeTushareClient:
    def stock_basic(self, **_params):
        return [
            {"ts_code": "002624.SZ", "symbol": "002624", "name": "Perfect World"},
            {"ts_code": "002602.SZ", "symbol": "002602", "name": "Century Huatong"},
            {"ts_code": "688256.SH", "symbol": "688256", "name": "AI Chip"},
            {"ts_code": "430001.BJ", "symbol": "430001", "name": "Beijing AI"},
        ]

    def ths_index(self, **_params):
        return [
            {"ts_code": "885010.TI", "name": "网络游戏"},
            {"ts_code": "885020.TI", "name": "人工智能"},
            {"ts_code": "885030.TI", "name": "白酒"},
        ]

    def ths_member(self, ts_code, **_params):
        return {
            "885010.TI": [
                {"code": "002624.SZ", "name": "Perfect World"},
                {"code": "002602.SZ", "name": "Century Huatong"},
            ],
            "885020.TI": [
                {"code": "688256.SH", "name": "AI Chip"},
                {"code": "430001.BJ", "name": "Beijing AI"},
            ],
            "885030.TI": [{"code": "600519.SH", "name": "Liquor"}],
        }[ts_code]


def test_discovers_configured_game_and_ai_concepts_including_beijing_exchange():
    settings = ResearchSettings(
        sector_rules=[
            SectorRule(id="game", name="Game", keywords=["游戏"]),
            SectorRule(
                id="ai",
                name="AI",
                keywords=["人工智能"],
                explicit_excludes=["430001"],
            ),
        ]
    )

    result = TushareUniverseDiscovery(pro_client=FakeTushareClient()).discover(settings)

    assert result.source_endpoint == "ths_member"
    assert [item.symbol for item in result.stocks] == ["002602", "002624", "688256"]
    assert result.matched_concepts == {"game": ["网络游戏"], "ai": ["人工智能"]}
    assert next(item for item in result.stocks if item.symbol == "688256").sectors == ["ai"]


def test_explicit_include_survives_when_concept_catalog_has_no_match():
    settings = ResearchSettings(
        sector_rules=[
            SectorRule(
                id="game", name="Game", keywords=["not-present"], explicit_includes=["002624"]
            )
        ]
    )

    result = TushareUniverseDiscovery(pro_client=FakeTushareClient()).discover(settings)

    assert result.stocks[0].symbol == "002624"
    assert result.stocks[0].sectors == ["game"]
