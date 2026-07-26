"""Bounded, opt-in public capability probe for the Phase 3 acceptance catalog.

The probe never sends credentials, retries requests, or writes provider payloads.
It prints normalized capability coverage only so maintainers can refresh the
checked-in matrix after an explicit manual live run.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any

import requests

from tradingagents.china_funds.catalog import ACCEPTANCE_CATALOG
from tradingagents.china_funds.eastmoney import EastmoneyFundProvider


def _error(callable_) -> tuple[Any, str | None]:
    try:
        return callable_(), None
    except Exception as exc:  # noqa: BLE001 - the matrix reports capability isolation
        return None, type(exc).__name__


def _cached_get(timeout_seconds: float):
    cache: dict[tuple[str, tuple[tuple[str, str], ...]], requests.Response] = {}

    def get(url: str, *, params=None, timeout=None):
        key = (url, tuple(sorted((str(key), str(value)) for key, value in (params or {}).items())))
        if key not in cache:
            cache[key] = requests.get(url, params=params, timeout=timeout_seconds)
        return cache[key]

    return get


def probe(code: str, analysis_date: str, timeout_seconds: float) -> dict[str, Any]:
    provider = EastmoneyFundProvider(
        timeout_seconds=timeout_seconds,
        http_get=_cached_get(timeout_seconds),
    )
    identity, identity_error = _error(lambda: provider.fetch_identity(code))
    nav, nav_error = _error(lambda: provider.fetch_nav(code, analysis_date))
    status, status_error = _error(lambda: provider.fetch_transaction_status(code))
    fees, fees_error = _error(lambda: provider.fetch_fees(code))
    disclosure, disclosure_error = _error(lambda: provider.fetch_disclosure(code))
    benchmark, benchmark_error = _error(lambda: provider.fetch_benchmark(code))

    nav_points = tuple(nav.value or ()) if nav else ()
    disclosure_value = disclosure.value or {} if disclosure else {}
    return {
        "code": code,
        "identity": bool(identity and identity.value),
        "nav_points": len(nav_points),
        "nav_latest_date": nav_points[-1].date if nav_points else None,
        "transaction_status": bool(status and status.value),
        "fees": len(tuple(fees.value or ())) if fees else 0,
        "manager": bool(disclosure_value.get("manager")),
        "holdings": len(tuple(disclosure_value.get("holdings") or ())),
        "asset_allocation": bool(disclosure_value.get("asset_allocation")),
        "benchmark": bool(benchmark and benchmark.value and benchmark.value.disclosed_text),
        "errors": {
            name: error
            for name, error in {
                "identity": identity_error,
                "nav": nav_error,
                "transaction_status": status_error,
                "fees": fees_error,
                "disclosure": disclosure_error,
                "benchmark": benchmark_error,
            }.items()
            if error
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--json", action="store_true", help="emit one normalized JSON document")
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 30:
        parser.error("--timeout must be greater than zero and no more than 30 seconds")
    date.fromisoformat(args.analysis_date)

    rows = [probe(item.code, args.analysis_date, args.timeout) for item in ACCEPTANCE_CATALOG]
    if args.json:
        print(json.dumps({"analysis_date": args.analysis_date, "items": rows}, ensure_ascii=False))
        return 0
    for row in rows:
        coverage = ", ".join(
            name
            for name in ("identity", "transaction_status", "asset_allocation", "benchmark")
            if row[name]
        )
        print(
            f"{row['code']} nav={row['nav_points']} latest={row['nav_latest_date']} "
            f"fees={row['fees']} holdings={row['holdings']} coverage={coverage or 'none'} "
            f"errors={','.join(row['errors']) or 'none'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
