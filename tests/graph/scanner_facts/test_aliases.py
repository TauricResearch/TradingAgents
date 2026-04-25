from tradingagents.graph.scanner_facts.aliases import (
    COMMODITY_ALIASES,
    FX_ALIASES,
    INDEX_ALIASES,
    MACRO_ALIASES,
    SECTOR_ALIASES,
    TICKER_ALIASES,
    resolve_alias,
)


def test_ticker_aliases_returns_list():
    aliases = TICKER_ALIASES.get("ON", [])
    assert isinstance(aliases, list)
    assert "ON Semiconductor" in aliases or "Onsemi" in aliases


def test_sector_aliases_technology():
    aliases = SECTOR_ALIASES.get("Technology", [])
    assert "Information Technology" in aliases


def test_index_aliases_sp500():
    aliases = INDEX_ALIASES.get("S&P 500", [])
    assert any("SPX" in a or "S&P" in a for a in aliases)


def test_resolve_alias_ticker():
    # "ON Semiconductor" should resolve to canonical id "ON"
    result = resolve_alias("ON Semiconductor", registry=TICKER_ALIASES)
    assert result == "ON"


def test_resolve_alias_not_found_returns_none():
    result = resolve_alias("UNKNOWNXYZ", registry=TICKER_ALIASES)
    assert result is None


def test_all_registry_values_are_lists():
    for registry in (
        TICKER_ALIASES,
        SECTOR_ALIASES,
        INDEX_ALIASES,
        MACRO_ALIASES,
        COMMODITY_ALIASES,
        FX_ALIASES,
    ):
        for key, val in registry.items():
            assert isinstance(val, list), f"{key} value must be a list"
