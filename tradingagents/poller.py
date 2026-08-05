"""Media poller — accumulates social/news history for backtesting.

Polls each configured source (hourly by default), appending every new item to a
media store (local SQLite by default, or any database via ``MEDIA_DB_URL``),
deduped on the provider's stable id. See ``dataflows.media_sources`` (fetchers)
and ``dataflows.media_store`` (storage).

Designed to be cloud-hostable: every knob has an environment-variable form, so a
container can run with no CLI arguments. Env vars (CLI flags override them):

    MEDIA_POLLER_TICKERS   comma-separated; required only for ticker sources
    MEDIA_POLLER_SOURCES   subset of the sources; default = keyless (+x if token)
    MEDIA_POLLER_INTERVAL  seconds between polls in daemon mode      (default 3600)
    MEDIA_POLLER_X_INTERVAL seconds between X discovery cycles       (default 86400)
    MEDIA_POLLER_X_TOPICS  max discovered topics per cycle           (default 3)
    MEDIA_POLLER_X_LIMIT   results per discovered X query            (default 10)
    MEDIA_POLLER_ONCE      "1"/"true" → poll once and exit (for cron/scheduler)
    MEDIA_DB_URL           store location; default ~/.tradingagents/cache/media.db
    X_BEARER_TOKEN         enables the 'x' source (paid)
    TRUTHSOCIAL_TOKEN      enables Truth Social

Run modes:
    tradingagents-poller --tickers NVDA,AAPL          # hourly daemon
    tradingagents-poller --tickers NVDA --once        # one-shot (cron/scheduler)
    tradingagents-poller --stats                      # collection summary
    tradingagents-poller --window NVDA --end 2026-06-28 --days 7
    python -m tradingagents.poller --tickers NVDA     # equivalent
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import time
from datetime import datetime, timezone

from tradingagents.dataflows.media_sources import (
    FETCHERS,
    KEYLESS_SOURCES,
    SELECTABLE_SOURCES,
    fetch_global_news,
    fetch_polymarket_odds,
    fetch_top_news_headlines,
    fetch_x_topic,
    fetch_x_trends,
    looks_company_authored,
)
from tradingagents.dataflows.media_store import open_store
from tradingagents.dataflows.trading_clock import TradingClock
from tradingagents.default_config import DEFAULT_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("media_poller")


# Topic discovery is deliberately entity-agnostic. It starts from ranked news
# feeds and live trends instead of a watchlist of companies, politicians, or
# products, then spends at most three recent-search calls on the day's strongest
# cross-source stories.
_DISCOVERY_CATEGORIES = ("world", "business", "technology")
_QUERY_STOPWORDS = {
    "a", "about", "according", "after", "against", "all", "amid", "an", "and", "are", "as",
    "at", "be", "before", "but", "by", "can", "confirms", "could", "for", "from", "has",
    "have", "how", "in", "into", "is", "it", "its", "may", "more", "new", "not",
    "of", "on", "or", "over", "report", "reports", "says", "than", "that", "the", "their", "this",
    "to", "up", "was", "what", "when", "where", "which", "who", "why", "will",
    "with", "would",
}
_GENERIC_CAPITALIZED = {
    "Analysis", "Breaking", "Exclusive", "Explainer", "Here", "How", "Live",
    "My", "New", "Opinion", "The", "This", "Update", "What", "When", "Why",
}
_LOW_INFORMATION_HEADLINE = re.compile(
    r"\b(best|deal|discount|guide|hands[- ]on|how to|review|rumor|versus|vs\.?|wishlist)\b",
    re.IGNORECASE,
)
def _env_bool(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_sources(explicit: list[str] | None) -> list[str]:
    """Sources to poll: explicit list if given, else the keyless set plus 'x'
    when X_BEARER_TOKEN is present. Validates against the registry."""
    if explicit:
        sources = explicit
    else:
        sources = list(KEYLESS_SOURCES)
        if os.environ.get("X_BEARER_TOKEN"):
            sources.append("x")
    unknown = [s for s in sources if s not in FETCHERS]
    if unknown:
        raise ValueError(f"unknown source(s): {','.join(unknown)}. "
                         f"Choose from: {','.join(SELECTABLE_SOURCES)}")
    return sources


def _within(rows: list[dict], since: float | None) -> list[dict]:
    """Keep only items posted after ``since`` (the previous poll's clock time).

    This makes each poll incremental — during continuous polling the window is
    ~1 hour, and after an overnight/weekend/holiday gap it sweeps everything
    posted since the last poll. Undated items are kept (dedup is the backstop)."""
    if since is None:
        return rows
    return [r for r in rows if r.get("created_utc") is None or r["created_utc"] > since]


def poll_once(store, tickers: list[str], sources: list[str],
              now: float, since: float | None) -> None:
    for ticker in tickers:
        parts = []
        for src in sources:
            rows = _within(FETCHERS[src](ticker, now), since)
            parts.append(f"{src} +{store.store(rows)}")
        logger.info("%s: %s", ticker, " · ".join(parts))
        time.sleep(1.0)  # be polite between tickers


def poll_macro_once(store, themes: dict, now: float, since: float | None) -> None:
    """Snapshot the macro layer: per theme, global/theme news (windowed like the
    social sources) and live Polymarket odds. Odds are always stored — each poll
    is a fresh point in the probability time series. FRED is omitted (it's fully
    historical and fetched live at backtest time)."""
    for theme, spec in themes.items():
        news_new = 0
        for query in spec.get("queries", []):
            news_new += store.store(_within(fetch_global_news(query, now, theme), since))
        odds_new = 0
        for topic in spec.get("prediction_topics", []):
            odds_new += store.store_odds(fetch_polymarket_odds(topic, now, theme))
        logger.info("macro[%s]: globalnews +%d · polymarket-odds +%d",
                    theme, news_new, odds_new)


def _headline_without_publisher(title: str) -> str:
    """Remove Google News' trailing `` - Publisher`` attribution."""
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _topic_key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _headline_without_publisher(text).lower()))


def _trend_matches_headline(trend: str, headline: str) -> bool:
    trend_words = set(re.findall(r"[a-z0-9]+", trend.lower().lstrip("#")))
    headline_words = set(re.findall(r"[a-z0-9]+", headline.lower()))
    meaningful = {word for word in trend_words if len(word) >= 4 and word not in _QUERY_STOPWORDS}
    if not meaningful:
        return False
    needed = 1 if len(meaningful) == 1 else 2
    return len(meaningful & headline_words) >= needed


def _headline_query(title: str) -> str:
    """Turn a discovered headline into a compact X query without a watchlist.

    Named phrases are extracted from the headline itself and paired with one
    descriptive word. This is broad enough to capture public reaction while
    avoiding a brittle exact-headline search.
    """
    headline = _headline_without_publisher(title)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&.'’+-]*", headline)
    capitalized_runs: list[list[str]] = []
    run: list[str] = []
    for token in tokens:
        is_capitalized = token[0].isupper() or any(char.isupper() for char in token[1:])
        if is_capitalized and token.lower() not in _QUERY_STOPWORDS:
            run.append(token)
        elif run:
            capitalized_runs.append(run)
            run = []
    if run:
        capitalized_runs.append(run)

    anchors = []
    for words in capitalized_runs:
        while words and words[0] in _GENERIC_CAPITALIZED:
            words = words[1:]
        if not words:
            continue
        distinctive = [
            word for word in words
            if any(c.isdigit() for c in word)
            or any(c.isupper() for c in word[1:])
            or (len(word) == 1 and word.isupper())
        ]
        if len(words) > 3:
            words = distinctive[:2] or words[:2]
        phrase = " ".join(words[:3])
        if len(words) > 1 or distinctive:
            anchors.append((phrase, bool(distinctive)))
    anchors = sorted(
        set(anchors),
        key=lambda value: (value[1], len(value[0].split()), len(value[0])),
        reverse=True,
    )

    chosen = [anchors[0][0]] if anchors else []
    anchor_words = {word.lower() for phrase in chosen for word in phrase.split()}
    signals = [
        token for token in tokens
        if len(token) >= 4
        and token.lower() not in _QUERY_STOPWORDS
        and token.lower() not in anchor_words
        and token not in _GENERIC_CAPITALIZED
    ]

    parts = [f'"{phrase.replace(chr(34), "")}"' for phrase in chosen]
    if parts and len(parts) < 2 and signals:
        parts.append(signals[0])
    if not parts:
        parts = signals[:3]
    return " ".join(parts)[:400]


def _looks_company_authored(headline: dict) -> bool:
    """Reject press-release/newsroom items; discovery should measure reaction."""
    return looks_company_authored(headline.get("publisher"), headline.get("title"))


def discover_x_topics(max_topics: int = 3) -> list[dict]:
    """Select a small, diverse set of current high-information news topics.

    Ranked top-news feeds supply candidates. US and worldwide X trends can
    boost a matching headline, but cannot introduce an entertainment-only
    search on their own. One candidate per world/business/technology category
    maximizes coverage when the normal three-topic budget is used.
    """
    headlines = fetch_top_news_headlines()
    trends = fetch_x_trends(1) + fetch_x_trends(23424977)
    trend_names = [trend["name"] for trend in trends if trend.get("name")]

    grouped: dict[str, dict] = {}
    for headline in headlines:
        if _LOW_INFORMATION_HEADLINE.search(headline.get("title", "")) or \
                _looks_company_authored(headline):
            continue
        key = _topic_key(headline.get("title", ""))
        if not key:
            continue
        candidate = grouped.setdefault(key, {
            **headline,
            "categories": set(),
            "ranks": {},
        })
        category = headline.get("category", "general")
        candidate["categories"].add(category)
        candidate["ranks"][category] = min(
            candidate["ranks"].get(category, 10_000), headline.get("rank", 10_000)
        )

    candidates = []
    for candidate in grouped.values():
        best_rank = min(candidate["ranks"].values())
        cross_feed_bonus = 18 * (len(candidate["categories"]) - 1)
        trend_bonus = 30 if any(
            _trend_matches_headline(name, candidate["title"]) for name in trend_names
        ) else 0
        candidate["score"] = 100 - min(best_rank, 20) * 4 + cross_feed_bonus + trend_bonus
        candidate["query"] = _headline_query(candidate["title"])
        if candidate["query"]:
            candidates.append(candidate)

    chosen = []
    used_keys = set()
    for category in _DISCOVERY_CATEGORIES:
        eligible = [
            candidate for candidate in candidates
            if category in candidate["categories"] and _topic_key(candidate["title"]) not in used_keys
        ]
        if not eligible or len(chosen) >= max_topics:
            continue
        best = max(
            eligible,
            key=lambda candidate: (
                candidate["score"] - candidate["ranks"].get(category, 20) * 2,
                candidate.get("created_utc") or 0,
            ),
        )
        best = {**best, "topic": f"trend_{category}", "category": category}
        chosen.append(best)
        used_keys.add(_topic_key(best["title"]))

    if len(chosen) < max_topics:
        remaining = sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)
        for candidate in remaining:
            key = _topic_key(candidate["title"])
            if key in used_keys:
                continue
            category = next(iter(candidate["categories"]), "general")
            chosen.append({**candidate, "topic": f"trend_{category}", "category": category})
            used_keys.add(key)
            if len(chosen) >= max_topics:
                break
    return chosen


def _discovery_news_row(topic: dict, now: float) -> dict:
    return {
        "source": "trendnews",
        "external_id": topic["external_id"],
        "ticker": f"@{topic['topic']}".upper(),
        "subreddit": None,
        "author": topic.get("publisher"),
        "sentiment": None,
        "created_utc": topic.get("created_utc"),
        "title": topic.get("title"),
        "body": topic.get("body", ""),
        "fetched_utc": now,
    }


def poll_x_topics_once(store, now: float, limit: int = 10,
                       max_topics: int = 3) -> None:
    """Discover today's broad stories and capture bounded public X discussion."""
    since = max(store.get_meta("last_x_poll_utc") or now - 86400, now - 86400)
    topics = discover_x_topics(max_topics=max_topics)
    for topic in topics:
        news_new = store.store([_discovery_news_row(topic, now)])
        rows = _within(
            fetch_x_topic(topic["topic"], topic["query"], now, limit=limit),
            since,
        )
        logger.info(
            "x-discovery[%s]: %s · query=%r · news +%d · x +%d",
            topic["category"], _headline_without_publisher(topic["title"]),
            topic["query"], news_new, store.store(rows),
        )
    # Record attempted cycles too, so billing/auth failures don't retry hourly.
    store.set_meta("last_x_poll_utc", now)


def _x_poll_due(store, now: float, interval: int) -> bool:
    last = store.get_meta("last_x_poll_utc")
    return last is None or now - last >= interval


def run_cycle(store, tickers: list[str], sources: list[str], macro_themes: dict,
              x_enabled: bool = False, x_interval: int = 86400,
              x_limit: int = 10, x_topic_limit: int = 3,
              force_x: bool = False) -> None:
    """One poll cycle over the incremental window (last_poll_utc → now)."""
    since = store.get_meta("last_poll_utc")
    now = datetime.now(timezone.utc).timestamp()
    if since:
        logger.info("Window: items posted after %s",
                    datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    if sources:
        poll_once(store, tickers, sources, now, since)
    if macro_themes:
        poll_macro_once(store, macro_themes, now, since)
    if x_enabled and (force_x or _x_poll_due(store, now, x_interval)):
        poll_x_topics_once(store, now, limit=x_limit, max_topics=x_topic_limit)
    # X has its own cursor. An X-only smoke test must not advance the shared
    # ticker/news cursor or it can create an unrecoverable collection gap.
    if sources or macro_themes:
        store.set_meta("last_poll_utc", now)


def check_paper_heartbeat(store, now: float, max_age: float) -> bool:
    """Independent watchdog for the paper worker's database heartbeat."""
    success = store.get_meta("paper:last_success_utc")
    failure = store.get_meta("paper:last_failure_utc")
    healthy = bool(success and now - success <= max_age and (not failure or success >= failure))
    if success is None:
        logger.warning("Paper watchdog: no success heartbeat recorded yet")
    elif now - success > max_age:
        logger.error("Paper watchdog: success heartbeat is %.1f hours stale", (now - success) / 3600)
    elif failure and failure > success:
        logger.error("Paper watchdog: latest paper heartbeat is a failure")
    return healthy


def _sleep(seconds: float, stop: dict) -> None:
    """Sleep in short slices so a stop signal is honoured promptly."""
    slept = 0.0
    while slept < seconds and not stop["flag"]:
        time.sleep(min(5.0, seconds - slept))
        slept += 5.0


def poll_forever(store, tickers: list[str], sources: list[str], interval: int,
                 macro_themes: dict, clock: TradingClock | None = None,
                 x_enabled: bool = False, x_interval: int = 86400,
                 x_limit: int = 10, x_topic_limit: int = 3,
                 paper_heartbeat_max_age: float | None = None) -> None:
    stop = {"flag": False}

    def _handle(signum, _frame):
        logger.info("Received signal %s — finishing current cycle then exiting.", signum)
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    x_label = (f" + X discovery (up to {x_topic_limit} topics) every {x_interval}s"
               if x_enabled else "")
    logger.info("Polling %s [%s]%s%s every %ds%s. Ctrl-C / SIGTERM to stop.",
                ",".join(tickers), ",".join(sources),
                " + macro" if macro_themes else "", x_label, interval,
                " during extended trading hours" if clock else "")
    while not stop["flag"]:
        if clock is not None and not clock.is_polling_time():
            wake = clock.next_open()
            wait = max(60.0, (wake - datetime.now(timezone.utc)).total_seconds())
            logger.info("Outside trading hours — sleeping until %s",
                        wake.strftime("%Y-%m-%d %H:%M UTC"))
            _sleep(wait, stop)
            continue
        try:
            run_cycle(store, tickers, sources, macro_themes, x_enabled,
                      x_interval=x_interval, x_limit=x_limit, x_topic_limit=x_topic_limit)
            if paper_heartbeat_max_age:
                check_paper_heartbeat(
                    store, datetime.now(timezone.utc).timestamp(), paper_heartbeat_max_age
                )
        except Exception:  # noqa: BLE001 — daemon must survive transient providers/DBs
            logger.exception("Poll cycle failed; cursor remains unchanged and the next cycle retries")
            try:
                store.set_meta("poller:last_failure_utc", datetime.now(timezone.utc).timestamp())
            except Exception:  # noqa: BLE001 — the original failure is the useful one
                logger.exception("Could not record poller failure heartbeat")
        _sleep(interval, stop)
    logger.info("Stopped.")


def print_stats(store) -> None:
    rows = store.stats()
    if not rows:
        print("No data collected yet.")
        return
    print(f"{'TICKER':<8} {'SOURCE':<11} {'ROWS':>7}  EARLIEST → LATEST (post time, UTC)")
    for ticker, source, n, lo, hi in rows:
        lo_s = datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d %H:%M") if lo else "?"
        hi_s = datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%d %H:%M") if hi else "?"
        print(f"{ticker:<8} {source:<11} {n:>7}  {lo_s} → {hi_s}")

    odds = store.odds_stats()
    if odds:
        print(f"\n{'THEME':<14} {'MARKETS':>7} {'SNAPSHOTS':>9}  EARLIEST → LATEST (capture, UTC)")
        for theme, n_markets, n_snap, lo, hi in odds:
            lo_s = datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d %H:%M") if lo else "?"
            hi_s = datetime.fromtimestamp(hi, timezone.utc).strftime("%Y-%m-%d %H:%M") if hi else "?"
            print(f"{theme:<14} {n_markets:>7} {n_snap:>9}  {lo_s} → {hi_s}")


def print_window(store, ticker: str, end: str, days: int) -> None:
    rows = store.window(ticker, end, days)
    print(f"{ticker.upper()} — {len(rows)} items in the {days}d window ending {end}:")
    for r in rows:
        ts = (datetime.fromtimestamp(r["created_utc"], timezone.utc).strftime("%Y-%m-%d %H:%M")
              if r.get("created_utc") else "?")
        tag = r.get("sentiment") or (f"r/{r['subreddit']}" if r.get("subreddit") else "")
        text = (r.get("title") or r.get("body") or "").replace("\n", " ")[:120]
        print(f"  [{ts} · {r['source']:<10} {tag:<10}] {text}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", default=os.getenv("MEDIA_POLLER_TICKERS"),
                   help="Comma-separated tickers (env: MEDIA_POLLER_TICKERS)")
    p.add_argument("--sources", default=os.getenv("MEDIA_POLLER_SOURCES"),
                   help="Comma-separated subset of: " + ",".join(SELECTABLE_SOURCES)
                        + " (env: MEDIA_POLLER_SOURCES). Default: keyless + 'x' if token set.")
    p.add_argument("--db", default=os.getenv("MEDIA_DB_URL"),
                   help="Store URL/path (env: MEDIA_DB_URL). Default: local SQLite.")
    p.add_argument("--interval", type=int,
                   default=int(os.getenv("MEDIA_POLLER_INTERVAL", "3600")),
                   help="Seconds between polls in daemon mode (env: MEDIA_POLLER_INTERVAL)")
    p.add_argument("--x-interval", type=int,
                   default=int(os.getenv("MEDIA_POLLER_X_INTERVAL", "86400")),
                   help="Seconds between X discovery cycles (default 86400 / 1 day)")
    p.add_argument("--x-topics", type=int,
                   default=int(os.getenv("MEDIA_POLLER_X_TOPICS", "3")),
                   help="Maximum discovered topics per X cycle (default 3)")
    p.add_argument("--x-limit", type=int,
                   default=int(os.getenv("MEDIA_POLLER_X_LIMIT", "10")),
                   help="Results per broad X query (X API minimum/default: 10)")
    p.add_argument("--once", action="store_true", default=_env_bool("MEDIA_POLLER_ONCE"),
                   help="Poll once and exit (env: MEDIA_POLLER_ONCE)")
    p.add_argument("--no-macro", dest="macro", action="store_false", default=True,
                   help="Skip the macro snapshot (Polymarket odds + theme news). "
                        "Macro is on by default; it captures unrecoverable data.")
    trading_default = (os.getenv("MEDIA_POLLER_TRADING_HOURS", "true").strip().lower()
                       not in ("0", "false", "no", "off"))
    p.add_argument("--no-trading-hours", dest="trading_hours", action="store_false",
                   default=trading_default,
                   help="Poll around the clock instead of gating to market hours. "
                        "By default the daemon polls only during the extended US session "
                        "(04:00–20:00 ET) on NYSE trading days (env: MEDIA_POLLER_TRADING_HOURS).")
    p.add_argument("--stats", action="store_true", help="Print collection stats and exit")
    p.add_argument("--window", metavar="TICKER", help="Print the backtest window and exit")
    p.add_argument("--end", help="Window end date YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, default=7, help="Window length in days (default: 7)")
    args = p.parse_args(argv)

    store = open_store(args.db)
    try:
        if args.stats:
            print_stats(store)
            return
        if args.window:
            end = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print_window(store, args.window, end, args.days)
            return

        tickers = (
            [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
            if args.tickers else []
        )

        explicit = ([s.strip().lower() for s in args.sources.split(",") if s.strip()]
                    if args.sources else None)
        try:
            sources = resolve_sources(explicit)
        except ValueError as exc:
            p.error(str(exc))

        x_selected = "x" in sources
        ticker_sources = [source for source in sources if source != "x"]
        if ticker_sources and not tickers:
            p.error(
                "--tickers (or MEDIA_POLLER_TICKERS) is required for ticker-specific sources"
            )
        x_enabled = bool(x_selected and os.environ.get("X_BEARER_TOKEN"))
        if x_selected and not os.environ.get("X_BEARER_TOKEN"):
            logger.warning("source 'x' selected but X_BEARER_TOKEN is unset — it returns nothing.")
        if "truthsocial" in sources and not os.environ.get("TRUTHSOCIAL_TOKEN"):
            logger.warning("source 'truthsocial' selected but TRUTHSOCIAL_TOKEN is unset — "
                           "Cloudflare will likely block it.")
        macro_themes = DEFAULT_CONFIG.get("macro_themes", {}) if args.macro else {}
        if not ticker_sources and not macro_themes and not x_enabled:
            p.error("no enabled ticker, macro, or X collection source")
        store_label = args.db or (
            "configured database" if os.getenv("MEDIA_DB_URL") or os.getenv("DATABASE_URL")
            else "local SQLite (default)"
        )
        logger.info("Store: %s%s", store_label,
                    f" · macro: {len(macro_themes)} themes" if macro_themes else " · macro off")

        if args.once:
            # One-shot (cron/manual) always polls — gating is the daemon's job;
            # schedule cron during trading hours externally if desired.
            run_cycle(store, tickers, ticker_sources, macro_themes, x_enabled,
                      x_interval=args.x_interval, x_limit=args.x_limit,
                      x_topic_limit=args.x_topics, force_x=True)
        else:
            clock = TradingClock() if args.trading_hours else None
            poll_forever(store, tickers, ticker_sources, args.interval, macro_themes, clock,
                         x_enabled=x_enabled, x_interval=args.x_interval,
                         x_limit=args.x_limit, x_topic_limit=args.x_topics,
                         paper_heartbeat_max_age=float(
                             os.getenv("PAPER_HEARTBEAT_MAX_AGE", "0")
                         ) or None)
    finally:
        store.close()


if __name__ == "__main__":
    main()
