from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Set

import websocket

from tradingagents.services.autopilot_worker import AutopilotWorker
from tradingagents.services.hypothesis_store import HypothesisStore, HypothesisRecord


class RealtimeNewsBroker:
    """Subscribe to Alpaca news WebSocket and forward events to the autopilot worker."""

    DEFAULT_URL = "wss://stream.data.alpaca.markets/v1beta1/news"

    def __init__(
        self,
        store: HypothesisStore,
        worker: AutopilotWorker,
        api_key: str,
        secret_key: str,
        *,
        url: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.store = store
        self.worker = worker
        self.api_key = api_key
        self.secret_key = secret_key
        self.url = url or self.DEFAULT_URL
        self.logger = logger or logging.getLogger(__name__)
        self.watchers: Dict[str, Set[str]] = defaultdict(set)
        self.ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def bootstrap_watchers(self) -> None:
        self.refresh_watchers()

    def refresh_watchers(self, records: Optional[List[HypothesisRecord]] = None) -> int:
        """Rebuild the news watcher map from stored hypotheses."""

        dataset = records or self.store.list()
        with self._lock:
            self.watchers.clear()
            registered = 0
            for record in dataset:
                registered += self._register_symbol_unlocked(record.ticker.upper(), record.id)
                for symbol in self._extract_symbols_from_triggers(record):
                    registered += self._register_symbol_unlocked(symbol, record.id)
        return registered

    def _extract_symbols_from_triggers(self, record: HypothesisRecord) -> List[str]:
        symbols: List[str] = []
        for raw in record.triggers:
            text = str(raw).strip().lower()
            if text.startswith("news"):
                parts = text.split(":", 1)
                if len(parts) == 2 and parts[1].strip():
                    symbols.append(parts[1].strip().upper())
                else:
                    symbols.append(record.ticker.upper())
        return symbols

    def _register_symbol(self, symbol: str, hypothesis_id: str) -> int:
        if not symbol:
            return 0
        symbol_key = symbol.upper()
        with self._lock:
            return self._register_symbol_unlocked(symbol_key, hypothesis_id)

    def _register_symbol_unlocked(self, symbol: str, hypothesis_id: str) -> int:
        if not symbol:
            return 0
        bucket = self.watchers[symbol]
        before = len(bucket)
        bucket.add(hypothesis_id)
        return 1 if len(bucket) > before else 0

    def start(self) -> None:
        if self.ws is not None:
            self.logger.info("News broker already running")
            return
        self.bootstrap_watchers()

        headers = [
            f"APCA-API-KEY-ID: {self.api_key}",
            f"APCA-API-SECRET-KEY: {self.secret_key}",
        ]

        self.ws = websocket.WebSocketApp(
            self.url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        def _run():  # pragma: no cover - network behavior
            self.logger.info("Connecting to Alpaca news stream …")
            self.ws.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _on_open(self, ws):  # pragma: no cover - network callback
        self.logger.info("News stream connected; subscribing to all news…")
        ws.send(json.dumps({"action": "subscribe", "news": ["*"]}))

    def _on_message(self, ws, message):  # pragma: no cover - network callback
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if isinstance(data, list):
            for item in data:
                self._handle_news(item)
        else:
            self._handle_news(data)

    def _handle_news(self, payload: Dict[str, object]) -> None:
        if payload.get("T") != "n":
            return
        symbols = payload.get("symbols") or []
        if not isinstance(symbols, list):
            return
        for symbol in symbols:
            symbol_key = str(symbol or "").upper()
            with self._lock:
                targets = list(self.watchers.get(symbol_key, ()))
            for hypothesis_id in targets:
                self.worker.enqueue_event(
                    hypothesis_id,
                    event_type="news",
                    payload=payload,
                )

    def _on_error(self, ws, error):  # pragma: no cover - network callback
        self.logger.error("News stream error: %s", error)

    def _on_close(self, ws, code, msg):  # pragma: no cover - network callback
        self.logger.info("News stream closed: %s %s", code, msg)
        self.ws = None
