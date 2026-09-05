from tradingagents.research_platform.research_settings import (
    DataPeriodPreset,
    JsonResearchSettingsStore,
    ResearchSettings,
)


def test_default_settings_cover_game_ai_and_extensible_periods():
    settings = ResearchSettings()

    assert {item.id for item in settings.sector_rules} == {"game", "ai"}
    assert settings.default_lookback_days == 365
    assert {item.days for item in settings.period_presets} >= {90, 180, 365, 730, 1825}


def test_settings_store_round_trips_custom_period_without_credentials(tmp_path):
    store = JsonResearchSettingsStore(tmp_path)
    settings = ResearchSettings(
        default_period_id="custom",
        period_presets=[DataPeriodPreset(id="custom", name="18 months", days=548)],
    )

    store.save(settings)

    assert store.load() == settings
    assert "TOKEN" not in store.path.read_text(encoding="utf-8")
