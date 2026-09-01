"""Single-ticker Execution Agent: turn a research write-up into a paper ticket."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import asdict, dataclass
from typing import Any

import requests

from .journal import append_execution_journal
from .parser import ParsedTradeDecision, parse_trade_decision
from .position_plan import (
    clear_position_plan,
    load_position_plans,
    plan_blocks_sell,
    plan_storage_key,
    save_position_plans,
    stop_loss_breached,
    upsert_position_plan,
)

logger = logging.getLogger(__name__)

PAPER_ALPACA_URL = "https://paper-api.alpaca.markets"
_DEFAULT_FALLBACK_CASH_PCT = 10.0


def is_live_alpaca_url(url: str | None) -> bool:
    """True when the host is Alpaca live trading rather than paper."""
    lowered = (url or "").lower()
    return "api.alpaca.markets" in lowered and "paper-api.alpaca.markets" not in lowered


@dataclass
class ExecutionResult:
    """Observable result of an execution-agent run."""

    enabled: bool
    ticker: str
    decision: ParsedTradeDecision
    cash_allocation_pct: float = 0.0
    account_snapshot: dict[str, Any] | None = None
    positions_snapshot: list[dict[str, Any]] | None = None
    order_submitted: bool = False
    order_action: str = "hold"
    order_type: str = "none"
    quantity: float = 0
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    stop_loss_attached: bool = False
    estimated_notional: float | None = None
    alpaca_order_id: str | None = None
    alpaca_status: str | None = None
    alpaca_submitted_at: str | None = None
    filled_qty: float | None = None
    filled_avg_price: float | None = None
    time_horizon: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = asdict(self.decision)
        return data


class AlpacaPaperClient:
    """Tiny REST client for Alpaca's Trading API."""

    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        base_url: str = PAPER_ALPACA_URL,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = (base_url or PAPER_ALPACA_URL).rstrip("/")
        self.timeout = timeout
        if is_live_alpaca_url(self.base_url):
            logger.warning(
                "ALPACA_BASE_URL points at live trading (%s). "
                "Paper trading (paper-api.alpaca.markets) is the default.",
                self.base_url,
            )

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_positions(self) -> list[dict[str, Any]]:
        positions = self._request("GET", "/v2/positions")
        return positions if isinstance(positions, list) else []

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v2/orders", json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
            },
            timeout=self.timeout,
            **kwargs,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text.strip()
            raise requests.HTTPError(
                f"Alpaca {method} {path} failed with {response.status_code}: {body}",
                response=response,
            ) from exc
        return response.json() if response.content else {}


class ExecutionAgent:
    """Turn one ticker's PM + Trader write-up into a cash-% recommendation and optional paper order."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        client: AlpacaPaperClient | Any = None,
    ) -> None:
        self.config = config or {}
        self._client = client

    def run(
        self,
        *,
        ticker: str,
        portfolio_manager_text: str,
        trader_text: str | None = None,
        trade_date: str | None = None,
    ) -> ExecutionResult:
        decision = parse_trade_decision(portfolio_manager_text, trader_text)
        cash_pct = self._cash_pct(decision)
        enabled = self._config_bool("execution_enabled", default=True)

        if not enabled:
            _, reason = resolve_execution_action(
                decision,
                held_qty=0.0,
                current_price=None,
                position_plan=None,
                trade_date=trade_date or "",
            )
            recommended = decision.action
            return self._finish(
                ExecutionResult(
                    enabled=False,
                    ticker=ticker,
                    decision=decision,
                    cash_allocation_pct=cash_pct,
                    order_action=recommended,
                    order_type="none",
                    quantity=0,
                    limit_price=decision.entry_price,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.price_target,
                    time_horizon=decision.time_horizon,
                    message=(
                        "Execution disabled (recommendations only). "
                        "Set TRADINGAGENTS_EXECUTION_ENABLED=true to submit Alpaca paper trades. "
                        f"Recommendation: {recommended} "
                        f"{cash_pct:g}% of available cash. {reason}"
                    ).strip(),
                ),
                ticker=ticker,
                trade_date=trade_date,
                portfolio_manager_text=portfolio_manager_text,
            )

        try:
            client = self._get_client()
        except ValueError as exc:
            return self._finish(
                ExecutionResult(
                    enabled=True,
                    ticker=ticker,
                    decision=decision,
                    cash_allocation_pct=cash_pct,
                    order_action=decision.action,
                    limit_price=decision.entry_price,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.price_target,
                    time_horizon=decision.time_horizon,
                    message=str(exc),
                ),
                ticker=ticker,
                trade_date=trade_date,
                portfolio_manager_text=portfolio_manager_text,
            )

        try:
            account = _compact_account(client.get_account())
            positions = [_compact_position(p) for p in client.get_positions()]
        except Exception as exc:
            logger.warning("Could not load Alpaca account state: %s", exc)
            return self._finish(
                ExecutionResult(
                    enabled=True,
                    ticker=ticker,
                    decision=decision,
                    cash_allocation_pct=cash_pct,
                    order_action=decision.action,
                    limit_price=decision.entry_price,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.price_target,
                    time_horizon=decision.time_horizon,
                    message=f"Could not load Alpaca account state: {exc}",
                ),
                ticker=ticker,
                trade_date=trade_date,
                portfolio_manager_text=portfolio_manager_text,
            )

        account_scope = account.get("account_scope")
        plans = load_position_plans(self._position_plan_path())
        stored_plan = plans.get(
            plan_storage_key(account_scope=account_scope, ticker=ticker)
        )
        held_qty = _position_qty(ticker, positions)
        current_price = _position_price(ticker, positions) or decision.entry_price

        action, reason = resolve_execution_action(
            decision,
            held_qty=held_qty,
            current_price=current_price,
            position_plan=stored_plan,
            trade_date=trade_date or "",
            allow_short=self._config_bool("execution_allow_short", default=False),
        )

        cash = _to_float(account.get("cash")) or 0.0
        limit_price = decision.entry_price or current_price
        stop_loss = decision.stop_loss or (stored_plan or {}).get("stop_loss")
        take_profit = decision.price_target
        quantity = 0.0
        estimated_notional = None
        order_type = "none"

        if action == "buy":
            quantity = shares_from_available_cash(
                cash=cash,
                cash_pct=cash_pct,
                price=limit_price or 0.0,
            )
            estimated_notional = round(quantity * (limit_price or 0.0), 2) if quantity else 0.0
            order_type = "limit" if limit_price else "market"
            if quantity <= 0:
                action = "hold"
                reason = (
                    reason
                    + " No shares could be sized from available cash at the planned price."
                ).strip()
                order_type = "none"
        elif action == "sell":
            quantity = held_qty
            estimated_notional = round(quantity * (current_price or limit_price or 0.0), 2)
            order_type = "limit" if limit_price else "market"
            if quantity <= 0:
                action = "hold"
                reason = "No long position to sell; shorting is disabled."
                order_type = "none"
                quantity = 0.0

        result = ExecutionResult(
            enabled=True,
            ticker=ticker,
            decision=decision,
            cash_allocation_pct=cash_pct,
            account_snapshot=account,
            positions_snapshot=positions,
            order_action=action,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price if action == "buy" else (limit_price if action == "sell" else decision.entry_price),
            stop_loss=stop_loss,
            take_profit=take_profit,
            estimated_notional=estimated_notional,
            time_horizon=decision.time_horizon or (stored_plan or {}).get("time_horizon"),
            message=reason,
        )

        if action in {"buy", "sell"} and quantity > 0:
            payload = self._build_order_payload(
                ticker=ticker,
                action=action,
                quantity=quantity,
                limit_price=limit_price,
                stop_loss=stop_loss if action == "buy" else None,
            )
            if payload.get("order_class") == "oto":
                result.stop_loss_attached = True
            try:
                response = client.submit_order(payload)
            except Exception as exc:
                logger.warning("Alpaca order submit failed: %s", exc)
                result.message = f"{reason} Alpaca submit failed: {exc}".strip()
                return self._finish(
                    result,
                    ticker=ticker,
                    trade_date=trade_date,
                    portfolio_manager_text=portfolio_manager_text,
                )
            result.order_submitted = True
            result.alpaca_order_id = response.get("id")
            result.alpaca_status = response.get("status")
            result.alpaca_submitted_at = response.get("submitted_at")
            result.filled_qty = _to_float(response.get("filled_qty"))
            result.filled_avg_price = _to_float(response.get("filled_avg_price"))
            result.message = (
                f"{reason} Submitted Alpaca paper {action} for {quantity:g} {ticker.upper()}."
            ).strip()

            if action == "buy":
                plans = upsert_position_plan(
                    plans,
                    account_scope=account_scope,
                    ticker=ticker,
                    trade_date=trade_date or "",
                    portfolio_manager_text=portfolio_manager_text,
                    parsed_decision=asdict(decision),
                    limit_price=limit_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
                save_position_plans(self._position_plan_path(), plans)
            elif action == "sell":
                plans = clear_position_plan(
                    plans, account_scope=account_scope, ticker=ticker
                )
                save_position_plans(self._position_plan_path(), plans)
        else:
            result.message = reason or "Execution Agent chose to hold."

        return self._finish(
            result,
            ticker=ticker,
            trade_date=trade_date,
            portfolio_manager_text=portfolio_manager_text,
        )

    def _build_order_payload(
        self,
        *,
        ticker: str,
        action: str,
        quantity: float,
        limit_price: float | None,
        stop_loss: float | None,
    ) -> dict[str, Any]:
        qty = quantity
        attach_stop = action == "buy" and stop_loss is not None and stop_loss > 0
        if attach_stop:
            qty = math.floor(qty)
        tif = str(self.config.get("alpaca_time_in_force") or "gtc")
        if qty != int(qty):
            tif = "day"
        payload: dict[str, Any] = {
            "symbol": ticker.upper(),
            "qty": _format_number(qty),
            "side": action,
            "time_in_force": tif,
        }
        if limit_price:
            payload["type"] = "limit"
            payload["limit_price"] = _format_number(round(float(limit_price), 2))
        else:
            payload["type"] = "market"
        if attach_stop and qty >= 1:
            payload["order_class"] = "oto"
            payload["stop_loss"] = {"stop_price": _format_number(round(float(stop_loss), 2))}
        if self._config_bool("alpaca_extended_hours", default=False) and payload["type"] == "limit":
            payload["extended_hours"] = True
        return payload

    def _cash_pct(self, decision: ParsedTradeDecision) -> float:
        if decision.cash_allocation_pct is not None:
            return float(decision.cash_allocation_pct)
        return self._config_float("execution_fallback_cash_pct", default=_DEFAULT_FALLBACK_CASH_PCT)

    def _get_client(self) -> AlpacaPaperClient | Any:
        if self._client is not None:
            return self._client
        api_key = self.config.get("alpaca_api_key") or os.getenv("ALPACA_API_KEY") or ""
        secret_key = self.config.get("alpaca_secret_key") or os.getenv("ALPACA_SECRET_KEY") or ""
        if not api_key or not secret_key:
            raise ValueError(
                "Alpaca API key and secret are required when execution is enabled. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys only)."
            )
        base_url = (
            self.config.get("alpaca_base_url")
            or os.getenv("ALPACA_BASE_URL")
            or PAPER_ALPACA_URL
        )
        timeout = self._config_float("alpaca_timeout_seconds", default=20.0)
        return AlpacaPaperClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=str(base_url),
            timeout=timeout,
        )

    def _position_plan_path(self) -> str:
        return str(
            self.config.get("execution_position_plan_path")
            or os.path.join(
                os.path.expanduser("~"),
                ".tradingagents",
                "execution",
                "position_plans.json",
            )
        )

    def _journal_path(self) -> str:
        return str(
            self.config.get("execution_journal_path")
            or os.path.join(
                os.path.expanduser("~"),
                ".tradingagents",
                "execution",
                "execution_journal.md",
            )
        )

    def _finish(
        self,
        result: ExecutionResult,
        *,
        ticker: str,
        trade_date: str | None,
        portfolio_manager_text: str,
    ) -> ExecutionResult:
        try:
            account_scope = None
            if result.account_snapshot:
                account_scope = result.account_snapshot.get("account_scope")
            append_execution_journal(
                path=self._journal_path(),
                ticker=ticker,
                account_scope=account_scope,
                trade_date=trade_date,
                portfolio_manager_text=portfolio_manager_text,
                execution_report=result.to_dict(),
            )
        except Exception as exc:
            logger.warning("Could not append execution journal: %s", exc)
        return result

    def _config_bool(self, key: str, *, default: bool) -> bool:
        value = self.config.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    def _config_float(self, key: str, *, default: float) -> float:
        value = self.config.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


def resolve_execution_action(
    decision: ParsedTradeDecision,
    *,
    held_qty: float,
    current_price: float | None,
    position_plan: dict[str, Any] | None,
    trade_date: str,
    allow_short: bool = False,
) -> tuple[str, str]:
    """Map PM intent + stored horizon/stop into buy, sell, or hold."""
    parsed = asdict(decision)
    stop = decision.stop_loss
    if stop is None and position_plan:
        stop = _to_float(position_plan.get("stop_loss"))

    if held_qty > 0:
        if stop_loss_breached(current_price=current_price, stop_loss=stop):
            return "sell", "Stop-loss / significant loss versus the stored plan."
        blocked, reason = plan_blocks_sell(
            plan=position_plan,
            trade_date=trade_date,
            parsed_decision=parsed,
            current_price=current_price,
        )
        if blocked:
            return "hold", reason
        if decision.action == "sell":
            return "sell", reason or "Portfolio Manager rated Sell; exiting the long position."
        if decision.action == "buy":
            return "hold", "Already holding this name; not spending more cash on an add."
        return "hold", reason or "Holding the existing long position."

    if decision.action == "buy":
        return "buy", "Portfolio Manager rated Buy/Overweight; size from available cash only."
    if decision.action == "sell":
        if allow_short:
            return "sell", "No long position; shorting is enabled."
        return "hold", "No long position to sell; shorting is disabled."
    return "hold", "Portfolio Manager rated Hold; no order."


def shares_from_available_cash(*, cash: float, cash_pct: float, price: float) -> float:
    """Integer-or-fractional shares funded only by Alpaca cash, never equity."""
    if cash <= 0 or cash_pct <= 0 or price <= 0:
        return 0.0
    pct = min(100.0, max(0.0, cash_pct))
    notional = min(cash, cash * (pct / 100.0))
    qty = notional / price
    qty = math.floor(qty * 10_000) / 10_000
    if qty * price - cash > 1e-6:
        qty = math.floor((cash / price) * 10_000) / 10_000
    return max(0.0, qty)


def format_execution_report(execution_report: dict[str, Any]) -> str:
    """Render an execution_report dict as markdown for reports and the CLI."""
    decision = execution_report.get("decision") or {}
    lines = [
        f"**Enabled**: {execution_report.get('enabled')}",
        f"**Ticker**: {execution_report.get('ticker')}",
        f"**Recommended action**: {execution_report.get('order_action')}",
        f"**Percent of available cash**: {execution_report.get('cash_allocation_pct')}",
        f"**Time horizon**: {execution_report.get('time_horizon') or decision.get('time_horizon') or ''}",
        f"**PM rating**: {decision.get('rating')}",
        f"**Order submitted**: {execution_report.get('order_submitted')}",
        f"**Order type**: {execution_report.get('order_type')}",
        f"**Quantity**: {execution_report.get('quantity')}",
    ]
    if execution_report.get("limit_price") is not None:
        lines.append(f"**Limit price**: {execution_report.get('limit_price')}")
    if execution_report.get("stop_loss") is not None:
        lines.append(f"**Stop loss**: {execution_report.get('stop_loss')}")
    if execution_report.get("take_profit") is not None:
        lines.append(f"**Take profit**: {execution_report.get('take_profit')}")
    if execution_report.get("estimated_notional") is not None:
        lines.append(f"**Estimated notional**: {execution_report.get('estimated_notional')}")
    if execution_report.get("alpaca_order_id"):
        lines.append(f"**Alpaca order id**: {execution_report.get('alpaca_order_id')}")
    if execution_report.get("alpaca_status"):
        lines.append(f"**Alpaca status**: {execution_report.get('alpaca_status')}")
    account = execution_report.get("account_snapshot") or {}
    if account.get("cash") is not None:
        lines.append(f"**Available cash**: {account.get('cash')}")
    if execution_report.get("message"):
        lines.extend(["", execution_report["message"]])
    return "\n".join(lines)


def _compact_account(account: dict[str, Any]) -> dict[str, Any]:
    account_id = str(account.get("id") or "")
    number = str(account.get("account_number") or "")
    return {
        "id": account_id,
        "account_number": number,
        "account_scope": _account_scope(account),
        "cash": _to_float(account.get("cash")),
        "buying_power": _to_float(account.get("buying_power")),
        "equity": _to_float(account.get("equity") or account.get("portfolio_value")),
        "long_market_value": _to_float(account.get("long_market_value")),
        "status": account.get("status"),
    }


def _compact_position(position: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(position.get("symbol") or "").upper(),
        "qty": _to_float(position.get("qty")),
        "market_value": _to_float(position.get("market_value")),
        "avg_entry_price": _to_float(position.get("avg_entry_price")),
        "current_price": _to_float(position.get("current_price")),
    }


def _account_scope(account: dict[str, Any]) -> str:
    account_id = str(account.get("id") or "")
    number = str(account.get("account_number") or "")
    return f"alpaca:{account_id[-8:] if account_id else 'unknown'}:{number[-4:] if number else 'na'}"


def _position_qty(ticker: str, positions: list[dict[str, Any]]) -> float:
    for position in positions:
        if str(position.get("symbol") or "").upper() == ticker.upper():
            return _to_float(position.get("qty")) or 0.0
    return 0.0


def _position_price(ticker: str, positions: list[dict[str, Any]]) -> float | None:
    for position in positions:
        if str(position.get("symbol") or "").upper() == ticker.upper():
            return _to_float(position.get("current_price"))
    return None


def _format_number(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
