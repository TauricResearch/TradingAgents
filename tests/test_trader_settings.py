"""What the repr of ``Settings`` shows, which a log line, an exception or a failing
assertion may print: everything but the secrets."""

from trader.settings import Settings

SECRETS = {
    "TRADER_TELEGRAM_TOKEN": "123456:bot-token-of-the-tests",
    "TRADER_WEB_TOKEN": "web-token-of-the-tests",
    "TRADER_LIVE_HEARTBEAT_URL": "https://hc-ping.example/beat-of-the-tests",
    "TRADER_OKX_DEMO_KEY": "okx-key-of-the-tests",
    "TRADER_OKX_DEMO_SECRET": "okx-secret-of-the-tests",
    "TRADER_OKX_DEMO_PASSPHRASE": "okx-passphrase-of-the-tests",
}


def test_the_repr_leaves_out_every_secret_the_settings_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADER_TELEGRAM_CHAT_ID", "chat-of-the-tests")
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    settings = Settings.from_env()
    assert settings.telegram_token == SECRETS["TRADER_TELEGRAM_TOKEN"]
    assert settings.web_token == SECRETS["TRADER_WEB_TOKEN"]
    assert settings.live_heartbeat_url == SECRETS["TRADER_LIVE_HEARTBEAT_URL"]
    assert settings.okx_demo is not None
    text = repr(settings)
    assert [name for name, value in SECRETS.items() if value in text] == []
    assert "chat-of-the-tests" in text and repr(tmp_path) in text
