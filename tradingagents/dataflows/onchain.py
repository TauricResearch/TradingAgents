"""On-chain metrics from free public sources.

The On-chain Analyst (Phase 2 — slot inherited from the Fundamentals
analyst) uses these signals to gauge supply/demand pressure that
isn't visible in price or news:

- ``blockchain.com`` charts API — hash rate, mempool stats, tx volume,
  total transaction fees, miner revenue. Free, no key.
- ``mempool.space`` API — current fee pressure, mempool depth,
  recent block timing. Free, no key.

ETF flow tracking (US spot BTC ETF custody changes) is intentionally
deferred. The reliable sources for that are paid (Glassnode, CryptoQuant,
Farside) and v1 deliberately stays free-only. The placeholder string
here documents what would land in Phase 2+.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Dict, List, Optional

import requests

from ._cache import cached_json

logger = logging.getLogger(__name__)

_BLOCKCHAIN_INFO = "https://api.blockchain.info"
_MEMPOOL_BASE = "https://mempool.space/api"


# ---------------------------------------------------------------------------
# blockchain.com — chart endpoints
# ---------------------------------------------------------------------------


def _blockchain_chart(name: str, timespan: str = "30days") -> Optional[List[Dict]]:
    """Fetch a single blockchain.com chart series."""
    url = f"{_BLOCKCHAIN_INFO}/charts/{name}"

    def _fetch():
        r = requests.get(
            url,
            params={"timespan": timespan, "format": "json", "cors": "true"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    try:
        payload = cached_json(
            f"blockchain_chart_{name}_{timespan}",
            ttl_seconds=1800,
            fetcher=_fetch,
        )
    except requests.RequestException as e:
        logger.warning("blockchain.com chart %s failed: %s", name, e)
        return None
    return payload.get("values", [])


def get_btc_onchain_summary(look_back_days: int = 7) -> Optional[Dict]:
    """Aggregate the recent N-day picture of BTC on-chain activity."""
    timespan = f"{max(look_back_days, 7)}days"
    metrics = {
        "hash_rate": "hash-rate",
        "transactions": "n-transactions",
        "transaction_fees_usd": "transaction-fees-usd",
        "miners_revenue": "miners-revenue",
        "mempool_count": "mempool-count",
    }
    summary: Dict[str, Dict] = {}
    any_success = False
    for label, chart in metrics.items():
        series = _blockchain_chart(chart, timespan)
        if not series:
            continue
        any_success = True
        first = series[0]["y"]
        last = series[-1]["y"]
        change_pct = ((last - first) / first * 100) if first else None
        summary[label] = {
            "first": first,
            "last": last,
            "change_pct": change_pct,
        }
    if not any_success:
        return None
    summary["window"] = timespan
    return summary


# ---------------------------------------------------------------------------
# mempool.space — current fee + mempool pressure
# ---------------------------------------------------------------------------


def get_mempool_pressure() -> Optional[Dict]:
    """Snapshot of mempool depth + fee recommendations."""

    def _fetch_fees():
        r = requests.get(f"{_MEMPOOL_BASE}/v1/fees/recommended", timeout=10)
        r.raise_for_status()
        return r.json()

    def _fetch_mempool():
        r = requests.get(f"{_MEMPOOL_BASE}/mempool", timeout=10)
        r.raise_for_status()
        return r.json()

    try:
        fees = cached_json("mempool_fees", ttl_seconds=120, fetcher=_fetch_fees)
        depth = cached_json("mempool_state", ttl_seconds=120, fetcher=_fetch_mempool)
    except requests.RequestException as e:
        logger.warning("mempool.space fetch failed: %s", e)
        return None

    return {
        "fastest_fee_sat_vb": fees.get("fastestFee"),
        "half_hour_fee_sat_vb": fees.get("halfHourFee"),
        "hour_fee_sat_vb": fees.get("hourFee"),
        "economy_fee_sat_vb": fees.get("economyFee"),
        "mempool_count": depth.get("count"),
        "mempool_vsize_vb": depth.get("vsize"),
        "mempool_total_fee_sats": depth.get("total_fee"),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_onchain_markdown(asset: str = "BTC", look_back_days: int = 7) -> str:
    if asset.upper() != "BTC":
        return f"On-chain metrics for {asset} are not wired up in v1 (BTC-only)."

    sections: List[str] = []

    summary = get_btc_onchain_summary(look_back_days=look_back_days)
    if summary:
        sections.append(f"### BTC on-chain — last {summary.get('window', f'{look_back_days}d')}")
        sections.append("")
        sections.append("| Metric | Start | Latest | Δ |")
        sections.append("|---|---:|---:|---:|")

        def _fmt(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                return f"{v:,.2f}"
            return f"{v:,}"

        rows = [
            ("Hash rate", "hash_rate"),
            ("Daily transactions", "transactions"),
            ("Tx fees (USD)", "transaction_fees_usd"),
            ("Miner revenue", "miners_revenue"),
            ("Mempool count", "mempool_count"),
        ]
        for label, key in rows:
            stats = summary.get(key)
            if not stats:
                sections.append(f"| {label} | — | — | — |")
                continue
            change = stats.get("change_pct")
            change_text = f"{change:+.2f}%" if isinstance(change, (int, float)) else "—"
            sections.append(
                f"| {label} | {_fmt(stats.get('first'))} | "
                f"{_fmt(stats.get('last'))} | {change_text} |"
            )
    else:
        sections.append("On-chain summary unavailable (blockchain.com fetch failed).")

    pressure = get_mempool_pressure()
    if pressure:
        sections.append("")
        sections.append("### Current mempool pressure (mempool.space)")
        sections.append("")
        sections.append(f"- Fastest fee: {pressure.get('fastest_fee_sat_vb', '—')} sat/vB")
        sections.append(f"- 30-min fee: {pressure.get('half_hour_fee_sat_vb', '—')} sat/vB")
        sections.append(f"- 1-hour fee: {pressure.get('hour_fee_sat_vb', '—')} sat/vB")
        sections.append(f"- Mempool count: {pressure.get('mempool_count', '—'):,} txs")

    sections.append("")
    sections.append(
        "_ETF custody flows (Farside / Glassnode) are intentionally deferred to "
        "v1.1 — paid sources only. v1 reads price + on-chain activity from free APIs._"
    )
    return "\n".join(sections)
