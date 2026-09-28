"""Derivatives planning and gated execution (FR-D): one responsibility.

A ``DerivativesExecutor`` composes an ``ExchangeBridge`` (shared config
merge, venue client, audit shape, redaction and RiskGuard) and adds only
the derivatives-specific surface: unified symbols ``base/quote:settle``
(e.g. ``BTC/USDT:USDT``), short semantics (side ``sell`` opens a short, no
held position required), margin sizing with leverage, and the three-layer
fail-closed gate:

(a) the config ``exec_derivatives`` key must be a literal True;
(b) the ``TRADINGAGENTS_EXEC_DERIVATIVES`` env flag must read true at call
    time, fail-closed (same pattern as TRADINGAGENTS_EXEC_LIVE);
(c) every execution needs ``confirm=True`` -- INCLUDING dry-runs, unlike
    the L1 spot bridge, per FR-D2.

Missing any layer refuses with an audit line and sends nothing.

PRD principle, restated for the operator: the derivatives gates ship OFF.
A sandbox or dry-run never proves the live path -- per-order confirm is
required even in dry-run so the operator consciously re-arms every send,
and the live path additionally needs both FR5 gates plus a raised
``risk_max_derivatives_exposure_pct`` (default 0 blocks all notional).

Risk: the shared RiskGuard caps leverage at ``risk_max_derivatives_leverage``
and derivatives notional at ``risk_max_derivatives_exposure_pct`` of equity;
plan sizing uses margin (``cost``) with notional = margin * leverage.
"""

from __future__ import annotations

import logging
from typing import Any

from tradingagents.agents.rating import RATINGS_5_TIER, is_review
from tradingagents.default_config import _BOOL_TRUE
from tradingagents.execution.bridge import ExchangeBridge
from tradingagents.execution.sizing import PlannedOrder, SizingRules
from tradingagents.portfolio import PortfolioContext

logger = logging.getLogger(__name__)

_BUY, _OVERWEIGHT, _HOLD, _UNDERWEIGHT, _SELL = RATINGS_5_TIER


def _env_derivatives_flag() -> bool:
    """Read TRADINGAGENTS_EXEC_DERIVATIVES at call time, fail-closed.

    The flag is deliberately absent from _ENV_OVERRIDES: its only consumer
    is this read, so it can never fold into the config half of the gate.
    None/"" or anything outside true/1/yes/on keeps derivatives closed.
    """
    import os

    raw = os.environ.get("TRADINGAGENTS_EXEC_DERIVATIVES")
    if not raw:
        return False
    return raw.strip().lower() in _BOOL_TRUE


class DerivativesExecutor:
    """Plan and execute leveraged orders behind the three-layer gate."""

    def __init__(
        self,
        config: dict | None = None,
        exchange_factory: Any = None,
        rules: SizingRules | None = None,
        exchange_id: str | None = None,
        risk_guard: Any = None,
    ) -> None:
        self._bridge = ExchangeBridge(
            config=config,
            exchange_factory=exchange_factory,
            rules=rules,
            exchange_id=exchange_id,
            risk_guard=risk_guard,
        )
        self.config = self._bridge.config
        self.rules = self._bridge.rules
        self.risk_guard = self._bridge.risk_guard

    # --- symbols ---------------------------------------------------------

    def symbol_for(self, ticker: str) -> str:
        """Unified derivatives symbol ``base/quote:settle`` (e.g. BTC/USDT:USDT).

        Built from the bridge's spot mapping (so ``exec_symbol_overrides``
        still wins); an override that already carries ``:settle`` passes
        through unchanged.
        """
        spot = self._bridge.symbol_for(ticker)
        if ":" in spot:
            return spot
        if "/" not in spot:
            raise ValueError(
                f"exec_symbol_overrides[{ticker!r}] = {spot!r} is not a recognizable "
                "ccxt symbol (expected BASE/QUOTE, optionally BASE/QUOTE:SETTLE)"
            )
        quote = spot.split("/", 1)[1]
        return f"{spot}:{quote}"

    # --- planning (FR-D1) --------------------------------------------------

    def plan_order(
        self,
        ticker: str,
        signal: str,
        portfolio: PortfolioContext | None = None,
        *,
        price: float | None = None,
        leverage: float = 1.0,
    ) -> PlannedOrder:
        """Size a derivatives plan; refuses (audited) unless gates (a)+(b) are open.

        ``side`` ``sell`` opens a SHORT -- no held position is needed, so
        Sell/Underweight size like Buy/Overweight instead of reading the
        book. ``cost`` is the margin; quantity covers notional*leverage.
        Without ``price`` the plan is a network read.
        """
        ccxt_symbol = self.symbol_for(ticker)
        shell = PlannedOrder(
            ticker=ticker, ccxt_symbol=ccxt_symbol, signal=signal,
            market="derivatives", leverage=leverage,
        )
        if self.config.get("exec_derivatives") is not True:
            raise self._refuse(
                shell,
                "exec_derivatives is not armed in config (literal True required); "
                "nothing was planned",
                phase="plan",
            )
        if not _env_derivatives_flag():
            raise self._refuse(
                shell,
                "TRADINGAGENTS_EXEC_DERIVATIVES is not set to true at call time; "
                "nothing was planned",
                phase="plan",
            )
        if price is None:
            price = self._bridge.fetch_price(ticker)
        mode = self._bridge.effective_mode()
        order = self._size(
            signal=signal, ticker=ticker, ccxt_symbol=ccxt_symbol,
            portfolio=portfolio, price=price, leverage=leverage,
        )
        order.mode = mode
        decision = self.risk_guard.check(order, portfolio, self.config["exec_log_path"])
        if decision.halted:
            self._bridge.audit_plan(
                order, action="rejected_by_risk", reason=decision.reason, phase="plan"
            )
            raise PermissionError(f"risk guard halted trading: {decision.reason}")
        if not decision.allowed:
            rejected = order.model_copy(
                update={"side": None, "quantity": None, "cost": None, "reason": decision.reason}
            )
            self._bridge.audit_plan(
                rejected, action="rejected_by_risk", reason=decision.reason, phase="plan"
            )
            return rejected
        self._bridge.audit_plan(order, action=order.side or "no_order", reason=order.reason)
        return order

    # --- execution (FR-D2) --------------------------------------------------

    def execute_order(
        self,
        order: PlannedOrder,
        confirm: bool = False,
        portfolio: PortfolioContext | None = None,
    ) -> str | None:
        """Execute a derivatives plan behind gates (a)+(b)+(c).

        Layer (c): ``confirm=True`` is required for EVERY send, including
        dry-runs. ``portfolio`` is MANDATORY and fail-closed: without it the
        risk guard's percentage caps (leverage, derivatives notional) would
        skip fail-open, so a None portfolio refuses before the guard runs.
        The risk guard re-checks immediately before anything is sent; live
        sends need the FR5 double gate as well.
        """
        if order.market != "derivatives":
            raise ValueError("DerivativesExecutor executes derivatives orders only")
        if order.needs_review or order.signal not in RATINGS_5_TIER:
            raise ValueError(
                f"order signal {order.signal!r} is not a tradeable rating; nothing was sent"
            )
        if order.side is None or order.quantity is None:
            raise ValueError(
                f"not an executable order: side={order.side!r}, quantity={order.quantity!r}"
            )
        if self.config.get("exec_derivatives") is not True:
            raise self._refuse(
                order,
                "exec_derivatives is not armed in config (literal True required); "
                "nothing was sent",
                phase="execute",
            )
        if not _env_derivatives_flag():
            raise self._refuse(
                order,
                "TRADINGAGENTS_EXEC_DERIVATIVES is not set to true at call time; "
                "nothing was sent",
                phase="execute",
            )
        if portfolio is None or (portfolio.cash is None and not portfolio.positions):
            # Fail-closed on purpose: the guard's percentage caps need equity.
            # A missing portfolio OR an unmarkable one (no cash, no positions)
            # would both make _equity return None and silently disarm
            # risk_max_derivatives_exposure_pct (default 0 blocks all notional).
            raise self._refuse(
                order,
                "derivatives execution requires a portfolio with computable equity: "
                "the risk guard's percentage caps fail open without it; "
                "nothing was sent",
                phase="execute",
            )
        mode = self._bridge.effective_mode()
        # fail_closed=True: same rule as the spot execute re-check -- an
        # unreadable audit log hides the halt/streak state a send decision
        # needs, so it refuses instead of passing.
        decision = self.risk_guard.check(
            order, portfolio, self.config["exec_log_path"], fail_closed=True
        )
        if decision.halted or not decision.allowed:
            self._bridge.audit_plan(
                order, action="rejected_by_risk", reason=decision.reason,
                confirmed=confirm, phase="execute",
            )
            raise PermissionError(f"risk guard refused execution: {decision.reason}")
        if confirm is not True:
            self._bridge.audit_plan(
                order, action="derivatives_denied",
                reason="derivatives execution requires confirm=True, even in dry-run",
                confirmed=confirm, phase="execute",
            )
            raise PermissionError(
                "derivatives execution requires confirm=True, even in dry-run; "
                "nothing was sent"
            )
        if mode == "dry":
            self._bridge.audit_plan(
                order, action=order.side or "no_order",
                reason="dry-run: order not sent to exchange",
                confirmed=confirm, phase="execute",
            )
            return None
        return self._execute_live(order, confirm)

    # --- internals -----------------------------------------------------------

    def _size(
        self,
        *,
        signal: str,
        ticker: str,
        ccxt_symbol: str,
        portfolio: PortfolioContext | None,
        price: float | None,
        leverage: float,
    ) -> PlannedOrder:
        """Derivatives mapping of the 5-tier signal; always returns a plan."""
        book = portfolio if portfolio is not None else PortfolioContext()
        floor = self.rules.min_order_cost

        def no_order(reason: str, *, needs_review: bool = False) -> PlannedOrder:
            return PlannedOrder(
                ticker=ticker, ccxt_symbol=ccxt_symbol, signal=signal,
                market="derivatives", leverage=leverage,
                needs_review=needs_review, reason=reason,
            )

        if is_review(signal):
            return no_order("REVIEW signal: no order without human review", needs_review=True)
        if signal == _HOLD:
            return no_order("Hold: no trade")
        if signal not in (_BUY, _OVERWEIGHT, _SELL, _UNDERWEIGHT):
            return no_order(
                f"unrecognized signal {signal!r}: no order without human review",
                needs_review=True,
            )
        if price is None or price <= 0:
            return no_order("price unavailable")
        if book.cash is None:
            return no_order("cash unavailable")
        long = signal in (_BUY, _OVERWEIGHT)
        side = "buy" if long else "sell"  # sell = short (FR-D1)
        fraction = self.rules.buy_fraction if signal in (_BUY, _SELL) else self.rules.overweight_fraction
        margin = book.cash * fraction
        notional = margin * leverage
        if notional < floor:
            return no_order("cost below exchange minimum")
        return PlannedOrder(
            ticker=ticker, ccxt_symbol=ccxt_symbol, signal=signal,
            side=side, quantity=notional / price, estimated_price=price,
            cost=margin, market="derivatives", leverage=leverage,
        )

    def _execute_live(self, order: PlannedOrder, confirm: bool) -> str | None:
        exchange = self._bridge.client()
        api_key = getattr(exchange, "apiKey", "") or ""
        secret = getattr(exchange, "secret", "") or ""
        if not api_key or not secret:
            self._bridge.audit_plan(
                order, action="derivatives_denied",
                reason="missing exchange API credentials",
                confirmed=confirm, phase="execute",
            )
            from tradingagents.execution.bridge import credential_env_names

            key_env, secret_env = credential_env_names(self._bridge.exchange_id)
            raise RuntimeError(
                f"live derivatives execution requires {key_env} and {secret_env}; "
                "nothing was sent"
            )
        import ccxt

        try:
            # load_markets first: ccxt's amount_to_precision requires the
            # markets loaded (same precondition as the spot path).
            exchange.load_markets()
            # Always pin the leverage -- including 1x: skipping the call at
            # 1x would leave the venue's per-symbol preset in charge of the
            # real leverage.
            exchange.set_leverage(int(order.leverage), order.ccxt_symbol)
            amount = exchange.amount_to_precision(order.ccxt_symbol, order.quantity)
            response = exchange.create_order(order.ccxt_symbol, "market", order.side, amount)
            order_id = response.get("id") if isinstance(response, dict) else None
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            self._bridge.audit_plan(
                order, action="rejected_at_execute",
                reason=f"exchange error: {exc}", confirmed=confirm, phase="execute",
            )
            raise RuntimeError(
                f"live derivatives order on {order.ccxt_symbol} failed: {exc}"
            ) from exc
        except Exception as exc:  # safety #4: nothing escapes the path unaudited
            self._bridge.audit_plan(
                order, action="rejected_at_execute",
                reason=f"unexpected error: {exc!r}", confirmed=confirm, phase="execute",
            )
            raise RuntimeError(
                f"live derivatives order on {order.ccxt_symbol} failed: {exc!r}"
            ) from exc

        try:
            self._bridge.audit_plan(
                order, action=order.side or "no_order",
                confirmed=confirm, order_id=order_id, phase="execute",
            )
        except OSError as exc:
            raise RuntimeError(
                f"order {order_id!r} WAS placed on {order.ccxt_symbol} but writing "
                f"the audit log failed: {exc}"
            ) from exc
        return order_id

    def _refuse(self, order: PlannedOrder, reason: str, *, phase: str) -> PermissionError:
        """Audit a gate refusal, then raise (fail-closed with a paper trail)."""
        self._bridge.audit_plan(order, action="derivatives_denied", reason=reason, phase=phase)
        return PermissionError(reason)
