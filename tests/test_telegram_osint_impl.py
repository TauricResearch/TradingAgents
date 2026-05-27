import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_get_telegram_signals_raises_when_creds_missing(monkeypatch):
    from tradingagents.dataflows.telegram_osint import get_telegram_signals
    from tradingagents.dataflows.errors import DataVendorError
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(DataVendorError, match="creds"):
        get_telegram_signals("AAPL", "2026-05-01", "2026-05-26")


@pytest.mark.unit
def test_get_telegram_signals_uses_osint_session(monkeypatch):
    from tradingagents.dataflows import telegram_osint as mod
    from tradingagents.default_config import DEFAULT_CONFIG
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "deadbeef")
    monkeypatch.setenv("TELEGRAM_OSINT_SESSION", "/tmp/iic_osint.session")
    # The vendor short-circuits when telegram_channels is empty; seed one
    # so the TelegramClient ctor actually runs and we can assert on its args.
    monkeypatch.setitem(DEFAULT_CONFIG, "telegram_channels", ["@example"])

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.iter_messages.return_value = iter([])

    with patch.object(mod, "TelegramClient", return_value=fake_client) as ctor:
        out = mod.get_telegram_signals("AAPL", "2026-05-01", "2026-05-26")
    args, kwargs = ctor.call_args
    assert "iic_osint.session" in args[0]
    assert isinstance(out, str)
