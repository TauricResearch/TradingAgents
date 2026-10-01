"""CFTC Commitments of Traders (COT) vendor.

Provides trader-positioning context from the CFTC Public Reporting Environment:
who is net long/short, how concentrated positioning is, and how it changed week
on week. This complements news (what happened) and macro prints (where the
economy stands) with positioning/crowding (who is already positioned).

Data source: https://publicreporting.cftc.gov (Socrata API, keyless for normal
usage). COT positions are snapshots as of Tuesday and typically released Friday;
for point-in-time safety, this vendor serves only reports whose likely public
release date (Tuesday + 3 days) is on/before ``curr_date``.

Raw API responses are cached on disk (under ``data_cache_dir/cftc``) by
(dataset, query) and refreshed only when a newer weekly report is expected,
so multi-symbol runs do not re-fetch identical COT payloads. The cache can be
disabled via ``cftc_cache_enabled`` and bounded by
``cftc_cache_max_age_days``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import get_current_date

logger = logging.getLogger(__name__)

CFTC_API_BASE = "https://publicreporting.cftc.gov/resource"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_WEEKS = 26
MAX_LOOKBACK_WEEKS = 260
SEARCH_LIMIT = 500
RELEASE_LAG_DAYS = 3

# Cache raw Socrata responses by (dataset, query) under data_cache_dir/cftc.
# COT is published weekly, so cache freshness is governed by whether the cached
# payload already includes the latest report date expected for ``curr_date``.
CACHE_SUBDIR = "cftc"
EMPTY_CACHE_TTL_HOURS = 24
DEFAULT_CACHE_MAX_AGE_DAYS = 48


@dataclass(frozen=True)
class TraderCategorySpec:
    label: str
    long_field: str
    short_field: str
    change_long_field: str
    change_short_field: str
    pct_long_field: str
    pct_short_field: str


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    label: str
    lead_signal: str
    categories: tuple[TraderCategorySpec, ...]


@dataclass(frozen=True)
class MarketMatch:
    dataset: DatasetSpec
    query_used: str
    market_name: str
    score: int
    rows: tuple[dict, ...]  # sorted newest -> oldest and already release-filtered


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        dataset_id="yw9f-hn96",
        label="Traders in Financial Futures (combined)",
        lead_signal="Leveraged Funds",
        categories=(
            TraderCategorySpec(
                "Dealer/Intermediary",
                "dealer_positions_long_all",
                "dealer_positions_short_all",
                "change_in_dealer_long_all",
                "change_in_dealer_short_all",
                "pct_of_oi_dealer_long_all",
                "pct_of_oi_dealer_short_all",
            ),
            TraderCategorySpec(
                "Asset Manager/Institutional",
                "asset_mgr_positions_long",
                "asset_mgr_positions_short",
                "change_in_asset_mgr_long",
                "change_in_asset_mgr_short",
                "pct_of_oi_asset_mgr_long",
                "pct_of_oi_asset_mgr_short",
            ),
            TraderCategorySpec(
                "Leveraged Funds",
                "lev_money_positions_long",
                "lev_money_positions_short",
                "change_in_lev_money_long",
                "change_in_lev_money_short",
                "pct_of_oi_lev_money_long",
                "pct_of_oi_lev_money_short",
            ),
            TraderCategorySpec(
                "Other Reportables",
                "other_rept_positions_long",
                "other_rept_positions_short",
                "change_in_other_rept_long",
                "change_in_other_rept_short",
                "pct_of_oi_other_rept_long",
                "pct_of_oi_other_rept_short",
            ),
        ),
    ),
    DatasetSpec(
        dataset_id="kh3c-gbw2",
        label="Disaggregated (combined)",
        lead_signal="Managed Money",
        categories=(
            TraderCategorySpec(
                "Producer/Merchant",
                "prod_merc_positions_long",
                "prod_merc_positions_short",
                "change_in_prod_merc_long",
                "change_in_prod_merc_short",
                "pct_of_oi_prod_merc_long",
                "pct_of_oi_prod_merc_short",
            ),
            TraderCategorySpec(
                "Swap Dealers",
                "swap_positions_long_all",
                "swap__positions_short_all",
                "change_in_swap_long_all",
                "change_in_swap_short_all",
                "pct_of_oi_swap_long_all",
                "pct_of_oi_swap_short_all",
            ),
            TraderCategorySpec(
                "Managed Money",
                "m_money_positions_long_all",
                "m_money_positions_short_all",
                "change_in_m_money_long_all",
                "change_in_m_money_short_all",
                "pct_of_oi_m_money_long_all",
                "pct_of_oi_m_money_short_all",
            ),
            TraderCategorySpec(
                "Other Reportables",
                "other_rept_positions_long",
                "other_rept_positions_short",
                "change_in_other_rept_long",
                "change_in_other_rept_short",
                "pct_of_oi_other_rept_long",
                "pct_of_oi_other_rept_short",
            ),
        ),
    ),
    DatasetSpec(
        dataset_id="jun7-fc8e",
        label="Legacy (combined)",
        lead_signal="Non-Commercial",
        categories=(
            TraderCategorySpec(
                "Commercial",
                "comm_positions_long_all",
                "comm_positions_short_all",
                "change_in_comm_long_all",
                "change_in_comm_short_all",
                "pct_of_oi_comm_long_all",
                "pct_of_oi_comm_short_all",
            ),
            TraderCategorySpec(
                "Non-Commercial",
                "noncomm_positions_long_all",
                "noncomm_positions_short_all",
                "change_in_noncomm_long_all",
                "change_in_noncomm_short_all",
                "pct_of_oi_noncomm_long_all",
                "pct_of_oi_noncomm_short_all",
            ),
            TraderCategorySpec(
                "Nonreportable",
                "nonrept_positions_long_all",
                "nonrept_positions_short_all",
                "change_in_nonrept_long_all",
                "change_in_nonrept_short_all",
                "pct_of_oi_nonrept_long_all",
                "pct_of_oi_nonrept_short_all",
            ),
        ),
    ),
)


DEFAULT_MARKET_QUERY = "E-MINI S&P 500"

TICKER_PROXIES = {
    "SPY": "E-MINI S&P 500",
    "IVV": "E-MINI S&P 500",
    "VOO": "E-MINI S&P 500",
    "QQQ": "NASDAQ-100 STOCK INDEX",
    "TQQQ": "NASDAQ-100 STOCK INDEX",
    "SQQQ": "NASDAQ-100 STOCK INDEX",
    "IWM": "RUSSELL 2000",
    "GLD": "GOLD",
    "SLV": "SILVER",
    "USO": "CRUDE OIL",
    "UUP": "U.S. DOLLAR INDEX",
    "TLT": "10-YEAR U.S. TREASURY NOTE",
    "BTC": "BITCOIN",
    "BTCUSD": "BITCOIN",
    "ETH": "ETHER",
    "ETHUSD": "ETHER",
}


def _request(dataset_id: str, query: str) -> list[dict]:
    params = {
        "$q": query,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(SEARCH_LIMIT),
    }
    response = requests.get(
        f"{CFTC_API_BASE}/{dataset_id}.json", params=params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _cache_settings() -> tuple[bool, int]:
    cfg = get_config()
    enabled = bool(cfg.get("cftc_cache_enabled", True))
    try:
        max_age_days = int(cfg.get("cftc_cache_max_age_days", DEFAULT_CACHE_MAX_AGE_DAYS))
    except (TypeError, ValueError):
        max_age_days = DEFAULT_CACHE_MAX_AGE_DAYS
    return enabled, max(1, max_age_days)


def _cache_dir() -> str:
    path = os.path.join(get_config()["data_cache_dir"], CACHE_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path(dataset_id: str, query: str) -> str:
    key = hashlib.sha256(f"{dataset_id}\n{query.strip().lower()}".encode()).hexdigest()
    return os.path.join(_cache_dir(), f"{dataset_id}-{key}.json")


def _prune_cache_dir(max_age_days: int) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    cache_dir = _cache_dir()
    for name in os.listdir(cache_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(cache_dir, name)
        try:
            modified = datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)
            if modified < cutoff:
                os.remove(path)
        except OSError:
            continue


def _load_cache(dataset_id: str, query: str) -> tuple[list[dict] | None, datetime | None]:
    path = _cache_path(dataset_id, query)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return None, None
        cached_at_raw = payload.get("cached_at")
        cached_at = None
        if isinstance(cached_at_raw, str):
            try:
                cached_at = datetime.fromisoformat(cached_at_raw.replace("Z", "+00:00"))
                if cached_at.tzinfo is None:
                    cached_at = cached_at.replace(tzinfo=UTC)
            except ValueError:
                cached_at = None
        return rows, cached_at
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("CFTC cache read failed for %s: %s", path, exc)
        return None, None


def _write_cache(dataset_id: str, query: str, rows: list[dict]) -> None:
    path = _cache_path(dataset_id, query)
    payload = {
        "dataset_id": dataset_id,
        "query": query,
        "cached_at": datetime.now(UTC).isoformat(),
        "rows": rows,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def _latest_report_date(rows: list[dict]) -> date | None:
    dates = [_parse_iso_date(r.get("report_date_as_yyyy_mm_dd")) for r in rows]
    valid = [d for d in dates if d is not None]
    return max(valid) if valid else None


def _expected_latest_report_date(as_of: date) -> date:
    """The newest Tuesday snapshot expected to be published by ``as_of``.

    COT is a Tuesday snapshot typically published on Friday; we model this as a
    fixed lag of ``RELEASE_LAG_DAYS`` and select the most recent Tuesday on or
    before that lagged date.
    """
    cutoff = as_of - timedelta(days=RELEASE_LAG_DAYS)
    # Monday=0 ... Sunday=6, Tuesday=1.
    days_since_tuesday = (cutoff.weekday() - 1) % 7
    return cutoff - timedelta(days=days_since_tuesday)


def _cache_is_fresh(rows: list[dict], cached_at: datetime | None, as_of: date) -> bool:
    latest = _latest_report_date(rows)
    if latest is not None:
        return latest >= _expected_latest_report_date(as_of)
    if cached_at is None:
        return False
    return datetime.now(UTC) - cached_at <= timedelta(hours=EMPTY_CACHE_TTL_HOURS)


def _request_cached(dataset_id: str, query: str, as_of: date) -> list[dict]:
    enabled, max_age_days = _cache_settings()
    if not enabled:
        return _request(dataset_id, query)

    _prune_cache_dir(max_age_days)

    rows, cached_at = _load_cache(dataset_id, query)
    if rows is not None and _cache_is_fresh(rows, cached_at, as_of):
        return rows

    try:
        fresh = _request(dataset_id, query)
    except requests.RequestException:
        # Serve stale cache when available: better a slightly stale positioning
        # read than dropping the signal entirely on a transient outage.
        if rows is not None:
            logger.warning(
                "CFTC fetch failed for %s/%r; serving stale cache", dataset_id, query
            )
            return rows
        raise

    _write_cache(dataset_id, query, fresh)
    return fresh


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _released_by(as_of: date, report_date: date) -> bool:
    return report_date + timedelta(days=RELEASE_LAG_DAYS) <= as_of


def _to_float(value) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _fmt_int(value: float | None) -> str:
    return "—" if value is None else f"{int(round(value)):,.0f}"


def _fmt_signed_int(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value)):+,d}"


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _market_score(market_name: str, query: str) -> int:
    market = market_name.lower()
    wanted = query.lower().strip()
    if not wanted:
        return 0

    score = 0
    if market == wanted:
        score += 100
    if market.startswith(wanted):
        score += 25
    if wanted in market:
        score += 60
    if "micro" in market and "micro" not in wanted:
        score -= 6

    tokens = [t for t in re.split(r"[^a-z0-9]+", wanted) if len(t) >= 2]
    if tokens:
        matched = sum(1 for t in tokens if t in market)
        score += matched * 8
        if matched == len(tokens):
            score += 20
    return score


def _sort_rows_desc(rows: list[dict]) -> list[dict]:
    def key(row: dict):
        d = _parse_iso_date(row.get("report_date_as_yyyy_mm_dd"))
        return d or date.min

    return sorted(rows, key=key, reverse=True)


def _pick_best_market(
    dataset: DatasetSpec,
    rows: list[dict],
    query: str,
    as_of: date,
    look_back_weeks: int,
) -> MarketMatch | None:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        report_date = _parse_iso_date(row.get("report_date_as_yyyy_mm_dd"))
        if report_date is None or not _released_by(as_of, report_date):
            continue
        market_name = (
            row.get("market_and_exchange_names")
            or row.get("contract_market_name")
            or ""
        ).strip()
        if not market_name:
            continue
        grouped.setdefault(market_name, []).append(row)

    best_name = None
    best_score = -1
    best_latest = date.min
    best_rows: list[dict] = []

    for market_name, market_rows in grouped.items():
        ordered_rows = _sort_rows_desc(market_rows)
        latest = _parse_iso_date(ordered_rows[0].get("report_date_as_yyyy_mm_dd")) or date.min
        score = _market_score(market_name, query)
        if score > best_score or (score == best_score and latest > best_latest):
            best_name = market_name
            best_score = score
            best_latest = latest
            best_rows = ordered_rows[:look_back_weeks]

    if best_name is None or best_score <= 0:
        return None

    return MarketMatch(
        dataset=dataset,
        query_used=query,
        market_name=best_name,
        score=best_score,
        rows=tuple(best_rows),
    )


def _is_ticker_like(topic: str) -> bool:
    text = topic.strip().upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", text))


def _candidate_queries(topic: str | None) -> list[str]:
    candidates: list[str] = []

    def add(value: str | None):
        if not value:
            return
        v = value.strip()
        if v and v not in candidates:
            candidates.append(v)

    add(topic)

    if topic and _is_ticker_like(topic) and topic.strip().upper() in TICKER_PROXIES:
        add(TICKER_PROXIES[topic.strip().upper()])

    if topic and _is_ticker_like(topic):
        add(DEFAULT_MARKET_QUERY)

    if not candidates:
        add(DEFAULT_MARKET_QUERY)

    return candidates


def _category_rows(match: MarketMatch) -> list[dict]:
    latest = match.rows[0]
    previous = match.rows[1] if len(match.rows) > 1 else None
    oi = _to_float(latest.get("open_interest_all"))

    output = []
    for spec in match.dataset.categories:
        long_val = _to_float(latest.get(spec.long_field))
        short_val = _to_float(latest.get(spec.short_field))
        if long_val is None and short_val is None:
            continue

        net = None if long_val is None or short_val is None else long_val - short_val

        if previous is not None:
            prev_long = _to_float(previous.get(spec.long_field))
            prev_short = _to_float(previous.get(spec.short_field))
            if prev_long is not None and prev_short is not None and net is not None:
                net_change = net - (prev_long - prev_short)
            else:
                net_change = None
        else:
            net_change = None

        if net_change is None:
            chg_long = _to_float(latest.get(spec.change_long_field))
            chg_short = _to_float(latest.get(spec.change_short_field))
            if chg_long is not None and chg_short is not None:
                net_change = chg_long - chg_short

        pct_long = _to_float(latest.get(spec.pct_long_field))
        pct_short = _to_float(latest.get(spec.pct_short_field))
        if oi and oi > 0:
            if pct_long is None and long_val is not None:
                pct_long = (long_val / oi) * 100
            if pct_short is None and short_val is not None:
                pct_short = (short_val / oi) * 100

        output.append(
            {
                "label": spec.label,
                "long": long_val,
                "short": short_val,
                "net": net,
                "net_change": net_change,
                "pct_long": pct_long,
                "pct_short": pct_short,
            }
        )

    return output


def _lead_signal_comment(match: MarketMatch) -> str:
    lead = next((s for s in match.dataset.categories if s.label == match.dataset.lead_signal), None)
    if lead is None:
        return ""

    series: list[float] = []
    for row in reversed(match.rows):
        long_val = _to_float(row.get(lead.long_field))
        short_val = _to_float(row.get(lead.short_field))
        if long_val is None or short_val is None:
            continue
        series.append(long_val - short_val)

    if len(series) < 2:
        return ""

    latest = series[-1]
    prev = series[-2]
    rank = sum(1 for value in series if value <= latest) / len(series) * 100

    if latest > 0:
        side = "net long"
    elif latest < 0:
        side = "net short"
    else:
        side = "flat"

    if rank >= 80:
        crowd = "crowded long"
    elif rank <= 20:
        crowd = "crowded short"
    else:
        crowd = "middle of its recent range"

    return (
        f"- **{lead.label}** are {side} {_fmt_int(abs(latest))} contracts "
        f"({_fmt_signed_int(latest - prev)} WoW), around the {rank:.0f}th percentile "
        f"of the last {len(series)} released reports ({crowd})."
    )


def _recent_lead_table(match: MarketMatch) -> str:
    lead = next((s for s in match.dataset.categories if s.label == match.dataset.lead_signal), None)
    if lead is None:
        return ""

    rows = []
    for row in match.rows[:6]:
        report_date = _parse_iso_date(row.get("report_date_as_yyyy_mm_dd"))
        if report_date is None:
            continue
        long_val = _to_float(row.get(lead.long_field))
        short_val = _to_float(row.get(lead.short_field))
        if long_val is None or short_val is None:
            continue
        rows.append((report_date.isoformat(), long_val - short_val))

    if not rows:
        return ""

    return (
        f"\n### Recent {lead.label} net positioning\n"
        "| Report date | Net contracts |\n| --- | ---: |\n"
        + "\n".join(f"| {d} | {_fmt_signed_int(net)} |" for d, net in rows)
        + "\n"
    )


def get_commitments_of_traders(
    topic: str | None,
    look_back_weeks: int | None = None,
    curr_date: str | None = None,
) -> str:
    """Return a COT positioning summary for a market keyword.

    Args:
        topic: COT market/topic keyword, e.g. "E-MINI S&P 500", "CRUDE OIL",
            "GOLD", "BITCOIN". If empty, a default market proxy is chosen.
        look_back_weeks: Trailing released reports to analyze (default 26).
        curr_date: Analysis date (YYYY-MM-DD). Reports released after this date
            are excluded.


    Returns:
        Markdown report with trader-class positioning, weekly net changes, and
        lead-speculator crowding context.
    """
    if look_back_weeks is None:
        look_back_weeks = DEFAULT_LOOKBACK_WEEKS
    look_back_weeks = max(4, min(int(look_back_weeks), MAX_LOOKBACK_WEEKS))

    as_of = _parse_iso_date(curr_date) or _parse_iso_date(get_current_date()) or date.today()
    queries = _candidate_queries(topic)

    best: MarketMatch | None = None
    last_error: Exception | None = None

    for query in queries:
        for dataset in DATASETS:
            try:
                rows = _request_cached(dataset.dataset_id, query, as_of)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "CFTC query failed for dataset %s and query %r: %s",
                    dataset.dataset_id,
                    query,
                    exc,
                )
                continue

            match = _pick_best_market(dataset, rows, query, as_of, look_back_weeks)
            if match is None:
                continue
            if best is None or match.score > best.score:
                best = match

        # Prefer the first query that produced a credible match.
        if best is not None and best.query_used == query:
            break

    if best is None:
        if last_error is not None:
            return (
                "CFTC COT data is currently unavailable (network/API error: "
                f"{last_error}). Proceed without COT positioning signal."
            )
        attempted = ", ".join(f"'{q}'" for q in queries)
        return (
            "No released CFTC COT market matched this query as of "
            f"{as_of.isoformat()}. Tried: {attempted}. Use a futures contract "
            "name such as 'E-MINI S&P 500', 'NASDAQ-100', '10-YEAR U.S. "
            "TREASURY NOTE', 'CRUDE OIL', 'GOLD', or 'BITCOIN'."
        )

    latest = best.rows[0]
    latest_report_date = _parse_iso_date(latest.get("report_date_as_yyyy_mm_dd"))
    if latest_report_date is None:
        return (
            "CFTC COT data was returned but did not include a valid report date. "
            "Proceed without this signal."
        )

    release_date = latest_report_date + timedelta(days=RELEASE_LAG_DAYS)
    open_interest = _to_float(latest.get("open_interest_all"))
    oi_change = _to_float(latest.get("change_in_open_interest_all"))

    lines = [
        f"## CFTC Commitments of Traders: {best.market_name}",
        f"- Report family: {best.dataset.label}",
        f"- Latest released report date (Tuesday snapshot): {latest_report_date.isoformat()}",
        f"- Earliest likely public release for that report: {release_date.isoformat()}",
        f"- Analysis window: last {len(best.rows)} released weekly reports through {as_of.isoformat()}",
    ]

    if open_interest is not None:
        lines.append(
            "- Open interest: "
            f"{_fmt_int(open_interest)} contracts ({_fmt_signed_int(oi_change)} WoW)"
        )

    if topic and best.query_used != topic:
        lines.append(
            f"- Query fallback used: '{best.query_used}' (requested '{topic}')"
        )

    categories = _category_rows(best)
    if categories:
        lines.extend(
            [
                "",
                "| Trader class | Long | Short | Net | Net WoW | %OI Long | %OI Short |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in categories:
            lines.append(
                f"| {row['label']} | {_fmt_int(row['long'])} | {_fmt_int(row['short'])} "
                f"| {_fmt_signed_int(row['net'])} | {_fmt_signed_int(row['net_change'])} "
                f"| {_fmt_pct(row['pct_long'])} | {_fmt_pct(row['pct_short'])} |"
            )

    lead_comment = _lead_signal_comment(best)
    if lead_comment:
        lines.extend(["", "### Positioning read-through", lead_comment])

    lines.append(
        "- COT is a positioning/crowding input, not a timing signal by itself; "
        "combine it with trend, macro, and event catalysts."
    )
    lines.append(
        "- Release timing note: this uses a standard Tuesday+3-day publication "
        "lag. Holiday weeks can shift the official release schedule."
    )

    recent_table = _recent_lead_table(best)
    if recent_table:
        lines.append(recent_table)

    return "\n".join(lines).strip() + "\n"
