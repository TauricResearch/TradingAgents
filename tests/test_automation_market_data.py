from automation.market_data import resolve_data_symbol


def test_resolve_data_symbol_defaults_to_requested_ticker():
    symbol = resolve_data_symbol("CFIETFIPSA.SN")
    assert symbol.requested == "CFIETFIPSA.SN"
    assert symbol.data_symbol == "CFIETFIPSA.SN"
    assert symbol.display_name == "CFIETFIPSA.SN"


def test_resolve_data_symbol_uses_object_alias():
    symbol = resolve_data_symbol(
        "CFIETFIPSA.SN",
        {"CFIETFIPSA.SN": {"data_symbol": "CFIIPSA.SN", "display_name": "ETF Singular IPSA"}},
    )
    assert symbol.data_symbol == "CFIIPSA.SN"
    assert symbol.display_name == "ETF Singular IPSA"


def test_resolve_data_symbol_uses_string_alias():
    symbol = resolve_data_symbol("A", {"A": "B"})
    assert symbol.data_symbol == "B"
