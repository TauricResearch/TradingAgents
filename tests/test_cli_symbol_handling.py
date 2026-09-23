"""CLI symbol validation/classification must agree with the data path.

Regressions for #980 (validation rejected GC=F), #981 (BTCUSD misclassified as
stock), #982 (BTC-USDT accepted but unpriceable on Yahoo).
"""
import pytest

import cli.run as cli_run
from cli.models import AssetType
from cli.prompts import detect_asset_type, is_valid_ticker_input, normalize_ticker_symbol
from tradingagents.dataflows.symbols import normalize_symbol


# --- #982: stablecoin-quoted crypto normalizes to Yahoo's -USD pair ---
@pytest.mark.parametrize("raw,expected", [
    ("BTCUSD", "BTC-USD"),
    ("BTCUSDT", "BTC-USD"),
    ("BTC-USDT", "BTC-USD"),
    ("BTC-USDC", "BTC-USD"),
    ("ethusdt", "ETH-USD"),
    # non-crypto must be untouched
    ("AAPL", "AAPL"),
    ("GC=F", "GC=F"),
    ("600519.SS", "600519.SS"),
    ("EURUSD", "EURUSD=X"),
])
def test_normalize_symbol_crypto_and_passthrough(raw, expected):
    assert normalize_symbol(raw) == expected


# --- #980: validation accepts Yahoo futures/forex symbols ---
@pytest.mark.parametrize("value,ok", [
    ("GC=F", True),
    ("EURUSD=X", True),
    ("AAPL", True),
    ("0700.HK", True),
    ("^GSPC", True),
    ("", True),                 # empty -> defaults to SPY downstream
    ("bad symbol!", False),     # space + '!' rejected
    ("A" * 40, False),          # too long
])
def test_ticker_input_validation(value, ok):
    assert is_valid_ticker_input(value) is ok


# --- #981/#982: asset-type classified on the canonical symbol ---
@pytest.mark.parametrize("raw,expected", [
    ("BTCUSD", AssetType.CRYPTO),
    ("BTC-USDT", AssetType.CRYPTO),
    ("BTC-USD", AssetType.CRYPTO),
    ("ETHUSD", AssetType.CRYPTO),
    ("AAPL", AssetType.STOCK),
    ("GC=F", AssetType.STOCK),
    ("600519.SS", AssetType.STOCK),
])
def test_detect_asset_type(raw, expected):
    assert detect_asset_type(raw) == expected


def test_cli_normalize_delegates_to_data_layer():
    # CLI must produce the same canonical symbol the data path will price.
    for raw in ("XAUUSD", "BTCUSD", "btc-usdt", "AAPL"):
        assert normalize_ticker_symbol(raw) == normalize_symbol(raw)


@pytest.mark.unit
def test_the_run_directory_cannot_escape_the_results_directory(tmp_path, monkeypatch):
    """Every other path that interpolates a ticker validates it first; the CLI's
    own results tree did not, so a ticker of '..' wrote a level up."""

    with pytest.raises(ValueError):
        cli_run._run_directory({"results_dir": str(tmp_path)}, "..", "2026-09-01")

    ok = cli_run._run_directory({"results_dir": str(tmp_path)}, "NVDA", "2026-09-01")
    assert str(ok).startswith(str(tmp_path))
