import pytest

from tradingagents.execution import (
    DryRunExecutor,
    ExecutionOrder,
    execute_orders,
)


def test_dry_run_executor_records_no_external_side_effects():
    executor = DryRunExecutor()
    order = ExecutionOrder(ticker="AAPL", action="buy", quantity=2)

    results = executor.execute([order])

    assert results[0].status == "planned"
    assert results[0].order == order
    assert executor.submitted_orders == []


def test_execution_order_rejects_zero_quantity():
    with pytest.raises(ValueError, match="quantity"):
        ExecutionOrder(ticker="AAPL", action="buy", quantity=0)


def test_execution_order_rejects_unsupported_action():
    with pytest.raises(ValueError, match="action"):
        ExecutionOrder(ticker="AAPL", action="hold", quantity=1)


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), float("-inf")])
def test_execution_order_rejects_non_finite_quantity(quantity):
    with pytest.raises(ValueError, match="quantity"):
        ExecutionOrder(ticker="AAPL", action="buy", quantity=quantity)


def test_execute_orders_dry_run_returns_planned_status():
    orders = [
        ExecutionOrder(ticker="AAPL", action="buy", quantity=2),
        ExecutionOrder(ticker="MSFT", action="sell", quantity=1),
    ]

    results = execute_orders(orders, dry_run=True)

    assert [result.status for result in results] == ["planned", "planned"]
