from tradingagents.research_platform.watchlist import JsonWatchlistStore


def test_watchlist_normalizes_deduplicates_and_sorts_symbols(tmp_path):
    store = JsonWatchlistStore(tmp_path)

    first = store.add(" nvda ")
    duplicate = store.add("NVDA")
    store.add("aapl")

    assert first.symbol == "NVDA"
    assert duplicate == first
    assert [entry.symbol for entry in store.list_entries()] == ["AAPL", "NVDA"]
    assert store.path.exists()


def test_watchlist_removes_known_symbol_and_keeps_unknown_removal_safe(tmp_path):
    store = JsonWatchlistStore(tmp_path)
    store.add("NVDA")

    assert store.remove("nvda") is True
    assert store.remove("NVDA") is False
    assert store.list_entries() == []
