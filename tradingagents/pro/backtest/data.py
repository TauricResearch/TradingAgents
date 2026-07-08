"""Bar replay: turn a historical bar series into per-step MarketSnapshots.

Lookahead safety is structural: the snapshot at step ``i`` contains only
bars up to and including ``i``, its indicators are computed from exactly
that window, and ``as_of`` is bar i's start. Fills happen on bar ``i+1``
in the engine — the decision never sees its own fill bar.

Review finding QUANT-01: without a historical corpus, replay snapshots
carry only bars+indicators, so macro/news/on-chain agents abstain and
backtests validate a technicals-only subsystem. ``HistoricalCorpus``
closes that gap: as-of-dated macro/onchain readings and news items,
sliced with the same no-future rule as bars. Without a corpus, the
snapshot records the missing feeds explicitly so results are labelled.

Works for any contract Timeframe (1m..1w). Tick data is pending the paid
microstructure feeds in docs/DATA_SOURCES.md.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from tradingagents.contracts import (
    AssetClass,
    MarketSnapshot,
    MetricReading,
    NewsItem,
    OHLCVBar,
)
from tradingagents.pro.ingestion.indicators import DEFAULT_INDICATOR_NAMES, compute_indicators


class HistoricalCorpus:
    """As-of-dated non-price context for replay: {timestamp: day-record}.

    Each day-record carries macro/onchain MetricReadings and NewsItems.
    ``as_of(ts)`` returns the latest record at or before ts — never after.
    """

    def __init__(self):
        self._days: list[tuple[datetime, dict]] = []  # sorted by timestamp

    def add_day(
        self,
        ts: datetime,
        macro: Sequence[MetricReading] = (),
        onchain: Sequence[MetricReading] = (),
        news: Sequence[NewsItem] = (),
    ) -> None:
        self._days.append((ts, {
            "macro": list(macro), "onchain": list(onchain), "news": list(news),
        }))
        self._days.sort(key=lambda pair: pair[0])

    def as_of(self, ts: datetime) -> dict:
        latest: dict = {"macro": [], "onchain": [], "news": []}
        for day_ts, record in self._days:
            if day_ts > ts:
                break
            latest = record
        return latest

    # --- JSONL persistence (the ingestion recorder's output format) ----------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for ts, record in self._days:
                handle.write(json.dumps({
                    "ts": ts.isoformat(),
                    "macro": [m.model_dump(mode="json") for m in record["macro"]],
                    "onchain": [m.model_dump(mode="json") for m in record["onchain"]],
                    "news": [n.model_dump(mode="json") for n in record["news"]],
                }) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> HistoricalCorpus:
        corpus = cls()
        with Path(path).open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                corpus.add_day(
                    datetime.fromisoformat(raw["ts"]),
                    macro=[MetricReading.model_validate(m) for m in raw["macro"]],
                    onchain=[MetricReading.model_validate(m) for m in raw["onchain"]],
                    news=[NewsItem.model_validate(n) for n in raw["news"]],
                )
        return corpus


class BarReplay:
    def __init__(
        self,
        symbol: str,
        asset: AssetClass,
        bars: Sequence[OHLCVBar],
        window: int = 250,
        indicator_names: Sequence[str] = DEFAULT_INDICATOR_NAMES,
        corpus: HistoricalCorpus | None = None,
    ):
        bars = sorted(bars, key=lambda b: b.start)
        timeframes = {b.timeframe for b in bars}
        if len(timeframes) > 1:
            raise ValueError("replay drives on a single timeframe series")
        if len(bars) < 3:
            raise ValueError("need at least 3 bars to replay")
        self.symbol = symbol
        self.asset = asset
        self.bars = list(bars)
        self.window = window
        self.indicator_names = tuple(indicator_names)
        self.corpus = corpus

    def __len__(self) -> int:
        return len(self.bars)

    def snapshot_at(self, i: int) -> MarketSnapshot:
        """Snapshot as of the close of bar ``i`` — bars after i do not exist."""
        if not 0 <= i < len(self.bars):
            raise IndexError(i)
        visible = self.bars[max(0, i + 1 - self.window) : i + 1]
        as_of = visible[-1].start
        context = (
            self.corpus.as_of(as_of)
            if self.corpus is not None
            else {"macro": [], "onchain": [], "news": []}
        )
        return MarketSnapshot(
            symbol=self.symbol,
            asset=self.asset,
            as_of=as_of,
            bars=visible,
            indicators=compute_indicators(visible, self.indicator_names),
            macro=context["macro"],
            onchain=context["onchain"],
            news=context["news"],
            missing_feeds=(
                [] if self.corpus is not None
                else ["macro:no-corpus", "onchain:no-corpus", "news:no-corpus"]
            ),
        )
