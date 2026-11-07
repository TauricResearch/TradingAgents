import json
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tests.test_trader_paper import BTC, DAY0, T0, FakeOKX
from trader.ledger import BUDGET_ERROR, Fill, Ledger, Position
from trader.okx import DAY_MS, Bar
from trader.prices import OFFICIAL
from trader.settings import Settings
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.memory.log import TradingMemoryLog
from web.api import app as app_module, data
from web.api.app import create_app

NOW = datetime.fromtimestamp(T0 / 1000, UTC)  # 2026-01-10 00:30 UTC: trade date 2026-01-09
MINUTE = 60_000
HOUR = 60 * MINUTE


class CountingOKX(FakeOKX):
    """FakeOKX with closes 80,000 and 80,800 on the two days before DAY0 + DAY, counting calls."""

    def __init__(self):
        super().__init__(last=79_000.0)
        self.daily = [Bar(DAY0 - DAY_MS, 0, 0, 0, 80_000), Bar(DAY0, 0, 0, 0, 80_800)]
        self.calls = []

    def last_price(self, inst):
        self.calls.append(("last", inst))
        return super().last_price(inst)

    def bars(self, inst, bar, start_ms, end_ms):
        self.calls.append(("bars", inst))
        return super().bars(inst, bar, start_ms, end_ms)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(data, "_now", lambda: NOW)
    # Whether web/ui/dist is built on this machine must not change the API's answers.
    monkeypatch.setattr(app_module, "UI_DIST", tmp_path / "no_dist")


def record(home, coin, trade_date, **fields):
    path = home / "logs" / coin / "x" / f"full_states_log_{trade_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"company_of_interest": coin, "trade_date": trade_date, **fields}))


def build(tmp_path, okx=None, validated=True):
    """A client over a paper account; validated: a short BTC, three midnights, research of
    2026-01-09 done (BTC), blocked by the budget (ETH) and pending (SOL)."""
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    if validated:
        ledger.record_attempt(
            "2026-01-08", BTC.research, DAY0 - DAY_MS + 10 * MINUTE, rating="Hold", error=None,
            tokens_in=80, tokens_out=40, cost_usd=2.0,
        )
        ledger.record_attempt(
            "2026-01-09", BTC.research, DAY0 + 10 * MINUTE, rating=None,
            error="RuntimeError: boom", tokens_in=10, tokens_out=5, cost_usd=0.5,
        )
        ledger.record_attempt(
            "2026-01-09", BTC.research, DAY0 + 20 * MINUTE, rating="Sell", error=None,
            tokens_in=100, tokens_out=50, cost_usd=1.0,
        )
        ledger.record_attempt(
            "2026-01-09", "ETH-USD", DAY0 + 25 * MINUTE, rating=None, error=BUDGET_ERROR,
            cost_usd=None,
        )
        ledger.commit(
            positions={BTC.swap: Position(-0.02, 80_000.0, 85_000.0)}, cash=10_000.0,
            fills=[
                Fill(DAY0 - DAY_MS, BTC.swap, 0.04, 79_000.0, 1.58, "trade", "2026-01-08"),
                Fill(T0, BTC.swap, -0.02, 80_000.0, 0.8, "trade", "2026-01-09"),
            ],
            funding=[(DAY0 + 8 * HOUR, BTC.swap, 0.0001, 0.16)],
            snapshots=[
                (DAY0, 10_000.0), (DAY0 + DAY_MS, 10_100.0), (DAY0 + 2 * DAY_MS, 10_050.0),
            ],
            meta={"validation_start": DAY0},
            executed=("2026-01-09", T0),
        )
        ledger.add_event(T0, "code_change", "a")
        ledger.add_event(T0 + MINUTE, "resume", "b")
        record(tmp_path, "BTC-USD", "2026-01-09", final_rating="Underweight")
        record(tmp_path, "BTC-USD", "2026-01-08")
        record(tmp_path, "SOL-USD", "2026-01-09", final_rating="Hold")
    ledger.db.close()
    return TestClient(create_app(settings, okx or CountingOKX()))


def test_accounts_lists_the_paper_account_first(tmp_path):
    accounts = build(tmp_path).get("/api/accounts").json()
    assert [a["id"] for a in accounts] == ["paper", "intraday"]
    account = accounts[0]
    assert account["id"] == "paper" and account["kind"] == "paper"
    assert account["capital"] == 10_000.0
    assert account["validation_start"] == "2026-01-10T00:00:00Z"
    assert account["halted"] is False
    assert account["watchlist"][0] == {
        "research": "BTC-USD", "swap": "BTC-USDT-SWAP", "spot": "BTC-USDT"
    }


def test_strategy_quotes_the_constants_the_trader_runs_on(tmp_path):
    body = build(tmp_path).get("/api/strategy").json()
    assert body["risk_per_unit"] == 0.02 and body["stop_atr_mult"] == 2.5
    assert body["rating_weights"] == {
        "Buy": 1.0, "Overweight": 0.5, "Underweight": -0.25, "Sell": -0.5
    }
    assert body["kill_drawdown"] == 0.2 and body["benchmark"] == "USDC-USD"
    assert body["analysts"] == ["market", "social", "news"]
    assert body["watchlist"] == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert body["holding_period_days"] == 5
    assert isinstance(body["deep_model"], str) and isinstance(body["quick_model"], str)


def test_overview_marks_the_account_and_sums_up_the_day(tmp_path):
    body = build(tmp_path).get("/api/accounts/paper/overview").json()
    assert body["equity"] == pytest.approx(10_020.0)  # short 0.02 from 80,000, marked at 79,000
    assert body["cash"] == 10_000.0 and body["peak"] == 10_000.0
    assert body["drawdown"] == 0.0 and body["halted"] is False
    assert body["processed_to"] == "2026-01-10T00:30:00Z"
    assert body["validation_start"] == "2026-01-10T00:00:00Z"
    assert body["days"] == 2

    # Net of the $1.50 spent after the first midnight: 10,000 / 10,098.5 / 10,048.5.
    strategy = body["performance"]["strategy"]
    assert strategy["cumulative"] == pytest.approx(0.00485)
    assert strategy["annualized"] == pytest.approx(1.00485 ** (365 / 2) - 1)
    assert strategy["max_drawdown"] == pytest.approx(1 - 10_048.5 / 10_098.5)
    assert strategy["calmar"] == pytest.approx(strategy["annualized"] / strategy["max_drawdown"])
    assert strategy["sharpe"] is not None
    # The baselines have closes for the first two midnights only: +1%, no drawdown.
    for name in ("equal_weight", "btc"):
        assert body["performance"][name]["cumulative"] == pytest.approx(0.01)
        assert body["performance"][name]["calmar"] is None

    assert body["llm"] == {
        "trade_date": "2026-01-09", "today": 1.5, "month": 3.5, "cap": None,
        "learned_days": 1, "learning_days": 7, "unknown": True,
    }

    [position] = body["positions"]
    assert position["inst"] == "BTC-USDT-SWAP" and position["coin"] == "BTC-USD"
    assert position["qty"] == -0.02 and position["entry"] == 80_000.0
    assert position["stop"] == 85_000.0 and position["price"] == 79_000.0
    assert position["notional"] == pytest.approx(1_580.0)
    assert position["unrealized"] == pytest.approx(20.0)
    assert position["stop_distance"] == pytest.approx(6_000 / 79_000)

    latest = body["latest"]
    assert latest["trade_date"] == "2026-01-09" and latest["executed"] is True
    btc, eth, sol = latest["coins"]
    assert btc == {
        "coin": "BTC-USD", "state": "done", "rating": "Sell", "error": None, "cost_usd": 1.5,
        "fills": [{"qty": -0.02, "price": 80_000.0}],
    }
    assert eth == {
        "coin": "ETH-USD", "state": "failed", "rating": None, "error": BUDGET_ERROR,
        "cost_usd": None, "fills": [],
    }
    assert sol["state"] == "pending" and sol["cost_usd"] is None and sol["fills"] == []


def test_overview_before_the_validation_period(tmp_path):
    body = build(tmp_path, validated=False).get("/api/accounts/paper/overview").json()
    assert body["equity"] == 10_000.0 and body["positions"] == []
    assert body["validation_start"] is None and body["days"] == 0
    assert body["performance"] == {"strategy": None, "equal_weight": None, "btc": None}
    assert body["llm"]["today"] == 0 and body["llm"]["unknown"] is False
    assert body["latest"]["executed"] is False
    assert [c["state"] for c in body["latest"]["coins"]] == ["pending"] * 3


def test_equity_aligns_the_baselines_with_the_midnights(tmp_path):
    body = build(tmp_path).get("/api/accounts/paper/equity").json()
    assert body["live"] == {"ts": "2026-01-10T00:30:00Z", "equity": pytest.approx(10_020.0)}
    assert [p["ts"] for p in body["points"]] == [
        "2026-01-10T00:00:00Z", "2026-01-11T00:00:00Z", "2026-01-12T00:00:00Z"
    ]
    assert [p["strategy"] for p in body["points"]] == [10_000.0, 10_100.0, 10_050.0]
    assert [p["strategy_net"] for p in body["points"]] == [10_000.0, 10_098.5, 10_048.5]
    assert [p["equal_weight"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]
    assert [p["btc"] for p in body["points"]] == [10_000.0, pytest.approx(10_100.0), None]


def test_equity_has_no_points_before_the_validation_period(tmp_path):
    body = build(tmp_path, validated=False).get("/api/accounts/paper/equity").json()
    assert body["points"] == []
    assert body["live"]["equity"] == 10_000.0


def test_fills_newest_first_with_since_and_limit(tmp_path):
    client = build(tmp_path)
    fills = client.get("/api/accounts/paper/fills").json()
    assert [f["trade_date"] for f in fills] == ["2026-01-09", "2026-01-08"]
    assert fills[0] == {
        "ts": "2026-01-10T00:30:00Z", "inst": "BTC-USDT-SWAP", "coin": "BTC-USD", "qty": -0.02,
        "price": 80_000.0, "fee": 0.8, "reason": "trade", "trade_date": "2026-01-09",
    }
    since = client.get("/api/accounts/paper/fills", params={"since": "2026-01-10T00:00:00Z"})
    assert [f["trade_date"] for f in since.json()] == ["2026-01-09"]
    assert len(client.get("/api/accounts/paper/fills", params={"limit": 1}).json()) == 1
    assert client.get("/api/accounts/paper/fills", params={"since": "yesterday"}).status_code == 422


def test_funding_events_and_attempts(tmp_path):
    client = build(tmp_path)
    assert client.get("/api/accounts/paper/funding").json() == [{
        "ts": "2026-01-10T08:00:00Z", "inst": "BTC-USDT-SWAP", "coin": "BTC-USD",
        "rate": 0.0001, "amount": 0.16,
    }]
    assert client.get(
        "/api/accounts/paper/funding", params={"since": "2026-01-11T00:00:00Z"}
    ).json() == []
    assert client.get("/api/accounts/paper/events").json() == [
        {"ts": "2026-01-10T00:31:00Z", "kind": "resume", "text": "b"},
        {"ts": "2026-01-10T00:30:00Z", "kind": "code_change", "text": "a"},
    ]
    attempts = client.get("/api/accounts/paper/attempts").json()
    assert [(a["trade_date"], a["coin"], a["rating"]) for a in attempts] == [
        ("2026-01-09", "ETH-USD", None), ("2026-01-09", "BTC-USD", "Sell"),
        ("2026-01-09", "BTC-USD", None), ("2026-01-08", "BTC-USD", "Hold"),
    ]
    assert attempts[1] == {
        "trade_date": "2026-01-09", "coin": "BTC-USD", "ts": "2026-01-10T00:20:00Z",
        "rating": "Sell", "error": None, "tokens_in": 100, "tokens_out": 50, "cost_usd": 1.0,
    }
    assert attempts[0]["error"] == BUDGET_ERROR and attempts[0]["cost_usd"] is None


def test_accuracy_is_zero_without_a_memory_log_and_scored_with_one(tmp_path):
    client = build(tmp_path)
    assert client.get("/api/accounts/paper/accuracy").json() == {
        "resolved": 0, "pending": 0, "unscored": 0, "holding": "", "benchmark": "USDC-USD",
        "by_rating": {},
    }
    log = TradingMemoryLog({"memory_log_path": str(tmp_path / "memory" / "trading_memory.md")})
    log.store_decision("BTC-USD", "2026-01-08", "Rating: Buy\n\nx")
    log.update_with_outcome("BTC-USD", "2026-01-08", 0.03, 0.02, 5, "note", "2026-01-15")
    log.store_decision("BTC-USD", "2026-01-09", "Rating: Sell\n\nx")
    body = client.get("/api/accounts/paper/accuracy").json()
    assert body["resolved"] == 1 and body["pending"] == 1 and body["holding"] == "5 trading days"
    assert body["by_rating"] == {"Buy": {"count": 1, "hit_rate": 1.0, "mean_alpha": 0.02}}


def test_research_index_merges_the_records_with_the_attempts(tmp_path):
    rows = build(tmp_path).get("/api/research").json()
    assert rows == [
        # The record's rating over the attempts'; cost and tokens over every attempt of the day.
        {"coin": "BTC-USD", "trade_date": "2026-01-09", "rating": "Underweight", "cost_usd": 1.5,
         "tokens_in": 110, "tokens_out": 55},
        {"coin": "SOL-USD", "trade_date": "2026-01-09", "rating": "Hold", "cost_usd": None,
         "tokens_in": None, "tokens_out": None},
        {"coin": "BTC-USD", "trade_date": "2026-01-08", "rating": "Hold", "cost_usd": 2.0,
         "tokens_in": 80, "tokens_out": 40},
    ]


def test_research_record_is_served_as_written(tmp_path):
    client = build(tmp_path)
    response = client.get("/api/research/BTC-USD/2026-01-09")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["final_rating"] == "Underweight"
    assert client.get("/api/research/ETH-USD/2026-01-09").status_code == 404
    assert client.get("/api/research/BTC-USD/2026-01-07").status_code == 404


@pytest.mark.parametrize("path", [
    "/api/research/btc-usd/2026-01-09",      # lower case
    "/api/research/BTC-USD/20260109",        # not a date
    "/api/research/%2E%2E/2026-01-09",       # "..", decoded by the server
    "/api/research/.hidden/2026-01-09",
])
def test_research_record_rejects_what_is_no_coin_or_date(tmp_path, path):
    assert build(tmp_path).get(path).status_code == 422


def test_research_record_path_cannot_leave_the_results_dir(tmp_path):
    (tmp_path / "full_states_log_2026-01-09.json").write_text("{}")
    client = build(tmp_path)
    # httpx resolves the dot segments: the request never reaches the research route.
    assert client.get("/api/research/../2026-01-09").status_code == 404
    assert client.get("/api/research/../../2026-01-09").status_code == 404


def test_unknown_account_and_missing_ledger_are_404(tmp_path):
    client = build(tmp_path)
    response = client.get("/api/accounts/live/overview")
    assert response.status_code == 404 and "live" in response.json()["detail"]
    empty = TestClient(create_app(Settings(home=tmp_path / "empty"), CountingOKX()))
    [account] = [a for a in empty.get("/api/accounts").json() if a["id"] == "paper"]
    assert account["capital"] is None and account["validation_start"] is None
    response = empty.get("/api/accounts/paper/overview")
    assert response.status_code == 404 and "ledger" in response.json()["detail"]
    assert empty.get("/api/research").status_code == 404


def test_quotes_are_cached_between_requests(tmp_path):
    okx = CountingOKX()
    client = build(tmp_path, okx)
    for _ in range(3):
        client.get("/api/accounts/paper/overview")
        client.get("/api/accounts/paper/equity")
    assert okx.calls.count(("last", BTC.swap)) == 1
    assert sum(1 for kind, _ in okx.calls if kind == "bars") == 3  # one spot series per coin


def test_the_web_never_writes_the_ledger(tmp_path):
    client = build(tmp_path)
    before = (tmp_path / "ledger.sqlite").read_bytes()
    for path in ("overview", "equity", "fills", "funding", "events", "attempts", "accuracy"):
        assert client.get(f"/api/accounts/paper/{path}").status_code == 200
    assert client.get("/api/research").status_code == 200
    assert (tmp_path / "ledger.sqlite").read_bytes() == before


def test_root_without_a_built_ui_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "UI_DIST", tmp_path / "no_dist")
    response = build(tmp_path).get("/")
    assert response.status_code == 200 and "/api" in response.text


def test_a_built_ui_is_served_with_the_spa_fallback(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>ui</html>")
    (dist / "assets" / "app.js").write_text("js")
    monkeypatch.setattr(app_module, "UI_DIST", dist)
    client = build(tmp_path)
    assert client.get("/").text == "<html>ui</html>"
    assert client.get("/assets/app.js").text == "js"
    assert client.get("/research/BTC-USD").text == "<html>ui</html>"
    assert client.get("/api/nope").status_code == 404
    assert client.get("/api/accounts").status_code == 200


# -- models and the LLM settings (ADR 0007) ------------------------------------

# The .env of the machine under test: Anthropic models the catalog has not caught up
# with, spelt with dots as the API accepts them; an Anthropic key, no OpenAI key.
ENV_DEEP, ENV_QUICK = "claude-sonnet-5.5", "claude-haiku-5.5"
OPUS = {"model": "claude-opus-5-5", "provider": "anthropic", "price": None}  # priced by the table
HAIKU = {"model": "claude-haiku-5-5", "provider": "anthropic", "price": [0.2, 0.9]}
SWITCH = {"deep": OPUS, "quick": HAIKU, "confirm": True}
HAIKU_NOTE = OFFICIAL["claude-haiku-5-5"].note  # the table's remark on the price; sonnet has none
assert HAIKU_NOTE and not OFFICIAL["claude-sonnet-5-5"].note and not OFFICIAL["claude-opus-5-5"].note


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "llm_provider", "anthropic")
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_llm", ENV_DEEP)
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_llm", ENV_QUICK)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TRADER_PRICE_DEEP", "")
    monkeypatch.setenv("TRADER_PRICE_QUICK", "")


def fingerprints(home, paper=None, intraday=None):
    """Store the research fingerprints the two accounts' jobs would have recorded; the
    intraday ledger is created for it."""
    settings = Settings(home=home)
    if paper is not None:
        ledger = Ledger(settings.ledger_path)
        ledger.set("fingerprint", {"version": "0.7.1", "code": "abc", **paper})
        ledger.db.close()
    if intraday is not None:
        ledger = Ledger(settings.intraday_ledger_path)
        ledger.initialize(1_000.0, T0)
        ledger.set("fingerprint", {"prompt": "v1", **intraday})
        ledger.db.close()


def provider(body, provider_id):
    return next(p for p in body["providers"] if p["id"] == provider_id)


def test_models_shows_the_env_models_priced_by_the_table_and_the_catalog(tmp_path, llm_env):
    body = build(tmp_path).get("/api/models").json()
    assert body["current"] == {
        "deep": {"model": ENV_DEEP, "provider": "anthropic", "price": [2.0, 10.0],
                 "price_note": None},
        "quick": {"model": ENV_QUICK, "provider": "anthropic", "price": [0.1, 0.5],
                  "price_note": HAIKU_NOTE},
        "source": "env", "updated_at": None, "applied": {},  # no fingerprint recorded yet
    }
    assert body["history"] == []
    assert [p["id"] for p in body["providers"]] == list(MODEL_OPTIONS)
    assert all(m["id"] != "custom" for p in body["providers"] for m in p["models"])

    anthropic = provider(body, "anthropic")
    assert (anthropic["name"], anthropic["has_key"], anthropic["key_env"]) == (
        "Anthropic", True, "ANTHROPIC_API_KEY"
    )
    assert provider(body, "openai")["has_key"] is False
    assert (provider(body, "ollama")["has_key"], provider(body, "ollama")["key_env"]) == (True, None)
    assert provider(body, "ollama")["name"] == "Ollama（本地）"

    sonnet = next(m for m in anthropic["models"] if m["id"] == "claude-sonnet-5")
    assert sonnet["modes"] == ["quick", "deep"] and sonnet["in_catalog"] is True
    assert sonnet["label"].startswith("Claude Sonnet 5")
    assert sonnet["price"] == [2.0, 10.0] and sonnet["price_as_of"] == "2026-11-07"
    assert sonnet["price_source"].startswith("https://")
    assert sonnet["price_note"] == OFFICIAL["claude-sonnet-5"].note  # the table has a remark
    opus = next(m for m in anthropic["models"] if m["id"] == "claude-opus-5-5")
    assert opus["price"] == [4.0, 20.0] and opus["price_note"] is None  # priced, nothing to say
    unpriced = next(m for m in provider(body, "google")["models"] if m["id"] == "gemini-3.5-flash")
    assert (
        unpriced["price"], unpriced["price_source"], unpriced["price_as_of"], unpriced["price_note"]
    ) == (None,) * 4

    # The current models the catalog lacks follow their provider's list, priced by the table.
    assert anthropic["models"][-2:] == [
        {"id": ENV_QUICK, "label": ENV_QUICK, "modes": ["quick"], "price": [0.1, 0.5],
         "price_source": sonnet["price_source"], "price_as_of": "2026-11-07",
         "price_note": HAIKU_NOTE, "in_catalog": False},
        {"id": ENV_DEEP, "label": ENV_DEEP, "modes": ["deep"], "price": [2.0, 10.0],
         "price_source": sonnet["price_source"], "price_as_of": "2026-11-07",
         "price_note": None, "in_catalog": False},
    ]


def test_models_tells_per_account_whether_its_fingerprint_names_the_current_models(
    tmp_path, llm_env
):
    client = build(tmp_path)
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": ENV_QUICK}, intraday={"model": "old"})
    assert client.get("/api/models").json()["current"]["applied"] == {
        "paper": True, "intraday": False,
    }
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": "old"}, intraday={"model": ENV_DEEP})
    assert client.get("/api/models").json()["current"]["applied"] == {
        "paper": False, "intraday": True,
    }


def test_switching_the_models_writes_settings_json_and_nothing_else(tmp_path, llm_env):
    client = build(tmp_path)
    fingerprints(tmp_path, paper={"deep": ENV_DEEP, "quick": ENV_QUICK}, intraday={"model": ENV_DEEP})
    ledgers = [tmp_path / "ledger.sqlite", tmp_path / "intraday" / "ledger.sqlite"]
    before = [path.read_bytes() for path in ledgers]

    response = client.post("/api/settings/llm", json=SWITCH)
    assert response.status_code == 200, response.text
    body = response.json()
    current = body["current"]
    assert current["deep"] == {
        "model": "claude-opus-5-5", "provider": "anthropic", "price": [4.0, 20.0], "price_note": None,
    }
    # The hand-entered price is in effect; the note is still the table's remark on the model.
    assert current["quick"] == {
        "model": "claude-haiku-5-5", "provider": "anthropic", "price": [0.2, 0.9],
        "price_note": HAIKU_NOTE,
    }
    assert current["source"] == "settings"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", current["updated_at"])
    assert current["applied"] == {"paper": False, "intraday": False}  # until their next run
    assert body["history"] == [{
        "at": current["updated_at"], "deep": "claude-opus-5-5", "quick": "claude-haiku-5-5",
        "note": "web",
    }]
    # The hand-priced quick model is not in the catalog; the deep one is, so nothing is added.
    anthropic = provider(body, "anthropic")
    assert [m["id"] for m in anthropic["models"] if not m["in_catalog"]] == ["claude-haiku-5-5"]
    assert next(m for m in anthropic["models"] if m["id"] == "claude-opus-5-5")["in_catalog"]

    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["llm"] == {
        "deep_think_llm": "claude-opus-5-5", "deep_think_provider": "anthropic",
        "quick_think_llm": "claude-haiku-5-5", "quick_think_provider": "anthropic",
    }
    assert saved["prices"] == {"claude-opus-5-5": [4.0, 20.0], "claude-haiku-5-5": [0.2, 0.9]}
    assert client.get("/api/models").json() == body  # read again from the file, not cached
    assert [path.read_bytes() for path in ledgers] == before

    # The trader reads the same file: its next run researches with the new models.
    settings = Settings.with_overrides(tmp_path)
    assert (settings.price_deep, settings.price_quick) == ((4.0, 20.0), (0.2, 0.9))
    assert data.strategy(settings)["deep_model"] == "claude-opus-5-5"


def test_strategy_quotes_the_switched_models_without_a_restart(tmp_path, llm_env):
    client = build(tmp_path)
    before = client.get("/api/strategy").json()
    assert (before["deep_model"], before["quick_model"]) == (ENV_DEEP, ENV_QUICK)
    assert client.post("/api/settings/llm", json=SWITCH).status_code == 200
    after = client.get("/api/strategy").json()
    assert (after["deep_model"], after["quick_model"]) == ("claude-opus-5-5", "claude-haiku-5-5")
    assert {k: v for k, v in after.items() if k not in ("deep_model", "quick_model")} == {
        k: v for k, v in before.items() if k not in ("deep_model", "quick_model")
    }


def test_a_second_switch_extends_the_history_and_merges_the_prices(tmp_path, llm_env):
    client = build(tmp_path)
    assert client.post("/api/settings/llm", json=SWITCH).status_code == 200
    back = {
        "deep": {"model": ENV_DEEP, "provider": "anthropic", "price": None},
        "quick": {"model": "claude-haiku-5-5", "provider": "anthropic", "price": None},
        "confirm": True,
    }
    body = client.post("/api/settings/llm", json=back).json()
    assert body["current"]["deep"] == {
        "model": ENV_DEEP, "provider": "anthropic", "price": [2.0, 10.0], "price_note": None,
    }
    # A null price takes the table's, which replaces the hand-entered one saved last time.
    assert body["current"]["quick"]["price"] == [0.1, 0.5]
    assert [(h["deep"], h["quick"]) for h in body["history"]] == [
        (ENV_DEEP, "claude-haiku-5-5"), ("claude-opus-5-5", "claude-haiku-5-5"),
    ]
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["prices"] == {
        "claude-opus-5-5": [4.0, 20.0], "claude-haiku-5-5": [0.1, 0.5], ENV_DEEP: [2.0, 10.0],
    }


@pytest.mark.parametrize("change, detail", [
    ({"confirm": False}, "确认"),
    ({"deep": {**OPUS, "provider": "openai"}}, "密钥"),
    ({"deep": {**OPUS, "provider": "nobody"}}, "密钥"),
    ({"deep": {**OPUS, "model": "my-own-model"}}, "单价"),
    ({"quick": {**HAIKU, "price": [0.2, -0.9]}}, "不能为负"),
    ({"deep": {**OPUS, "model": " "}}, "模型 ID 为空"),
])
def test_a_switch_is_refused_without_confirmation_a_key_or_a_price(tmp_path, llm_env, change, detail):
    client = build(tmp_path)
    response = client.post("/api/settings/llm", json={**SWITCH, **change})
    assert response.status_code == 400 and detail in response.json()["detail"]
    assert not (tmp_path / "settings.json").exists()
    assert client.get("/api/models").json()["current"]["source"] == "env"


@pytest.mark.parametrize("body", [
    {"deep": OPUS, "confirm": True},                                  # no quick tier
    {**SWITCH, "quick": {**HAIKU, "price": [0.2, 0.9, 1.0]}},         # three numbers
    {**SWITCH, "quick": {**HAIKU, "price": "cheap"}},
    {**SWITCH, "deep": {"model": "claude-opus-5-5"}},                 # no provider
])
def test_a_misshapen_switch_is_422(tmp_path, llm_env, body):
    client = build(tmp_path)
    assert client.post("/api/settings/llm", json=body).status_code == 422
    assert not (tmp_path / "settings.json").exists()
