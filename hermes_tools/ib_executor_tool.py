"""Hermes tool: IB Gateway bracket order execution.

Connects to IB Gateway via ib_insync and exposes order management as
Hermes-callable sync functions.  The event loop / async layer of ib_insync
is encapsulated entirely inside each function — callers see plain sync APIs.

Env vars consumed:
    IB_GATEWAY_HOST   Hostname or IP of IB Gateway (default: "127.0.0.1")
    IB_GATEWAY_PORT   Port number (default: 4002 — paper trading)
    IB_ACCOUNT_ID     IB account string (e.g. "DU123456")

Error handling:
    All functions return {"error": str} on failure instead of raising so
    Hermes can surface the message in Telegram without crashing the tool.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 4002
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0   # seconds; doubles each retry


def _ib_host() -> str:
    return os.environ.get("IB_GATEWAY_HOST", _DEFAULT_HOST)


def _ib_port() -> int:
    raw = os.environ.get("IB_GATEWAY_PORT", str(_DEFAULT_PORT))
    try:
        return int(raw)
    except ValueError:
        logger.warning("IB_GATEWAY_PORT=%r is not an integer, using %d", raw, _DEFAULT_PORT)
        return _DEFAULT_PORT


def _ib_account() -> str:
    return os.environ.get("IB_ACCOUNT_ID", "")


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def _connect() -> Any:
    """Return a connected IB instance with exponential-backoff retry.

    Raises:
        RuntimeError: if all retries are exhausted.
    """
    try:
        from ib_insync import IB
    except ImportError as exc:
        raise ImportError(
            "ib_insync is required for IB execution. "
            "Install it with: pip install ib_insync"
        ) from exc

    host = _ib_host()
    port = _ib_port()
    account = _ib_account()

    ib = IB()
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            # clientId changes each call to avoid collisions across processes.
            client_id = int(time.time()) % 9000 + 1000
            ib.connect(host, port, clientId=client_id, readonly=False, account=account)
            logger.info("IB connected: %s:%d (attempt %d)", host, port, attempt)
            return ib
        except Exception as exc:
            last_exc = exc
            delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "IB connection attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, _MAX_RETRIES, exc, delay,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(delay)

    raise RuntimeError(
        f"Failed to connect to IB Gateway at {host}:{port} "
        f"after {_MAX_RETRIES} attempts: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def ib_place_bracket(
    ticker: str,
    shares: int,
    entry: float,
    stop: float,
) -> dict:
    """Place a bracket order: LMT buy entry + STP stop-loss.

    The two orders are linked as a bracket so IB treats them atomically.
    Before placing, open orders are checked to prevent duplicates.

    Args:
        ticker: Stock symbol, e.g. "AAPL".
        shares: Number of shares to buy.
        entry:  Limit price for the entry order.
        stop:   Stop price for the stop-loss order.

    Returns:
        {"order_id": int, "status": str} on success.
        {"error": str} on failure.
    """
    if not ticker or not isinstance(ticker, str):
        return {"error": "ticker must be a non-empty string"}
    if not isinstance(shares, int) or shares <= 0:
        return {"error": f"shares must be a positive integer, got {shares!r}"}
    if not isinstance(entry, (int, float)) or entry <= 0:
        return {"error": f"entry must be a positive number, got {entry!r}"}
    if not isinstance(stop, (int, float)) or stop <= 0:
        return {"error": f"stop must be a positive number, got {stop!r}"}
    if stop >= entry:
        return {"error": f"stop ({stop}) must be below entry ({entry}) for a long bracket"}

    ticker = ticker.strip().upper()

    try:
        from ib_insync import IB, Stock, LimitOrder, StopOrder, util  # noqa: F401
    except ImportError as exc:
        return {"error": str(exc)}

    ib = None
    try:
        ib = _connect()
        account = _ib_account() or ib.managedAccounts()[0]

        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)

        # Duplicate guard: check for existing open orders on this ticker.
        open_orders = ib.openOrders()
        for existing in open_orders:
            if (
                hasattr(existing, "contract")
                and existing.contract.symbol == ticker
                and existing.order.action == "BUY"
            ):
                logger.warning(
                    "Duplicate guard: open BUY order already exists for %s — aborting", ticker
                )
                return {
                    "error": (
                        f"Duplicate order blocked: an open BUY order for {ticker} "
                        "already exists. Cancel it before placing a new bracket."
                    )
                }

        # Build bracket orders.
        parent = LimitOrder(
            action="BUY",
            totalQuantity=shares,
            lmtPrice=round(entry, 2),
            account=account,
            transmit=False,   # hold until child is attached
        )
        stop_child = StopOrder(
            action="SELL",
            totalQuantity=shares,
            stopPrice=round(stop, 2),
            account=account,
            parentId=0,       # will be set after parent is placed
            transmit=True,
        )

        parent_trade = ib.placeOrder(contract, parent)
        parent_id = parent_trade.order.orderId
        stop_child.parentId = parent_id

        ib.placeOrder(contract, stop_child)

        # Brief settle to capture initial status.
        ib.sleep(1)

        status = parent_trade.orderStatus.status or "Submitted"
        logger.info(
            "ib_place_bracket: placed for %s — parentId=%d status=%s",
            ticker, parent_id, status,
        )
        return {"order_id": parent_id, "status": status}

    except Exception as exc:
        logger.exception("ib_place_bracket failed for %s", ticker)
        return {"error": str(exc)}
    finally:
        if ib is not None:
            ib.disconnect()


def ib_cancel_order(order_id: int) -> dict:
    """Cancel an open IB order by order ID.

    Args:
        order_id: The orderId returned by ib_place_bracket.

    Returns:
        {"order_id": int, "status": "Cancelled"} on success.
        {"error": str} on failure.
    """
    if not isinstance(order_id, int) or order_id <= 0:
        return {"error": f"order_id must be a positive integer, got {order_id!r}"}

    try:
        from ib_insync import IB, Order
    except ImportError as exc:
        return {"error": str(exc)}

    ib = None
    try:
        ib = _connect()

        open_trades = {t.order.orderId: t for t in ib.openTrades()}
        if order_id not in open_trades:
            return {"error": f"No open order found with order_id={order_id}"}

        trade = open_trades[order_id]
        ib.cancelOrder(trade.order)
        ib.sleep(1)

        status = trade.orderStatus.status or "Cancelled"
        logger.info("ib_cancel_order: orderId=%d status=%s", order_id, status)
        return {"order_id": order_id, "status": status}

    except Exception as exc:
        logger.exception("ib_cancel_order failed for order_id=%d", order_id)
        return {"error": str(exc)}
    finally:
        if ib is not None:
            ib.disconnect()


def ib_get_positions() -> list[dict]:
    """Return all open positions as a list of dicts.

    Each dict has keys: ticker, exchange, currency, position, avg_cost, market_value.
    Returns [{"error": str}] on failure (list so the return type is consistent).
    """
    try:
        from ib_insync import IB
    except ImportError as exc:
        return [{"error": str(exc)}]

    ib = None
    try:
        ib = _connect()
        account = _ib_account() or ib.managedAccounts()[0]

        positions = ib.positions(account=account)
        result = []
        for pos in positions:
            result.append({
                "ticker":       pos.contract.symbol,
                "exchange":     pos.contract.exchange,
                "currency":     pos.contract.currency,
                "position":     pos.position,
                "avg_cost":     pos.avgCost,
                "market_value": round(pos.position * pos.avgCost, 2),
            })

        logger.info("ib_get_positions: %d positions found", len(result))
        return result

    except Exception as exc:
        logger.exception("ib_get_positions failed")
        return [{"error": str(exc)}]
    finally:
        if ib is not None:
            ib.disconnect()


def ib_get_account_value() -> dict:
    """Return current account equity.

    Returns:
        {"equity": float, "currency": str, "account": str} on success.
        {"error": str} on failure.
    """
    try:
        from ib_insync import IB
    except ImportError as exc:
        return {"error": str(exc)}

    ib = None
    try:
        ib = _connect()
        account = _ib_account() or ib.managedAccounts()[0]

        account_values = ib.accountValues(account=account)

        # NetLiquidation is the standard "total equity" field in TWS.
        net_liq = next(
            (v for v in account_values if v.tag == "NetLiquidation" and v.currency != "BASE"),
            None,
        )
        if net_liq is None:
            # Fallback: BASE currency
            net_liq = next(
                (v for v in account_values if v.tag == "NetLiquidation"),
                None,
            )

        if net_liq is None:
            return {"error": "NetLiquidation not found in account values"}

        equity = float(net_liq.value)
        currency = net_liq.currency
        logger.info("ib_get_account_value: equity=%.2f %s", equity, currency)
        return {"equity": equity, "currency": currency, "account": account}

    except Exception as exc:
        logger.exception("ib_get_account_value failed")
        return {"error": str(exc)}
    finally:
        if ib is not None:
            ib.disconnect()
