"""Item-level view of the news and social feeds.

The news, StockTwits and Reddit fetchers render what they fetched into one
prompt block. A consumer that judges items one at a time (the sentiment
analyst's Jev filter) needs the items themselves, so each fetcher also returns a
``Feed``: the items it kept plus the exact block it would have rendered. A
caller that cannot use the items falls back to that block without fetching
again, which matters for Reddit, where a second request inside a minute is
rate-limited.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedItem:
    """One news article or social post, as the prompt block shows it."""

    source: str  # "news", "stocktwits" or "reddit"
    text: str  # summary or post body, trimmed the way the block trims it
    title: str = ""
    published: str = ""  # display string only; windowing already happened in the fetcher
    author: str = ""  # publisher, @user, or r/subreddit
    label: str | None = None  # the author's own Bullish/Bearish tag (StockTwits)


@dataclass(frozen=True)
class Feed:
    """A source's items and the prompt block rendered from them.

    ``text`` is the block the fetcher's string function returns: the formatted
    items, or a placeholder when there are none. ``unavailable`` separates a
    source that could not answer for the window (a failed fetch or a coverage
    gap) from one that answered with silence.
    """

    text: str
    items: tuple[FeedItem, ...] = ()
    unavailable: bool = False
