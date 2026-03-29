import pytest
from datetime import date, timedelta


def _iso_days_out(days: int) -> str:
    """Expiration string relative to today so DTE assertions never go stale."""
    return (date.today() + timedelta(days=days)).isoformat()


MOCK_EXPIRATIONS_RESPONSE = {
    "expirations": {
        "date": [_iso_days_out(d) for d in (7, 14, 21, 28, 45)]
    }
}

MOCK_SINGLE_EXPIRATION_RESPONSE = {
    "expirations": {
        "date": _iso_days_out(21)
    }
}

MOCK_CHAIN_RESPONSE = {
    "options": {
        "option": [
            {
                "symbol": "AAPL260417C00170000",
                "underlying": "AAPL",
                "option_type": "call",
                "strike": 170.0,
                "expiration_date": _iso_days_out(20),
                "bid": 5.10,
                "ask": 5.30,
                "last": 5.20,
                "volume": 1234,
                "open_interest": 5678,
                "greeks": {
                    "delta": 0.55,
                    "gamma": 0.04,
                    "theta": -0.08,
                    "vega": 0.25,
                    "rho": 0.03,
                    "phi": -0.02,
                    "bid_iv": 0.28,
                    "mid_iv": 0.29,
                    "ask_iv": 0.30,
                    "smv_vol": 0.285,
                    "updated_at": "2026-04-01 12:00:00"
                }
            },
            {
                "symbol": "AAPL260417P00170000",
                "underlying": "AAPL",
                "option_type": "put",
                "strike": 170.0,
                "expiration_date": _iso_days_out(20),
                "bid": 3.40,
                "ask": 3.60,
                "last": 3.50,
                "volume": 890,
                "open_interest": 2345,
                "greeks": {
                    "delta": -0.45,
                    "gamma": 0.04,
                    "theta": -0.07,
                    "vega": 0.25,
                    "rho": -0.02,
                    "phi": 0.02,
                    "bid_iv": 0.27,
                    "mid_iv": 0.28,
                    "ask_iv": 0.29,
                    "smv_vol": 0.280,
                    "updated_at": "2026-04-01 12:00:00"
                }
            },
            {
                "symbol": "AAPL260417C00175000",
                "underlying": "AAPL",
                "option_type": "call",
                "strike": 175.0,
                "expiration_date": _iso_days_out(20),
                "bid": 2.80,
                "ask": 3.00,
                "last": 2.90,
                "volume": 567,
                "open_interest": 1234,
                "greeks": {
                    "delta": 0.40,
                    "gamma": 0.05,
                    "theta": -0.09,
                    "vega": 0.24,
                    "rho": 0.02,
                    "phi": -0.01,
                    "bid_iv": 0.30,
                    "mid_iv": 0.31,
                    "ask_iv": 0.32,
                    "smv_vol": 0.305,
                    "updated_at": "2026-04-01 12:00:00"
                }
            }
        ]
    }
}

MOCK_CHAIN_NO_GREEKS_RESPONSE = {
    "options": {
        "option": [
            {
                "symbol": "AAPL260417C00170000",
                "underlying": "AAPL",
                "option_type": "call",
                "strike": 170.0,
                "expiration_date": _iso_days_out(20),
                "bid": 5.10,
                "ask": 5.30,
                "last": 5.20,
                "volume": 1234,
                "open_interest": 5678,
                "greeks": None
            }
        ]
    }
}

MOCK_SINGLE_CONTRACT_RESPONSE = {
    "options": {
        "option": {
            "symbol": "AAPL260417C00170000",
            "underlying": "AAPL",
            "option_type": "call",
            "strike": 170.0,
            "expiration_date": _iso_days_out(20),
            "bid": 5.10,
            "ask": 5.30,
            "last": 5.20,
            "volume": 1234,
            "open_interest": 5678,
            "greeks": {
                "delta": 0.55, "gamma": 0.04, "theta": -0.08,
                "vega": 0.25, "rho": 0.03, "phi": -0.02,
                "bid_iv": 0.28, "mid_iv": 0.29, "ask_iv": 0.30,
                "smv_vol": 0.285, "updated_at": "2026-04-01 12:00:00"
            }
        }
    }
}
