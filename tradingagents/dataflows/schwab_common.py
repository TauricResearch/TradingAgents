"""Shared Schwab Market Data helpers: errors, token discovery, client, candles.

Schwab is an **opt-in** OHLCV / technical-indicator vendor for US equities and
ETFs. TradingAgents does **not** implement an OAuth login — it consumes a
``token.json`` produced by **any schwab-py login** and lets ``schwab-py``
refresh the access token as needed.

Key facts baked into this module (verified against schwab-py source, see the
plan's step 12):

- ``schwab-py`` is an **optional** dependency. Its import is deferred into
  ``get_client()`` so a clean install without the ``schwab`` extra never fails
  at import time (the module top level must not import ``schwab``/``httpx``).
- ``schwab-py``'s HTTP client is authlib's ``OAuth2Client`` (an ``httpx.Client``
  subclass); responses are ``httpx.Response`` and the client **never** raises on
  a non-200 status. Status-code classification lives in the vendor layer.
- ``client_from_token_file`` (NOT ``easy_client``) is used: it only refreshes the
  access token via the refresh token and never opens a browser login flow, so it
  is safe headless. It requires a *wrapped* token (top-level
  ``creation_timestamp``), which a schwab-py-written ``token.json`` satisfies.
"""

from __future__ import annotations

import json
import os
from datetime import timezone

import pandas as pd

from .errors import VendorNotConfiguredError, VendorRateLimitError

# Column order stockstats and the OHLCV CSV format expect (title-case). The
# reference ``_helpers.py`` produces a lowercase dict — we deliberately do NOT
# copy that casing; stockstats requires title-case ``Open/High/Low/Close``.
_OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class SchwabNotConfiguredError(VendorNotConfiguredError):
    """Raised when Schwab is selected but cannot be used.

    Covers a missing/incompatible token, absent ``SCHWAB_APP_KEY`` /
    ``SCHWAB_APP_SECRET``, or ``schwab-py`` not being installed. As a
    ``VendorNotConfiguredError`` (hence ``ValueError``), the router treats it as
    "vendor unavailable" and falls back to the next configured vendor.
    """


class SchwabRateLimitError(VendorRateLimitError):
    """Raised on HTTP 429 from Schwab so the router skips to the next vendor."""


def resolve_token_path() -> str:
    """Locate a schwab-py ``token.json``.

    Search order (first match wins), accepting **both** environment variable
    names so users who already set the US-Stock-Analysis
    ``SCHWAB_NATIVE_TOKEN_PATH`` do not have to duplicate it:

    1. ``$SCHWAB_TOKEN_PATH`` (this project's preferred name).
    2. ``$SCHWAB_NATIVE_TOKEN_PATH`` (US-Stock-Analysis compatibility).
    3. ``$XDG_STATE_HOME/schwab-marketdata-mcp/token.json``.
    4. ``~/.local/state/schwab-marketdata-mcp/token.json``.
    5. ``~/.config/schwab-marketdata-mcp/token.json`` (legacy).

    The default-location directory names follow the schwab-marketdata-mcp
    convention (one common source of the token); an explicit
    ``SCHWAB_TOKEN_PATH`` overrides them for tokens produced by any other
    schwab-py login.

    An explicit path from either env var is returned even if it does not exist
    (so ``get_client`` reports a clear "token not found" via the loader);
    discovered candidates must exist to be returned.

    Raises:
        SchwabNotConfiguredError: when no token file can be located.
    """
    for env_var in ("SCHWAB_TOKEN_PATH", "SCHWAB_NATIVE_TOKEN_PATH"):
        explicit = os.environ.get(env_var)
        if explicit:
            return os.path.expanduser(explicit)

    candidates: list[str] = []
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        candidates.append(
            os.path.join(xdg_state, "schwab-marketdata-mcp", "token.json")
        )
    home = os.path.expanduser("~")
    candidates.append(
        os.path.join(home, ".local", "state", "schwab-marketdata-mcp", "token.json")
    )
    candidates.append(
        os.path.join(home, ".config", "schwab-marketdata-mcp", "token.json")
    )

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    raise SchwabNotConfiguredError(
        "Schwab token file not found. Set SCHWAB_TOKEN_PATH (or "
        "SCHWAB_NATIVE_TOKEN_PATH) to a token.json produced by any schwab-py "
        "login. "
        f"Searched: {candidates}."
    )


# Process-wide client singleton. Reused across calls so the refresh token is
# shared through one schwab-py client (its authlib session refreshes and writes
# the token back atomically). Reset in tests via ``_reset_client_cache()``.
_client_cache = None


def _reset_client_cache() -> None:
    """Drop the cached client so tests don't leak a fake across cases."""
    global _client_cache
    _client_cache = None


def get_client():
    """Return a cached synchronous schwab-py ``Client``, or raise if unusable.

    Uses ``schwab.auth.client_from_token_file(..., asyncio=False)`` which reuses
    the existing token and only refreshes the access token as needed — it never
    triggers a browser login (unlike ``easy_client``, which deletes tokens older
    than ~6.5 days and falls through to a login flow that hangs headless).

    ``schwab-py`` is imported lazily here so a clean install without the
    ``schwab`` extra never fails at module import.

    Raises:
        SchwabNotConfiguredError: when ``schwab-py`` is not installed, the
            credentials are missing, or the token file is missing/incompatible
            (e.g. a non-wrapped token lacking ``creation_timestamp``).
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    app_key = os.environ.get("SCHWAB_APP_KEY")
    app_secret = os.environ.get("SCHWAB_APP_SECRET")
    if not app_key or not app_secret:
        raise SchwabNotConfiguredError(
            "SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set (your Schwab "
            "developer app credentials) to refresh the Schwab access token."
        )

    # resolve_token_path may raise SchwabNotConfiguredError; let it propagate.
    token_path = resolve_token_path()

    try:
        # Deferred import: the schwab extra is optional, so importing at module
        # top level would break a clean install without it (and the smoke test).
        from schwab.auth import client_from_token_file

        client = client_from_token_file(
            token_path, app_key, app_secret, asyncio=False
        )
    except SchwabNotConfiguredError:
        raise
    except (
        ImportError,
        ValueError,
        KeyError,
        FileNotFoundError,
        json.JSONDecodeError,
    ) as exc:
        # ImportError: schwab-py not installed. ValueError: TokenMetadata
        # rejected a non-wrapped token (no creation_timestamp). The others cover
        # a missing/corrupt token file. All mean "Schwab unavailable" -> fall
        # back to yfinance.
        raise SchwabNotConfiguredError(
            "Schwab client unavailable (schwab-py not installed, or the token "
            "is missing/incompatible). Install with `pip install "
            "\".[schwab]\"` and produce a compatible token via any schwab-py "
            f"login. Cause: {exc}"
        ) from exc

    _client_cache = client
    return client


def candles_to_ohlcv_df(resp_json: dict) -> pd.DataFrame:
    """Convert a Schwab price-history payload to a title-case OHLCV DataFrame.

    Schwab returns ``{"candles": [{"open","high","low","close","volume",
    "datetime"}, ...], ...}`` where ``datetime`` is **epoch milliseconds**
    (verified via the reference ``_helpers.py``). The returned frame has:

    - Columns ``Date, Open, High, Low, Close, Volume`` (title-case: stockstats
      requires it; the lowercase reference dict is NOT copied).
    - ``Date`` as **tz-naive** ``datetime64`` (day granularity). We derive the
      calendar date from the epoch-ms via UTC — matching the reference — then
      keep it tz-naive so downstream date comparisons (look-ahead trimming,
      ``_coerce_ohlcv_dates``) never hit a tz-aware ``TypeError``.

      TODO(实测): confirm whether Schwab's daily ``datetime`` ms is US/Eastern
      midnight or UTC midnight. With no live Schwab credential here we follow the
      reference's UTC interpretation; because we collapse to a calendar date this
      only matters at the UTC/ET day boundary. Either way the frame is tz-naive.
    - Rows sorted ascending by ``Date`` (stockstats' ``wrap()`` assumes ascending
      order; the reference does not sort).
    - Duplicate ``Date`` rows dropped keeping the **last** (a tz-boundary or
      after-hours bar can produce two rows for one day; the later one wins).
    - Rows with a null ``Close`` dropped (a Schwab halted-session candle may have
      a null close; dropping is safer than keeping it). We deliberately do
      **not** ffill and do **not** call ``_clean_dataframe`` here — the OHLCV
      path must not fabricate prices. Cleaning happens only on the indicator
      path.

    Emptiness is judged solely by ``candles`` being missing/empty; we do **not**
    assume a top-level ``empty`` field exists.

    Returns:
        A DataFrame that may be empty (caller maps that to ``NoMarketDataError``).
    """
    candles = None
    if isinstance(resp_json, dict):
        candles = resp_json.get("candles")

    if not candles:
        # Missing or empty candles -> no usable rows. Return an empty, correctly
        # shaped frame so the caller's emptiness check is uniform.
        return pd.DataFrame(columns=["Date", *_OHLCV_COLUMNS])

    df = pd.DataFrame(candles)

    # Epoch ms -> tz-naive calendar-date datetime64. Convert via UTC then strip
    # tz so the column is tz-naive (see docstring TODO on the tz choice).
    epoch_ms = pd.to_numeric(df.get("datetime"), errors="coerce")
    df["Date"] = (
        pd.to_datetime(epoch_ms, unit="ms", utc=True)
        .dt.tz_convert(timezone.utc)
        .dt.tz_localize(None)
        .dt.normalize()
    )

    rename_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    df = df.rename(columns=rename_map)

    keep = ["Date", *[c for c in _OHLCV_COLUMNS if c in df.columns]]
    df = df[keep]

    # Ascending order (stockstats assumes it); then dedupe by day keeping the
    # later bar; then drop halted-session null-close rows (never ffill here).
    df = df.sort_values("Date").reset_index(drop=True)
    df = df.drop_duplicates(subset=["Date"], keep="last")
    if "Close" in df.columns:
        df = df.dropna(subset=["Close"])

    return df.reset_index(drop=True)
