"""Delta Exchange (India) live venue adapter — VenueAdapter v2 transport.

Deliberately separate from ``ingestion/delta_exchange.py``: the market-data
read path and the money write path never share a client, so a data outage
can't take trading hygiene down with it (and vice versa).

Design points (go-live Phase 1):
- **No write retries here.** ``place_order`` raises ``AdapterError`` on
  transport failure and the OMS (Phase 2) owns the resolve-by-coid loop.
  Read endpoints retry with exponential backoff + jitter.
- **Typed error taxonomy**: network/5xx/429 → ``AdapterError`` (transient);
  semantic 4xx → terminal REJECTED in the returned OrderUpdate.
- **Client-side token bucket** against the documented 10 000 units/5 min
  budget (order ops cost 5); a venue 429 honors ``X-RATE-LIMIT-RESET``.
- **Clock skew**: signatures die after 5s; ``check_clock`` refuses trading
  when |skew| > 2s.
- **Sizes are integer contracts** — the InstrumentService owns the
  canonical-quantity ↔ contracts conversion (never hardcoded).
- Credentials are redacted from every exception and log line.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Protocol

from tradingagents.pro.execution.adapters.delta_auth import (
    MAX_CLOCK_SKEW_SECONDS,
    DeltaCredentials,
    clock_skew_seconds,
    redact,
    sign,
)
from tradingagents.pro.execution.instruments import InstrumentInfo, InstrumentService
from tradingagents.pro.execution.interface import (
    AccountState,
    AdapterCapabilities,
    AdapterError,
    BracketSpec,
    BrokerPosition,
    OrderSpec,
    OrderState,
    OrderUpdate,
)

logger = logging.getLogger(__name__)

PROD_BASE = "https://api.india.delta.exchange"
TESTNET_BASE = "https://cdn-ind.testnet.deltaex.org"

# documented request weights (units); budget 10_000 per 5 minutes
_WEIGHT_ORDER = 5
_WEIGHT_READ = 3
_BUDGET_UNITS = 10_000
_BUDGET_WINDOW = 300.0

# canonical -> Delta venue symbols this adapter will trade
SYMBOL_MAP = {"BTC-USD": "BTCUSD", "XAUUSD": "XAUTUSD"}
_REVERSE_MAP = {v: k for k, v in SYMBOL_MAP.items()}


class HttpResponse(Protocol):
    status_code: int
    headers: dict

    def json(self) -> dict: ...


class HttpClient(Protocol):
    """Injectable transport seam (same style as ingestion/base.py) —
    conformance tests run against a fake implementing this."""

    def request(self, method: str, url: str, *, params: dict | None = None,
                data: str | None = None, headers: dict | None = None,
                timeout: float = 30.0) -> HttpResponse: ...


class _RequestsClient:
    def __init__(self):
        import requests

        self._session = requests.Session()

    def request(self, method, url, *, params=None, data=None, headers=None,
                timeout=30.0):
        return self._session.request(
            method, url, params=params, data=data,
            headers={"User-Agent": "tradingagents-pro/0.1",
                     "Content-Type": "application/json", **(headers or {})},
            timeout=timeout,
        )


class _TokenBucket:
    """Client-side budget so we throttle ourselves before the venue does."""

    def __init__(self, budget: int = _BUDGET_UNITS, window: float = _BUDGET_WINDOW):
        self.budget = budget
        self.window = window
        self._spent: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def spend(self, units: int) -> None:
        with self._lock:
            now = time.monotonic()
            self._spent = [(t, u) for t, u in self._spent
                           if now - t < self.window]
            if sum(u for _, u in self._spent) + units > self.budget:
                raise AdapterError(
                    "client-side rate budget exhausted; backing off"
                )
            self._spent.append((now, units))


def _order_state(order: dict) -> OrderState:
    state = order.get("state", "")
    size = float(order.get("size") or 0)
    unfilled = float(order.get("unfilled_size") or 0)
    if state == "open":
        return (OrderState.PARTIALLY_FILLED if 0 < unfilled < size
                else OrderState.ACKED)
    if state == "pending":
        return OrderState.SUBMITTED
    if state == "closed":
        return OrderState.FILLED
    if state == "cancelled":
        # partial fills before the cancel ride along in filled_quantity
        return OrderState.CANCELED
    return OrderState.UNKNOWN


class DeltaAdapter:
    """VenueAdapter for Delta India. BTCUSD perp + XAUTUSD (Tether Gold,
    ≈ spot gold with a small disclosed basis)."""

    def __init__(self, credentials: DeltaCredentials,
                 base_url: str = TESTNET_BASE,
                 http: HttpClient | None = None,
                 instruments: InstrumentService | None = None,
                 max_read_retries: int = 3):
        self._creds = credentials
        self._base = base_url.rstrip("/")
        self._http = http or _RequestsClient()
        self._bucket = _TokenBucket()
        self._max_read_retries = max_read_retries
        self.name = f"delta:{'testnet' if 'testnet' in self._base else 'india'}"
        self.instruments = instruments or InstrumentService(
            fetch=self._fetch_instruments, fail_closed=True,
        )
        self._clock_checked = False

    @classmethod
    def from_env(cls, testnet: bool = True, **kwargs) -> DeltaAdapter:
        prefix = "DELTA_TESTNET" if testnet else "DELTA"
        key = os.environ.get(f"{prefix}_API_KEY", "")
        secret = os.environ.get(f"{prefix}_API_SECRET", "")
        if not key or not secret:
            raise AdapterError(
                f"{prefix}_API_KEY/{prefix}_API_SECRET not set — refusing to "
                "construct a live adapter without credentials"
            )
        base = TESTNET_BASE if testnet else PROD_BASE
        return cls(DeltaCredentials(key, secret), base_url=base, **kwargs)

    # --- transport -------------------------------------------------------------

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 body: str = "", auth: bool = True, weight: int = _WEIGHT_READ,
                 retryable: bool = True) -> dict:
        self._bucket.spend(weight)
        from urllib.parse import urlencode

        query = f"?{urlencode(params)}" if params else ""
        attempts = (1 + self._max_read_retries) if retryable else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            headers = (sign(self._creds, method, path, query, body)
                       if auth else {})
            try:
                response = self._http.request(
                    method, f"{self._base}{path}", params=params,
                    data=body or None, headers=headers,
                )
            except Exception as exc:  # network layer
                last_error = AdapterError(
                    redact(f"{method} {path}: {exc}",
                           self._creds.api_key, self._creds.api_secret))
                self._sleep_backoff(attempt)
                continue
            if response.status_code == 429:
                reset_ms = response.headers.get("X-RATE-LIMIT-RESET", "1000")
                last_error = AdapterError(
                    f"429 from venue; reset in {reset_ms}ms")
                time.sleep(min(float(reset_ms) / 1000.0, 10.0))
                continue
            if response.status_code >= 500:
                last_error = AdapterError(f"{response.status_code} from venue")
                self._sleep_backoff(attempt)
                continue
            payload = response.json()
            if response.status_code >= 400:
                # semantic 4xx: terminal, caller maps to REJECTED
                raise _SemanticError(redact(
                    str(payload.get("error", payload)),
                    self._creds.api_key, self._creds.api_secret,
                ))
            self._maybe_check_clock(response)
            return payload
        raise last_error or AdapterError(f"{method} {path}: exhausted retries")

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(min(0.25 * (2 ** attempt), 4.0) * (0.5 + random.random()))

    def _maybe_check_clock(self, response) -> None:
        if self._clock_checked:
            return
        date_header = response.headers.get("Date", "")
        if not date_header:
            return
        skew = clock_skew_seconds(date_header)
        self._clock_checked = True
        if abs(skew) > MAX_CLOCK_SKEW_SECONDS:
            raise AdapterError(
                f"local/venue clock skew {skew:+.1f}s exceeds "
                f"{MAX_CLOCK_SKEW_SECONDS}s budget — signatures expire in 5s; "
                "fix NTP before trading"
            )

    def check_clock(self) -> None:
        """Boot-time skew check (forces one cheap authenticated-less call)."""
        self._clock_checked = False
        self._request("GET", "/v2/products", params={"page_size": 1},
                      auth=False)

    # --- instruments -------------------------------------------------------------

    def _fetch_instruments(self) -> dict[str, InstrumentInfo]:
        payload = self._request("GET", "/v2/products", auth=False)
        infos: dict[str, InstrumentInfo] = {}
        for product in payload.get("result", []):
            canonical = _REVERSE_MAP.get(product.get("symbol", ""))
            if canonical is None:
                continue
            infos[canonical] = InstrumentInfo(
                symbol=canonical,
                venue_symbol=product["symbol"],
                product_id=product.get("id"),
                tick_size=float(product.get("tick_size") or 0.01),
                contract_value=float(product.get("contract_value") or 1.0),
                min_contracts=1,
                max_leverage=float(product.get("default_leverage") or 1.0),
                as_of=time.time(),
            )
        missing = set(SYMBOL_MAP) - set(infos)
        if missing:
            raise AdapterError(f"venue product list missing {sorted(missing)}")
        return infos

    def supported_symbols(self) -> set[str]:
        return set(SYMBOL_MAP)

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            native_bracket=True,           # SL/TP fields on the order payload
            terminal_on_place=False,
            supports_client_oid_lookup=True,  # GET /v2/orders/client_order_id/{id}
            supports_streams=False,        # WS not implemented yet — honest
        )

    # --- orders ------------------------------------------------------------------

    def _to_update(self, order: dict) -> OrderUpdate:
        canonical = _REVERSE_MAP.get(order.get("product_symbol", ""))
        info = (self.instruments.get(canonical) if canonical
                else InstrumentInfo(symbol="?", venue_symbol="?"))
        size = float(order.get("size") or 0)
        unfilled = float(order.get("unfilled_size") or 0)
        return OrderUpdate(
            client_order_id=order.get("client_order_id", ""),
            state=_order_state(order),
            venue_order_id=str(order.get("id", "")),
            filled_quantity=info.to_quantity(size - unfilled),
            avg_fill_price=float(order.get("average_fill_price") or 0),
            commission=float(order.get("paid_commission") or 0),
            reason=str(order.get("error") or ""),
            ts=datetime.now(timezone.utc),
            raw=order,
        )

    def place_order(self, spec: OrderSpec,
                    bracket: BracketSpec | None = None) -> OrderUpdate:
        import json as _json

        info = self.instruments.get(spec.symbol)
        contracts = info.to_contracts(spec.quantity)
        if contracts < info.min_contracts:
            return OrderUpdate(
                client_order_id=spec.client_order_id,
                state=OrderState.REJECTED,
                reason=f"{spec.quantity} {spec.symbol} rounds to {contracts} "
                       f"contracts, below venue minimum {info.min_contracts}",
            )
        payload: dict = {
            "product_symbol": info.venue_symbol,
            "size": contracts,
            "side": spec.side.lower(),
            "order_type": ("limit_order" if spec.order_type == "limit"
                           else "market_order"),
            "client_order_id": spec.client_order_id,
            "reduce_only": spec.reduce_only,
            "time_in_force": spec.time_in_force,
        }
        if spec.order_type == "limit" and spec.limit_price is not None:
            payload["limit_price"] = str(info.round_price(spec.limit_price))
        if bracket is not None:
            payload["bracket_stop_loss_price"] = str(
                info.round_price(bracket.stop_loss_price))
            if bracket.take_profits:
                # venue supports one native TP; the OMS sends the FINAL
                # target (matches the paper engine's exit semantics)
                payload["bracket_take_profit_price"] = str(
                    info.round_price(bracket.take_profits[-1][0]))
        try:
            result = self._request(
                "POST", "/v2/orders", body=_json.dumps(payload),
                weight=_WEIGHT_ORDER, retryable=False,  # OMS owns resolve
            )
        except _SemanticError as exc:
            return OrderUpdate(client_order_id=spec.client_order_id,
                               state=OrderState.REJECTED, reason=str(exc))
        return self._to_update(result.get("result", {}))

    def cancel_order(self, client_order_id: str) -> OrderUpdate:
        import json as _json

        existing = self.get_order(client_order_id)
        if existing is None:
            return OrderUpdate(client_order_id=client_order_id,
                               state=OrderState.REJECTED,
                               reason="unknown order")
        if existing.state.terminal:
            return existing
        product_id = existing.raw.get("product_id")
        try:
            result = self._request(
                "DELETE", "/v2/orders",
                body=_json.dumps({"client_order_id": client_order_id,
                                  "product_id": product_id}),
                weight=_WEIGHT_ORDER, retryable=False,
            )
        except _SemanticError as exc:
            return OrderUpdate(client_order_id=client_order_id,
                               state=OrderState.UNKNOWN, reason=str(exc))
        return self._to_update(result.get("result", {}))

    def get_order(self, client_order_id: str) -> OrderUpdate | None:
        try:
            result = self._request(
                "GET", f"/v2/orders/client_order_id/{client_order_id}")
        except _SemanticError:
            return None
        order = result.get("result")
        return self._to_update(order) if order else None

    def open_orders(self) -> list[OrderUpdate]:
        result = self._request("GET", "/v2/orders",
                               params={"states": "open,pending"})
        return [self._to_update(o) for o in result.get("result", [])]

    def poll_updates(self, since: datetime) -> list[OrderUpdate]:
        # REST correctness backbone: open orders + recent history
        updates = {u.client_order_id: u for u in self.open_orders()}
        result = self._request(
            "GET", "/v2/orders/history",
            params={"start_time": int(since.timestamp() * 1_000_000)})
        for order in result.get("result", []):
            update = self._to_update(order)
            updates.setdefault(update.client_order_id, update)
        return sorted(updates.values(), key=lambda u: u.ts)

    # --- account ------------------------------------------------------------------

    def positions(self) -> list[BrokerPosition]:
        result = self._request("GET", "/v2/positions",
                               params={"product_ids": "all"})
        rows = result.get("result", [])
        if isinstance(rows, dict):
            rows = [rows]
        out = []
        for row in rows:
            canonical = _REVERSE_MAP.get(row.get("product_symbol", ""))
            size = float(row.get("size") or 0)
            if canonical is None or size == 0:
                continue
            info = self.instruments.get(canonical)
            out.append(BrokerPosition(
                symbol=canonical,
                side="BUY" if size > 0 else "SELL",
                quantity=info.to_quantity(abs(size)),
                avg_price=float(row.get("entry_price") or 0),
            ))
        return out

    def account(self) -> AccountState:
        result = self._request("GET", "/v2/wallet/balances")
        balances = result.get("result", [])
        cash = sum(float(b.get("available_balance") or 0) for b in balances)
        equity = sum(float(b.get("balance") or 0) for b in balances)
        return AccountState(venue=self.name, equity=equity, cash=cash,
                            positions=tuple(self.positions()))


class _SemanticError(Exception):
    """4xx the venue means: terminal for this request, never retried."""
