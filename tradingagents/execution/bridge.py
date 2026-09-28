"""ExchangeBridge: ccxt lifecycle, planning, risk-gated execution (multi-exchange).

Multi-exchange (L2): ``exec_exchange_id`` (or the ``exchange_id`` argument)
selects the ccxt class; credentials come from ``{ID}_API_KEY`` / ``{ID}_SECRET``
env vars only -- never from the config dict, never logged, never written to
the audit trail (safety #5). ``exec_symbol_overrides`` maps a pipeline ticker
to a full ccxt symbol and wins over the default ``base/quote`` mapping.

Gate model (FR5): the effective mode is computed AT EXECUTE TIME and is
authoritative -- live only when BOTH independent gates are open: the config
``exec_live`` key must be a literal True (armed in code; deliberately NOT
env-overridable) AND the ``TRADINGAGENTS_EXEC_LIVE`` env flag must read true
at that moment, fail-closed (anything but true/1/yes/on means dry). The env
flag's only consumer is that read, so one variable can never arm both halves.
``PlannedOrder.mode`` is informational and never grants execution rights.
Dry-run never touches the exchange (simulated fill), so it needs no confirm;
live execution requires an explicit ``confirm=True`` and never runs without
credentials. Safety #4: every exception on the execution path is audited
before it raises, and a live order that WAS placed but whose success-audit
could not be written raises a distinctive "order was placed" error so a
retry can never become a duplicate.

Risk guard (FR-K3/K4, L2): every plan and every execution is checked by a
``RiskGuard`` built from the config ``risk_*`` keys (injectable via
``risk_guard`` for tests). A halted day refuses everything with a
``PermissionError``; a plan that breaches a percentage limit comes back as a
no-order plan (the "always returns a plan" contract holds) audited as
``rejected_by_risk``; ``execute_order`` re-checks immediately before
anything is sent, so a halt raised by any process on the shared audit log
blocks both the dry and live paths.

Audit lines carry a ``phase`` field ("plan" or "execute"): the risk guard
replays only executed lines, so a planned order is never double-counted as
a filled one. Lines without ``phase`` (legacy, control events) are treated
as executed history.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from tradingagents.agents.rating import RATINGS_5_TIER
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.symbols import crypto_base
from tradingagents.default_config import _BOOL_TRUE
from tradingagents.execution.audit import append_event
from tradingagents.execution.risk import RiskGuard, RiskLimits
from tradingagents.execution.sizing import PlannedOrder, SizingRules, compute
from tradingagents.portfolio import PortfolioContext, Position

logger = logging.getLogger(__name__)


def credential_env_names(exchange_id: str) -> tuple[str, str]:
    """Env var names for an exchange's credentials: ``{ID}_API_KEY``/``{ID}_SECRET``.

    "binance" maps to the L1 names BINANCE_API_KEY / BINANCE_SECRET unchanged;
    every other id follows the same pattern (okx -> OKX_API_KEY, ...).
    """
    upper = exchange_id.strip().upper()
    return f"{upper}_API_KEY", f"{upper}_SECRET"


def _default_exchange_factory(exchange_id: str) -> Any:
    """Build the configured ccxt client lazily; credentials from env only.

    ``exchange_id`` must name a ``ccxt.Exchange`` subclass (e.g. "binance",
    "okx"); anything else raises before any network call. ccxt is imported
    here, not at module level, so importing tradingagents.execution stays
    cheap and tests can inject fakes.
    """
    import ccxt

    klass = getattr(ccxt, exchange_id, None)
    if not (isinstance(klass, type) and issubclass(klass, ccxt.Exchange)):
        raise ValueError(
            f"exec_exchange_id {exchange_id!r} does not name a ccxt exchange class"
        )
    key_env, secret_env = credential_env_names(exchange_id)
    return klass({
        "apiKey": os.environ.get(key_env, ""),
        "secret": os.environ.get(secret_env, ""),
        "enableRateLimit": True,
    })


class PreTradeRejection(RuntimeError):
    """A live order was refused before reaching the exchange; already audited.

    Subclasses RuntimeError so callers catching RuntimeError keep working,
    while the pass-through handler in _execute_live can tell these audited
    rejections apart from any other RuntimeError an injected exchange client
    might raise -- the latter must fall through to the generic audited
    handler instead of riding this one (safety #4).
    """


class ExchangeBridge:
    """Signal -> plan -> risk check -> approval-gated execution on one venue.

    ``config`` is shallow-merged OVER a fresh deepcopy of the process config
    (``get_config()`` already returns a copy), so a partial dict like
    ``{"exec_live": True}`` never raises KeyError and every unspecified key
    keeps its process value. The merge happens once at construction: a later
    ``set_config()`` is NOT seen by an existing bridge -- build a new one.
    ``rules`` overrides the default FR2 sizing mapping when given.
    ``exchange_id`` overrides ``exec_exchange_id``; the default factory
    resolves it to the ccxt class of the same (lowercase) name.
    ``risk_guard`` overrides the default guard built from the ``risk_*``
    config keys (tests inject a permissive or scripted guard here).
    """

    def __init__(
        self,
        config: dict | None = None,
        exchange_factory: Callable[[], Any] | None = None,
        rules: SizingRules | None = None,
        exchange_id: str | None = None,
        risk_guard: RiskGuard | None = None,
    ) -> None:
        base = get_config()
        self.config: dict = {**base, **config} if config is not None else base
        self.exchange_id = str(
            exchange_id if exchange_id is not None else self.config.get("exec_exchange_id")
        ).strip().lower()
        if not self.exchange_id:
            raise ValueError("exec_exchange_id is empty; cannot select a ccxt exchange class")
        if exchange_factory is not None:
            self._exchange_factory = exchange_factory
        else:
            self._exchange_factory = lambda: _default_exchange_factory(self.exchange_id)
        self.rules = rules if rules is not None else SizingRules()
        self._exchange: Any | None = None
        self.risk_guard = risk_guard if risk_guard is not None else self._build_risk_guard()

    def _build_risk_guard(self) -> RiskGuard:
        limits = RiskLimits(
            max_daily_loss_pct=float(self.config["risk_max_daily_loss_pct"]),
            max_position_pct_per_asset=float(self.config["risk_max_position_pct_per_asset"]),
            max_total_exposure_pct=float(self.config["risk_max_total_exposure_pct"]),
            max_consecutive_loss_count=int(self.config["risk_max_consecutive_loss_count"]),
            max_derivatives_leverage=float(self.config["risk_max_derivatives_leverage"]),
            max_derivatives_exposure_pct=float(self.config["risk_max_derivatives_exposure_pct"]),
        )
        return RiskGuard(limits=limits, price_of=self._price_of_ticker)

    def _price_of_ticker(self, ticker: str) -> float | None:
        """Mark a pipeline-form ticker via the exchange; None when unpriceable."""
        try:
            symbol = self.symbol_for(ticker)
        except ValueError:
            return None
        return self._fetch_price(symbol)

    def symbol_for(self, ticker: str) -> str:
        """Map a pipeline (Yahoo-form) ticker to the ccxt symbol.

        ``exec_symbol_overrides`` (config-only, keyed by pipeline ticker)
        wins first -- it is the escape hatch for pairs outside the closed
        crypto set. Otherwise the base must come from the pipeline's closed
        crypto set via ``crypto_base``, the quote from ``exec_quote_currency``.
        Anything else raises.
        """
        overrides = self.config.get("exec_symbol_overrides")
        if isinstance(overrides, dict):
            override = overrides.get(ticker)
            if override:
                return str(override)
        base = crypto_base(ticker)
        if not base:
            raise ValueError(
                f"{ticker!r} is not an executable crypto symbol; the bridge "
                "only trades the pipeline's known crypto bases (or provide "
                "an exec_symbol_overrides entry)"
            )
        quote = str(self.config.get("exec_quote_currency") or "").strip().upper()
        if not quote:
            raise ValueError("exec_quote_currency is empty; cannot build a ccxt symbol")
        return f"{base}/{quote}"

    def plan_order(
        self,
        ticker: str,
        signal: str,
        portfolio: PortfolioContext | None = None,
        *,
        price: float | None = None,
    ) -> PlannedOrder:
        """Size ``signal`` for ``ticker`` and write one audit line (FR2-4, FR7).

        Without ``price`` the plan is a network read (FR3): fetch_ticker AND
        load_markets, so the exchange's own minimum cost decides the plan.
        With ``price`` given the plan stays fully offline and uses the rules
        floor -- the live execute re-check with fresh market limits is then
        authoritative. ``mode`` on the returned plan records the gate value
        at plan time only; the audit line records confirmed=False because
        nothing has been confirmed yet.
        """
        ccxt_symbol = self.symbol_for(ticker)
        min_cost = self.rules.min_order_cost
        if price is None:
            exchange = self._exchange_or_raise()
            price = self._fetch_price(ccxt_symbol)
            market_min = self._market_min_cost(exchange.load_markets(), ccxt_symbol)
            if market_min is not None:
                min_cost = market_min
        mode = self._effective_mode()
        order = compute(
            self.rules,
            signal=signal,
            ticker=ticker,
            ccxt_symbol=ccxt_symbol,
            portfolio=portfolio,
            price=price,
            min_cost=min_cost,
        )
        order.mode = mode  # informational; the execute-time gate decides for real
        decision = self.risk_guard.check(order, portfolio, self.config["exec_log_path"])
        if decision.halted:
            self._audit(
                action="rejected_by_risk",
                order=order,
                mode=mode,
                confirmed=False,
                reason=decision.reason,
                phase="plan",
            )
            raise PermissionError(f"risk guard halted trading: {decision.reason}")
        if not decision.allowed:
            # The always-returns-a-plan contract: a limit breach comes back as
            # a no-order plan carrying the risk reason, never an exception.
            rejected = order.model_copy(
                update={"side": None, "quantity": None, "cost": None, "reason": decision.reason}
            )
            self._audit(
                action="rejected_by_risk",
                order=rejected,
                mode=mode,
                confirmed=False,
                reason=decision.reason,
                phase="plan",
            )
            return rejected
        self._audit(
            action=order.side or "no_order",
            order=order,
            mode=mode,
            confirmed=False,
            reason=order.reason,
            phase="plan",
        )
        return order

    def execute_order(
        self,
        order: PlannedOrder,
        confirm: bool = False,
        portfolio: PortfolioContext | None = None,
    ) -> str | None:
        """Execute ``order``; live requires both gates open AND confirm=True.

        Dry mode simulates the fill without calling the exchange at all and
        returns None. Live mode returns the exchange order id (None if the
        response carries none). Every refusal or failure on the live path is
        audited before it raises; nothing is ever sent on a refusal (#4).

        The risk guard re-checks immediately before anything is sent (FR-K3):
        a halt on the shared audit log -- including one appended by another
        process after the plan was made -- or a limit breach raises
        PermissionError on both the dry and live paths. Pass ``portfolio``
        to re-check the percentage limits too; without it only the
        denominator-free checks (halt, consecutive losses) run, and the dry
        path stays fully offline.

        Three refusals raise without an audit line because nothing could ever
        be sent: an order whose signal is not a tradeable 5-tier rating or
        that is flagged needs_review (safety #3 must hold on the execution
        surface too, not only at plan time), one without side/quantity, and
        a derivatives plan -- the spot surface must never route one, because
        the FR-D gates and the derivatives risk caps live only on
        ``DerivativesExecutor`` (a spot venue selected via
        ``exec_exchange_id`` is not a derivatives venue either).
        """
        if getattr(order, "market", "spot") == "derivatives":
            raise ValueError(
                f"derivatives plan for {order.ticker!r} cannot execute through "
                "the spot ExchangeBridge; use DerivativesExecutor (FR-D) -- "
                "nothing was sent"
            )
        if order.needs_review or order.signal not in RATINGS_5_TIER:
            raise ValueError(
                f"order signal {order.signal!r} is not a tradeable rating; nothing was sent"
            )
        if order.side is None or order.quantity is None:
            raise ValueError(
                f"not an executable order: side={order.side!r}, quantity={order.quantity!r}"
            )
        mode = self._effective_mode()
        # fail_closed=True: a send is being decided, so an unreadable audit
        # log (locked by a backup/AV scan, permissions) must refuse -- the
        # halt and loss-streak state it carries cannot be verified.
        decision = self.risk_guard.check(
            order, portfolio, self.config["exec_log_path"], fail_closed=True
        )
        if decision.halted or not decision.allowed:
            self._audit(
                action="rejected_by_risk",
                order=order,
                mode=mode,
                confirmed=confirm,
                reason=decision.reason,
                phase="execute",
            )
            raise PermissionError(f"risk guard refused execution: {decision.reason}")
        if mode == "dry":
            return self._execute_dry(order, confirm)
        return self._execute_live(order, confirm)

    def sync_portfolio(self) -> PortfolioContext:
        """Read the exchange balance into a broker-neutral PortfolioContext (FR6).

        Position tickers use the pipeline's Yahoo form (``BTC-USD``) so
        ``PortfolioContext.position_in`` matches the same strings the rest of
        the framework uses. Balances outside the known crypto bases are
        skipped with a log line; the quote currency becomes the cash.
        """
        exchange = self._exchange_or_raise()
        balance = exchange.fetch_balance()
        quote = str(self.config.get("exec_quote_currency") or "USDT").strip().upper()
        positions: list[Position] = []
        for currency, amount in (balance.get("total") or {}).items():
            if currency == quote:
                continue
            base = crypto_base(f"{currency}-USD")
            if base is None:
                logger.info("sync_portfolio: skipping unmapped balance %r", currency)
                continue
            quantity = float(amount or 0.0)
            if quantity == 0:
                continue
            positions.append(Position(ticker=f"{base}-USD", quantity=quantity))
        cash = (balance.get("free") or {}).get(quote)
        if cash is None:
            cash = (balance.get(quote) or {}).get("free")
        return PortfolioContext(cash=cash, currency=quote, positions=positions)

    def _execute_dry(self, order: PlannedOrder, confirm: bool) -> None:
        # Simulated fill: no exchange call of any kind, so no write endpoint
        # can be reached and no confirm is needed (FR4).
        self._audit(
            action=order.side or "no_order",
            order=order,
            mode="dry",
            confirmed=confirm,
            order_id=None,
            reason="dry-run: order not sent to exchange",
            phase="execute",
        )

    def _execute_live(self, order: PlannedOrder, confirm: bool) -> str | None:
        if confirm is not True:
            self._audit(
                action="execute_denied",
                order=order,
                mode="live",
                confirmed=confirm,
                reason="live execution requires confirm=True",
                phase="execute",
            )
            raise PermissionError("live execution requires confirm=True; nothing was sent")
        exchange = self._exchange_or_raise()
        api_key = getattr(exchange, "apiKey", "") or ""
        secret = getattr(exchange, "secret", "") or ""
        if not api_key or not secret:
            self._audit(
                action="execute_denied",
                order=order,
                mode="live",
                confirmed=confirm,
                reason="missing exchange API credentials",
                phase="execute",
            )
            key_env, secret_env = credential_env_names(self.exchange_id)
            raise RuntimeError(
                f"live execution requires {key_env} and {secret_env}; nothing was sent"
            )
        # Lazy ccxt import: only this live path needs the exception classes.
        import ccxt

        try:
            # load_markets first: ccxt's amount_to_precision requires the
            # markets loaded and raises ExchangeError("markets not loaded")
            # otherwise (verified on ccxt 4.5.84).
            markets = exchange.load_markets()
            amount = exchange.amount_to_precision(order.ccxt_symbol, order.quantity)
            fresh_price = self._fetch_price(order.ccxt_symbol)
            min_cost = self._market_min_cost(markets, order.ccxt_symbol)
            if min_cost is None:
                min_cost = self.rules.min_order_cost
            if fresh_price is None:
                self._audit(
                    action="rejected_at_execute",
                    order=order,
                    mode="live",
                    confirmed=confirm,
                    qty_precision=amount,
                    reason="fresh price unavailable at execute",
                    phase="execute",
                )
                raise PreTradeRejection(
                    f"cannot verify {order.ccxt_symbol} price at execute time; nothing was sent"
                )
            # Decide on the amount that will actually hit the wire: ccxt
            # TRUNCATES the planned quantity to the precision step, so a plan
            # that passed the minimum on the full float can truncate below it.
            sent_cost = float(amount) * fresh_price
            if sent_cost < min_cost:
                self._audit(
                    action="rejected_at_execute",
                    order=order,
                    mode="live",
                    confirmed=confirm,
                    qty_precision=amount,
                    reason="cost below exchange minimum at execute",
                    phase="execute",
                )
                raise PreTradeRejection(
                    f"{order.ccxt_symbol} cost {sent_cost:.8g} is below the exchange "
                    f"minimum {min_cost:.8g} after precision truncation; nothing was sent"
                )
            response = exchange.create_order(order.ccxt_symbol, "market", order.side, amount)
            order_id = response.get("id") if isinstance(response, dict) else None
        except PreTradeRejection:
            raise  # business rejections above are already audited
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            self._audit_rejected(order, confirm, f"exchange error: {exc}")
            raise RuntimeError(f"live order on {order.ccxt_symbol} failed: {exc}") from exc
        except Exception as exc:  # safety #4: nothing escapes the path unaudited
            self._audit_rejected(order, confirm, f"unexpected error: {exc!r}")
            raise RuntimeError(f"live order on {order.ccxt_symbol} failed: {exc!r}") from exc

        try:
            self._audit(
                action=order.side or "no_order",
                order=order,
                mode="live",
                confirmed=confirm,
                order_id=order_id,
                qty_precision=amount,
                phase="execute",
            )
        except OSError as exc:
            # The order already exists on the exchange: never let this look
            # like a failed order, or a caller retry would duplicate it.
            raise RuntimeError(
                f"order {order_id!r} WAS placed on {order.ccxt_symbol} but writing "
                f"the audit log failed: {exc}"
            ) from exc
        return order_id

    def _effective_mode(self) -> str:
        # ``is True`` on purpose: the config gate only opens on a real boolean
        # (what _coerce produces, or an explicit True injection). Strings like
        # "false" or "0" in the config dict must fail closed, not ride Python
        # truthiness.
        live = self.config.get("exec_live") is True and self._env_live_flag()
        return "live" if live else "dry"

    def effective_mode(self) -> str:
        """The gate-decided mode right now: ``"live"`` or ``"dry"`` (FR5).

        Public because orchestrators (the daily runner) need the same value
        the bridge will use, without reaching into private state.
        """
        return self._effective_mode()

    def audit_plan(
        self,
        order: PlannedOrder,
        *,
        action: str,
        reason: str | None = None,
        confirmed: bool = False,
        order_id: str | None = None,
        phase: str = "plan",
    ) -> None:
        """Public audit writer for orchestrators (e.g. the daily runner and
        the derivatives executor).

        Keeps their lines in the bridge's exact shape and redaction rules
        instead of hand-building dicts in another module.
        """
        self._audit(
            action=action,
            order=order,
            mode=self._effective_mode(),
            confirmed=confirmed,
            order_id=order_id,
            reason=reason,
            phase=phase,
        )

    def fetch_price(self, ticker: str) -> float | None:
        """Last price for a pipeline-form ticker via the venue; None if unavailable."""
        return self._price_of_ticker(ticker)

    def client(self) -> Any:
        """The venue client this bridge trades through (built lazily).

        Composed executors (derivatives) reuse the same client so call
        recording, rate limiting and credential redaction stay in one place.
        """
        return self._exchange_or_raise()

    @staticmethod
    def _env_live_flag() -> bool:
        """Read TRADINGAGENTS_EXEC_LIVE at call time, fail-closed.

        This read is the ONLY consumer of the flag: it is deliberately absent
        from _ENV_OVERRIDES, so the same variable can never fold into the
        config half of the gate and collapse FR5's two conditions into one.
        None/"" or anything outside true/1/yes/on keeps the bridge dry.
        """
        raw = os.environ.get("TRADINGAGENTS_EXEC_LIVE")
        if not raw:
            return False
        return raw.strip().lower() in _BOOL_TRUE

    def _exchange_or_raise(self) -> Any:
        if self._exchange is None:
            self._exchange = self._exchange_factory()
        return self._exchange

    def _fetch_price(self, symbol: str) -> float | None:
        exchange = self._exchange_or_raise()
        ticker = exchange.fetch_ticker(symbol)
        if not isinstance(ticker, dict):
            return None
        for key in ("last", "close"):
            value = ticker.get(key)
            if value:
                return float(value)
        return None

    @staticmethod
    def _market_min_cost(markets: Any, symbol: str) -> float | None:
        if not isinstance(markets, dict):
            return None
        market = markets.get(symbol) or {}
        cost = (market.get("limits") or {}).get("cost") or {}
        minimum = cost.get("min")
        return float(minimum) if minimum is not None else None

    def _audit(
        self,
        *,
        action: str,
        order: PlannedOrder,
        mode: str,
        confirmed: bool,
        order_id: str | None = None,
        qty_precision: str | None = None,
        reason: str | None = None,
        phase: str = "execute",
    ) -> None:
        """Write one audit line (FR7). The mode recorded is the effective one.

        ``phase`` separates planned from executed lines so the risk guard's
        FIFO replay never double-counts a plan that later executed.
        """
        event: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": order.ticker,
            "ccxt_symbol": order.ccxt_symbol,
            "signal": order.signal,
            "action": action,
            "qty": order.quantity,
            "price_est": order.estimated_price,
            "mode": mode,
            "confirmed": confirmed,
            "order_id": order_id,
            "phase": phase,
            # The risk guard's FIFO replay needs the market to recognize a
            # derivatives sell as a short opener; leverage documents the
            # notional multiplier alongside price_est.
            "market": getattr(order, "market", "spot"),
            "leverage": getattr(order, "leverage", 1.0),
        }
        if qty_precision is not None:
            event["qty_precision"] = qty_precision
        if reason is not None:
            # Safety #5: strip any credential that leaked into interpolated
            # exception text before it reaches the audit trail.
            event["reason"] = self._redact(reason)
        append_event(self.config["exec_log_path"], event)

    def _audit_rejected(self, order: PlannedOrder, confirm: bool, reason: str) -> None:
        """Record an exchange-side rejection of a live order (safety #4)."""
        self._audit(
            action="rejected_at_execute",
            order=order,
            mode="live",
            confirmed=confirm,
            reason=reason,
            phase="execute",
        )

    def _redact(self, text: str) -> str:
        """Replace the client's credentials with a marker, wherever they appear."""
        for secret in (getattr(self._exchange, "apiKey", ""), getattr(self._exchange, "secret", "")):
            if secret:
                text = text.replace(str(secret), "[redacted]")
        return text
