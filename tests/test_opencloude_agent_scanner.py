from opencloude_agent.opportunity_scanner import OpportunityScanner


def test_opportunity_scanner_limits_candidates():
    scanner = OpportunityScanner(max_candidates=1)

    opportunities = scanner.scan(
        {
            "AAPL": {
                "close": 200,
                "volume": 10_000_000,
                "return_20d": 0.10,
                "benchmark_return_20d": 0.02,
            },
            "MSFT": {
                "close": 400,
                "volume": 5_000_000,
                "return_20d": 0.03,
                "benchmark_return_20d": 0.02,
            },
        }
    )

    assert len(opportunities) == 1
    assert opportunities[0].ticker == "AAPL"
