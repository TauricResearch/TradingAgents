from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional

try:  # optional dependency
    from alpaca.data.live import StockDataStream
    from alpaca.data.enums import DataFeed
except ImportError:  # pragma: no cover - only when dependency missing
    StockDataStream = None  # type: ignore
    DataFeed = None  # type: ignore

from tradingagents.services.autopilot_worker import AutopilotWorker
from tradingagents.services.hypothesis_store import HypothesisStore, HypothesisRecord


@dataclass
class PriceTrigger:
    hypothesis_id: str
    symbol: str
    operator: str
    value: float


class RealtimeBroker:
    """Subscribe to Alpaca stock data stream and enqueue autopilot events."""

    def __init__(
        self,
        store: HypothesisStore,
        worker: AutopilotWorker,
        api_key: str,
        secret_key: str,
        *,
        feed: str = "iex",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.store = store
        self.worker = worker
        self.logger = logger or logging.getLogger(__name__)
        if StockDataStream is None or DataFeed is None:
            raise RuntimeError(
                "alpaca-py is required for realtime broker. Install with `pip install alpaca-py`."
            )
        data_feed = DataFeed.IEX if feed.lower() == "iex" else DataFeed.SIP
        self.stream = StockDataStream(api_key, secret_key, feed=data_feed)
        self.triggers: Dict[str, List[PriceTrigger]] = {}
        self._subscribed: set[str] = set()
        self._registered_keys: set[str] = set()
        self._lock = threading.Lock()

    def bootstrap_triggers(self) -> None:
        self.refresh_triggers(reset=True)

    def refresh_triggers(
        self,
        records: Optional[List[HypothesisRecord]] = None,
        *,
        reset: bool = False,
    ) -> int:
        """Register triggers for stored hypotheses.

        When ``reset`` is True the in-memory trigger cache is rebuilt so updates to
        hypothesis triggers take effect immediately.
        Returns the number of triggers registered during this call (useful for logging).
        """

        dataset = records or self.store.list()
        with self._lock:
            if reset:
                self.triggers.clear()
                self._registered_keys.clear()

            registered = 0
            for record in dataset:
                for trigger in self._parse_triggers(record):
                    if self._register_trigger_locked(trigger):
                        registered += 1
        return registered

    def _parse_triggers(self, record: HypothesisRecord) -> List[PriceTrigger]:
        triggers: List[PriceTrigger] = []
        for raw in record.triggers:
            text = str(raw).strip().lower()
            if text.startswith("price >="):
                try:
                    symbol, value = self._extract_symbol_value(record.ticker, text, ">=")
                    triggers.append(
                        PriceTrigger(
                            hypothesis_id=record.id,
                            symbol=symbol,
                            operator=">=",
                            value=value,
                        )
                    )
                except ValueError:
                    continue
            elif text.startswith("price <="):
                try:
                    symbol, value = self._extract_symbol_value(record.ticker, text, "<=")
                    triggers.append(
                        PriceTrigger(
                            hypothesis_id=record.id,
                            symbol=symbol,
                            operator="<=",
                            value=value,
                        )
                    )
                except ValueError:
                    continue
        return triggers

    def _extract_symbol_value(self, default_symbol: str, text: str, operator: str) -> (str, float):
        left, right = text.replace("price", "").split(operator, 1)
        symbol = left.strip().upper() or default_symbol.upper()
        value = float(right.strip())
        return symbol, value

    def _register_trigger_locked(self, trigger: PriceTrigger) -> bool:
        key = self._trigger_key(trigger)
        if key in self._registered_keys:
            return False

        self._registered_keys.add(key)
        symbol = trigger.symbol
        bucket = self.triggers.setdefault(symbol, [])
        bucket.append(trigger)
        if symbol not in self._subscribed:
            self.stream.subscribe_trades(self._trade_handler, symbol)
            self._subscribed.add(symbol)
        return True

    def _trigger_key(self, trigger: PriceTrigger) -> str:
        return f"{trigger.hypothesis_id}:{trigger.symbol}:{trigger.operator}:{trigger.value}"

    async def _trade_handler(self, data) -> None:  # pragma: no cover - network callback
        symbol = getattr(data, "symbol", "")
        price = getattr(data, "price", None)
        if not symbol or price is None:
            return
        with self._lock:
            triggers = list(self.triggers.get(symbol, []))
        for trigger in triggers:
            if self._evaluate(trigger, price):
                self.worker.enqueue_event(
                    trigger.hypothesis_id,
                    event_type="price_threshold",
                    payload={"symbol": symbol, "price": price, "operator": trigger.operator, "value": trigger.value},
                )

    def _evaluate(self, trigger: PriceTrigger, price: float) -> bool:
        if trigger.operator == ">=":
            return price >= trigger.value
        if trigger.operator == "<=":
            return price <= trigger.value
        return False

    def run_forever(self) -> None:
        self.bootstrap_triggers()
        self.logger.info("Starting Alpaca stock data stream …")
        try:
            self.stream.run()
        except KeyboardInterrupt:  # pragma: no cover - manual stop
            self.logger.info("Realtime broker stopped")
