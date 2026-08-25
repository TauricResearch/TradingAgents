from cli import main as cli_main
from tradingagents.discovery.stock_discovery import StockCandidate


def _candidate(symbol):
    return StockCandidate(
        symbol=symbol,
        score=80.0,
        latest_price=100.0,
        return_percent=4.0,
        relative_volume=2.0,
        volatility_percent=2.0,
        reasons=("momentum positivo (+4.0% en el periodo)",),
    )


def test_prompt_for_discovery_ticker_returns_selected_candidate(monkeypatch):
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *args, **kwargs: "2")
    monkeypatch.setattr(cli_main, "select_discovery_regions", lambda: ["us", "europe"])

    selected = cli_main.prompt_for_discovery_ticker(
        discover_fn=lambda **kwargs: [_candidate("AAPL"), _candidate("SAP.DE")]
    )

    assert selected == "SAP.DE"


def test_prompt_for_discovery_ticker_falls_back_to_manual_input(monkeypatch):
    monkeypatch.setattr(cli_main, "get_ticker", lambda: "MSFT")
    monkeypatch.setattr(cli_main, "select_discovery_regions", lambda: ["us"])

    selected = cli_main.prompt_for_discovery_ticker(discover_fn=lambda **kwargs: [])

    assert selected == "MSFT"


def test_prompt_for_discovery_ticker_passes_selected_region_symbols(monkeypatch):
    monkeypatch.setattr(cli_main, "select_discovery_regions", lambda: ["japan"])
    monkeypatch.setattr(cli_main.typer, "prompt", lambda *args, **kwargs: "1")
    calls = []

    def discover(**kwargs):
        calls.append(kwargs["symbols"])
        return [_candidate("7203.T")]

    selected = cli_main.prompt_for_discovery_ticker(discover_fn=discover)

    assert selected == "7203.T"
    assert calls == [cli_main.symbols_for_regions(["japan"])]