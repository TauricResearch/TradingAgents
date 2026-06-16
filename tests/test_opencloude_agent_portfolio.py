from opencloude_agent.portfolio import PaperPortfolio


def test_paper_portfolio_starts_with_ten_thousand_usd():
    portfolio = PaperPortfolio()

    assert portfolio.cash_usd == 10000.0
    assert portfolio.to_dict()["total_value_usd"] == 10000.0


def test_paper_portfolio_simulates_buy_and_sell():
    portfolio = PaperPortfolio()

    cost = portfolio.simulate_buy("AAPL", 10, 100)
    assert cost == 1000.0
    assert portfolio.positions["AAPL"] == 10
    assert portfolio.cash_usd == 9000.0

    proceeds = portfolio.simulate_sell("AAPL", 4, 120)
    assert proceeds == 480.0
    assert portfolio.positions["AAPL"] == 6
    assert portfolio.cash_usd == 9480.0
    assert portfolio.to_dict({"AAPL": 120})["total_value_usd"] == 10200.0
