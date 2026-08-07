"""Bitcoin network hashrate vendor (mempool.space).

Surfaces Bitcoin miner/network-health signal that no equity-oriented vendor
covers. A rising hashrate signals miner confidence/network security
strength; a sharp drop can precede or accompany capitulation-driven sell
pressure from miners.

Uses mempool.space's public API — no key, no auth. Bitcoin-only: hashrate
is not a meaningful signal for other assets.
"""
import datetime as _dt
import logging

import requests

logger = logging.getLogger(__name__)

HASHRATE_API = "https://mempool.space/api/v1/mining/hashrate/3d"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 15


def get_network_hashrate() -> str:
    """Return current Bitcoin network hashrate and difficulty, with a short trend.

    Returns:
        A markdown report with the current hashrate/difficulty and the last
        3 daily average-hashrate readings.
    """
    try:
        response = requests.get(HASHRATE_API, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.warning("mempool.space hashrate fetch failed: %s", e)
        return f"Network hashrate data is currently unavailable ({e})."

    current = data.get("currentHashrate", 0) / 1e18
    difficulty = data.get("currentDifficulty", 0)
    series = data.get("hashrates", [])[-3:]

    lines = [
        "### Bitcoin Network Hashrate (mempool.space)",
        "",
        f"**Current hashrate:** {current:,.1f} EH/s",
        f"**Current difficulty:** {difficulty:,.0f}",
        "",
        "| Date (UTC) | Avg Hashrate (EH/s) |",
        "| --- | ---: |",
    ]
    for point in series:
        date = _dt.datetime.utcfromtimestamp(point["timestamp"]).strftime("%Y-%m-%d")
        lines.append(f"| {date} | {point['avgHashrate'] / 1e18:,.1f} |")
    return "\n".join(lines)
