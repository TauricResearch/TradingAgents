"""DEBYKO perpetual context, separate from the daily OHLCV/indicator path."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.symbols import crypto_base, normalize_symbol

API_BASE = "https://api.debyko.com"
LAYERS = ("ticker", "mark", "funding", "oi", "stats")
MAX_SETTLEMENT_PAGES = 3
PAGE_SIZE = 100


def _instrument(ticker: str) -> str:
    symbol = normalize_symbol(ticker)
    if isinstance(symbol, str) and re.fullmatch(r"[A-Z0-9]{1,30}-PERP", symbol):
        return symbol
    # Spot-style symbols must never silently become derivatives. This is a
    # separate, explicit consent, not merely the graph's generic crypto mode.
    if get_config().get("debyko_allow_crypto_pairs") is True:
        base = crypto_base(symbol)
        if base:
            return f"{base}-PERP"
    raise NoMarketDataError(ticker, detail="DEBYKO context requires -PERP; crypto pairs need explicit opt-in")


def _now() -> datetime:
    return datetime.now(UTC)


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        pass
    raise VendorUnavailableError("DEBYKO returned an invalid settlement timestamp")


def _request(method: str, path: str, key: str, **kwargs) -> dict:
    """Fixed origin, header authentication, bounded requests, no secret-bearing errors."""
    error = None
    try:
        response = requests.request(
            method,
            API_BASE + path,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=(5, 20),
            allow_redirects=False,
            **kwargs,
        )
        if response.status_code != 200:
            error = f"DEBYKO {path} returned HTTP {response.status_code}"
        else:
            payload = response.json()
            if (isinstance(payload, dict) and isinstance(payload.get("items"), list)
                    and all(isinstance(row, dict) for row in payload["items"])):
                return payload
            error = f"DEBYKO {path} returned an invalid data envelope"
    except (requests.RequestException, ValueError) as exc:
        error = f"DEBYKO {path} unavailable: {str(exc).replace(key, '***')}"
    # Outside the except block: request/response objects may carry auth headers.
    raise VendorUnavailableError(error)


def _snapshot(payload: dict, instrument: str) -> list[dict]:
    result = []
    for row in payload["items"]:
        if row.get("instrument") != instrument or row.get("kind") != "perpetual":
            continue
        layers = {}
        for name in LAYERS:
            sources = row.get("layers", {})
            if not isinstance(sources, dict) or not isinstance(sources.get(name, {}), dict):
                raise VendorUnavailableError("DEBYKO returned invalid snapshot layers")
            source = sources.get(name, {})
            layer = {k: source[k] for k in (
                "status", "reason", "venue_ts", "received_at", "age_ms", "valid_until"
            ) if k in source}
            if not layer:
                layer = {"status": "missing", "reason": "layer_not_returned"}
            # Even an unexpected stale response containing values/withheld must
            # not turn into a number in an analyst's context.
            if source.get("status") == "present":
                if not all(isinstance(source.get(k, {}), dict) for k in ("values", "units")):
                    raise VendorUnavailableError("DEBYKO returned invalid snapshot values/units")
                layer["values"] = source.get("values", {})
                layer["units"] = source.get("units", {})
            layers[name] = layer
        result.append({**{k: row[k] for k in (
            "instrument", "venue", "venue_symbol", "quote"
        ) if k in row}, "layers": layers})
    return result


def _comparison(rows: list[dict]) -> dict:
    rates = []
    for row in rows:
        funding = row["layers"]["funding"]
        if funding.get("status") != "present":
            continue
        rate = funding.get("values", {}).get("funding_8h")
        if funding.get("units", {}).get("funding_8h") != "fraction":
            continue
        try:
            value = Decimal(str(rate))
        except InvalidOperation:
            continue
        if value.is_finite():
            rates.append((value, row, rate))

    def entry(pair):
        _, row, rate = pair
        return {"venue": row["venue"], "venue_symbol": row["venue_symbol"],
                "funding_8h": rate, "unit": "fraction",
                "venue_ts": row["layers"]["funding"].get("venue_ts")}

    return {
        "basis": "API funding_8h, fraction per 8h; present values only; OI is not summed",
        "lowest_rate": entry(min(rates, key=lambda x: x[0])) if rates else None,
        "highest_rate": entry(max(rates, key=lambda x: x[0])) if rates else None,
    }


def get_perpetual_context(ticker: str, as_of_date: str | None = None) -> str:
    """Per-venue funding/OI/prices/stats and a bounded trailing-day settlement window.

    Past runs withhold live snapshots. Settlement times, origin and missing
    statuses remain explicit; this is not candle data or a price feed.
    """
    instrument = _instrument(ticker)
    key = os.getenv("DEBYKO_API_KEY", "").strip()
    if not key:
        raise VendorNotConfiguredError("DEBYKO_API_KEY environment variable is not set")
    now = _now()
    day = datetime.strptime(as_of_date, "%Y-%m-%d").replace(tzinfo=UTC) if as_of_date else now
    if day.date() > now.date():
        raise NoMarketDataError(ticker, instrument, "analysis date is in the future")
    historical = day.date() < now.date()
    end = day + timedelta(days=1) if historical else now
    start = end - timedelta(days=1)
    where = f"instrument = {instrument}"
    snapshot = None if historical else _request("POST", "/v2/snapshots", key, json={
        "where": where, "layers": list(LAYERS), "kind": "perpetual",
        "number_format": "string", "units": "published",
    })
    rows = [] if snapshot is None else _snapshot(snapshot, instrument)
    query = {"where": where, "from": start.isoformat(), "to": end.isoformat(),
             "number_format": "string", "order": "desc", "limit": PAGE_SIZE}
    settlements, not_recorded = [], []
    cursor, settlement_error = None, None
    try:
        for _ in range(MAX_SETTLEMENT_PAGES):
            page = _request("GET", "/v2/funding/settlements", key, params=query.copy())
            not_recorded.extend(x for x in page.get("not_recorded", []) if x not in not_recorded)
            for row in page["items"]:
                if row.get("instrument") != instrument or row.get("kind") != "perpetual":
                    continue
                if not start < _instant(row.get("time")) <= end:
                    continue
                item = dict(row)
                if item.get("status") != "present":
                    for field in ("rate", "rate_8h", "cap", "floor", "cap_8h", "floor_8h", "at_cap"):
                        item.pop(field, None)
                settlements.append(item)
            cursor = page.get("next_cursor")
            if not cursor:
                break
            query["cursor"] = cursor
    except VendorUnavailableError as exc:
        if not rows and not settlements:
            raise
        settlement_error = str(exc)
    if not rows and not settlements and not not_recorded:
        raise NoMarketDataError(ticker, instrument, "no snapshot or settlement rows in this window")
    data = {
        "requested_ticker": ticker, "instrument": instrument,
        "notice": "Perpetual derivatives context only, not spot quotes, OHLCV or daily indicators. "
                  "Rates are fractions, with each venue's own interval and units. "
                  "Unknown is not zero. Do not use non-present layers as numbers.",
        "current": "withheld: live snapshots are not historical observations" if historical else {
            "evaluated_at": snapshot.get("evaluated_at"), "venues": rows,
            "cross_venue": _comparison(rows), "missing": snapshot.get("missing", []),
        },
        "settlements": {"from_exclusive": start.isoformat(), "to_inclusive": end.isoformat(),
                        "items": settlements, "not_recorded": not_recorded,
                        "truncated": bool(cursor), "unavailable": settlement_error,
                        "notice": "Settlement prints, not current predictions; origin is preserved. "
                                  "An empty/truncated/unavailable window does not mean zero funding."},
    }
    return f"# DEBYKO perpetual context for {instrument}\n\n" + json.dumps(data, ensure_ascii=False)
