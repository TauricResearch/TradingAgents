"""OKX's signed (private) REST API, for the demo execution account (ADR 0008).

Only OKX's simulated trading is reachable from here: every request carries the
``x-simulated-trading: 1`` header, and ``OKXPrivate`` refuses to be built for the
live environment. The credentials are a separate API key made in OKX's demo
trading area with the trade permission only; they come from the environment
(``OKXCredentials.from_env``) and never appear in a repr, a log or an error.

Every call returns plain dataclasses with the few fields the executor needs, in
the units the account keeps: contract counts are OKX's (``sz``, signed by the
position's side in net mode), prices and fees in USDT, times in UTC milliseconds.
Errors follow ``trader.okx``: a connection failure, timeout, 429 or 5xx is retried
with the same pauses, a non-zero OKX code raises ``OKXPrivateError`` carrying the
code so that callers can tell e.g. a duplicate client order id (already placed)
from a real failure.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import requests

from trader.okx import _RETRY_PAUSES, BASE_URL, OKXError

SIMULATED_HEADER = "x-simulated-trading"
PROBE_ORDER_ID = "1"  # OKX order ids are 18-digit; this one can never exist
DUPLICATE_CLIENT_ID = "51016"  # OKX's code for a clOrdId / algoClOrdId that already exists
TIMESTAMP_EXPIRED = "50102"    # the request's timestamp was more than 30 s off OKX's clock
_PAGE = 100                    # rows per page; the most fills and bills endpoints give
_DAY_MS = 86_400_000
RECENT_FILLS_MS = 3 * _DAY_MS - 3_600_000  # the span the three-day fills endpoint is sure to hold
_TIMEOUT = 10


class OKXPrivateError(OKXError):
    """OKX answered a signed request with a non-zero code (the order's ``sCode`` when
    the request was an order). ``code`` is that code as OKX spells it, ``message``
    its text."""

    def __init__(self, path: str, code: str, message: str):
        super().__init__(f"{path} failed with code {code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, repr=False)
class OKXCredentials:
    """An API key of OKX's simulated trading. Masked wherever it is printed."""

    key: str
    secret: str
    passphrase: str

    def __repr__(self) -> str:
        return "OKXCredentials(***)"

    __str__ = __repr__

    @classmethod
    def from_env(cls, prefix: str = "TRADER_OKX_DEMO") -> OKXCredentials | None:
        """The credentials in ``<prefix>_KEY``, ``<prefix>_SECRET`` and
        ``<prefix>_PASSPHRASE``; None when none of them is set. ValueError, naming
        the missing variables and nothing else, when only some are."""
        names = [f"{prefix}_{part}" for part in ("KEY", "SECRET", "PASSPHRASE")]
        values = [os.getenv(name, "").strip() for name in names]
        if not any(values):
            return None
        missing = [name for name, value in zip(names, values, strict=True) if not value]
        if missing:
            raise ValueError(f"{', '.join(missing)} must be set along with the other OKX variables")
        return cls(*values)


@dataclass(frozen=True)
class AccountConfig:
    position_mode: str   # "net_mode" or "long_short_mode"
    account_level: str   # "1" spot, "2" single-currency margin, "3" multi-currency, "4" portfolio
    permissions: str     # e.g. "read_only,trade"


@dataclass(frozen=True)
class Balance:
    """One currency's balance. ``equity`` includes unrealized PnL, ``cash`` does not,
    ``available`` is what new orders may use as margin."""

    ccy: str
    equity: float
    cash: float
    available: float
    unrealized: float


@dataclass(frozen=True)
class ExchangePosition:
    inst: str
    contracts: float      # signed: short positions are negative (net mode)
    avg_price: float
    unrealized: float
    leverage: float
    margin_mode: str      # "cross" or "isolated"
    liquidation_price: float | None
    updated: int          # UTC ms


@dataclass(frozen=True)
class Order:
    order_id: str
    client_id: str
    inst: str
    state: str            # live, partially_filled, filled, canceled, mmp_canceled
    side: str             # buy or sell
    size: float           # contracts asked
    filled: float         # contracts filled so far
    avg_price: float | None
    fee: float            # negative when paid
    algo_client_id: str   # the stop's algoClOrdId when a stop triggered this order
    updated: int


@dataclass(frozen=True)
class ExchangeFill:
    bill_id: str
    trade_id: str
    order_id: str
    client_id: str        # the order's clOrdId; "" when the order had none
    inst: str
    side: str
    contracts: float      # unsigned, as OKX reports it
    price: float
    fee: float            # negative when paid
    ts: int


@dataclass(frozen=True)
class StopOrder:
    """A pending conditional order: a stop that closes ``contracts`` at market once the
    last price crosses ``trigger``."""

    algo_id: str
    client_id: str
    inst: str
    side: str
    contracts: float
    trigger: float
    reduce_only: bool
    created: int


@dataclass(frozen=True)
class FundingBill:
    bill_id: str
    inst: str
    amount: float         # change of balance: negative when paid, positive when received
    ts: int


def sign(secret: str, timestamp: str, method: str, path: str, body: str = "") -> str:
    """OKX's request signature: Base64 of HMAC-SHA256 over timestamp + method +
    request path (with its query string) + body."""
    message = f"{timestamp}{method}{path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(), message, hashlib.sha256).digest()).decode()


def timestamp(now: float) -> str:
    """OKX's timestamp header for a UNIX time: ISO 8601 in UTC with milliseconds."""
    return datetime.fromtimestamp(now, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OKXPrivate:
    """Signed calls to OKX's simulated trading (ADR 0008)."""

    def __init__(
        self,
        credentials: OKXCredentials,
        session: requests.Session | None = None,
        simulated: bool = True,
        clock: Callable[[], float] = time.time,
    ):
        if not simulated:
            raise ValueError(
                "live trading is not enabled: only OKX simulated trading is reachable (ADR 0008)"
            )
        self._credentials = credentials
        self.session = session or requests.Session()
        self.clock = clock

    def __repr__(self) -> str:
        return "OKXPrivate(simulated)"

    # -- account ------------------------------------------------------------

    def account_config(self) -> AccountConfig:
        row = self._get("/api/v5/account/config")[0]
        return AccountConfig(
            position_mode=row["posMode"], account_level=row["acctLv"], permissions=row["perm"]
        )

    def set_position_mode(self, net: bool = True) -> None:
        """Switch between net and long/short mode; OKX refuses while a position or
        pending order exists."""
        self._post("/api/v5/account/set-position-mode",
                   {"posMode": "net_mode" if net else "long_short_mode"})

    def set_leverage(self, inst: str, leverage: int, margin_mode: str = "cross") -> None:
        self._post("/api/v5/account/set-leverage",
                   {"instId": inst, "lever": str(leverage), "mgnMode": margin_mode})

    def balance(self, ccy: str = "USDT") -> Balance:
        """The balance of ``ccy``; all zero when the account holds none of it."""
        details = self._get("/api/v5/account/balance", ccy=ccy)[0]["details"]
        rows = [d for d in details if d["ccy"] == ccy]
        if not rows:
            return Balance(ccy, 0.0, 0.0, 0.0, 0.0)
        row = rows[0]
        return Balance(
            ccy=ccy,
            equity=_float(row["eq"]),
            cash=_float(row["cashBal"]),
            available=_float(row["availBal"]),
            unrealized=_float(row.get("upl")),
        )

    def positions(self) -> list[ExchangePosition]:
        """Open swap positions, contracts signed by side. A position OKX reports at
        zero contracts (just closed) is left out."""
        out = []
        for row in self._get("/api/v5/account/positions", instType="SWAP"):
            contracts = _float(row["pos"])
            if contracts == 0:
                continue
            if row.get("posSide") == "short":  # long/short mode reports unsigned counts
                contracts = -abs(contracts)
            out.append(ExchangePosition(
                inst=row["instId"],
                contracts=contracts,
                avg_price=_float(row["avgPx"]),
                unrealized=_float(row.get("upl")),
                leverage=_float(row.get("lever")),
                margin_mode=row["mgnMode"],
                liquidation_price=_float(row["liqPx"]) if row.get("liqPx") else None,
                updated=int(row["uTime"]),
            ))
        return out

    # -- orders -------------------------------------------------------------

    def place_market(
        self, inst: str, contracts: float, client_id: str,
        reduce_only: bool = False, margin_mode: str = "cross",
    ) -> str:
        """A market order for ``contracts`` (positive buys, negative sells); returns
        OKX's order id. ``client_id`` makes it idempotent: a second placement with
        the same id raises OKXPrivateError with code DUPLICATE_CLIENT_ID."""
        if contracts == 0:
            raise ValueError("a market order needs a non-zero contract count")
        row = self._post("/api/v5/trade/order", {
            "instId": inst,
            "tdMode": margin_mode,
            "side": "buy" if contracts > 0 else "sell",
            "ordType": "market",
            "sz": _size(contracts),
            "clOrdId": client_id,
            "reduceOnly": reduce_only,
        })[0]
        return row["ordId"]

    def check_trade_permission(self, inst: str) -> None:
        """Raise OKXPrivateError when the key cannot place orders on ``inst``; a no-op
        when it can. The account endpoints do not tell: a key whose trade permission
        leaves out crypto reads config, balance and leverage fine and fails only at
        the order (50123). The probe cancels an order that cannot exist: a 50xxx
        answer is the gateway refusing the key, a 51xxx one (51400, the order does
        not exist) means the request went through. Nothing is placed or changed."""
        try:
            self._post("/api/v5/trade/cancel-order", {"instId": inst, "ordId": PROBE_ORDER_ID})
        except OKXPrivateError as exc:
            if exc.code.startswith("50"):
                raise

    def order(self, inst: str, client_id: str | None = None, order_id: str | None = None) -> Order:
        """An order by client or exchange id; OKXPrivateError (code 51603) when there
        is none."""
        if not (client_id or order_id):
            raise ValueError("order() needs a client_id or an order_id")
        params = {"instId": inst}
        if order_id:
            params["ordId"] = order_id
        else:
            params["clOrdId"] = client_id
        return _order(self._get("/api/v5/trade/order", **params)[0])

    def fills(self, begin_ms: int, end_ms: int) -> list[ExchangeFill]:
        """Swap fills with ``begin_ms <= ts < end_ms``, oldest first.

        The three-day endpoint is the one OKX keeps for recently filled orders (and
        the one with the room in its rate limit); the three-month history is for
        catching up after a long gap. So the part of the window within RECENT_FILLS_MS
        of now is read from the three-day endpoint and only the part older than that
        from the history, merged by bill id.
        """
        recent_from = int(self.clock() * 1000) - RECENT_FILLS_MS
        rows: dict[str, dict] = {}
        if begin_ms < recent_from:
            for r in self._pages("/api/v5/trade/fills-history", {"instType": "SWAP"},
                                 begin_ms, min(end_ms, recent_from)):
                rows[r["billId"]] = r
        if end_ms > recent_from:
            for r in self._pages("/api/v5/trade/fills", {"instType": "SWAP"},
                                 max(begin_ms, recent_from), end_ms):
                rows[r["billId"]] = r
        return [
            ExchangeFill(
                bill_id=r["billId"], trade_id=r["tradeId"], order_id=r["ordId"],
                client_id=r.get("clOrdId") or "", inst=r["instId"], side=r["side"],
                contracts=_float(r["fillSz"]), price=_float(r["fillPx"]), fee=_float(r["fee"]),
                ts=int(r["ts"]),
            )
            for r in sorted(rows.values(), key=lambda r: (int(r["ts"]), int(r["billId"])))
        ]

    def close_position(self, inst: str, margin_mode: str = "cross", client_id: str | None = None) -> None:
        """Close the whole position at market and cancel the orders that were closing
        it; ``client_id`` names the closing order's fills. A no-op error (51023, no
        position) is swallowed."""
        body = {"instId": inst, "mgnMode": margin_mode, "autoCxl": True}
        if client_id:
            body["clOrdId"] = client_id
        try:
            self._post("/api/v5/trade/close-position", body)
        except OKXPrivateError as exc:
            if exc.code != "51023":
                raise

    # -- stops --------------------------------------------------------------

    def place_stop(
        self, inst: str, contracts: float, trigger: float, client_id: str,
        margin_mode: str = "cross",
    ) -> str:
        """A reduce-only conditional order closing ``contracts`` of a position (positive
        for a long, negative for a short) at market once the last price crosses
        ``trigger``; returns the algo id. Idempotent on ``client_id`` like place_market."""
        if contracts == 0:
            raise ValueError("a stop needs a non-zero contract count")
        row = self._post("/api/v5/trade/order-algo", {
            "instId": inst,
            "tdMode": margin_mode,
            "side": "sell" if contracts > 0 else "buy",
            "ordType": "conditional",
            "sz": _size(contracts),
            "slTriggerPx": _price(trigger),
            "slOrdPx": "-1",
            "slTriggerPxType": "last",
            "reduceOnly": True,
            "algoClOrdId": client_id,
        })[0]
        return row["algoId"]

    def pending_stops(self) -> list[StopOrder]:
        """Conditional orders still waiting for their trigger, on any swap."""
        rows = self._get("/api/v5/trade/orders-algo-pending", ordType="conditional", instType="SWAP")
        return [
            StopOrder(
                algo_id=r["algoId"], client_id=r.get("algoClOrdId") or "", inst=r["instId"],
                side=r["side"], contracts=_float(r["sz"]), trigger=_float(r["slTriggerPx"]),
                reduce_only=str(r.get("reduceOnly", "")).lower() == "true", created=int(r["cTime"]),
            )
            for r in rows
        ]

    def cancel_stops(self, stops: list[StopOrder]) -> None:
        """Cancel pending conditional orders; one already gone (51400/51401) is ignored."""
        if not stops:
            return
        try:
            self._post("/api/v5/trade/cancel-algos",
                       [{"algoId": s.algo_id, "instId": s.inst} for s in stops])
        except OKXPrivateError as exc:
            if exc.code not in ("51400", "51401"):
                raise

    # -- funding ------------------------------------------------------------

    def funding_bills(self, begin_ms: int, end_ms: int) -> list[FundingBill]:
        """Funding fees settled on swaps with ``begin_ms <= ts < end_ms``, oldest first,
        from the three-month bill archive (bill type 8)."""
        rows = self._pages("/api/v5/account/bills-archive",
                           {"instType": "SWAP", "type": "8"}, begin_ms, end_ms)
        return [
            FundingBill(bill_id=r["billId"], inst=r["instId"], amount=_float(r["balChg"]), ts=int(r["ts"]))
            for r in rows
        ]

    # -- transport ----------------------------------------------------------

    def _get(self, path: str, **params) -> list:
        query = f"?{urlencode(params)}" if params else ""
        return self._request("GET", path + query)

    def _post(self, path: str, body: dict | list) -> list:
        return self._request("POST", path, json.dumps(body, separators=(",", ":")))

    def _request(self, method: str, path: str, body: str = "") -> list:
        """``data`` of a signed request; retries and errors as ``OKX._get``, plus the
        per-item ``sCode`` of an order endpoint that reports a failure."""
        for pause in (*_RETRY_PAUSES, None):
            try:
                response = self.session.request(
                    method, BASE_URL + path, data=body or None, headers=self._headers(method, path, body),
                    timeout=_TIMEOUT,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                if pause is None:
                    raise
                time.sleep(pause)
        try:
            answer = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        code = answer.get("code")
        if code != "0":
            # An order endpoint reports each item's own sCode; the first failed one explains.
            data = answer.get("data") if isinstance(answer.get("data"), list) else []
            failed = [d for d in data if isinstance(d, dict) and d.get("sCode") not in (None, "0")]
            item = failed[0] if failed else {}
            raise OKXPrivateError(
                path.split("?")[0], item.get("sCode") or str(code), item.get("sMsg") or answer.get("msg", "")
            )
        return answer["data"]

    def _headers(self, method: str, path: str, body: str) -> dict[str, str]:
        stamp = timestamp(self.clock())
        return {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self._credentials.key,
            "OK-ACCESS-SIGN": sign(self._credentials.secret, stamp, method, path, body),
            "OK-ACCESS-TIMESTAMP": stamp,
            "OK-ACCESS-PASSPHRASE": self._credentials.passphrase,
            SIMULATED_HEADER: "1",
        }

    def _pages(self, path: str, params: dict, begin_ms: int, end_ms: int) -> list[dict]:
        """Rows of a newest-first, bill-id-paged endpoint with ``begin_ms <= ts < end_ms``,
        oldest first. Each page asks for the rows older than the last page's oldest
        bill id; paging stops at an empty or short page, or once a row is older than
        ``begin_ms``."""
        rows: dict[str, dict] = {}
        after = None
        while True:
            page_params = {**params, "begin": str(begin_ms), "end": str(end_ms), "limit": str(_PAGE)}
            if after is not None:
                page_params["after"] = after
            page = self._get(path, **page_params)
            for row in page:
                if begin_ms <= int(row["ts"]) < end_ms:
                    rows[row["billId"]] = row
            if len(page) < _PAGE or any(int(row["ts"]) < begin_ms for row in page):
                break
            oldest = page[-1]["billId"]
            if oldest == after:
                raise OKXError(f"{path} paging did not advance past bill {after}")
            after = oldest
        return sorted(rows.values(), key=lambda r: (int(r["ts"]), int(r["billId"])))


def _order(row: dict) -> Order:
    return Order(
        order_id=row["ordId"], client_id=row.get("clOrdId") or "", inst=row["instId"],
        state=row["state"], side=row["side"], size=_float(row["sz"]), filled=_float(row["accFillSz"]),
        avg_price=_float(row["avgPx"]) if row.get("avgPx") else None, fee=_float(row.get("fee")),
        algo_client_id=row.get("algoClOrdId") or "", updated=int(row["uTime"]),
    )


def _float(value) -> float:
    """OKX sends numbers as strings and leaves an unknown one empty."""
    return float(value) if value not in (None, "") else 0.0


def _size(contracts: float) -> str:
    """An unsigned contract count as OKX wants it: no exponent, no trailing zeros."""
    return _price(abs(contracts))


def _price(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"
