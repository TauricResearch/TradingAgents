"""The live account's API key (ADR 0010): a file of its own, refused unless only its
owner can read it, it is complete and its values are such as a request header carries,
read into nothing but the client of OKX's production environment, which is built for
OKX's hosts alone; and no refusal says anything the file holds."""

import os
from pathlib import Path

import pytest

from tests.test_trader_okx_private import NOW, FakeSession
from trader.live import keys
from trader.okx_private import OKXCredentials, OKXPrivate

KEY, SECRET, PASSPHRASE = "live-key-1a2b", "LIVE-SECRET-9F8E", "Live#pass${HOME}$1!"
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
    text = "# the live account's key\n" + "".join(f"{line}\n" for line in lines.values() if line)
    path.write_text(text, encoding="utf-8")
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
    # The quoted passphrase keeps its "#" and its "${HOME}": nothing is cut off or interpolated.
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
    # Nor is anything at a path that runs through a file.
    (tmp_path / "plain").write_text("no directory\n")
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(tmp_path / "plain" / "okx-live.env")
    assert str(info.value) == f"{tmp_path / 'plain' / 'okx-live.env'} 不存在"


def test_what_is_at_the_path_but_is_no_regular_file_is_refused_unread(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *args, **options: pytest.fail("it was read"))
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(tmp_path)  # a directory
    assert str(info.value) == f"{tmp_path} 不是文件"


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o666, 0o700 | 0o020, 0o601])
def test_a_key_file_others_can_read_or_write_is_refused_unread(tmp_path, monkeypatch, mode):
    path = write_key_file(tmp_path / "okx-live.env", mode=mode)
    monkeypatch.setattr(Path, "read_text", lambda *args, **options: pytest.fail("the file was read"))
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


@pytest.mark.parametrize("over, unfit", [
    # In double quotes dotenv reads \n as a line break: requests would quote the whole value
    # in the error it raises on sending it.
    ({"TRADER_OKX_LIVE_PASSPHRASE": 'TRADER_OKX_LIVE_PASSPHRASE="Ab\\ncd1!"'}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_PASSPHRASE": "TRADER_OKX_LIVE_PASSPHRASE='Ab cd1!'"}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_PASSPHRASE": "TRADER_OKX_LIVE_PASSPHRASE=' Abcd1!'"}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_PASSPHRASE": "TRADER_OKX_LIVE_PASSPHRASE='Pass口令1!'"}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_PASSPHRASE": "TRADER_OKX_LIVE_PASSPHRASE=Ab\x7fcd1!"}, "TRADER_OKX_LIVE_PASSPHRASE"),
    ({"TRADER_OKX_LIVE_KEY": 'TRADER_OKX_LIVE_KEY="live\\tkey"'}, "TRADER_OKX_LIVE_KEY"),
    ({"TRADER_OKX_LIVE_KEY": "TRADER_OKX_LIVE_KEY=kéy-1a2b"}, "TRADER_OKX_LIVE_KEY"),
    ({"TRADER_OKX_LIVE_SECRET": "TRADER_OKX_LIVE_SECRET=密钥9F8E"}, "TRADER_OKX_LIVE_SECRET"),
    ({"TRADER_OKX_LIVE_KEY": "TRADER_OKX_LIVE_KEY='live key'",
      "TRADER_OKX_LIVE_PASSPHRASE": 'TRADER_OKX_LIVE_PASSPHRASE="Ab\\rcd1!"'},
     "TRADER_OKX_LIVE_KEY、TRADER_OKX_LIVE_PASSPHRASE"),
])
def test_a_value_that_is_not_visible_ascii_is_refused_naming_only_its_variable(tmp_path, over, unfit):
    path = write_key_file(tmp_path / "okx-live.env", **over)
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    # The whole message: the path, the variable, what is wrong. Nothing of the value.
    assert str(info.value) == f"{path} 里 {unfit} 的值含空白、控制字符或非 ASCII 字符"


def test_a_key_file_its_owner_cannot_read_is_refused_as_a_key_file(tmp_path):
    path = write_key_file(tmp_path / "okx-live.env", mode=0o000)
    if os.access(path, os.R_OK):
        pytest.skip("this user reads a file whatever its mode")
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    assert str(info.value) == f"{path} 读不了：没有权限"


def test_a_key_file_in_a_directory_that_cannot_be_entered_is_refused_as_a_key_file(tmp_path):
    (tmp_path / "locked").mkdir()
    path = write_key_file(tmp_path / "locked" / "okx-live.env")
    path.parent.chmod(0o000)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("this user enters a directory whatever its mode")
        with pytest.raises(keys.LiveKeyError) as info:
            keys.load(path)
    finally:
        path.parent.chmod(0o700)
    # Not "不存在": Path.is_file() says False of it from Python 3.14 on, where it raised before.
    assert str(info.value) == f"{path} 读不了：没有权限"


def test_any_other_error_of_the_system_is_named_by_its_errno(tmp_path):
    path = tmp_path / "okx-live.env"
    path.symlink_to(path)  # a link to itself: following it never arrives
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    assert str(info.value) == f"{path} 读不了：ELOOP"


def test_a_key_file_that_is_not_utf8_text_is_refused_without_a_byte_of_it(tmp_path):
    path = tmp_path / "okx-live.env"
    path.write_bytes(b"TRADER_OKX_LIVE_KEY=live-key-1a2b\nTRADER_OKX_LIVE_SECRET=\xff\xfeL\x00I\x00V\x00E\x00\n")
    path.chmod(0o600)
    with pytest.raises(keys.LiveKeyError) as info:
        keys.load(path)
    assert str(info.value) == f"{path} 不是 UTF-8 文本"
    # The decoding error it replaces holds the file's bytes and says which one it stopped
    # at: it does not come along, as cause or as context.
    assert info.value.__cause__ is None and info.value.__context__ is None


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
        [(("GET", "/api/v5/account/balance?ccy=USDT"), [{"details": [{"ccy": "USDT", "eq": "1", "cashBal": "1", "availBal": "1"}]}])], base_url="https://openapi.okx.com"
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


def test_the_hosts_a_production_client_may_be_pointed_at_are_okxs_two():
    assert keys.BASE_URLS == ("https://openapi.okx.com", "https://www.okx.com")
    assert keys.BASE_URL == "https://openapi.okx.com"


@pytest.mark.parametrize("url", [
    "https://elsewhere.example", "http://openapi.okx.com", "https://us.okx.com", "https://openapi.okx.com/",
    "https://openapi.okx.com@elsewhere.example", "https://OPENAPI.okx.com", "", None,
])
def test_no_client_is_built_for_any_other_host_and_the_key_is_not_read_for_one(key_path, monkeypatch, url):
    monkeypatch.setattr(keys, "load", lambda *args: pytest.fail("the key file was read"))
    monkeypatch.setattr(keys, "OKXPrivate", lambda *args, **options: pytest.fail("a client was built"))
    with pytest.raises(ValueError, match="the live key is sent to https://openapi.okx.com or https://www.okx.com only"):
        keys.client(url)
