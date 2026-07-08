"""IntelService aggregation, FRED calendar, exports, SPA fallback."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_pro_pipeline_graph import CONFIG, FakePipelineLLM, pipeline_snapshot  # noqa: E402
from tradingagents.contracts import MetricReading, utc_now  # noqa: E402
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.dashboard.intel import IntelService  # noqa: E402
from tradingagents.pro.ingestion.fred_macro import FredMacroFeed  # noqa: E402
from tradingagents.pro.memory import ProMemory  # noqa: E402


def reading(name, value=1.0):
    return MetricReading(name=name, value=value, unit="x",
                         as_of=utc_now(), source="fake")


class TestIntelService:
    def test_partial_failure_disclosed_not_fatal(self):
        service = IntelService(feeds={
            "derivatives": lambda: [reading("FUNDING_RATE", 0.0001)],
            "fred_macro": lambda: (_ for _ in ()).throw(
                RuntimeError("FRED_API_KEY not set")),
        })
        view = service.snapshot()
        assert [m["name"] for m in view["metrics"]] == ["FUNDING_RATE"]
        assert view["missing_feeds"] == ["fred_macro: FRED_API_KEY not set"]
        assert any(f["provider"] == "Coinglass"
                   for f in view["unsubscribed_feeds"])

    def test_snapshot_ttl_cache(self):
        calls = {"n": 0}

        def counted():
            calls["n"] += 1
            return [reading("X")]

        clock = {"t": 0.0}
        service = IntelService(feeds={"only": counted}, ttl=60,
                               now=lambda: clock["t"])
        service.snapshot()
        service.snapshot()
        assert calls["n"] == 1
        clock["t"] = 61.0
        service.snapshot()
        assert calls["n"] == 2

    def test_hanging_feed_hits_deadline_not_forever(self):
        import time as _time

        def hang():
            _time.sleep(5)
            return [reading("LATE")]

        service = IntelService(
            feeds={"fast": lambda: [reading("FAST")],
                   "blackhole": hang},
            deadline=0.5,
        )
        t0 = _time.monotonic()
        view = service.snapshot()
        assert _time.monotonic() - t0 < 3.0  # bounded, not 30s+
        assert [m["name"] for m in view["metrics"]] == ["FAST"]
        assert any("no response within" in f for f in view["missing_feeds"])

    def test_calendar_with_and_without_source(self):
        service = IntelService(
            feeds={},
            calendar_source=lambda days: [
                {"date": "2026-07-15", "release": "CPI", "release_id": 10}],
        )
        view = service.calendar(7)
        assert view["releases"][0]["release"] == "CPI"

        broken = IntelService(
            feeds={},
            calendar_source=lambda days: (_ for _ in ()).throw(
                RuntimeError("no key")),
        )
        view = broken.calendar()
        assert view["releases"] == [] and "fred_calendar: no key" in view["missing_feeds"]


class TestFredCalendar:
    def test_release_dates_parsing(self):
        class FakeTransport:
            def get_json(self, url, params=None):
                assert "releases/dates" in url
                assert params["include_release_dates_with_no_data"] == "true"
                return {"release_dates": [
                    {"release_id": 10, "release_name": "Consumer Price Index",
                     "date": "2999-01-15"},
                    {"release_id": 50, "release_name": "Employment Situation",
                     "date": "2999-01-03"},
                ]}

        feed = FredMacroFeed(transport=FakeTransport(), api_key="k")
        releases = feed.get_release_dates(days_ahead=30)
        assert len(releases) == 2
        assert releases[0]["release"] == "Consumer Price Index"

    def test_calendar_requires_key(self, monkeypatch):
        from tradingagents.dataflows.fred import FredNotConfiguredError

        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(FredNotConfiguredError):
            FredMacroFeed().get_release_dates()


@pytest.fixture()
def seeded_client(tmp_path):
    from tradingagents.pro.dashboard.prefs import PrefsStore

    state = DashboardState(memory=ProMemory())
    state.prefs = PrefsStore(tmp_path / "prefs.json")
    state.intel = IntelService(feeds={"fake": lambda: [reading("F")]},
                               calendar_source=lambda d: [])
    state.recorder.record_run(
        FakePipelineLLM(), CONFIG, pipeline_snapshot(), memory=state.memory
    )
    return TestClient(create_app(state))


class TestIntelAndExportEndpoints:
    def test_intel_endpoint(self, seeded_client):
        view = seeded_client.get("/api/intel").json()
        assert view["metrics"][0]["name"] == "F"
        assert "session" in view

    def test_calendar_endpoint(self, seeded_client):
        assert seeded_client.get("/api/calendar").json()["releases"] == []

    def test_journal_csv_export(self, seeded_client):
        response = seeded_client.get("/api/export/journal.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in response.headers["content-disposition"]
        lines = response.text.strip().splitlines()
        assert lines[0] == "symbol,action,regime,pnl,won,closed_at"

    def test_report_export_has_every_section(self, seeded_client):
        report = seeded_client.get("/api/export/report.json").json()
        for section in ("overview", "recommendation", "status", "journal",
                        "backtest", "agents", "memory", "alerts",
                        "generated_at", "app_version"):
            assert section in report, section
        assert report["recommendation"]["action"] == "BUY"


class TestSpaFallback:
    def test_client_routes_serve_shell_api_still_404s(self):
        client = TestClient(create_app(DashboardState()))
        # no SPA build present in dev checkout -> legacy page everywhere
        for route in ("/", "/trade/BTC-USD", "/decisions/abc", "/legacy"):
            response = client.get(route)
            assert response.status_code == 200
            assert "TradingAgents Pro" in response.text
        assert client.get("/api/nope").status_code == 404
        assert client.get("/api/runs/zzz/timeline").status_code == 404
