"""The live account's API key (ADR 0010): a file of its own, refused unless only its
owner can read it and it is complete, read into nothing but the client of OKX's
production environment; and no refusal says anything the file holds."""

import os
from pathlib import Path

import pytest

from tests.test_trader_okx_private import NOW, FakeSession
from trader.live import keys
from trader.okx_private import OKXCredentials, OKXPrivate

KEY, SECRET, PASSPHRASE = "live-key-1a2b", "LIVE-SECRET-9F8E", "Live#pass ${HOME} $1"
SECRETS = (KEY, SECRET, PASSPHRASE, "Live#pass")


def write_key_file(path: Path, mode=0o600, **over) -> Path:
    """A key file as deploy/trader.env.example describes it; ``over`` replaces a
    variable's whole line (None drops it)."""
    lines = {
        "TRADER_OKX_LIVE_KEY": f"TRADER_OKX_LIVE_KEY={KEY}",
        "TRADER_OKX_LIVE_SECRET": f"TRADER_OKX_LIVE_SECRET = {SECRET}  ",
        "TRADER_OKX_LIVE_PASSPHRASE": f"TRADER_OKX_LIVE_PASSPHRASE='{PASSPHRASE}'",
    }
    lines.update(over)
    path.write_text("# the live account's key\n" + "".join(f"{line}\n" for line in lines.values() if line))
    path.chmod(mode)
    return path


@pytest.fixture
def key_path(tmp_path, monkeypatch):
    """A complete key file with mode 600 that the environment points at."""
    path = write_key_file(tmp_path / "okx-live.env")
    monkeypatch.setenv(keys.KEY_FILE_ENV, str(path))
    return path


def test_the_key_file_is_in_the_users_config_unless_the_environment_names_another(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TRADER_OKX_LIVE_KEY_FILE", raising=False)
    assert keys.key_file() == tmp_path / ".config" / "tradingagents" / "okx-live.env"
    monkeypatch.setenv("TRADER_OKX_LIVE_KEY_FILE", "  ")
    assert keys.key_file() == tmp_path / ".config" / "tradingagents" / "okx-live.env"
    monkeypatch.setenv("TRADER_OKX_LIVE_KEY_FILE", "~/elsewhere/live.env")
    assert keys.key_file() == tmp_path / "elsewhere" / "live.env"


def test_the_key_is_read_as_written_and_nothing_is_put_in_the_environment(key_path):
    before = dict(os.environ)
    creds = keys.load()
    # The quoted passphrase keeps its "#", its spaces and its "$": nothing is interpolated.
    assert creds == OKXCredentials(KEY, SECRET, PASSPHRASE)
    assert keys.load(key_path) == creds
    assert dict(os.environ) == before
    assert not any(name in os.environ for name in keys.NAMES)
    assert repr(creds) == "OKXCredentials(***)"


def test_a_missing_key_file_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "nowhere" / "okx-live.env"
    monkeypatch.setenv(keys.KEY_FILE_ENV, str(path))
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load()
    assert str(info.value) == f"{path} 不存在"
    with pytest.raises(keys.LiveKeyError, match="不存在"):  # a directory is no key file either
        keys.load(tmp_path)


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o666, 0o700 | 0o020, 0o601])
def test_a_key_file_others_can_read_or_write_is_refused_unread(tmp_path, monkeypatch, mode):
    path = write_key_file(tmp_path / "okx-live.env", mode=mode)
    monkeypatch.setattr(keys, "dotenv_values", lambda *args, **options: pytest.fail("the file was read"))
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    assert str(info.value) == f"{path} 的权限是 {mode:o}，比 600 宽：先 chmod 600 再运行"
    assert not any(secret in str(info.value) for secret in SECRETS)


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_a_key_file_only_its_owner_can_read_is_accepted(tmp_path, mode):
    path = write_key_file(tmp_path / "okx-live.env", mode=mode)
    assert keys.load(path).key == KEY


@pytest.mark.parametrize("over, missing", [
    ({"TRADER_OKX_LIVE_PASSPHRASE": None}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_SECRET": "TRADER_OKX_LIVE_SECRET="}, "TRADER_OKX_LIVE_SECRET"),
    ({"TRADER_OKX_LIVE_KEY": "TRADER_OKX_LIVE_KEY"}, "TRADER_OKX_LIVE_KEY"),
    ({"TRADER_OKX_LIVE_KEY": "TRADER_OKX_LIVE_KEY='  '", "TRADER_OKX_LIVE_SECRET": None},
     "TRADER_OKX_LIVE_KEY、TRADER_OKX_LIVE_SECRET"),
    (dict.fromkeys(keys.NAMES), "、".join(keys.NAMES)),
])
def test_an_incomplete_key_file_is_refused_naming_only_the_missing_variables(tmp_path, over, missing):
    path = write_key_file(tmp_path / "okx-live.env", **over)
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    assert str(info.value) == f"{path} 里缺 {missing}"
    assert not any(secret in str(info.value) for secret in SECRETS)


def test_the_demo_variables_are_no_live_key(tmp_path, monkeypatch):
    # The demo key of .env, whether in the environment or in the file, is not read as the live one.
    for part in ("KEY", "SECRET", "PASSPHRASE"):
        monkeypatch.setenv(f"TRADER_OKX_DEMO_{part}", f"demo-{part.lower()}")
        monkeypatch.setenv(f"TRADER_OKX_LIVE_{part}", f"env-{part.lower()}")
    path = tmp_path / "okx-live.env"
    path.write_text("TRADER_OKX_DEMO_KEY=k\nTRADER_OKX_DEMO_SECRET=s\nTRADER_OKX_DEMO_PASSPHRASE=p\n")
    path.chmod(0o600)
    with pytest.raises(keys.LiveKeyError, match="里缺 TRADER_OKX_LIVE_KEY、"):
        keys.load(path)


def test_the_client_of_the_key_file_is_a_production_one_on_okxs_documented_host(key_path, monkeypatch):
    session = FakeSession(
        [(("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": []}])], base_url="https://openapi.okx.com"
    )
    monkeypatch.setattr(
        keys, "OKXPrivate", lambda creds, **options: OKXPrivate(creds, session=session, clock=lambda: NOW, **options)
    )
    client = keys.client()
    assert (client.simulated, client.base_url, repr(client)) == (False, "https://openapi.okx.com", "OKXPrivate(live)")
    client.balance()
    assert session.urls == ["https://openapi.okx.com/api/v5/account/balance?ccy=USDT"]
    headers = session.calls[0][3]
    assert "x-simulated-trading" not in headers
    assert (headers["OK-ACCESS-KEY"], headers["OK-ACCESS-PASSPHRASE"]) == (KEY, PASSPHRASE)
    assert keys.client("https://www.okx.com").base_url == "https://www.okx.com"
    assert not any(secret in repr(client) for secret in SECRETS)


def test_no_client_is_built_from_a_key_file_that_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(keys.KEY_FILE_ENV, str(write_key_file(tmp_path / "okx-live.env", mode=0o644)))
    monkeypatch.setattr(keys, "OKXPrivate", lambda *args, **options: pytest.fail("a client was built"))
    with pytest.raises(keys.LiveKeyError):
        keys.client()
