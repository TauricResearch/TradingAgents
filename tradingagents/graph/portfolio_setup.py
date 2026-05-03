"""Portfolio Manager workflow graph setup.

Fan-out/fan-in workflow:
  START → load_portfolio → compute_risk → portfolio_integrity_guard → review_holdings
        → prioritize_candidates → candidate_handoff_guard → macro_summary (parallel)
                                                           → micro_summary  (parallel)
        → make_pm_decision → rescale_buys → cash_sweep → pm_decision_postcheck
        → execute_trades → record_pm_decisions → END

Non-LLM nodes (load_portfolio, compute_risk, prioritize_candidates, execute_trades,
portfolio_integrity_guard, pm_decision_postcheck, record_pm_decisions) receive
``repo``, ``config``, or memory dependencies via closure.
LLM nodes (review_holdings, macro_summary, micro_summary, pm_decision) are created
externally and passed in.

``portfolio_integrity_guard`` validates the raw portfolio payload before any LLM sees
it. It raises ``RuntimeError`` on degenerate or conservation-breaking data (ADR 024).

``pm_decision_postcheck`` validates the final PM decision (post cash-sweep) against
portfolio constraints before trade execution. It raises on any violation (ADR 024).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from tradingagents.instruments import resolve_instrument
from tradingagents.portfolio.candidate_prioritizer import prioritize_candidates
from tradingagents.portfolio.order_guards import buy_order_guard, resolve_buy_execution_price
from tradingagents.portfolio.portfolio_states import PortfolioManagerState
from tradingagents.portfolio.risk_evaluator import compute_portfolio_risk
from tradingagents.portfolio.trade_executor import TradeExecutor

logger = logging.getLogger(__name__)

# Default Portfolio dict for safe fallback when portfolio_data is empty or malformed
_EMPTY_PORTFOLIO_DICT = {
    "portfolio_id": "",
    "name": "",
    "cash": 0.0,
    "initial_cash": 0.0,
}


def _analysis_has_deep_dive(analysis: Any) -> bool:
    """Return True when a ticker analysis has a completed deep-dive decision."""
    if not isinstance(analysis, dict):
        return False
    status = str(analysis.get("analysis_status") or "").strip().lower()
    if status:
        return status == "completed"
    return bool(str(analysis.get("final_trade_decision") or "").strip())


def _structured_action_allows_candidate(analysis: dict[str, Any]) -> bool:
    """Only completed structured BUY decisions may become new buy candidates."""
    structured = analysis.get("final_trade_decision_structured") or {}
    if not isinstance(structured, dict):
        return False
    status = str(structured.get("status") or "").strip().lower()
    action = str(structured.get("action") or "").strip().upper()
    return status == "completed" and action == "BUY"


def _completed_scan_candidates(
    scan_summary: dict, ticker_analyses: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return only scan candidates with completed ticker deep-dive analyses."""
    completed: list[dict[str, Any]] = []
    raw_candidates = (
        scan_summary.get("equity_candidates") or scan_summary.get("stocks_to_investigate") or []
    )
    for raw_candidate in raw_candidates:
        if isinstance(raw_candidate, dict):
            candidate = dict(raw_candidate)
            ticker = (candidate.get("ticker") or candidate.get("symbol") or "").upper()
        else:
            ticker = str(raw_candidate).upper()
            candidate = {"ticker": ticker}
        if not ticker:
            continue
        instrument_key = (
            candidate.get("instrument_key")
            or resolve_instrument(ticker, source_context="scan").instrument_key
        )
        analysis = (
            ticker_analyses.get(instrument_key, {}) if isinstance(ticker_analyses, dict) else {}
        )
        if not _analysis_has_deep_dive(analysis):
            continue
        if not _structured_action_allows_candidate(analysis):
            continue
        candidate["ticker"] = ticker
        candidate["instrument_key"] = instrument_key
        candidate["candidate_final_trade_decision_summary"] = str(
            analysis.get("final_trade_decision") or ""
        ).strip()
        candidate["candidate_final_trade_decision_structured"] = dict(
            analysis.get("final_trade_decision_structured") or {}
        )
        completed.append(candidate)
    return completed


class PortfolioGraphSetup:
    """Builds the Portfolio Manager workflow graph with parallel summary fan-out.

    Args:
        agents: Dict with keys ``review_holdings``, ``macro_summary``,
                ``micro_summary``, and ``pm_decision`` mapping to LLM agent
                node functions.
        repo: PortfolioRepository instance (injected into closure nodes).
        config: Portfolio config dict.
        macro_memory: MacroMemory instance forwarded to summary agents.
        micro_memory: ReflexionMemory instance forwarded to summary agents.
    """

    def __init__(
        self,
        agents: dict[str, Any],
        repo: Any = None,
        config: dict[str, Any] | None = None,
        macro_memory: Any = None,
        micro_memory: Any = None,
    ) -> None:
        self.agents = agents
        self._repo = repo
        self._config = config or {}
        # Memory instances are already baked into the agent closures at the call site
        # (portfolio_graph.py passes them to create_macro/micro_summary_agent).
        # Stored here for future direct access by non-LLM closure nodes if needed.
        self._macro_memory = macro_memory
        self._micro_memory = micro_memory

    # ------------------------------------------------------------------
    # Node factories (non-LLM)
    # ------------------------------------------------------------------

    def _make_load_portfolio_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        repo = self._repo
        config = self._config

        def load_portfolio_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_id = state["portfolio_id"]
            prices = state.get("prices") or {}
            try:
                if repo is None:
                    from tradingagents.portfolio.repository import PortfolioRepository

                    _repo = PortfolioRepository(config=config)
                else:
                    _repo = repo
                portfolio, holdings = _repo.get_portfolio_with_holdings(portfolio_id, prices)

                # Ensure total_value is set so downstream nodes can rely on it.
                # get_portfolio_with_holdings only enriches (and sets total_value) when
                # prices is non-empty.  When holdings are legitimately absent (new / empty
                # portfolio), we can safely fall back to cash-only.  When holdings exist
                # but prices are unavailable, leave total_value as None so
                # portfolio_integrity_guard raises a clear error rather than silently
                # propagating an understated value.
                if portfolio.total_value is None:
                    if not holdings:
                        # Legitimately empty portfolio — total value equals cash.
                        portfolio.total_value = portfolio.cash
                    elif prices:
                        # Some tickers may be absent from prices; compute best estimate.
                        equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                        portfolio.total_value = portfolio.cash + equity
                    # else: holdings present but no prices — leave None so guard catches it.

                # Serialize portfolio with total_value included so downstream nodes
                # (cash_sweep, pm_decision_postcheck, portfolio_integrity_guard) can read
                # it directly from the JSON without re-enriching from prices.
                portfolio_dict = portfolio.to_dict()
                portfolio_dict["total_value"] = portfolio.total_value

                # Include enriched per-holding fields when available (populated by
                # get_portfolio_with_holdings when prices are provided).  These allow
                # the integrity guard to run the conservation check and the postcheck
                # to compute projected position values without re-fetching prices.
                holdings_list = []
                for h in holdings:
                    h_dict = h.to_dict()
                    if h.current_value is not None:
                        h_dict["current_value"] = h.current_value
                    if h.current_price is not None:
                        h_dict["current_price"] = h.current_price
                    holdings_list.append(h_dict)

                data = {
                    "portfolio": portfolio_dict,
                    "holdings": holdings_list,
                }
            except Exception as exc:
                logger.error("load_portfolio_node: %s", exc)
                data = {"portfolio": {}, "holdings": [], "error": str(exc)}
            return {
                "portfolio_data": json.dumps(data),
                "sender": "load_portfolio",
            }

        return load_portfolio_node

    def _make_compute_risk_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        def compute_risk_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_data_str = state.get("portfolio_data") or "{}"
            prices = state.get("prices") or {}
            try:
                portfolio_data = json.loads(portfolio_data_str)
                from tradingagents.portfolio.models import Holding, Portfolio

                portfolio = Portfolio.from_dict(
                    portfolio_data.get("portfolio") or _EMPTY_PORTFOLIO_DICT
                )
                holdings = [Holding.from_dict(h) for h in (portfolio_data.get("holdings") or [])]

                # Enrich holdings with prices so current_value is populated
                if prices and portfolio.total_value is None:
                    equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                    total_value = portfolio.cash + equity
                    for h in holdings:
                        if h.ticker in prices:
                            h.enrich(prices[h.ticker], total_value)
                    portfolio.enrich(holdings)

                # Build simple price histories from single-point prices
                # (real usage would pass historical prices via scan_summary or state)
                price_histories: dict[str, list[float]] = {}
                scan_summary = state.get("scan_summary") or {}
                for h in holdings:
                    history = scan_summary.get("price_histories", {}).get(h.ticker)
                    if history:
                        price_histories[h.ticker] = history
                    elif h.ticker in prices:
                        # Single-point price — returns will be empty, metrics None
                        price_histories[h.ticker] = [prices[h.ticker]]

                metrics = compute_portfolio_risk(portfolio, holdings, price_histories)
            except Exception as exc:
                logger.error("compute_risk_node: %s", exc)
                metrics = {"error": str(exc)}
            return {
                "risk_metrics": json.dumps(metrics),
                "sender": "compute_risk",
            }

        return compute_risk_node

    def _make_portfolio_integrity_guard_node(
        self,
    ) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        """Deterministic guard node that validates portfolio_data before any LLM sees it.

        Checks (per ADR 024):
          1. Required fields — total_value, cash, holdings must be non-null.
          2. Type sanity — cash must be float >= 0, holdings must be list.
          3. Non-degenerate — cash=0 AND n_positions=0 means the loader likely failed.
          4. Conservation — |total_value - (cash + Σ current_value)| < $1 (when
             holdings have been enriched with current_value).
          5. Currency — all holdings share the portfolio's base currency.

        Raises RuntimeError with a specific reason on any violation.
        """

        def portfolio_integrity_guard_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_data_str = state.get("portfolio_data") or "{}"
            try:
                pd = json.loads(portfolio_data_str)
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError(
                    f"portfolio_integrity_guard: portfolio_data is not valid JSON — "
                    f"load_portfolio likely failed silently ({exc})"
                ) from exc

            portfolio = pd.get("portfolio") or {}
            holdings = pd.get("holdings") or []

            # Check 1: Required fields — total_value must be present and non-null.
            if portfolio.get("total_value") is None:
                raise RuntimeError(
                    "portfolio_integrity_guard: total_value is None — "
                    "load_portfolio likely failed silently"
                )

            # Check 2: Type sanity.
            cash = portfolio.get("cash")
            if not isinstance(cash, (int, float)) or cash < 0:
                raise RuntimeError(
                    f"portfolio_integrity_guard: cash must be a non-negative number, got {cash!r}"
                )

            if not isinstance(holdings, list):
                raise RuntimeError(
                    f"portfolio_integrity_guard: holdings must be a list, "
                    f"got {type(holdings).__name__}"
                )

            total_value = float(portfolio["total_value"])
            cash = float(cash)

            # Check 3: Non-degenerate — refuse to run the PM on an empty portfolio
            # (cash=0 AND no positions strongly indicates a silent loader failure).
            if cash == 0.0 and len(holdings) == 0:
                raise RuntimeError(
                    "portfolio_integrity_guard: empty portfolio "
                    "(cash=0, n_positions=0) — refusing to run PM"
                )

            # Check 4: Conservation — only when holdings have been enriched with
            # current_value (i.e. load_portfolio_node had prices available).
            enriched = [
                h for h in holdings if isinstance(h, dict) and h.get("current_value") is not None
            ]
            if enriched:
                holdings_equity = sum(float(h["current_value"]) for h in enriched)
                delta = abs(total_value - (cash + holdings_equity))
                if delta >= 1.0:
                    raise RuntimeError(
                        f"portfolio_integrity_guard: conservation check failed — "
                        f"total_value={total_value:.2f} != "
                        f"cash={cash:.2f} + holdings_equity={holdings_equity:.2f} "
                        f"(delta={delta:.2f})"
                    )

            # Check 5: Currency — all holdings must share the portfolio's base currency.
            # Mixed-currency state is unsupported (ADR 024).
            base_currency = portfolio.get("currency", "USD")
            for h in holdings:
                if not isinstance(h, dict):
                    continue
                holding_currency = h.get("currency")
                if holding_currency is not None and holding_currency != base_currency:
                    raise RuntimeError(
                        f"portfolio_integrity_guard: currency mismatch — "
                        f"portfolio currency={base_currency!r} but holding "
                        f"{h.get('ticker')!r} has currency={holding_currency!r}; "
                        "mixed-currency state is unsupported"
                    )

            return {"sender": "portfolio_integrity_guard"}

        return portfolio_integrity_guard_node

    def _make_pm_decision_postcheck_node(
        self,
    ) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        """Deterministic postcheck node that validates the final PM decision before trade execution.

        Reads the post-sweep ``pm_decision`` and ``portfolio_data`` from state, applies
        same-run sells then buys to project the post-trade portfolio state, then
        validates all constraints (per ADR 024):

          1. Cash adequacy — projected_cash >= projected_total_value * min_cash_pct.
          2. Position-cap — every ticker's projected value <= max_position_pct.
          3. Sector-cap — every sector's projected aggregate <= max_sector_pct.
          4. Cash-reserve floor — decision.cash_reserve_pct / 100 >= min_cash_pct.
          5. Sells reference real holdings — sell.ticker must exist in current holdings.
          6. No orphan holds — hold.ticker must exist in current holdings.
          7. Buy grounding — every non-cash-sweep buy has a completed candidate deep-dive.

        Raises RuntimeError with a specific reason on any violation.
        """
        config = self._config

        def pm_decision_postcheck_node(state: PortfolioManagerState) -> dict[str, Any]:
            pm_decision_str = state.get("pm_decision") or "{}"
            portfolio_data_str = state.get("portfolio_data") or "{}"
            prices = state.get("prices") or {}

            try:
                decision = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError(
                    f"pm_decision_postcheck: pm_decision is not valid JSON ({exc})"
                ) from exc

            try:
                pd = json.loads(portfolio_data_str)
            except (json.JSONDecodeError, TypeError) as exc:
                raise RuntimeError(
                    f"pm_decision_postcheck: portfolio_data is not valid JSON ({exc})"
                ) from exc

            portfolio = pd.get("portfolio") or {}
            raw_holdings = pd.get("holdings") or []

            # Build current holdings map: ticker → {shares, value, sector, price}.
            # Prefer live price from state, then serialised current_value/shares ratio,
            # then avg_cost as a last resort.
            current_holdings: dict[str, dict[str, Any]] = {}
            for h in raw_holdings:
                if not isinstance(h, dict):
                    continue
                ticker = h.get("ticker", "")
                if not ticker:
                    continue
                shares = float(h.get("shares", 0.0))
                live_price = float(prices.get(ticker) or 0.0)
                if live_price == 0.0:
                    stored_value = h.get("current_value")
                    if stored_value is not None and shares > 0:
                        live_price = float(stored_value) / shares
                    else:
                        live_price = float(h.get("avg_cost", 0.0))
                current_holdings[ticker] = {
                    "shares": shares,
                    "value": live_price * shares,
                    "sector": h.get("sector") or "Unknown",
                    "price": live_price,
                }

            portfolio_cash = float(portfolio.get("cash", 0.0))
            sells = decision.get("sells") or []
            buys = decision.get("buys") or []
            holds = decision.get("holds") or []
            cash_reserve_pct = decision.get("cash_reserve_pct")

            # Check 7: Buy rationale grounding.
            if buys:
                prioritized_candidates_str = state.get("prioritized_candidates") or "[]"
                try:
                    prioritized_candidates = json.loads(prioritized_candidates_str)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise RuntimeError(
                        f"pm_decision_postcheck: prioritized_candidates is not valid JSON ({exc})"
                    ) from exc
                if not isinstance(prioritized_candidates, list):
                    raise RuntimeError(
                        "pm_decision_postcheck: prioritized_candidates must be a JSON list"
                    )

                grounded_tickers: set[str] = set()
                for candidate in prioritized_candidates:
                    if not isinstance(candidate, dict):
                        continue
                    ticker = str(candidate.get("ticker") or "").strip().upper()
                    summary = str(
                        candidate.get("candidate_final_trade_decision_summary") or ""
                    ).strip()
                    if ticker and summary:
                        grounded_tickers.add(ticker)

                for buy in buys:
                    ticker = str(buy.get("ticker") or "").strip().upper()
                    sector = str(buy.get("sector") or "").strip()
                    is_cash_sweep = ticker == "SGOV" and sector.casefold() == "cash equivalent"
                    if is_cash_sweep:
                        continue
                    if ticker not in grounded_tickers:
                        raise RuntimeError(
                            f"pm_decision_postcheck: buy grounding violated for {ticker!r} — "
                            "missing completed candidate deep-dive in prioritized_candidates"
                        )

            # Check 5: Sells reference real holdings.
            for sell in sells:
                ticker = (sell.get("ticker") or "").strip()
                if ticker not in current_holdings:
                    raise RuntimeError(
                        f"pm_decision_postcheck: sell references ticker {ticker!r} "
                        "which is not in current holdings"
                    )

            # Check 6: No orphan holds.
            for hold in holds:
                ticker = (hold.get("ticker") or "").strip()
                if ticker not in current_holdings:
                    raise RuntimeError(
                        f"pm_decision_postcheck: hold references ticker {ticker!r} "
                        "which is not in current holdings"
                    )

            # Project post-trade state: apply sells first, then buys.
            projected_cash = portfolio_cash
            projected_holdings: dict[str, dict[str, Any]] = {
                ticker: dict(data) for ticker, data in current_holdings.items()
            }

            for sell in sells:
                ticker = (sell.get("ticker") or "").strip()
                sell_shares = float(sell.get("shares", 0.0))
                h = projected_holdings[ticker]
                sell_price = float(prices.get(ticker) or h["price"])
                proceeds = sell_shares * sell_price
                projected_cash += proceeds
                h["shares"] -= sell_shares
                h["value"] -= proceeds
                if h["shares"] <= 0:
                    del projected_holdings[ticker]

            for buy in buys:
                ticker = (buy.get("ticker") or "").strip()
                buy_shares = float(buy.get("shares", 0.0))
                buy_price = resolve_buy_execution_price(buy, prices)
                guard_violation = buy_order_guard(buy, buy_price)
                if guard_violation:
                    raise RuntimeError(
                        f"pm_decision_postcheck: order guard failed — {guard_violation}"
                    )
                buy_cost = buy_shares * buy_price
                projected_cash -= buy_cost
                buy_sector = buy.get("sector") or "Unknown"
                if ticker in projected_holdings:
                    projected_holdings[ticker]["shares"] += buy_shares
                    projected_holdings[ticker]["value"] += buy_cost
                else:
                    projected_holdings[ticker] = {
                        "shares": buy_shares,
                        "value": buy_cost,
                        "sector": buy_sector,
                        "price": buy_price,
                    }

            projected_equity = sum(h["value"] for h in projected_holdings.values())
            projected_total_value = projected_cash + projected_equity

            min_cash_pct = float(config.get("min_cash_pct", 0.05))
            max_position_pct = float(config.get("max_position_pct", 0.15))
            max_sector_pct = float(config.get("max_sector_pct", 0.35))

            # Check 1: Cash adequacy.
            if projected_total_value > 0:
                min_required_cash = projected_total_value * min_cash_pct
                if projected_cash < min_required_cash:
                    raise RuntimeError(
                        f"pm_decision_postcheck: cash adequacy violated — "
                        f"projected_cash={projected_cash:.2f} < "
                        f"required={min_required_cash:.2f} "
                        f"(min_cash_pct={min_cash_pct:.1%}, "
                        f"projected_total_value={projected_total_value:.2f})"
                    )

            # Check 2: Position-cap compliance.
            # SGOV (cash-sweep equivalent) is exempt — the PM legitimately parks
            # idle cash there and it can exceed the per-equity position cap.
            if projected_total_value > 0:
                for ticker, h in projected_holdings.items():
                    if ticker == "SGOV" and h.get("sector", "").casefold() == "cash equivalent":
                        continue  # cash-sweep position is exempt from per-ticker cap
                    ticker_pct = h["value"] / projected_total_value
                    if ticker_pct > max_position_pct:
                        raise RuntimeError(
                            f"pm_decision_postcheck: position cap violated for {ticker!r} — "
                            f"projected={ticker_pct:.1%} > max={max_position_pct:.1%}"
                        )

            # Check 3: Sector-cap compliance.
            # "cash equivalent" sector is exempt — SGOV sweep can legitimately
            # represent the majority of the portfolio when the PM is risk-off.
            if projected_total_value > 0:
                sector_values: dict[str, float] = {}
                for h in projected_holdings.values():
                    s = h["sector"]
                    sector_values[s] = sector_values.get(s, 0.0) + h["value"]
                for sector, s_value in sector_values.items():
                    if sector.casefold() == "cash equivalent":
                        continue  # cash-equivalent sector is exempt from sector cap
                    sector_pct = s_value / projected_total_value
                    if sector_pct > max_sector_pct:
                        raise RuntimeError(
                            f"pm_decision_postcheck: sector cap violated for {sector!r} — "
                            f"projected={sector_pct:.1%} > max={max_sector_pct:.1%}"
                        )

            # Check 4: Cash-reserve floor.
            # cash_reserve_pct in the PM decision is expressed as a percentage (e.g.
            # 80.0 means 80%); min_cash_pct in config is a fraction (e.g. 0.05 = 5%).
            if cash_reserve_pct is not None:
                stated_pct = float(cash_reserve_pct) / 100.0
                if stated_pct < min_cash_pct:
                    raise RuntimeError(
                        f"pm_decision_postcheck: cash_reserve_pct floor violated — "
                        f"stated={cash_reserve_pct:.1f}% < min={min_cash_pct:.1%}"
                    )

            return {"sender": "pm_decision_postcheck"}

        return pm_decision_postcheck_node

    def _make_prioritize_candidates_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        config = self._config

        def prioritize_candidates_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_data_str = state.get("portfolio_data") or "{}"
            scan_summary = state.get("scan_summary") or {}
            ticker_analyses = state.get("ticker_analyses") or {}
            try:
                portfolio_data = json.loads(portfolio_data_str)
                from tradingagents.portfolio.models import Holding, Portfolio

                portfolio = Portfolio.from_dict(
                    portfolio_data.get("portfolio") or _EMPTY_PORTFOLIO_DICT
                )
                holdings = [Holding.from_dict(h) for h in (portfolio_data.get("holdings") or [])]
                candidates = _completed_scan_candidates(scan_summary, ticker_analyses)
                prices = state.get("prices") or {}
                if prices:
                    equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                    total_value = portfolio.cash + equity
                    for h in holdings:
                        if h.ticker in prices:
                            h.enrich(prices[h.ticker], total_value)
                    portfolio.enrich(holdings)

                from tradingagents.portfolio.memory_loader import build_selection_memory

                try:
                    selection_memory = build_selection_memory()
                except Exception as exc:
                    logger.warning(
                        "prioritize_candidates_node: could not load selection_memory: %s", exc
                    )
                    selection_memory = None

                ranked = prioritize_candidates(
                    candidates, portfolio, holdings, config, selection_memory=selection_memory
                )
            except Exception as exc:
                logger.error("prioritize_candidates_node: %s", exc)
                ranked = []
            return {
                "prioritized_candidates": json.dumps(ranked),
                "sender": "prioritize_candidates",
            }

        return prioritize_candidates_node

    def _make_candidate_handoff_guard_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        """Validates candidate flow from prioritize_candidates to summary agents.

        Raises CandidateHandoffError when:
        - All candidates have extraction_failed status and n_out == 0
        - Candidate drop count is unaccountable (n_in - n_out != accounted drops)

        Accounted drops include: extraction_failed, analysis_failed,
        completed HOLD/SELL, empty/timeout_fallback, no deep-dive.
        """
        def candidate_handoff_guard_node(state: PortfolioManagerState) -> dict[str, Any]:
            from tradingagents.agents.utils.output_validation import CandidateHandoffError

            scan_summary = state.get("scan_summary") or {}
            ticker_analyses = state.get("ticker_analyses") or {}
            prioritized_raw = state.get("prioritized_candidates") or "[]"
            try:
                prioritized = json.loads(prioritized_raw) if isinstance(prioritized_raw, str) else prioritized_raw
            except (json.JSONDecodeError, TypeError):
                prioritized = []

            equity_candidates = (
                scan_summary.get("equity_candidates") or scan_summary.get("stocks_to_investigate") or []
            )
            n_in = len(equity_candidates)
            n_out = len(prioritized) if isinstance(prioritized, list) else 0

            if n_in == 0:
                return {"sender": "candidate_handoff_guard"}

            # Count each category of drop
            n_extr_fail = 0
            n_other_fail = 0
            n_not_buy = 0
            n_no_entry = 0
            per_ticker_status: dict[str, str] = {}

            for raw_candidate in equity_candidates:
                instrument_key = ""
                if isinstance(raw_candidate, dict):
                    ticker = (raw_candidate.get("ticker") or raw_candidate.get("symbol") or "").upper()
                    instrument_key = str(raw_candidate.get("instrument_key") or "")
                else:
                    ticker = str(raw_candidate).upper()
                if not ticker:
                    n_no_entry += 1
                    continue

                analysis = {}
                if isinstance(ticker_analyses, dict):
                    analysis = ticker_analyses.get(ticker, {})
                    if not analysis and instrument_key:
                        analysis = ticker_analyses.get(instrument_key, {})
                structured = analysis.get("final_trade_decision_structured") or {}
                analysis_status = str(analysis.get("analysis_status") or "").lower()
                status = str(structured.get("status") or "").lower()
                action = str(structured.get("action") or "").upper()

                if status == "extraction_failed":
                    n_extr_fail += 1
                    per_ticker_status[ticker] = "extraction_failed"
                elif analysis_status == "failed" and status != "extraction_failed":
                    n_other_fail += 1
                    per_ticker_status[ticker] = "analysis_failed"
                elif status in {"empty", "timeout_fallback"}:
                    n_not_buy += 1
                    per_ticker_status[ticker] = status
                elif status == "completed" and action in {"HOLD", "SELL"}:
                    n_not_buy += 1
                    per_ticker_status[ticker] = f"completed:{action}"
                elif not analysis and not structured:
                    n_no_entry += 1
                    per_ticker_status[ticker] = "no_deep_dive"
                else:
                    per_ticker_status[ticker] = f"completed:{action}"

            accounted_drop = n_extr_fail + n_other_fail + n_not_buy + n_no_entry

            if n_in > 0 and n_out == 0 and n_extr_fail == n_in:
                raise CandidateHandoffError(
                    kind="all_extraction_failed",
                    n_in=n_in,
                    n_out=n_out,
                    per_ticker_status=per_ticker_status,
                )

            if n_in - n_out != accounted_drop:
                raise CandidateHandoffError(
                    kind="unaccountable_drop",
                    n_in=n_in,
                    n_out=n_out,
                    per_ticker_status=per_ticker_status,
                )

            logger.info(
                "candidate_handoff_guard: ok n_in=%d n_out=%d n_extraction_failed=%d n_not_buy=%d",
                n_in,
                n_out,
                n_extr_fail,
                n_not_buy,
            )
            return {"sender": "candidate_handoff_guard"}

        return candidate_handoff_guard_node

    def _make_rescale_buys_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        """Deterministic guard that scales buy notional to fit within the cash ceiling.

        Computed ceiling: max(0, cash - min_cash_pct * total_value).
        When aggregate buy notional exceeds the ceiling, ALL buy shares are scaled
        down proportionally so the sum of (shares × execution_price) equals the
        ceiling. When the ceiling is ≤ 0, all buys are cleared.

        Notional is measured with ``resolve_buy_execution_price`` — the *same*
        live-price source that ``pm_decision_postcheck`` uses to project cash.
        Using ``entry_price`` here would let a rescaled basket pass this node
        and still breach the floor in postcheck whenever live > entry (P2).

        This runs BEFORE cash_sweep so the SGOV sweep added by that node is not
        subject to rescaling (it manages cash the PM chose not to deploy).
        """
        config = self._config

        def rescale_buys_node(state: PortfolioManagerState) -> dict[str, Any]:
            pm_decision_str = state.get("pm_decision") or "{}"
            portfolio_data_str = state.get("portfolio_data") or "{}"
            prices = state.get("prices") or {}

            try:
                decision = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError):
                return {"pm_decision": pm_decision_str, "sender": "rescale_buys"}

            try:
                pd = json.loads(portfolio_data_str)
                portfolio = pd.get("portfolio") or {}
                cash = float(portfolio.get("cash", 0.0))
                total_value = float(portfolio.get("total_value") or cash)
            except Exception:
                return {"pm_decision": pm_decision_str, "sender": "rescale_buys"}

            min_cash_pct = float(config.get("min_cash_pct", 0.05))
            ceiling = max(0.0, cash - min_cash_pct * total_value)

            buys = decision.get("buys") or []
            if not buys:
                return {"pm_decision": pm_decision_str, "sender": "rescale_buys"}

            # Per-buy execution price: prefer live price (same source as
            # postcheck). Fall back to entry_price only if the live price is
            # missing or non-positive — postcheck will then reject the basket
            # for missing prices, which is the correct behavior.
            def _exec_price(buy: dict) -> float:
                try:
                    return resolve_buy_execution_price(buy, prices)
                except Exception:
                    return float(buy.get("entry_price", 0.0))

            total_notional = sum(
                float(b.get("shares", 0.0)) * _exec_price(b) for b in buys if isinstance(b, dict)
            )

            if total_notional <= 0.0:
                return {"pm_decision": pm_decision_str, "sender": "rescale_buys"}

            if ceiling <= 0.0:
                logger.warning(
                    "rescale_buys: ceiling=0 (cash=%.2f, total_value=%.2f, min_cash_pct=%.2f) — "
                    "dropping all %d buy order(s)",
                    cash,
                    total_value,
                    min_cash_pct,
                    len(buys),
                )
                decision["buys"] = []
                return {"pm_decision": json.dumps(decision), "sender": "rescale_buys"}

            if total_notional > ceiling:
                scale = ceiling / total_notional
                logger.warning(
                    "rescale_buys: total_notional=%.2f exceeds ceiling=%.2f (priced at "
                    "execution) — scaling all buys by %.4f",
                    total_notional,
                    ceiling,
                    scale,
                )
                for b in buys:
                    if isinstance(b, dict):
                        b["shares"] = float(b.get("shares", 0.0)) * scale
                decision["buys"] = buys

            return {"pm_decision": json.dumps(decision), "sender": "rescale_buys"}

        return rescale_buys_node

    def _make_cash_sweep_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        """Node to automatically sweep excess cash into a cash-equivalent ETF."""
        config = self._config

        def cash_sweep_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_data_str = state.get("portfolio_data") or "{}"
            pm_decision_str = state.get("pm_decision") or "{}"
            prices = state.get("prices") or {}

            try:
                portfolio_data = json.loads(portfolio_data_str)
                from tradingagents.portfolio.models import Holding, Portfolio

                portfolio = Portfolio.from_dict(
                    portfolio_data.get("portfolio") or _EMPTY_PORTFOLIO_DICT
                )
                holdings = [Holding.from_dict(h) for h in (portfolio_data.get("holdings") or [])]

                if prices and portfolio.total_value is None:
                    equity = sum(prices.get(h.ticker, 0.0) * h.shares for h in holdings)
                    total_value = portfolio.cash + equity
                    for h in holdings:
                        if h.ticker in prices:
                            h.enrich(prices[h.ticker], total_value)
                    portfolio.enrich(holdings)

                total_value = portfolio.total_value or portfolio.cash

                # Sweep target reads from config; defaults to min_cash_pct so a
                # deployment that raises the floor (e.g. min_cash_pct=0.10) does
                # not have its operator-intent silently violated by a hardcoded
                # 5% sweep target. ``target_cash_pct`` may still be set
                # explicitly when desk policy wants a buffer above the floor.
                min_cash_pct = float(config.get("min_cash_pct", 0.05))
                target_cash_pct = float(config.get("target_cash_pct", min_cash_pct))
                sweep_etf = "SGOV"
                sweep_etf_price = prices.get(sweep_etf, 100.0)  # Assume 100.0 if not in prices

                try:
                    decisions = json.loads(pm_decision_str)
                except (json.JSONDecodeError, TypeError):
                    decisions = {"sells": [], "buys": []}

                if "buys" not in decisions:
                    decisions["buys"] = []

                # Subtract already-approved BUY notional (post-rescale) from
                # available cash before computing sweep excess. Without this,
                # the sweep would size SGOV against pre-buy cash and the
                # combined basket (PM buys + SGOV) would breach the cash
                # floor in postcheck — defeating rescale_buys upstream (P1).
                # Use resolve_buy_execution_price so this matches postcheck's
                # cash-projection arithmetic exactly. Skip any pre-existing
                # SGOV sweep order (defensive — sweep should not have run
                # yet, but graph re-entries can violate that assumption).
                approved_buys = decisions.get("buys") or []
                approved_buy_notional = 0.0
                for buy in approved_buys:
                    if not isinstance(buy, dict):
                        continue
                    if str(buy.get("ticker") or "").upper() == sweep_etf:
                        continue
                    try:
                        bp = resolve_buy_execution_price(buy, prices)
                    except Exception:
                        bp = float(buy.get("entry_price", 0.0))
                    approved_buy_notional += float(buy.get("shares", 0.0)) * bp

                cash_after_buys = portfolio.cash - approved_buy_notional

                sweep_details = "No sweep needed"
                if total_value > 0 and cash_after_buys > 0:
                    current_cash_pct = cash_after_buys / total_value
                    if current_cash_pct > target_cash_pct:
                        excess_cash = cash_after_buys - (total_value * target_cash_pct)
                        shares_to_buy = int(excess_cash / sweep_etf_price)

                        if shares_to_buy > 0:
                            analysis_date = state.get("analysis_date") or ""
                            sweep_buy = {
                                "ticker": sweep_etf,
                                "shares": float(shares_to_buy),
                                "entry_price": sweep_etf_price,
                                "limit_price": sweep_etf_price,
                                "max_chase_price": sweep_etf_price,
                                "order_type": "limit",
                                "valid_as_of": analysis_date,
                                "price_target": sweep_etf_price,
                                "stop_loss": 0.0,
                                "take_profit": sweep_etf_price,
                                "sector": "Cash Equivalent",
                                "rationale": f"Automatic cash sweep of excess cash (${excess_cash:.2f}) to maintain {target_cash_pct * 100:.1f}% target.",
                                "thesis": "Park excess cash in short-term treasury ETF",
                                "macro_alignment": "Defensive cash management",
                                "memory_note": "",
                                "position_sizing_logic": f"Sweep {shares_to_buy} shares at market price",
                            }
                            decisions["buys"].append(sweep_buy)
                            pm_decision_str = json.dumps(decisions)
                            sweep_details = f"Swept {shares_to_buy} shares of {sweep_etf}"
                            logger.info("CashSweep: %s", sweep_details)
            except Exception as exc:
                logger.error("cash_sweep_node: %s", exc)
                sweep_details = f"Error: {exc}"

            return {
                "pm_decision": pm_decision_str,
                "cash_sweep": sweep_details,
                "sender": "cash_sweep",
            }

        return cash_sweep_node

    def _make_execute_trades_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        repo = self._repo
        config = self._config

        def execute_trades_node(state: PortfolioManagerState) -> dict[str, Any]:
            portfolio_id = state["portfolio_id"]
            analysis_date = state.get("analysis_date") or ""
            prices = state.get("prices") or {}
            pm_decision_str = state.get("pm_decision") or "{}"
            try:
                decisions = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError):
                decisions = {}

            try:
                if repo is None:
                    from tradingagents.portfolio.repository import PortfolioRepository

                    _repo = PortfolioRepository(config=config)
                else:
                    _repo = repo
                executor = TradeExecutor(repo=_repo, config=config)
                result = executor.execute_decisions(
                    portfolio_id, decisions, prices, date=analysis_date
                )
            except Exception as exc:
                logger.error("execute_trades_node: %s", exc)
                result = {"error": str(exc), "executed_trades": [], "failed_trades": []}
            return {
                "execution_result": json.dumps(result),
                "sender": "execute_trades",
            }

        return execute_trades_node

    def _make_record_pm_decisions_node(self) -> Callable[[PortfolioManagerState], dict[str, Any]]:
        micro_memory = self._micro_memory

        def record_pm_decisions_node(state: PortfolioManagerState) -> dict[str, Any]:
            """Write final PM decisions to micro_reflexion memory.

            Runs after execute_trades. Fails silently — memory persistence
            must never break the portfolio pipeline.
            """
            if micro_memory is None:
                return {"sender": "record_pm_decisions"}

            analysis_date = state.get("analysis_date") or ""
            run_id = state.get("run_id")
            pm_decision_str = state.get("pm_decision") or "{}"
            execution_result_str = state.get("execution_result") or "{}"

            try:
                execution_result = json.loads(execution_result_str)
            except (json.JSONDecodeError, TypeError):
                execution_result = {}
            if isinstance(execution_result, dict) and execution_result.get("error"):
                logger.error(
                    "record_pm_decisions_node: skipping memory write because "
                    "execute_trades failed: %s",
                    execution_result.get("error"),
                )
                return {"sender": "record_pm_decisions"}
            if not str(analysis_date).strip():
                logger.error(
                    "record_pm_decisions_node: skipping memory write because "
                    "analysis_date is missing"
                )
                return {"sender": "record_pm_decisions"}

            try:
                decisions = json.loads(pm_decision_str)
            except (json.JSONDecodeError, TypeError):
                logger.error(
                    "record_pm_decisions_node: could not parse pm_decision JSON",
                    exc_info=True,
                )
                return {"sender": "record_pm_decisions"}

            if not isinstance(decisions, dict):
                logger.error("record_pm_decisions_node: pm_decision JSON was not an object")
                return {"sender": "record_pm_decisions"}

            failed: list[str] = []

            def record_orders(orders: Any, decision: str, confidence: str) -> None:
                if not isinstance(orders, list):
                    return
                for order in orders:
                    if not isinstance(order, dict):
                        continue
                    ticker = str(order.get("ticker") or "").strip().upper()
                    if not ticker:
                        continue
                    try:
                        micro_memory.record_decision(
                            ticker,
                            analysis_date,
                            decision,
                            rationale=order.get("rationale") or "",
                            confidence=confidence,
                            source="portfolio",
                            run_id=run_id,
                        )
                    except Exception:
                        failed.append(f"{decision}:{ticker}")
                        logger.error(
                            "record_pm_decisions_node: could not record %s decision for %s",
                            decision,
                            ticker,
                            exc_info=True,
                        )

            record_orders(decisions.get("buys") or [], "BUY", "high")
            record_orders(decisions.get("sells") or [], "SELL", "medium")
            record_orders(decisions.get("holds") or [], "HOLD", "medium")

            if failed:
                logger.error(
                    "record_pm_decisions_node: failed to record %d PM decision(s): %s",
                    len(failed),
                    ", ".join(failed),
                )

            return {"sender": "record_pm_decisions"}

        return record_pm_decisions_node

    # ------------------------------------------------------------------
    # Graph assembly
    # ------------------------------------------------------------------

    def setup_graph(self) -> Any:
        """Build and compile the portfolio workflow graph with parallel summary fan-out.

        Topology:
            START → load_portfolio → compute_risk → portfolio_integrity_guard
                  → review_holdings → prioritize_candidates
                  → macro_summary (parallel)
                  → micro_summary  (parallel)
                  → make_pm_decision → cash_sweep → pm_decision_postcheck
                  → execute_trades → record_pm_decisions → END

        Returns:
            A compiled LangGraph graph ready to invoke.
        """
        workflow = StateGraph(PortfolioManagerState)

        # Register non-LLM nodes
        workflow.add_node("load_portfolio", self._make_load_portfolio_node())
        workflow.add_node("compute_risk", self._make_compute_risk_node())
        workflow.add_node("portfolio_integrity_guard", self._make_portfolio_integrity_guard_node())
        workflow.add_node("prioritize_candidates", self._make_prioritize_candidates_node())
        workflow.add_node("candidate_handoff_guard", self._make_candidate_handoff_guard_node())
        workflow.add_node("rescale_buys", self._make_rescale_buys_node())
        workflow.add_node("cash_sweep", self._make_cash_sweep_node())
        workflow.add_node("pm_decision_postcheck", self._make_pm_decision_postcheck_node())
        workflow.add_node("execute_trades", self._make_execute_trades_node())
        workflow.add_node("record_pm_decisions", self._make_record_pm_decisions_node())

        # Register LLM nodes
        workflow.add_node("review_holdings", self.agents["review_holdings"])
        workflow.add_node("macro_summary", self.agents["macro_summary"])
        workflow.add_node("micro_summary", self.agents["micro_summary"])
        workflow.add_node("make_pm_decision", self.agents["pm_decision"])

        # Sequential backbone
        workflow.add_edge(START, "load_portfolio")
        workflow.add_edge("load_portfolio", "compute_risk")
        # Integrity guard validates portfolio_data before any LLM node sees it (ADR 024)
        workflow.add_edge("compute_risk", "portfolio_integrity_guard")
        workflow.add_edge("portfolio_integrity_guard", "review_holdings")
        workflow.add_edge("review_holdings", "prioritize_candidates")
        workflow.add_edge("prioritize_candidates", "candidate_handoff_guard")

        # Fan-out: candidate_handoff_guard → both summary nodes (parallel)
        workflow.add_edge("candidate_handoff_guard", "macro_summary")
        workflow.add_edge("candidate_handoff_guard", "micro_summary")

        # Fan-in: both summary nodes → make_pm_decision
        workflow.add_edge("macro_summary", "make_pm_decision")
        workflow.add_edge("micro_summary", "make_pm_decision")

        # Tail — rescale_buys runs FIRST on the LLM's BUYs to enforce the cash floor,
        # then cash_sweep adds the SGOV cash-equivalent order from the residual cash,
        # then postcheck validates all invariants. Order matters: SGOV is a deliberate
        # cash-park, not a discretionary BUY, so it must NOT be subject to proportional
        # rescaling. Reversing this order would let the sweep crowd out PM buys. (ADR 024)
        workflow.add_edge("make_pm_decision", "rescale_buys")
        workflow.add_edge("rescale_buys", "cash_sweep")
        workflow.add_edge("cash_sweep", "pm_decision_postcheck")
        workflow.add_edge("pm_decision_postcheck", "execute_trades")
        workflow.add_edge("execute_trades", "record_pm_decisions")
        workflow.add_edge("record_pm_decisions", END)

        return workflow.compile()
