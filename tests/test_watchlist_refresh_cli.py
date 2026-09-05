import json

from tradingagents.research_platform.watchlist import JsonWatchlistStore
from tradingagents.research_platform.watchlist_refresh_cli import main


def test_watchlist_refresh_cli_dry_run_lists_explicit_symbols(tmp_path, capsys):
    watchlist = JsonWatchlistStore(tmp_path)
    watchlist.add("600519")
    watchlist.add("0700.HK")

    exit_code = main(["--data-dir", str(tmp_path), "--dry-run"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "dry_run": True,
        "symbols": ["0700.HK", "600519"],
    }
