"""Invalid exported amounts must fail before they become decision-agent context."""

import json

import pytest
from pydantic import ValidationError

from tradingagents.portfolio import PortfolioContext, load_portfolio


def _book_with(field, amount):
    book = {"positions": [{"ticker": "AAPL", "quantity": 5}]}
    target = book if field == "cash" else book["positions"][0]
    target[field] = amount
    return book


@pytest.mark.unit
@pytest.mark.parametrize("field", ["cash", "quantity", "average_price"])
@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
def test_programmatic_portfolio_rejects_nonfinite_amounts(field, amount):
    with pytest.raises(ValidationError, match="finite number"):
        PortfolioContext.model_validate(_book_with(field, amount))


@pytest.mark.unit
@pytest.mark.parametrize("field", ["cash", "quantity", "average_price"])
@pytest.mark.parametrize("literal", [
    "NaN", "Infinity", "-Infinity", "1e400", '"NaN"', '"Infinity"', '"-Infinity"',
])
def test_portfolio_file_rejects_nonfinite_amounts(tmp_path, field, literal):
    path = tmp_path / "portfolio.json"
    # Cover JSON numbers that overflow as well as exports containing numeric strings.
    path.write_text(json.dumps(_book_with(field, "AMOUNT")).replace('"AMOUNT"', literal),
                    encoding="utf-8")

    with pytest.raises(ValueError, match="portfolio file .* is not usable:.*") as exc:
        load_portfolio(path)

    assert "finite number" in str(exc.value)
    assert field in str(exc.value)


@pytest.mark.unit
def test_finite_portfolio_preserves_short_positions_and_optional_amounts(tmp_path):
    book = {"cash": "-250.5", "positions": [
        {"ticker": "AAPL", "quantity": "-2.5", "average_price": "150.25"},
        {"ticker": "MSFT", "quantity": 0, "average_price": None},
    ]}
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(book), encoding="utf-8")

    portfolio = load_portfolio(path)

    assert portfolio.cash == -250.5
    assert portfolio.position_in("AAPL").quantity == -2.5
    assert portfolio.position_in("AAPL").average_price == 150.25
    assert portfolio.position_in("MSFT").quantity == 0
    assert portfolio.position_in("MSFT").average_price is None
    assert "Current position in AAPL: -2.5 units, average price 150.25" in portfolio.render("AAPL")
