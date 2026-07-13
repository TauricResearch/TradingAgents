"""PrefsStore: atomicity, concurrency, caps, endpoints."""

import json
import threading

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tradingagents.pro.alerting import AlertManager  # noqa: E402
from tradingagents.pro.dashboard.app import DashboardState, create_app  # noqa: E402
from tradingagents.pro.dashboard.prefs import (  # noqa: E402
    MAX_NOTIFICATIONS,
    NotificationSink,
    PrefsStore,
)


@pytest.fixture()
def store(tmp_path):
    return PrefsStore(tmp_path / "prefs.json")


class TestPrefsStore:
    def test_roundtrip_and_reload(self, store, tmp_path):
        store.put_prefs({"theme": "light", "layouts": {"home": [1, 2]}})
        reloaded = PrefsStore(tmp_path / "prefs.json")
        prefs = reloaded.get_prefs()
        assert prefs["theme"] == "light" and prefs["layouts"] == {"home": [1, 2]}

    def test_unknown_fields_rejected(self, store):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            store.put_prefs({"theme": "dark", "hacker": True})

    def test_corrupt_file_recovers_to_defaults(self, tmp_path):
        path = tmp_path / "prefs.json"
        path.write_text("{not json", encoding="utf-8")
        store = PrefsStore(path)
        # reskin: light is the default theme
        assert store.get_prefs()["theme"] == "light"

    def test_atomic_write_leaves_no_temp_files(self, store, tmp_path):
        for i in range(5):
            store.put_prefs({"theme": f"t{i}"})
        leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []
        assert json.loads((tmp_path / "prefs.json").read_text())["prefs"]["theme"] == "t4"

    def test_concurrent_writers_end_valid(self, store, tmp_path):
        def write(i):
            for j in range(10):
                store.upsert_watchlist({"name": f"w{i}", "symbols": [f"S{j}"]})

        threads = [threading.Thread(target=write, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        reloaded = PrefsStore(tmp_path / "prefs.json")
        names = {w["name"] for w in reloaded.watchlists()}
        assert names == {f"w{i}" for i in range(6)}

    def test_watchlist_upsert_and_delete(self, store):
        store.upsert_watchlist({"name": "gold", "symbols": ["XAUUSD"]})
        store.upsert_watchlist({"name": "gold", "symbols": ["XAUUSD", "SI=F"]})
        lists = store.watchlists()
        assert len(lists) == 1 and lists[0]["symbols"] == ["XAUUSD", "SI=F"]
        assert store.delete_watchlist("gold") is True
        assert store.delete_watchlist("gold") is False

    def test_saved_views_and_muted_events_roundtrip(self, store):
        saved = store.put_prefs({
            "theme": "dark",
            "views": [{"name": "gold focus", "path": "/trade/XAUUSD?tf=1h"}],
            "muted_events": ["iteration_error"],
        })
        assert saved["views"][0]["name"] == "gold focus"
        assert saved["muted_events"] == ["iteration_error"]

    def test_saved_view_validation(self, store):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            store.put_prefs({"views": [{"name": "", "path": "/x"}]})
        with pytest.raises(ValidationError):
            store.put_prefs({"views": [{"name": "x", "path": "/x",
                                        "sneaky": 1}]})

    def test_notification_cap_and_mark_read(self, store):
        for i in range(MAX_NOTIFICATIONS + 20):
            store.add_notification("info", "e", f"n{i}")
        notes = store.notifications()
        assert len(notes) == MAX_NOTIFICATIONS
        assert notes[0]["text"] == f"n{MAX_NOTIFICATIONS + 19}"  # newest first
        first_two = [n["id"] for n in notes[:2]]
        assert store.mark_read(first_two) == 2
        assert len(store.notifications(unread_only=True)) == MAX_NOTIFICATIONS - 2
        assert store.mark_read() == MAX_NOTIFICATIONS - 2  # mark all

    def test_notification_sink_bridges_alerts(self, store):
        manager = AlertManager(sinks=[NotificationSink(store)])
        manager.emit("critical", "kill_switch", "halted")
        note = store.notifications()[0]
        assert note["severity"] == "critical" and note["read"] is False


class TestPrefsEndpoints:
    @pytest.fixture()
    def state(self, tmp_path):
        state = DashboardState()
        state.prefs = PrefsStore(tmp_path / "prefs.json")
        return state

    @pytest.fixture()
    def client(self, state):
        return TestClient(create_app(state))

    def test_prefs_crud(self, client):
        assert client.get("/api/prefs").json()["theme"] == "light"  # reskin default
        updated = client.put("/api/prefs", json={"theme": "dark"}).json()
        assert updated["theme"] == "dark"
        assert client.put("/api/prefs", json={"nope": 1}).status_code == 422
        assert client.put(
            "/api/prefs", content=b"{" * 300_000,
            headers={"Content-Type": "application/json"},
        ).status_code == 413

    def test_watchlist_endpoints(self, client):
        created = client.post("/api/watchlists",
                              json={"name": "metals", "symbols": ["XAUUSD"]})
        assert created.status_code == 200
        assert client.get("/api/watchlists").json()[0]["name"] == "metals"
        assert client.delete("/api/watchlists/metals").json() == {"deleted": "metals"}
        assert client.delete("/api/watchlists/metals").status_code == 404

    def test_notification_endpoints(self, client, state):
        # notifications arrive via the sink in production; seed directly here
        note = state.prefs.add_notification("warning", "e", "check this")
        payload = client.get("/api/notifications").json()
        assert payload["unread"] == 1
        marked = client.post("/api/notifications/read",
                             json={"ids": [note["id"]]}).json()
        assert marked == {"marked": 1}
        assert client.get("/api/notifications").json()["unread"] == 0
