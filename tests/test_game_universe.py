from datetime import date

from tradingagents.research_platform.game_universe import (
    GameCatalystStatus,
    GameProductStatus,
    build_game_research_snapshot,
    list_game_universe_symbols,
)


def test_game_universe_starts_with_perfect_world_and_century_huatong():
    assert list_game_universe_symbols() == ["002602", "002624"]

    perfect_world = build_game_research_snapshot("002624", as_of_date=date(2026, 7, 12))
    century_huatong = build_game_research_snapshot("002602", as_of_date=date(2026, 7, 12))

    assert perfect_world.available is True
    assert perfect_world.company_name == "完美世界股份有限公司"
    assert {item.name for item in perfect_world.products} >= {"异环", "诛仙世界", "诛仙2"}
    assert perfect_world.pipeline_product_count == 7
    assert century_huatong.available is True
    assert {item.name for item in century_huatong.products} >= {"Whiteout Survival", "Kingshot"}
    assert century_huatong.live_product_count == 5


def test_game_universe_hides_facts_not_known_by_requested_date():
    before_disclosures = build_game_research_snapshot("002624", as_of_date=date(2026, 1, 1))
    before_century_catalog = build_game_research_snapshot(
        "002602", as_of_date=date(2026, 2, 1)
    )

    assert before_disclosures.available is False
    assert before_disclosures.company_name is None
    assert before_disclosures.research_focus == []
    assert before_disclosures.evidence == []
    assert {item.name for item in before_century_catalog.products} == {
        "Whiteout Survival",
        "Kingshot",
    }
    assert all(item.known_as_of <= date(2026, 2, 1) for item in before_century_catalog.products)


def test_game_universe_derives_catalyst_status_for_point_in_time():
    snapshot = build_game_research_snapshot("002624", as_of_date=date(2026, 4, 28))
    catalysts = {item.catalyst.catalyst_id: item.status for item in snapshot.catalysts}

    assert catalysts["nte-cn-launch"] == GameCatalystStatus.COMPLETED
    assert catalysts["nte-overseas-launch"] == GameCatalystStatus.UPCOMING
    assert catalysts["perfect-world-pipeline"] == GameCatalystStatus.UNDATED
    assert any(item.status == GameProductStatus.PIPELINE for item in snapshot.products)


def test_game_universe_returns_clear_empty_state_for_other_symbols():
    snapshot = build_game_research_snapshot("600519", as_of_date=date(2026, 7, 12))

    assert snapshot.available is False
    assert snapshot.products == []
    assert snapshot.catalysts == []
