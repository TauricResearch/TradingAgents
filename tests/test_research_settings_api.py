from json import dumps, loads
from threading import Thread
from urllib.request import Request, urlopen

from tradingagents.research_platform.cockpit import create_cockpit_server
from tradingagents.research_platform.universe_discovery import (
    DiscoveredStock,
    UniverseDiscoveryResult,
)


class FakeDiscovery:
    def discover(self, _settings):
        return UniverseDiscoveryResult(
            source_endpoint="fixture",
            stocks=[
                DiscoveredStock(
                    symbol="002624",
                    ts_code="002624.SZ",
                    name="Perfect World",
                    sectors=["game"],
                    sector_names=["Game"],
                ),
                DiscoveredStock(
                    symbol="688256",
                    ts_code="688256.SH",
                    name="AI Chip",
                    sectors=["ai"],
                    sector_names=["AI"],
                ),
            ],
            matched_concepts={"game": ["Game"], "ai": ["AI"]},
        )


def _request(url, *, method="GET", payload=None):
    request = Request(
        url,
        data=dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urlopen(request, timeout=2) as response:
        return response.status, loads(response.read().decode("utf-8"))


def test_settings_api_saves_previews_and_merges_discovered_watchlist(tmp_path):
    server = create_cockpit_server(tmp_path, port=0, universe_factory=FakeDiscovery)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"
    try:
        _, defaults = _request(base + "/api/research-settings")
        settings = defaults["settings"]
        settings["default_period_id"] = "6m"
        status, saved = _request(base + "/api/research-settings", method="PUT", payload=settings)
        _, preview = _request(base + "/api/universe-preview", method="POST")
        _, synced = _request(base + "/api/universe-sync", method="POST")
        _, watchlist = _request(base + "/api/watchlist")
        _, board = _request(base + "/api/watchlist-board")
        with urlopen(base + "/settings", timeout=2) as response:
            page = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.jobs.shutdown()

    assert status == 200
    assert saved["default_lookback_days"] == 180
    assert len(preview["discovery"]["stocks"]) == 2
    assert synced["watchlist_total"] == 2
    assert {item["symbol"]: item["sectors"] for item in watchlist["entries"]} == {
        "002624": ["game"],
        "688256": ["ai"],
    }
    assert {item["symbol"]: item["sector_names"] for item in board["items"]} == {
        "002624": ["\u6e38\u620f"],
        "688256": ["\u4eba\u5de5\u667a\u80fd"],
    }
    assert "研究配置" in page


def test_main_cockpit_posts_selected_extensible_lookback():
    from tradingagents.research_platform.cockpit import _APP_HTML

    assert 'href="/settings"' in _APP_HTML
    assert 'id="lookbackPeriod"' in _APP_HTML
    assert "lookback_days: Number($('lookbackPeriod').value)" in _APP_HTML
