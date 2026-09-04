# Coordinated Options-Wheel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paper-first Alpaca options-wheel sleeve that shares capital, positions, orders, and volatility limits with the existing seven-symbol equity automation while leaving the analysis graph unchanged.

**Architecture:** The existing graph continues to produce one rating per symbol. Pure risk and wheel-policy modules turn broker snapshots into reviewable targets and option intents; `AutomationCycleService` coordinates them before the existing idempotent submission boundary. Alpaca mapping stays in the broker adapter, and SQLite records daily-entry and option-intent state without treating local state as authoritative over Alpaca.

**Tech Stack:** Python 3.12, `decimal.Decimal`, Alpaca-py, SQLite, pytest, existing TradingAgents scheduler and automation graph.

**Specs:** `docs/superpowers/specs/2026-09-03-volatility-targeted-allocation-design.md` and `docs/superpowers/specs/2026-09-04-coordinated-options-wheel-design.md`

## Global Constraints

- Preserve `TradingAgentsGraph.propagate()` and the existing 3-2-2 analysis rotation.
- Alpaca is the only broker; paper mode is the initial implementation and activation target.
- Target annualized forecast volatility is `0.15`, maximum forecast volatility is `0.20`, and maximum gross exposure is `2.0` times account equity.
- Use 60 aligned trading days and require at least 40 aligned return observations.
- Total wheel exposure is at most `0.20` times account equity and each underlying has at most one active wheel contract.
- Contract filters are 14-28 DTE, absolute delta 0.15-0.30, open interest greater than 100, annualized yield between 0.04 and 1.00, score greater than 0.05, quote age no greater than 300 seconds, and a seven-day earnings blackout.
- Only `LIMIT`/`DAY` option orders are allowed; naked options, multi-leg orders, market option orders, forced liquidation, and fresh-start behavior are prohibited.
- New entries are considered once per New York trading date at or after 10:00; monitoring and risk-reducing exits run every 15 minutes while the equity market is open.
- Options execution defaults off. Live options require both live acknowledgements and are not activated by this plan.
- Existing user changes in the dirty worktree must not be reverted, reformatted, or folded into unrelated commits.

---

### Task 1: Pure Volatility and Gross-Exposure Sizing

**Files:**
- Create: `tradingagents/risk.py`
- Create: `tests/test_risk.py`

**Interfaces:**
- Produces: `RiskScaleResult`, `close_returns()`, `forecast_volatility()`, and `scale_equity_targets()`.
- `scale_equity_targets(equity_targets, fixed_option_exposure, equity, close_history, target_volatility, max_volatility, max_gross_leverage) -> RiskScaleResult` preserves the relative signed equity targets while treating existing option delta exposure as fixed.
- `close_history` is `Mapping[str, Sequence[tuple[date, Decimal]]]`; every symbol must have identical dates after alignment.

- [ ] **Step 1: Write failing calculation tests**

```python
# tests/test_risk.py
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tradingagents.risk import close_returns, forecast_volatility, scale_equity_targets


def _history(changes):
    prices = [Decimal("100")]
    for change in changes:
        prices.append(prices[-1] * (Decimal("1") + Decimal(str(change))))
    start = date(2026, 1, 2)
    return tuple((start + timedelta(days=index), price) for index, price in enumerate(prices))


def test_close_returns_requires_forty_aligned_observations():
    with pytest.raises(ValueError, match="40 aligned return observations"):
        close_returns({"AAPL": _history([0.01] * 39)})


def test_forecast_uses_signed_equity_and_option_exposure():
    history = {
        "AAPL": _history([0.01, -0.01] * 20),
        "MSFT": _history([-0.01, 0.01] * 20),
    }
    returns = close_returns(history)
    unhedged = forecast_volatility(
        {"AAPL": Decimal("50000")}, Decimal("100000"), returns
    )
    hedged = forecast_volatility(
        {"AAPL": Decimal("50000"), "MSFT": Decimal("50000")},
        Decimal("100000"),
        returns,
    )
    assert hedged < unhedged


def test_scaling_preserves_equity_target_ratios_and_respects_limits():
    history = {
        "AAPL": _history([0.02, -0.02] * 20),
        "MSFT": _history([0.01, -0.01] * 20),
    }
    result = scale_equity_targets(
        {"AAPL": Decimal("80000"), "MSFT": Decimal("-40000")},
        {"AAPL": Decimal("10000")},
        Decimal("100000"),
        history,
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("2.0"),
    )
    assert result.targets["AAPL"] == -Decimal("2") * result.targets["MSFT"]
    assert result.forecast_volatility <= Decimal("0.15") + Decimal("0.000001")
    assert result.gross_leverage <= Decimal("2.0")
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run: `.venv/bin/python -m pytest -q tests/test_risk.py`

Expected: collection fails with `ModuleNotFoundError: No module named 'tradingagents.risk'`.

- [ ] **Step 3: Implement deterministic risk calculations**

```python
# tradingagents/risk.py
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import sqrt


@dataclass(frozen=True)
class RiskScaleResult:
    targets: dict[str, Decimal]
    baseline_volatility: Decimal
    forecast_volatility: Decimal
    scale: Decimal
    gross_leverage: Decimal


def close_returns(
    history: Mapping[str, Sequence[tuple[date, Decimal]]],
) -> dict[str, tuple[Decimal, ...]]:
    if not history:
        raise ValueError("close history is required")
    common_dates = set.intersection(*(set(day for day, _ in rows) for rows in history.values()))
    ordered_dates = sorted(common_dates)[-61:]
    if len(ordered_dates) < 41:
        raise ValueError("at least 40 aligned return observations are required")
    result = {}
    for symbol, rows in history.items():
        by_date = {day: Decimal(value) for day, value in rows}
        closes = [by_date[day] for day in ordered_dates]
        if any(value <= 0 or not value.is_finite() for value in closes):
            raise ValueError("close prices must be positive and finite")
        result[symbol] = tuple(
            closes[index] / closes[index - 1] - Decimal("1")
            for index in range(1, len(closes))
        )
    return result


def forecast_volatility(exposure, equity, returns):
    equity = Decimal(equity)
    if equity <= 0 or not equity.is_finite():
        raise ValueError("equity must be positive and finite")
    lengths = {len(values) for values in returns.values()}
    if len(lengths) != 1:
        raise ValueError("return histories must be aligned")
    observation_count = lengths.pop()
    if not 40 <= observation_count <= 60:
        raise ValueError("40 to 60 aligned returns are required")
    portfolio = [
        sum(Decimal(exposure.get(symbol, 0)) / equity * values[index]
            for symbol, values in returns.items())
        for index in range(observation_count)
    ]
    mean = sum(portfolio) / Decimal(len(portfolio))
    variance = sum((value - mean) ** 2 for value in portfolio) / Decimal(39)
    return Decimal(str(sqrt(float(variance * Decimal("252")))))
```

Implement `scale_equity_targets()` from the annualized variance of the affine
return series `scale * equity_returns + option_returns`. If `a`, `b`, and `c`
are the annualized variance, covariance, and fixed-option variance terms, solve
`a*scale**2 + 2*b*scale + c <= target**2`, intersect that interval with the
non-negative gross-exposure interval, and select its largest value:

```python
def scale_equity_targets(
    equity_targets, fixed_option_exposure, equity, close_history,
    target_volatility, max_volatility, max_gross_leverage,
):
    returns = close_returns(close_history)
    equity = Decimal(equity)
    target = Decimal(target_volatility)
    maximum = Decimal(max_volatility)
    gross_limit = Decimal(max_gross_leverage) * equity
    option_gross = sum(abs(Decimal(value)) for value in fixed_option_exposure.values())
    equity_gross = sum(abs(Decimal(value)) for value in equity_targets.values())
    if equity <= 0 or equity_gross <= 0 or option_gross > gross_limit:
        raise ValueError("valid equity targets and gross capacity are required")
    gross_scale = (gross_limit - option_gross) / equity_gross
    equity_series = _portfolio_returns(equity_targets, equity, returns)
    option_series = _portfolio_returns(fixed_option_exposure, equity, returns)
    a = _annualized_variance(equity_series)
    b = _annualized_covariance(equity_series, option_series)
    c = _annualized_variance(option_series)
    discriminant = b * b - a * (c - target * target)
    if a <= 0 or discriminant < 0:
        raise ValueError("portfolio volatility target is infeasible")
    upper = (-b + discriminant.sqrt()) / a
    scale = min(gross_scale, upper)
    if scale < 0:
        raise ValueError("portfolio volatility target is infeasible")
    targets = {symbol: Decimal(value) * scale for symbol, value in equity_targets.items()}
    combined = dict(fixed_option_exposure)
    for symbol, value in targets.items():
        combined[symbol] = Decimal(combined.get(symbol, 0)) + value
    forecast = forecast_volatility(combined, equity, returns)
    gross = (sum(abs(value) for value in targets.values()) + option_gross) / equity
    if forecast > maximum:
        raise ValueError("scaled forecast exceeds maximum volatility")
    return RiskScaleResult(
        targets, forecast_volatility(
            {symbol: Decimal(equity_targets.get(symbol, 0)) + Decimal(fixed_option_exposure.get(symbol, 0))
             for symbol in set(equity_targets) | set(fixed_option_exposure)},
            equity, returns,
        ), forecast, scale, gross,
    )
```

Implement `_portfolio_returns`, `_annualized_variance`, and
`_annualized_covariance` as private Decimal helpers over the same 40-to-60 aligned
observations. Reject non-finite inputs and a zero or non-finite result.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_risk.py`

Expected: all tests pass.

- [ ] **Step 5: Commit the risk module**

```bash
git add tradingagents/risk.py tests/test_risk.py
git commit -m "feat: add volatility target sizing"
```

---

### Task 2: Risk Configuration and Batched Daily Closes

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/automation.py`
- Modify: `tradingagents/execution.py`
- Modify: `tests/test_env_overrides.py`
- Modify: `tests/test_automation_config.py`
- Modify: `tests/test_alpaca_execution.py`

**Interfaces:**
- Extends `AutomationSettings` with `target_volatility`, `max_volatility`, and `max_gross_leverage`.
- Extends `Broker` with `daily_closes(symbols: tuple[str, ...], limit: int = 61) -> dict[str, tuple[tuple[date, Decimal], ...]]`.
- `AlpacaBroker.daily_closes()` requests all seven symbols in one IEX daily-bar request.

- [ ] **Step 1: Add failing configuration tests**

```python
def test_settings_accept_volatility_policy():
    settings = AutomationSettings.from_config(_config(
        target_volatility=0.15,
        max_volatility=0.20,
        max_gross_leverage=2.0,
    ))
    assert settings.target_volatility == 0.15
    assert settings.max_volatility == 0.20
    assert settings.max_gross_leverage == 2.0


@pytest.mark.parametrize("values", [
    {"target_volatility": 0},
    {"target_volatility": 0.21, "max_volatility": 0.20},
    {"max_volatility": 0.21},
    {"max_gross_leverage": 2.01},
])
def test_settings_reject_invalid_volatility_policy(values):
    with pytest.raises(ValueError):
        AutomationSettings.from_config(_config(**values))
```

Add the three keys at their approved values to the `_config()` helper.

- [ ] **Step 2: Add a failing batched-bar adapter test**

```python
def test_daily_closes_requests_one_iex_batch(monkeypatch):
    captured = []

    class FakeRequest:
        def __init__(self, **fields):
            captured.append(fields)

    bars = {
        "AAPL": [SimpleNamespace(timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="100")],
        "MSFT": [SimpleNamespace(timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc), close="200")],
    }
    data_client = SimpleNamespace(get_stock_bars=lambda request: SimpleNamespace(data=bars))
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    broker._stock_data_client = data_client
    monkeypatch.setattr("tradingagents.execution._stock_bars_request_class", lambda: FakeRequest)

    result = broker.daily_closes(("AAPL", "MSFT"), limit=61)

    assert captured[0]["symbol_or_symbols"] == ["AAPL", "MSFT"]
    assert str(captured[0]["feed"]).lower().endswith("iex")
    assert result["AAPL"][0][1] == Decimal("100")
```

- [ ] **Step 3: Run the focused tests and confirm failures**

Run: `.venv/bin/python -m pytest -q tests/test_automation_config.py tests/test_env_overrides.py tests/test_alpaca_execution.py`

Expected: failures identify the absent settings and `daily_closes()` method.

- [ ] **Step 4: Add defaults, validation, and the broker method**

Add these overrides and defaults:

```python
"TRADINGAGENTS_TARGET_VOLATILITY": "target_volatility",
"TRADINGAGENTS_MAX_VOLATILITY": "max_volatility",
"TRADINGAGENTS_MAX_GROSS_LEVERAGE": "max_gross_leverage",

"target_volatility": 0.15,
"max_volatility": 0.20,
"max_gross_leverage": 2.0,
```

Validate `0 < target <= maximum <= 0.20` and
`1.0 <= max_gross_leverage <= 2.0`. Add lazy Alpaca imports for
`StockBarsRequest`, `TimeFrame.Day`, and `DataFeed.IEX`; request 61 daily bars in
one call, convert timestamps to dates and closes to positive finite `Decimal`
values, and fail if any requested symbol is absent.

- [ ] **Step 5: Run focused tests and commit**

Run: `.venv/bin/python -m pytest -q tests/test_automation_config.py tests/test_env_overrides.py tests/test_alpaca_execution.py`

Expected: all focused tests pass.

```bash
git add tradingagents/default_config.py tradingagents/automation.py tradingagents/execution.py tests/test_env_overrides.py tests/test_automation_config.py tests/test_alpaca_execution.py
git commit -m "feat: configure portfolio volatility controls"
```

---

### Task 3: Pure Wheel Policy and Reservations

**Files:**
- Create: `tradingagents/options.py`
- Create: `tests/test_options.py`

**Interfaces:**
- Produces immutable `OptionContract`, `EquityPosition`, `OptionPosition`, `OptionOpenOrder`, `WheelReservations`, and `OptionIntent` dataclasses.
- Produces `contract_metrics()`, `select_contract()`, `build_reservations()`, `option_delta_exposure()`, `option_intent_delta_exposure()`, `plan_profit_exit()`, and `plan_new_entry()`.
- All money, price, strike, delta, quantity, and exposure fields use `Decimal`.

- [ ] **Step 1: Write failing filter and reservation tests**

```python
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from tradingagents.options import (
    EquityPosition,
    OptionContract,
    OptionOpenOrder,
    OptionPosition,
    build_reservations,
    option_delta_exposure,
    select_contract,
)

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)


def _contract(symbol="AAPL261002P00300000", kind="put", strike="300", delta="-0.20"):
    return OptionContract(
        symbol=symbol,
        underlying="AAPL",
        kind=kind,
        strike=Decimal(strike),
        expiration=date(2026, 10, 2),
        delta=Decimal(delta),
        bid=Decimal("3.00"),
        ask=Decimal("3.20"),
        open_interest=Decimal("500"),
        quote_time=NOW,
    )


def test_select_contract_uses_reviewed_filters_and_highest_score():
    lower = _contract()
    higher = _contract(symbol="AAPL261002P00310000", strike="310")
    assert select_contract((lower, higher), NOW, date(2026, 12, 1)).symbol == lower.symbol


def test_short_put_and_covered_call_reservations_are_reconstructed():
    reservations = build_reservations(
        equities=(EquityPosition("AAPL", Decimal("250"), Decimal("300"), Decimal("320")),),
        options=(OptionPosition("AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.2")),),
        orders=(OptionOpenOrder("AAPL261002C00350000", "AAPL", "call", "sell_to_open", Decimal("1"), Decimal("0"), Decimal("350")),),
    )
    assert reservations.put_collateral["AAPL"] == Decimal("30000")
    assert reservations.covered_shares["AAPL"] == Decimal("100")


def test_short_put_has_positive_delta_equivalent_exposure():
    position = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("3"), Decimal("-0.20")
    )
    assert option_delta_exposure((position,), {"AAPL": Decimal("320")}) == {
        "AAPL": Decimal("6400")
    }


def test_profit_exit_buys_back_at_half_the_opening_credit():
    position = OptionPosition(
        "AAPL261002P00300000", "AAPL", "put", Decimal("-1"), Decimal("4.00"), Decimal("-0.20")
    )
    contract = _contract()
    contract = replace(contract, bid=Decimal("1.80"), ask=Decimal("2.00"))
    intent = plan_profit_exit(position, contract, NOW)
    assert intent.side == "buy"
    assert intent.position_intent == "buy_to_close"
    assert intent.limit_price == Decimal("2.00")
```

- [ ] **Step 2: Run the tests and verify the module is absent**

Run: `.venv/bin/python -m pytest -q tests/test_options.py`

Expected: collection fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement strict dataclasses and calculations**

Define the public types exactly:

```python
@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    kind: str
    strike: Decimal
    expiration: date
    delta: Decimal
    bid: Decimal
    ask: Decimal
    open_interest: Decimal
    quote_time: datetime


@dataclass(frozen=True)
class EquityPosition:
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal


@dataclass(frozen=True)
class OptionPosition:
    symbol: str
    underlying: str
    kind: str
    qty: Decimal
    avg_entry_price: Decimal
    delta: Decimal


@dataclass(frozen=True)
class OptionOpenOrder:
    symbol: str
    underlying: str
    kind: str
    position_intent: str
    qty: Decimal
    filled_qty: Decimal
    strike: Decimal
    order_id: str = ""
    client_order_id: str = ""
    submitted_at: datetime | None = None


@dataclass(frozen=True)
class WheelReservations:
    put_collateral: dict[str, Decimal]
    covered_shares: dict[str, Decimal]


@dataclass(frozen=True)
class OptionIntent:
    symbol: str
    underlying: str
    kind: str
    side: str
    position_intent: str
    qty: Decimal
    limit_price: Decimal
    delta: Decimal
```

Use the formulas from the approved design:

```python
def contract_metrics(contract: OptionContract, now: datetime) -> tuple[Decimal, Decimal, int]:
    dte = (contract.expiration - now.astimezone(NEW_YORK).date()).days
    annualized_yield = contract.bid / contract.strike * Decimal(365) / Decimal(dte + 1)
    score = (Decimal(1) - abs(contract.delta)) * Decimal(250) / Decimal(dte + 5) * contract.bid / contract.strike
    return annualized_yield, score, dte
```

`select_contract()` rejects missing/future/stale quote timestamps, non-positive or
crossed quotes, boundary failures, and earnings within seven days; it returns the
highest `(score, symbol)` deterministically. `build_reservations()` requires every
short call to be covered by a distinct 100-share long lot, rejects short equity
as a call source without rejecting unrelated shorts, rejects quantities above one
contract or multiple active contracts for one underlying, and includes remaining
sell-to-open put order quantity in collateral. `option_delta_exposure()` uses
`quantity * delta * 100 * spot`.

`option_intent_delta_exposure()` applies a positive contract sign to buys and a
negative contract sign to sells, then uses the same delta formula. This lets the
coordinator test the exact proposed post-trade exposure before order preparation.

`plan_profit_exit()` returns a buy-to-close intent only when the validated current
ask is no greater than 50% of the positive opening credit. It uses the current ask
as the limit and never applies entry-only earnings or decision filters.

- [ ] **Step 4: Add and pass decision-policy tests**

```python
def test_put_requires_buy_or_overweight_and_empty_underlying():
    assert plan_new_entry("AAPL", "Hold", (), (), (), (), NOW, date(2026, 12, 1), Decimal("200000")) is None


def test_call_requires_reserved_long_lot_and_hold_or_underweight():
    call = _contract("AAPL261002C00350000", "call", "350", "0.20")
    equity = EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320"))
    intent = plan_new_entry(
        "AAPL", "Hold", (equity,), (), (), (call,), NOW, date(2026, 12, 1), Decimal("200000")
    )
    assert intent.position_intent == "sell_to_open"
    assert intent.kind == "call"
    assert intent.limit_price == Decimal("3.10")
```

Run: `.venv/bin/python -m pytest -q tests/test_options.py`

Expected: all tests pass.

- [ ] **Step 5: Commit the pure policy**

```bash
git add tradingagents/options.py tests/test_options.py
git commit -m "feat: add options wheel policy"
```

---

### Task 4: Alpaca Option Snapshot and Limit-Order Mapping

**Files:**
- Modify: `tradingagents/execution.py`
- Modify: `tests/test_alpaca_execution.py`

**Interfaces:**
- Extends `AccountSnapshot` with `options_buying_power: Decimal`.
- Adds `AlpacaBroker.option_snapshot(symbols)`, `option_contracts(underlying, kind, now)`, and `wheel_positions_and_orders()` returning `(tuple[EquityPosition, ...], tuple[OptionPosition, ...], tuple[OptionOpenOrder, ...])`.
- Adds `prepare_option_order(intent, cycle_id) -> OptionOrderRequestSpec` and `submit_option_idempotent(spec) -> str`.
- Adds `cancel_stale_option_order(order_id, client_order_id) -> None`, which rejects every client ID not prefixed `ta-wheel-` before calling Alpaca.
- `OptionOrderRequestSpec` contains symbol, quantity, side, position intent, limit price, `day`, and deterministic client order ID.

Define `options_buying_power` with `Decimal("0")` as its dataclass default so
existing equity-only test snapshots remain source compatible. Define
`OptionOrderRequestSpec` in `execution.py` with fields matching the constructor
used below.

- [ ] **Step 1: Add failing account and mapping tests**

```python
def test_account_maps_options_buying_power():
    raw = SimpleNamespace(
        cash="100000", equity="120000", buying_power="200000",
        options_buying_power="75000", trading_blocked=False,
        account_blocked=False, trade_suspended_by_user=False,
        status=_enum("ACTIVE"),
    )
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace(get_account=lambda: raw))
    assert broker.account().options_buying_power == Decimal("75000")


def test_option_order_is_limit_day_with_position_intent(monkeypatch):
    captured = []
    class FakeLimitOrderRequest:
        def __init__(self, **fields):
            captured.append(fields)
    monkeypatch.setattr("tradingagents.execution._limit_order_request_class", lambda: FakeLimitOrderRequest)
    client = SimpleNamespace(
        get_order_by_client_id=lambda value: None,
        submit_order=lambda order_data: SimpleNamespace(id="option-order"),
    )
    broker = AlpacaBroker("key", "secret", "paper", client=client)
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000", Decimal("1"), "sell", "sell_to_open",
        Decimal("3.10"), "day", "wheel-stable-id"
    )
    assert broker.submit_option_idempotent(spec) == "option-order"
    assert captured[0]["limit_price"] == 3.1
    assert str(captured[0]["position_intent"]).lower().endswith("sell_to_open")
```

- [ ] **Step 2: Run focused tests and confirm the missing interfaces**

Run: `.venv/bin/python -m pytest -q tests/test_alpaca_execution.py`

Expected: failures identify absent option types and methods.

- [ ] **Step 3: Implement lazy Alpaca option adapters**

Use Alpaca-py's `GetOptionContractsRequest`, `OptionHistoricalDataClient`,
`OptionSnapshotRequest`, `LimitOrderRequest`, and `PositionIntent`. Convert SDK
values immediately to Task 3 dataclasses and `Decimal`. Fetch contracts only for
the requested underlying and type, 14-28 DTE, status active. Keep quote timestamps
from Alpaca; do not synthesize missing timestamps or Greeks.

Build client IDs from
`cycle_id|contract_symbol|side|position_intent|quantity|limit_price`, prefixed
`ta-wheel-`, with a 24-character SHA-256 suffix. Validate paper/live mode and both
acknowledgements before option submission or lookup in live auto-execution mode.

- [ ] **Step 4: Add failure tests for unsafe requests**

```python
@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")])
def test_option_submission_rejects_non_positive_limit(price):
    broker = AlpacaBroker("key", "secret", "paper", client=SimpleNamespace())
    spec = OptionOrderRequestSpec("AAPL261002P00300000", Decimal("1"), "sell", "sell_to_open", price, "day", "id")
    with pytest.raises(ValueError, match="limit price"):
        broker.submit_option_idempotent(spec)


def test_live_options_require_separate_ack_before_lookup():
    calls = []
    broker = AlpacaBroker(
        "key", "secret", "live", client=SimpleNamespace(
            get_order_by_client_id=lambda value: calls.append("lookup")
        ), live_ack="I_UNDERSTAND_LIVE_ORDERS", live_options_ack=""
    )
    spec = OptionOrderRequestSpec(
        "AAPL261002P00300000", Decimal("1"), "sell", "sell_to_open",
        Decimal("3.10"), "day", "wheel-live-id"
    )
    with pytest.raises(ValueError, match="live options acknowledgment"):
        broker.submit_option_idempotent(spec)
    assert calls == []


def test_cancel_rejects_orders_not_owned_by_the_wheel():
    calls = []
    broker = AlpacaBroker(
        "key", "secret", "paper",
        client=SimpleNamespace(cancel_order_by_id=lambda value: calls.append(value)),
    )
    with pytest.raises(ValueError, match="not owned"):
        broker.cancel_stale_option_order("order-id", "manual-order")
    assert calls == []
```

- [ ] **Step 5: Run and commit**

Run: `.venv/bin/python -m pytest -q tests/test_alpaca_execution.py`

Expected: all tests pass.

```bash
git add tradingagents/execution.py tests/test_alpaca_execution.py
git commit -m "feat: map alpaca option data and orders"
```

---

### Task 5: Persist Option Intents and Daily Entry State

**Files:**
- Modify: `tradingagents/automation_state.py`
- Modify: `tests/test_automation_state.py`

**Interfaces:**
- Adds `record_option_intent()`, `update_option_intent()`, `unresolved_option_client_order_id()`, `last_option_entry_date()`, `mark_option_entry_date()`, `observe_wheel_phase()`, and `wheel_phase()`.
- The option-intent natural identity includes cycle ID and contract symbol; daily entry uses New York ISO date.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_option_intent_round_trip_and_retry_identity(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.record_option_intent(
            "cycle", NOW, "AAPL261002P00300000", "AAPL", "sell_to_open",
            Decimal("1"), Decimal("3.10"), "wheel-id"
        )
        state.update_option_intent("cycle", "AAPL261002P00300000", "error", "wheel-id")
        assert state.unresolved_option_client_order_id(
            "AAPL261002P00300000", "sell_to_open", Decimal("1"), Decimal("3.10")
        ) == "wheel-id"


def test_daily_option_entry_marker_is_durable(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        assert state.last_option_entry_date() is None
        state.mark_option_entry_date(date(2026, 9, 4))
        assert state.last_option_entry_date() == date(2026, 9, 4)


def test_disappearing_short_option_requires_two_stable_settlement_snapshots(tmp_path):
    with AutomationState(tmp_path / "state.db") as state:
        state.observe_wheel_phase("AAPL", "short_put", "put-contract", NOW)
        state.observe_wheel_phase("AAPL", "empty", "cash=70000|shares=0", NOW + timedelta(minutes=15))
        assert state.wheel_phase("AAPL") == "settling"
        state.observe_wheel_phase("AAPL", "empty", "cash=70000|shares=0", NOW + timedelta(minutes=30))
        assert state.wheel_phase("AAPL") == "put_ready"
```

- [ ] **Step 2: Run the focused tests**

Run: `.venv/bin/python -m pytest -q tests/test_automation_state.py`

Expected: failures identify the missing methods.

- [ ] **Step 3: Add the minimal schema and methods**

Add `option_order_intents` with columns `cycle_id`, `contract_symbol`,
`underlying`, `created_at`, `position_intent`, `quantity`, `limit_price`, `status`,
and `client_order_id`, using `(cycle_id, contract_symbol)` as primary key. Store
the daily marker in existing `metadata` under `last_option_entry_date`.

Add `wheel_phases` with `underlying`, `phase`, `fingerprint`, `updated_at`, and
`stable_observations`. A transition from `short_put` or `short_call` to an empty
broker snapshot becomes `settling`. It becomes `put_ready` only after two
identical, aware snapshots at least 15 minutes apart; a changed snapshot resets
the count. A resulting long lot becomes `long_shares` immediately. Use the same
transaction and timestamp conventions as equity intents.

- [ ] **Step 4: Run and commit**

Run: `.venv/bin/python -m pytest -q tests/test_automation_state.py`

Expected: all tests pass.

```bash
git add tradingagents/automation_state.py tests/test_automation_state.py
git commit -m "feat: persist option automation state"
```

---

### Task 6: Configuration and Shared Automation Coordination

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/automation.py`
- Modify: `tradingagents/allocation.py`
- Modify: `tradingagents/scheduler.py`
- Modify: `tests/test_env_overrides.py`
- Modify: `tests/test_automation_config.py`
- Modify: `tests/test_automation_cycle.py`
- Modify: `tests/test_scheduler.py`

**Interfaces:**
- Extends `AutomationSettings` with the six options settings from the design.
- Adds `AutomationCycleService.manage_options(due_time) -> OptionCycleResult`.
- Adds `reconcile_targets(..., minimum_positions=None)` so reserved covered shares form a signed minimum long notional during equity reconciliation.

Define the cycle result beside `CycleResult`:

```python
@dataclass(frozen=True)
class OptionCycleResult:
    cycle_id: str
    intents: tuple[OptionIntent, ...]
    submitted_order_ids: tuple[str, ...]
    suppressed_reason: str | None
```

- [ ] **Step 1: Add failing options configuration tests**

```python
def test_options_defaults_are_safe():
    settings = AutomationSettings.from_config(_config(
        options_enabled=False,
        options_auto_execute=False,
        options_max_equity_fraction=0.20,
        options_entry_time_et="10:00",
        options_earnings_path="/tmp/earnings.json",
        live_options_ack="",
    ))
    assert not settings.options_enabled
    assert not settings.options_auto_execute
    assert settings.options_max_equity_fraction == 0.20


def test_options_fraction_cannot_exceed_twenty_percent():
    with pytest.raises(ValueError, match="no greater than 0.20"):
        AutomationSettings.from_config(_config(options_max_equity_fraction=0.21))
```

- [ ] **Step 2: Add failing coordination tests**

```python
def test_reserved_covered_shares_cannot_be_sold(warmed_service):
    warmed_service.broker.position_values = {"AAPL": Decimal("32000")}
    warmed_service.broker.equity_lots = (
        EquityPosition("AAPL", Decimal("100"), Decimal("300"), Decimal("320")),
    )
    warmed_service.broker.option_orders = (
        OptionOpenOrder(
            "AAPL261002C00350000", "AAPL", "call", "sell_to_open",
            Decimal("1"), Decimal("0"), Decimal("350")
        ),
    )
    warmed_service.ratings["AAPL"] = "Sell"
    result = warmed_service.run_analysis_cycle(NOW)
    aapl = next(intent for intent in result.order_intents if intent.symbol == "AAPL")
    assert aapl.target_notional >= Decimal("32000")


def test_option_entry_is_suppressed_when_combined_risk_exceeds_limit(warmed_service):
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    warmed_service.broker.close_history = _aligned_history(Decimal("0.08"))
    result = warmed_service.manage_options(NOW)
    assert result.intents == ()
    assert result.suppressed_reason == "combined portfolio risk exceeds limit"


def test_dry_run_records_ticket_without_submitting(warmed_service):
    warmed_service.settings = replace(
        warmed_service.settings, options_enabled=True, options_auto_execute=False
    )
    warmed_service.broker.option_contract_values = {
        "AAPL": (_eligible_put("AAPL", NOW),),
    }
    result = warmed_service.manage_options(NOW)
    assert result.intents
    assert warmed_service.broker.submitted_options == []
```

Add these complete helpers above the tests and extend `FakeBroker` with
`equity_lots`, `option_positions`, `option_orders`, `option_contract_values`,
`close_history`, `submitted_options`, `wheel_positions_and_orders()`,
`option_contracts()`, `daily_closes()`, and `submit_option_idempotent()`:

```python
def _eligible_put(symbol, now):
    return OptionContract(
        symbol=f"{symbol}261002P00300000", underlying=symbol, kind="put",
        strike=Decimal("300"), expiration=date(2026, 10, 2),
        delta=Decimal("-0.20"), bid=Decimal("3.00"), ask=Decimal("3.20"),
        open_interest=Decimal("500"), quote_time=now,
    )


def _aligned_history(change):
    start = date(2026, 7, 1)
    result = {}
    for symbol in ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"):
        price = Decimal("100")
        rows = [(start, price)]
        for index in range(40):
            signed = change if index % 2 == 0 else -change
            price *= Decimal("1") + signed
            rows.append((start + timedelta(days=index + 1), price))
        result[symbol] = tuple(rows)
    return result


def _fake_wheel_positions_and_orders(self):
    return self.equity_lots, self.option_positions, self.option_orders


def _fake_option_contracts(self, underlying, kind, now):
    return self.option_contract_values.get(underlying, ())


def _fake_submit_option(self, spec):
    self.submitted_options.append(spec)
    return f"option-{spec.symbol}"
```

Initialize every new fake field to an empty tuple/dict, assign the three helper
methods on `FakeBroker`, and make `daily_closes()` return `close_history`. The
helpers must not bypass any production policy function.

- [ ] **Step 3: Run focused tests and confirm failures**

Run: `.venv/bin/python -m pytest -q tests/test_automation_config.py tests/test_automation_cycle.py tests/test_scheduler.py`

Expected: failures identify missing settings, reservation-aware reconciliation,
and `manage_options()`.

- [ ] **Step 4: Implement the shared cycle sequence**

Add these defaults and environment overrides exactly:

```python
"options_enabled": False,
"options_auto_execute": False,
"options_max_equity_fraction": 0.20,
"options_entry_time_et": "10:00",
"options_earnings_path": os.path.join(_TRADINGAGENTS_HOME, "automation", "earnings.json"),
"live_options_ack": "",
```

In `manage_options()`:

1. Return immediately when options are disabled or the equity market is closed.
2. Read account, equity positions, option positions, all open orders, latest
   prices, fresh decisions, daily closes, and earnings cache before planning.
3. Rebuild reservations from broker state and reject internally inconsistent
   coverage or collateral.
4. Update each underlying's persisted broker phase. Suppress every new entry in
   `settling`, but continue validated risk-reducing exits.
5. Plan validated buy-to-close profit exits before new entries. Cancel an
   unfilled wheel-owned option order only when it is at least 10 minutes old; a
   cancellation failure blocks new exposure for that cycle.
6. Require 10:00 New York time, no daily marker, fresh decisions, no same-symbol
   equity order, and wheel exposure no greater than 20% for new entries.
7. Calculate combined delta exposure and call `scale_equity_targets()`; reject a
   proposed option whose post-trade volatility exceeds 15%, whose gross exposure
   exceeds 2.0, or whose collateral exceeds cash/options buying power.
8. Persist every intent. With auto-execution false, mark it `planned`; otherwise
   submit idempotently and record the Alpaca order ID.
9. Mark the daily entry date only after a new-entry ticket is persisted. Do not
   mark it for monitoring-only cycles or failed planning.

In the existing equity section of `run_analysis_cycle()`, when options are
enabled, read the same broker wheel snapshot before target reconciliation. Convert
covered-share reservations to minimum long notionals using current prices, pass
those minimums to `reconcile_targets()`, pass open-option delta exposure to
`scale_equity_targets()`, and subtract short-put collateral from cash available
for new equity buys. A reservation or risk-read failure returns a suppressed
`CycleResult` and submits neither equity nor option orders.

Call `manage_options()` as a third 15-minute scheduler task. Preserve the existing
analysis and position task deadlines and leases.

- [ ] **Step 5: Add fail-closed regression tests**

```python
@pytest.mark.parametrize("failure", [
    "options_buying_power", "option_positions", "option_orders",
    "option_quote", "option_delta", "earnings_cache", "daily_closes",
])
def test_option_read_failure_submits_nothing(warmed_service, failure):
    warmed_service.broker.option_failure = failure
    result = warmed_service.manage_options(NOW)
    assert result.submitted_order_ids == ()
    assert result.suppressed_reason


def test_scheduler_runs_options_on_fifteen_minute_deadline(scheduler):
    scheduler.run_once(NOW)
    scheduler.run_once(NOW + timedelta(minutes=14))
    scheduler.run_once(NOW + timedelta(minutes=15))
    assert scheduler.service.option_calls == [NOW, NOW + timedelta(minutes=15)]
```

- [ ] **Step 6: Run the integrated automation suite and commit**

Run: `.venv/bin/python -m pytest -q tests/test_risk.py tests/test_options.py tests/test_automation_config.py tests/test_automation_state.py tests/test_automation_cycle.py tests/test_scheduler.py tests/test_alpaca_execution.py`

Expected: all tests pass and existing equity-only tests remain unchanged in
behavior when `options_enabled` is false.

```bash
git add tradingagents/default_config.py tradingagents/automation.py tradingagents/allocation.py tradingagents/scheduler.py tests/test_env_overrides.py tests/test_automation_config.py tests/test_automation_cycle.py tests/test_scheduler.py
git commit -m "feat: coordinate equity and options automation"
```

---

### Task 7: Earnings Cache Refresh

**Files:**
- Create: `scripts/refresh_earnings.py`
- Create: `tests/test_refresh_earnings.py`

**Interfaces:**
- Produces `refresh_earnings(symbols, fetch, now) -> dict`, `write_earnings_cache(path, symbols, fetch, now) -> None`, and a CLI that reads the existing env-backed watchlist and atomically writes `options_earnings_path`.
- Cache shape is `{"source": "Wall Street Horizon", "retrieved_at": <aware ISO timestamp>, "symbols": {<symbol>: <ISO date>}}`.

- [ ] **Step 1: Write failing parser and atomicity tests**

```python
def test_refresh_requires_exact_watchlist_and_confirmed_future_dates():
    pages = {symbol: f"{symbol}'s next earnings date is CONFIRMED for Friday 12/11/2026" for symbol in SYMBOLS}
    payload = refresh_earnings(SYMBOLS, pages.__getitem__, NOW)
    assert payload["source"] == "Wall Street Horizon"
    assert payload["symbols"] == {symbol: "2026-12-11" for symbol in SYMBOLS}


def test_refresh_rejects_unconfirmed_or_past_date():
    with pytest.raises(ValueError, match="confirmed future earnings date"):
        refresh_earnings(("AAPL",), lambda symbol: "estimated 01/01/2026", NOW)


def test_failed_refresh_does_not_replace_existing_cache(tmp_path):
    target = tmp_path / "earnings.json"
    target.write_text('{"old": true}')
    with pytest.raises(OSError):
        write_earnings_cache(
            target, ("AAPL",),
            lambda symbol: (_ for _ in ()).throw(OSError("network")), NOW
        )
    assert target.read_text() == '{"old": true}'
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_refresh_earnings.py`

Expected: import fails because the script is absent.

- [ ] **Step 3: Implement the confirmed-date refresh**

Use `urllib.request.Request` with a fixed user agent, an explicit seven-symbol to
Wall Street Horizon page mapping, and a regular expression that accepts only an
explicit `CONFIRMED` date. Require every configured symbol to be supported and
returned exactly once. Write JSON to a sibling temporary file, `fsync`, then
replace the target. Log symbols and timestamps but never environment values.

- [ ] **Step 4: Run and commit**

Run: `.venv/bin/python -m pytest -q tests/test_refresh_earnings.py`

Expected: all tests pass.

```bash
git add scripts/refresh_earnings.py tests/test_refresh_earnings.py
git commit -m "feat: refresh wheel earnings calendar"
```

---

### Task 8: Documentation, Dry-Run Reporting, and Safe Deployment Artifacts

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `scripts/paper_trading_report.py`
- Modify: `tests/test_automation_config.py`
- Modify: `tests/test_paper_trading_report.py`
- Create: `deploy/com.tradingagents.earnings-refresh.plist.example`

**Interfaces:**
- Documents every new environment key without real credentials.
- Adds `format_report(account, positions, broker_orders, equity_intents, option_intents, risk_summary, now) -> str`.
- Daily report includes option positions, option intents, reserved collateral,
  covered shares, option delta exposure, combined forecast volatility, gross
  leverage, and suppression reasons.
- The plist example refreshes earnings before market open but is not installed or loaded.

- [ ] **Step 1: Add failing documentation and report tests**

```python
def test_env_example_documents_every_option_override():
    text = Path(".env.example").read_text()
    required = {
        "TRADINGAGENTS_OPTIONS_ENABLED",
        "TRADINGAGENTS_OPTIONS_AUTO_EXECUTE",
        "TRADINGAGENTS_OPTIONS_MAX_EQUITY_FRACTION",
        "TRADINGAGENTS_OPTIONS_ENTRY_TIME_ET",
        "TRADINGAGENTS_OPTIONS_EARNINGS_PATH",
        "TRADINGAGENTS_LIVE_OPTIONS_ACK",
    }
    assert all(name in text for name in required)


def test_report_displays_wheel_risk_without_credentials(tmp_path):
    account = SimpleNamespace(status="ACTIVE", cash="100000", portfolio_value="120000")
    option_intents = [
        ("2026-09-04T14:00:00+00:00", "AAPL261002P00300000", "AAPL", "sell_to_open", "1", "3.10", "planned")
    ]
    risk = {
        "wheel_collateral": Decimal("30000"),
        "covered_shares": {"META": Decimal("100")},
        "option_delta_exposure": Decimal("6400"),
        "combined_forecast_volatility": Decimal("0.149"),
        "gross_leverage": Decimal("1.42"),
        "suppressed_reason": None,
    }
    report = format_report(account, [], [], [], option_intents, risk, NOW)
    assert "Wheel collateral" in report
    assert "Combined forecast volatility" in report
    assert "ALPACA_SECRET_KEY" not in report
```

- [ ] **Step 2: Run focused tests and confirm failures**

Run: `.venv/bin/python -m pytest -q tests/test_automation_config.py tests/test_paper_trading_report.py`

Expected: failures identify missing environment documentation and option report fields.

- [ ] **Step 3: Document setup and add read-only reporting**

Document that options do not guarantee profit, explain CSP assignment and covered
call upside caps, list exact thresholds, show dry-run commands, and state that
`TRADINGAGENTS_OPTIONS_AUTO_EXECUTE=false` produces tickets only. Include separate
paper and live acknowledgement descriptions without placing acknowledgement
values in `.env.example` as enabled defaults.

Add an unloaded plist example whose program arguments call the repository Python
and `scripts/refresh_earnings.py`, with a weekday 08:30 America/New_York calendar
schedule. Do not run `launchctl` in this task.

- [ ] **Step 4: Run and commit**

Run: `.venv/bin/python -m pytest -q tests/test_automation_config.py tests/test_paper_trading_report.py`

Expected: all tests pass.

```bash
git add .env.example README.md scripts/paper_trading_report.py tests/test_automation_config.py tests/test_paper_trading_report.py deploy/com.tradingagents.earnings-refresh.plist.example
git commit -m "docs: add options wheel operations guide"
```

---

### Task 9: Full Verification and Open-Market Dry Run

**Files:**
- Modify only if a verified defect is found; return to the owning task's test-first cycle before changing code.

**Interfaces:**
- Produces test evidence and a read-only dry-run report; it does not enable automatic option execution or load a service.

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run static verification**

Run: `.venv/bin/python -m compileall -q tradingagents scripts cli`

Expected: exit code 0.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 3: Verify safe configuration without displaying secrets**

Run a Python check using `dotenv_values('.env')` that prints only the six options
settings, credential presence booleans, and configured Alpaca mode. Confirm:

```text
TRADINGAGENTS_OPTIONS_ENABLED=true
TRADINGAGENTS_OPTIONS_AUTO_EXECUTE=false
TRADINGAGENTS_OPTIONS_MAX_EQUITY_FRACTION=0.20
TRADINGAGENTS_ALPACA_MODE=paper
ALPACA_API_KEY_PRESENT=true
ALPACA_SECRET_KEY_PRESENT=true
```

- [ ] **Step 4: Refresh earnings and run an open-market dry cycle**

Run: `.venv/bin/python scripts/refresh_earnings.py`

Expected: exactly seven confirmed future dates and a retrieval timestamp less
than 24 hours old.

Run: `.venv/bin/python -m cli.main automate --once`

Expected: the report contains current option quotes, DTE, delta, open interest,
yield, score, strike, limit price, reservations, combined volatility, gross
leverage, and buying-power checks. It reports zero option submissions and zero
strategy cancellations.

- [ ] **Step 5: Stop at the activation gate**

Present the full verification totals and dry-run tickets to the user. Do not set
`TRADINGAGENTS_OPTIONS_AUTO_EXECUTE=true`, do not set a live acknowledgement, and
do not load or restart an options-capable service until the user gives a new,
explicit activation approval.
