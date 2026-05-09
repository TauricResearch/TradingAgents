from gui.config import _empty_config
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
