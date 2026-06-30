"""Shared helpers for invoking the `opencli` external binary safely.

All three social-scraper modules (twitter, youtube, reddit) centralise
opencli path resolution and ticker validation here so the logic is tested
and maintained in one place.
"""
import re
import shutil
from functools import lru_cache

# Allowlist: only uppercase/lowercase letters, digits, dot, hyphen.
# Rejects anything that could inject shell metacharacters.
_VALID_TICKER = re.compile(r"^[A-Za-z0-9.\-]{1,20}$")


def is_valid_ticker(ticker: str) -> bool:
    """Return True iff *ticker* matches the safe allowlist pattern."""
    return bool(_VALID_TICKER.fullmatch(ticker))


@lru_cache(maxsize=1)
def resolve_opencli() -> str | None:
    """Return the absolute path to the ``opencli`` executable, or ``None``.

    Uses :func:`shutil.which` so it works on every OS:

    * On POSIX the plain binary is found on PATH.
    * On Windows, ``shutil.which`` resolves the ``.cmd`` npm shim
      (``opencli.cmd``) automatically, so we never need ``shell=True``.

    Result is cached after the first call.
    """
    return shutil.which("opencli")
