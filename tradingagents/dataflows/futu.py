"""Futu OpenD vendor implementation.

Futu requires the **OpenD** gateway daemon running locally with a logged-in
Futu account; the Python SDK talks to OpenD over a local TCP socket
(default 127.0.0.1:11111). Treat Futu strictly as a fallback vendor —
never block a run on its availability.

To activate: start OpenD, install futu-api, set ``futu_opend_host`` and
``futu_opend_port`` in DEFAULT_CONFIG (defaults provided), and append
``"futu"`` to a vendor list (e.g. ``"core_stock_apis": "yfinance, futu"``).

NOTE: Bodies are minimal stubs. ``_ctx`` handles connection + import failures
cleanly; the actual data-fetch + Markdown-formatting work is TODO. Futu
symbols are market-prefixed (e.g. "HK.00700", "US.AAPL") — callers must
translate the framework's ticker before passing it through.
"""

from .config import get_config
from .errors import DataVendorError


def _ctx():
    try:
        from futu import OpenQuoteContext  # type: ignore
    except ImportError as e:
        raise DataVendorError("futu-api not installed") from e
    cfg = get_config()
    try:
        return OpenQuoteContext(
            host=cfg.get("futu_opend_host", "127.0.0.1"),
            port=int(cfg.get("futu_opend_port", 11111)),
        )
    except Exception as e:
        raise DataVendorError(f"Cannot reach OpenD: {e}") from e


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Daily klines via ctx.request_history_kline(...).

    TODO: translate ``symbol`` to Futu's market-prefixed format and format the
    response into the same Markdown table shape as ``get_YFin_data_online``."""
    ctx = _ctx()
    try:
        raise DataVendorError("futu.get_stock_data: implementation pending")
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def get_options_chain(symbol: str, expiration: str = "") -> str:
    """Options chain via ctx.get_option_chain(...) then get_market_snapshot(...) for IV/greeks.

    TODO: implement and format to match ``yfinance_options.get_options_chain``."""
    ctx = _ctx()
    try:
        raise DataVendorError("futu.get_options_chain: implementation pending")
    finally:
        try:
            ctx.close()
        except Exception:
            pass
