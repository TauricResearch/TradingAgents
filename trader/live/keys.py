"""The live account's API key and the production client built from it (ADR 0010).

The key is real money's, so it is kept away from everything that does not trade with
it: in a file of its own rather than in .env, which every command and the dashboard
load and which gets copied between machines, and outside TRADER_HOME, which is copied
and backed up as a whole. Only the ``live`` commands call ``load``: the key is not in
``Settings``, is never put in the environment, and importing this module reads nothing.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from dotenv import dotenv_values

from trader.okx_private import OKXCredentials, OKXPrivate

# OKX's production REST host, as its API documentation names it (since 2026-05-20;
# www.okx.com, which the public and the demo client use, keeps working).
BASE_URL = "https://openapi.okx.com"

KEY_FILE_ENV = "TRADER_OKX_LIVE_KEY_FILE"  # a path, for a key file kept somewhere else
DEFAULT_KEY_FILE = Path("~/.config/tradingagents/okx-live.env")
NAMES = ("TRADER_OKX_LIVE_KEY", "TRADER_OKX_LIVE_SECRET", "TRADER_OKX_LIVE_PASSPHRASE")


class LiveKeyError(Exception):
    """The live key file cannot be used. The message names the file and what is wrong
    with it, never anything the file holds."""


def key_file() -> Path:
    """Where the live key is kept: the path in TRADER_OKX_LIVE_KEY_FILE, else
    ~/.config/tradingagents/okx-live.env."""
    return Path(os.getenv(KEY_FILE_ENV, "").strip() or DEFAULT_KEY_FILE).expanduser()


def load(path: Path | None = None) -> OKXCredentials:
    """The key in ``path`` (``key_file()`` by default), a dotenv file of the three
    ``NAMES``. LiveKeyError when the file is missing, when anyone but its owner may
    read or write it (its mode must be 600 or tighter), or when a name has no value.
    Nothing is written to the environment."""
    path = path or key_file()
    if not path.is_file():
        raise LiveKeyError(f"{path} 不存在")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise LiveKeyError(f"{path} 的权限是 {mode:o}，比 600 宽：先 chmod 600 再运行")
    # No interpolation: a "$" in a secret or passphrase is the character itself.
    values = dotenv_values(path, interpolate=False)
    found = [(values.get(name) or "").strip() for name in NAMES]
    missing = [name for name, value in zip(NAMES, found, strict=True) if not value]
    if missing:
        raise LiveKeyError(f"{path} 里缺 {'、'.join(missing)}")
    return OKXCredentials(*found)


def client(base_url: str = BASE_URL) -> OKXPrivate:
    """The signed client of OKX's production environment, on the key in the key file.
    This is the one place that builds one (tests/test_trader_live_layering.py)."""
    return OKXPrivate(load(), simulated=False, base_url=base_url)
