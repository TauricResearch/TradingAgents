"""Broker CSV exports read into a portfolio."""

import pytest

from webui.importers import parse_positions_csv

pytestmark = pytest.mark.unit


# Schwab's "Positions" export: an account line above the header, money written
# for a person, "--" where a field does not apply, and cash and total rows
# mixed in with the holdings.
SCHWAB = '''"Positions for account Individual ...123 as of 04:15 PM ET, 2026/10/02"

"Symbol","Description","Quantity","Price","Price Change %","Market Value","Cost Basis","Gain/Loss %","Security Type"
"AAPL","APPLE INC","100","$230.00","0.52%","$23,000.00","$15,000.00","53.33%","Equity"
"NVDA","NVIDIA CORP","40","$178.50","-1.2%","$7,140.00","$4,000.00","78.5%","Equity"
"AAPL 01/17/2026 200.00 C","CALL APPLE INC","2","$32.10","--","$6,420.00","$4,100.00","56.6%","Option"
"Cash & Cash Investments","--","--","--","--","$25,431.18","--","--","Cash and Money Market"
"Account Total","--","--","--","--","$61,991.18","--","--","--"

"Important: The information provided is for general informational purposes."
'''


def test_schwab_positions_and_cash():
    result = parse_positions_csv(SCHWAB)
    book = result.portfolio

    assert [p.ticker for p in book.positions] == ["AAPL", "NVDA"]
    assert book.positions[0].quantity == 100
    # Average price is the cost basis over the quantity, not the market price.
    assert book.positions[0].average_price == pytest.approx(150.0)
    assert book.positions[1].average_price == pytest.approx(100.0)
    assert book.cash == pytest.approx(25431.18)
    assert book.currency == "USD"


def test_options_row_is_skipped_and_named():
    result = parse_positions_csv(SCHWAB)
    assert not any("01/17/2026" in p.ticker for p in result.portfolio.positions)
    assert any("options contract" in note for note in result.skipped)


def test_account_total_is_not_a_position():
    result = parse_positions_csv(SCHWAB)
    assert "ACCOUNT TOTAL" not in [p.ticker for p in result.portfolio.positions]


def test_multiple_accounts_blend_into_one_book():
    """Two accounts holding the same symbol make one position at a blended cost."""
    csv_text = (
        '"Positions for account Brokerage ...111"\n'
        '"Symbol","Quantity","Market Value","Cost Basis"\n'
        '"AAPL","100","$23,000.00","$10,000.00"\n'
        '"Cash & Cash Investments","--","$1,000.00","--"\n'
        '\n'
        '"Positions for account Roth IRA ...222"\n'
        '"Symbol","Quantity","Market Value","Cost Basis"\n'
        '"AAPL","100","$23,000.00","$20,000.00"\n'
        '"Cash & Cash Investments","--","$500.00","--"\n'
    )
    book = parse_positions_csv(csv_text).portfolio

    assert len(book.positions) == 1
    assert book.positions[0].quantity == 200
    assert book.positions[0].average_price == pytest.approx(150.0)   # (10k + 20k) / 200
    assert book.cash == pytest.approx(1500.0)


def test_missing_cost_basis_leaves_average_price_unset():
    """A withheld cost basis must not read as an entry price of zero."""
    csv_text = (
        '"Symbol","Quantity","Cost Basis"\n'
        '"AAPL","100","--"\n'
    )
    result = parse_positions_csv(csv_text)

    assert result.portfolio.positions[0].average_price is None
    assert any("no cost basis" in w for w in result.warnings)


def test_average_cost_column_is_used_when_there_is_no_basis():
    csv_text = (
        '"Symbol","Quantity","Average Cost"\n'
        '"MSFT","50","$300.00"\n'
    )
    book = parse_positions_csv(csv_text).portfolio
    assert book.positions[0].average_price == pytest.approx(300.0)


def test_short_position_keeps_its_sign():
    csv_text = (
        '"Symbol","Quantity","Cost Basis"\n'
        '"TSLA","-25","($5,000.00)"\n'
    )
    book = parse_positions_csv(csv_text).portfolio
    assert book.positions[0].quantity == -25
    # The sign lives on the quantity; a price per unit stays positive.
    assert book.positions[0].average_price == pytest.approx(200.0)


def test_no_cash_row_leaves_cash_unset_and_says_so():
    result = parse_positions_csv('"Symbol","Quantity"\n"AAPL","10"\n')
    assert result.portfolio.cash is None
    assert any("no cash row" in w for w in result.warnings)


def test_a_file_without_a_positions_table_is_rejected():
    result = parse_positions_csv("some,unrelated,csv\n1,2,3\n")
    assert result.is_empty
    assert any("no positions table" in w for w in result.warnings)


def test_empty_file():
    assert parse_positions_csv("").is_empty


def test_fidelity_column_names():
    """A different broker's header still parses; only the names differ."""
    csv_text = (
        "Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value,Average Cost Basis\n"
        "X123,Individual,GOOGL,ALPHABET INC,30,$180.00,$5400.00,$120.00\n"
    )
    book = parse_positions_csv(csv_text).portfolio
    assert book.positions[0].ticker == "GOOGL"
    assert book.positions[0].quantity == 30
    assert book.positions[0].average_price == pytest.approx(120.0)


def test_the_disclaimer_footer_is_not_reported_as_a_skipped_position():
    """Schwab's legal footer is one cell of prose; it belongs in neither list."""
    result = parse_positions_csv(SCHWAB)
    assert not any("Important" in note for note in result.skipped)
    assert len(result.skipped) == 1          # the options contract, and nothing else
