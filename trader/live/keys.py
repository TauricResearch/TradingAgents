"""The live account's API key and the production client built from it (ADR 0010).

The key is real money's, so it is kept away from everything that does not trade with
it: in a file of its own rather than in .env, which every command and the dashboard
load and which gets copied between machines, and outside TRADER_HOME, which is copied
and backed up as a whole. Only the ``live`` commands call ``load``: the key is not in
``Settings``, is never put in the environment, and importing this module reads nothing.
"""

from __future__ import annotations

import errno
import io
import os
import re
import stat
from pathlib import Path

from dotenv import dotenv_values

from trader.okx_private import OKXCredentials, OKXPrivate

# The hosts a production client may be pointed at, and no other: the one OKX's API
# documentation names for production (since 2026-05-20), and www.okx.com, which it
# named before and keeps working; the public and the demo client use the latter.
BASE_URLS = ("https://openapi.okx.com", "https://www.okx.com")
BASE_URL = BASE_URLS[0]

KEY_FILE_ENV = "TRADER_OKX_LIVE_KEY_FILE"  # a path, for a key file kept somewhere else
DEFAULT_KEY_FILE = Path("~/.config/tradingagents/okx-live.env")
NAMES = ("TRADER_OKX_LIVE_KEY", "TRADER_OKX_LIVE_SECRET", "TRADER_OKX_LIVE_PASSPHRASE")
# What a value is made of: visible ASCII characters. Anything else is a slip in the file
# that OKX would refuse at best, and that requests quotes in the error it raises at worst.
_VISIBLE_ASCII = re.compile(r"[\x21-\x7e]+")


class LiveKeyError(Exception):
    """The live key file cannot be used. The message names the file and what is wrong
    with it, never anything the file holds."""


def key_file() -> Path:
    """Where the live key is kept: the path in TRADER_OKX_LIVE_KEY_FILE, else
    ~/.config/tradingagents/okx-live.env."""
    return Path(os.getenv(KEY_FILE_ENV, "").strip() or DEFAULT_KEY_FILE).expanduser()


def load(path: Path | None = None) -> OKXCredentials:
    """The key in ``path`` (``key_file()`` by default), a dotenv file of the three
    ``NAMES``. LiveKeyError when nothing is at the path, when what is there is no regular
    file or cannot be read, when anyone but its owner may read or write it (its mode
    must be 600 or tighter), when a name has no value, or when a value holds anything
    but visible ASCII characters: a blank, a line break, a control or a non-ASCII
    character. Nothing is written to the environment."""
    path = path or key_file()
    refused = None
    try:
        # One stat, and its errors told apart below. Path.is_file() and its like turn
        # errors into False, and which of them depends on the Python version: all, from 3.14.
        status = path.stat()
        mode = stat.S_IMODE(status.st_mode)
        if not stat.S_ISREG(status.st_mode):
            refused = f"{path} 不是文件"
        elif mode & 0o077:
            refused = f"{path} 的权限是 {mode:o}，比 600 宽：先 chmod 600 再运行"
        else:
            # Read here and not by dotenv, which asks os.path.isfile() first and takes a
            # file it cannot reach for an empty one.
            text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):  # nothing there, or a file on the way to it
        refused = f"{path} 不存在"
    except PermissionError:  # mode 000, say, or a directory on the way that cannot be entered
        refused = f"{path} 读不了：没有权限"
    except OSError as exc:  # named by its errno: the system's own wording is not ours to rely on
        refused = f"{path} 读不了：{errno.errorcode.get(exc.errno, type(exc).__name__)}"
    except UnicodeDecodeError:
        refused = f"{path} 不是 UTF-8 文本"
    if refused:
        # Raised here, outside the handlers: the decoding error holds the bytes of the file
        # and says which one it stopped at, and is not to come along as this one's context.
        raise LiveKeyError(refused)
    # No interpolation: a "$" in a secret or passphrase is the character itself.
    values = dotenv_values(stream=io.StringIO(text), interpolate=False)
    found = [values.get(name) or "" for name in NAMES]
    missing = [name for name, value in zip(NAMES, found, strict=True) if not value.strip()]
    if missing:
        raise LiveKeyError(f"{path} 里缺 {'、'.join(missing)}")
    unfit = [name for name, value in zip(NAMES, found, strict=True) if not _VISIBLE_ASCII.fullmatch(value)]
    if unfit:
        raise LiveKeyError(f"{path} 里 {'、'.join(unfit)} 的值含空白、控制字符或非 ASCII 字符")
    return OKXCredentials(*found)


def client(base_url: str = BASE_URL) -> OKXPrivate:
    """The signed client of OKX's production environment, on the key in the key file.
    This is the one place that builds one (tests/test_trader_live_layering.py), and it
    builds none for a ``base_url`` that is not one of BASE_URLS: ValueError, before the
    key is read. The key's headers go to OKX and nowhere else."""
    if base_url not in BASE_URLS:
        raise ValueError(f"the live key is sent to {' or '.join(BASE_URLS)} only, not to {base_url}")
    return OKXPrivate(load(), simulated=False, base_url=base_url)
