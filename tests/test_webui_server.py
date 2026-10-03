"""The UI's HTTP surface, with the graph itself stubbed out.

No run here calls a model: the worker is replaced where a test needs to see a
run's lifecycle, so the suite stays offline and fast.
"""

import json

import pytest

pytest.importorskip("fastapi", reason="the web UI extra is not installed")
pytest.importorskip("httpx", reason="TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from webui.server import create_app  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def config(tmp_path):
    """A config whose portfolio and memory log live in the test's own directory."""
    return {
        "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
        "results_dir": str(tmp_path / "logs"),
        "data_cache_dir": str(tmp_path / "cache"),
    }


@pytest.fixture(autouse=True)
def _never_run_the_graph(monkeypatch):
    """Submitting a run must not call a model.

    The worker is a daemon thread that outlives the test, so the suite's
    network block (a monkeypatch, undone at teardown) would not stop a run that
    starts late. Replacing the execution itself is what keeps the suite offline.
    """
    from webui.runs import RunManager

    def executed(self, record):
        record.status = "done"
        record.rating = "Hold"
        record.emit("status", status="done", rating="Hold")

    monkeypatch.setattr(RunManager, "_execute", executed)


@pytest.fixture
def client(config):
    with TestClient(create_app(config)) as client:
        yield client


BOOK = {
    "cash": 25000.0,
    "currency": "USD",
    "positions": [{"ticker": "NVDA", "quantity": 120, "average_price": 150.0}],
}


# --- portfolio ---


def test_no_saved_book_reads_as_null_not_as_flat(client):
    """The three states the pipeline distinguishes must survive the API."""
    assert client.get("/api/portfolio").json()["portfolio"] is None


def test_save_then_read_round_trips(client):
    saved = client.put("/api/portfolio", json=BOOK)
    assert saved.status_code == 200

    book = client.get("/api/portfolio").json()["portfolio"]
    assert book["cash"] == 25000.0
    assert book["positions"][0]["ticker"] == "NVDA"


def test_an_empty_book_is_saved_as_a_flat_book(client):
    client.put("/api/portfolio", json={"cash": 500.0, "positions": []})
    book = client.get("/api/portfolio").json()["portfolio"]
    assert book is not None and book["positions"] == []


def test_delete_returns_to_no_book(client):
    client.put("/api/portfolio", json=BOOK)
    assert client.delete("/api/portfolio").json()["deleted"] is True
    assert client.get("/api/portfolio").json()["portfolio"] is None


def test_a_malformed_book_is_rejected(client):
    assert client.put("/api/portfolio", json={"positions": [{"ticker": "X"}]}).status_code == 422


def test_the_saved_file_is_what_the_cli_accepts(client, config):
    """A book saved here loads through the CLI's own --portfolio reader."""
    from tradingagents.portfolio import load_portfolio
    from webui import store

    client.put("/api/portfolio", json=BOOK)
    loaded = load_portfolio(store.portfolio_path(config))
    assert loaded.position_in("NVDA").quantity == 120


# --- CSV import ---


SCHWAB_CSV = (
    '"Positions for account Individual ...123"\n'
    '"Symbol","Quantity","Market Value","Cost Basis"\n'
    '"AAPL","100","$23,000.00","$15,000.00"\n'
    '"Cash & Cash Investments","--","$5,000.00","--"\n'
)


def test_import_previews_without_saving(client):
    body = client.post("/api/portfolio/import", content=SCHWAB_CSV).json()

    assert body["saved"] is False
    assert body["portfolio"]["positions"][0]["ticker"] == "AAPL"
    # The preview must not have touched the stored book.
    assert client.get("/api/portfolio").json()["portfolio"] is None


def test_import_with_save_commits_the_book(client):
    client.post("/api/portfolio/import?save=true", content=SCHWAB_CSV)
    book = client.get("/api/portfolio").json()["portfolio"]
    assert book["positions"][0]["ticker"] == "AAPL"
    assert book["cash"] == 5000.0


def test_import_rejects_a_file_with_no_positions(client):
    assert client.post("/api/portfolio/import", content="a,b\n1,2\n").status_code == 422


def test_import_rejects_an_empty_body(client):
    assert client.post("/api/portfolio/import", content="").status_code == 400


# --- run submission ---


def test_a_run_needs_a_ticker(client):
    assert client.post("/api/runs", json={"ticker": "  "}).status_code == 400


def test_an_unknown_analyst_is_rejected(client):
    response = client.post("/api/runs", json={"ticker": "NVDA", "analysts": ["astrology"]})
    assert response.status_code == 400
    assert "astrology" in response.json()["detail"]


def test_crypto_drops_the_fundamentals_analyst(client):
    """A crypto ticker has no filings; the analyst is dropped, not failed on."""
    run = client.post("/api/runs", json={
        "ticker": "BTC-USD", "analysts": ["market", "fundamentals"],
    }).json()

    assert run["asset_type"] == "crypto"
    assert run["analysts"] == ["market"]


def test_crypto_with_only_fundamentals_is_rejected(client):
    response = client.post("/api/runs", json={"ticker": "BTC-USD", "analysts": ["fundamentals"]})
    assert response.status_code == 400


def test_a_run_without_a_saved_book_is_not_marked_as_having_one(client):
    """``use_portfolio`` cannot invent a book that was never saved."""
    run = client.post("/api/runs", json={"ticker": "NVDA", "use_portfolio": True}).json()
    assert run["with_portfolio"] is False


def test_a_run_uses_the_book_once_one_is_saved(client):
    client.put("/api/portfolio", json=BOOK)
    run = client.post("/api/runs", json={"ticker": "NVDA", "use_portfolio": True}).json()
    assert run["with_portfolio"] is True


def test_the_book_run_queues_one_run_per_holding(client):
    client.put("/api/portfolio", json={
        "cash": 1000.0,
        "positions": [
            {"ticker": "NVDA", "quantity": 10},
            {"ticker": "AAPL", "quantity": 5},
        ],
    })
    body = client.post("/api/runs/book", json={"analysts": ["market"]}).json()

    assert [r["ticker"] for r in body["runs"]] == ["NVDA", "AAPL"]
    # One batch, so the UI can group them.
    assert len({r["batch_id"] for r in body["runs"]}) == 1


def test_the_book_run_needs_a_book(client):
    assert client.post("/api/runs/book", json={}).status_code == 400


def test_a_queued_run_can_be_cancelled(client):
    run = client.post("/api/runs", json={"ticker": "NVDA"}).json()
    # The worker may already have picked it up; either way it must not 404.
    assert client.post(f"/api/runs/{run['id']}/cancel").status_code == 200


def test_an_unknown_run_is_a_404(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.post("/api/runs/nope/cancel").status_code == 404


# --- meta ---


def test_config_offers_providers_and_their_models(client):
    body = client.get("/api/config").json()

    assert "openai" in body["providers"]
    assert body["models"]["anthropic"]["deep"]
    assert {a["value"] for a in body["analysts"]} == {"market", "social", "news", "fundamentals"}
    assert body["today"]


def test_analysts_endpoint_reflects_the_asset(client):
    assert "fundamentals" in client.get("/api/analysts?ticker=NVDA").json()["analysts"]
    assert "fundamentals" not in client.get("/api/analysts?ticker=BTC-USD").json()["analysts"]


def test_history_reads_the_memory_log(client, config):
    from pathlib import Path

    log = Path(config["memory_log_path"])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "[2026-09-01 | NVDA | Buy | +4.2% | +1.1% | 5d | resolved:2026-09-08]\n"
        "DECISION:\nBought the dip.\n\nREFLECTION:\nThe thesis held.\n",
        encoding="utf-8",
    )
    entries = client.get("/api/history").json()["entries"]

    assert entries[0]["ticker"] == "NVDA"
    assert entries[0]["rating"] == "Buy"
    assert entries[0]["pending"] is False


def test_the_page_and_its_assets_are_served(client):
    assert "TradingAgents" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


# --- the event stream ---


def test_events_replay_from_the_start_of_the_run(client):
    """A browser that connects late sees everything the run has already emitted."""
    run = client.post("/api/runs", json={"ticker": "NVDA"}).json()
    record = client.app.state.manager.get(run["id"])
    record.cancel()                      # end it without calling a model
    record.emit("report", key="market_report", content="hello")

    with client.stream("GET", f"/api/runs/{run['id']}/events") as response:
        payloads = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                payloads.append(json.loads(line[6:]))
            if any(p.get("kind") == "report" for p in payloads):
                break

    assert payloads[0]["kind"] == "status"          # replayed from the first event
    assert any(p.get("content") == "hello" for p in payloads)
