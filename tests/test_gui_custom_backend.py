from gui.config import _empty_config
from gui import storage
from gui.chat import _llm_settings
from service.schemas import RunCreateRequest


def test_gui_defaults_include_custom_backend_url():
    cfg = _empty_config()

    assert cfg["defaults"]["backend_url"] == ""


def test_run_create_request_accepts_custom_backend_url():
    req = RunCreateRequest(
        ticker="SPY",
        trade_date="2026-05-08",
        llm_provider="openai",
        deep_think_llm="custom-deep",
        quick_think_llm="custom-quick",
        backend_url="https://llm.example.com/v1",
    )

    assert req.backend_url == "https://llm.example.com/v1"


def test_storage_persists_run_backend_url(tmp_path, monkeypatch):
    db_path = tmp_path / "gui.db"
    monkeypatch.setattr(storage, "DB_PATH", db_path)

    storage.init_db()
    storage.create_run(
        run_id="run-1",
        ticker="SPY",
        trade_date="2026-05-08",
        provider="openai",
        deep_model="custom-deep",
        quick_model="custom-quick",
        debate_rounds=1,
        risk_rounds=1,
        vendors={"core_stock_apis": "yfinance"},
        backend_url="https://llm.example.com/v1",
    )

    row = storage.get_run("run-1")

    assert row is not None
    assert row["backend_url"] == "https://llm.example.com/v1"


def test_llm_settings_prefers_run_backend_url(monkeypatch):
    monkeypatch.setattr(
        "gui.chat.load_config",
        lambda: {
            "defaults": {
                "llm_provider": "openai",
                "quick_think_llm": "default-quick",
                "backend_url": "https://default.example.com/v1",
            }
        },
    )

    provider, model, backend_url = _llm_settings(
        {
            "provider": "openai",
            "quick_model": "run-quick",
            "backend_url": "https://run.example.com/v1",
        }
    )

    assert provider == "openai"
    assert model == "run-quick"
    assert backend_url == "https://run.example.com/v1"
