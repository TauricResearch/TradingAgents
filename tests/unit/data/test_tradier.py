"""Comprehensive unit tests for Tradier data layer (Phase 1 requirements).

Covers: DATA-01 (chain retrieval), DATA-02 (expirations), DATA-03 (Greeks present),
DATA-04 (IV present), DATA-05 (DTE filtering), DATA-08 (vendor registration),
plus edge cases (no Greeks, single contract, single expiration, rate limits,
caching, sandbox URL).

All tests use mocked API responses -- no real Tradier calls are made.
"""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from conftest import (
    _iso_days_out,
    MOCK_EXPIRATIONS_RESPONSE,
    MOCK_SINGLE_EXPIRATION_RESPONSE,
    MOCK_CHAIN_RESPONSE,
    MOCK_CHAIN_NO_GREEKS_RESPONSE,
    MOCK_SINGLE_CONTRACT_RESPONSE,
)
from tradingagents.dataflows.tradier import (
    get_options_expirations,
    get_options_chain,
    get_options_chain_structured,
    clear_options_cache,
    OptionsChain,
    OptionsContract,
)
from tradingagents.dataflows.tradier_common import (
    TradierRateLimitError,
    get_base_url,
    make_tradier_request,
)
from tradingagents.dataflows.interface import (
    TOOLS_CATEGORIES,
    VENDOR_LIST,
    VENDOR_METHODS,
)


# ---------------------------------------------------------------------------
# TestGetExpirations (DATA-02)
# ---------------------------------------------------------------------------


class TestGetExpirations:
    """DATA-02: Options expirations retrieval with DTE filtering."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_expirations_filtered_by_dte(self, mock_request):
        mock_request.return_value = MOCK_EXPIRATIONS_RESPONSE
        result = get_options_expirations("AAPL", 0, 50)
        assert isinstance(result, list)
        today = date.today()
        for d in result:
            from datetime import datetime
            exp = datetime.strptime(d, "%Y-%m-%d").date()
            dte = (exp - today).days
            assert 0 <= dte <= 50, f"Date {d} has DTE {dte}, outside 0-50 range"

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_expirations_returns_list_of_strings(self, mock_request):
        mock_request.return_value = MOCK_EXPIRATIONS_RESPONSE
        result = get_options_expirations("AAPL", 0, 50)
        assert len(result) == 5
        for d in result:
            assert isinstance(d, str)

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_single_expiration_normalized(self, mock_request):
        """Pitfall 5: single-item response comes as string, not list."""
        mock_request.return_value = MOCK_SINGLE_EXPIRATION_RESPONSE
        result = get_options_expirations("AAPL", 0, 50)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == _iso_days_out(21)

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_expirations_narrow_dte_filter(self, mock_request):
        mock_request.return_value = MOCK_EXPIRATIONS_RESPONSE
        # Only dates between 10 and 25 DTE should pass
        result = get_options_expirations("AAPL", 10, 25)
        today = date.today()
        for d in result:
            from datetime import datetime
            exp = datetime.strptime(d, "%Y-%m-%d").date()
            dte = (exp - today).days
            assert 10 <= dte <= 25


# ---------------------------------------------------------------------------
# TestGetOptionsChain (DATA-01)
# ---------------------------------------------------------------------------


class TestGetOptionsChain:
    """DATA-01: Options chain retrieval with correct structure."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_chain_structure(self, mock_request):
        mock_request.side_effect = [
            MOCK_EXPIRATIONS_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        assert chain.underlying == "AAPL"
        assert len(chain.contracts) > 0

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_chain_contract_values(self, mock_request):
        mock_request.side_effect = [
            MOCK_EXPIRATIONS_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        c = chain.contracts[0]
        assert c.bid == 5.10
        assert c.volume == 1234
        assert c.open_interest == 5678

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_single_contract_normalization(self, mock_request):
        """Pitfall 2: single contract comes as dict, not list."""
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_SINGLE_CONTRACT_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        assert len(chain.contracts) == 1
        assert chain.contracts[0].symbol == "AAPL260417C00170000"

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_chain_string_format(self, mock_request):
        """get_options_chain returns string for LLM consumption."""
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        result = get_options_chain("AAPL")
        assert isinstance(result, str)
        assert "AAPL" in result


# ---------------------------------------------------------------------------
# TestGreeksPresent (DATA-03)
# ---------------------------------------------------------------------------


class TestGreeksPresent:
    """DATA-03: Greeks fields populated when present in API response."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_greeks_values(self, mock_request):
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        c = chain.contracts[0]
        assert c.delta == 0.55
        assert c.gamma == 0.04
        assert c.theta == -0.08
        assert c.vega == 0.25
        assert c.rho == 0.03
        assert c.greeks_updated_at == "2026-04-01 12:00:00"


# ---------------------------------------------------------------------------
# TestGreeksAbsent (Pitfall 1)
# ---------------------------------------------------------------------------


class TestGreeksAbsent:
    """Pitfall 1: Greeks null in response should not crash."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_no_greeks_yields_none(self, mock_request):
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_NO_GREEKS_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        c = chain.contracts[0]
        assert c.delta is None
        assert c.gamma is None
        assert c.theta is None
        assert c.vega is None
        assert c.rho is None
        assert c.greeks_updated_at is None

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_no_greeks_no_exception(self, mock_request):
        """Parsing should succeed without raising."""
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_NO_GREEKS_RESPONSE,
        ]
        # Should not raise
        chain = get_options_chain_structured("AAPL")
        assert len(chain.contracts) == 1


# ---------------------------------------------------------------------------
# TestIVPresent (DATA-04)
# ---------------------------------------------------------------------------


class TestIVPresent:
    """DATA-04: IV fields populated when present in API response."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_iv_values(self, mock_request):
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        chain = get_options_chain_structured("AAPL")
        c = chain.contracts[0]
        assert c.bid_iv == 0.28
        assert c.mid_iv == 0.29
        assert c.ask_iv == 0.30
        assert c.smv_vol == 0.285


# ---------------------------------------------------------------------------
# TestDTEFilter (DATA-05)
# ---------------------------------------------------------------------------


class TestDTEFilter:
    """DATA-05: DTE-based filtering on OptionsChain."""

    def test_filter_by_dte_range(self):
        today = date.today()
        contracts = [
            OptionsContract(
                symbol=f"TEST{i}", underlying="TEST", option_type="call",
                strike=100.0 + i * 5,
                expiration_date=(today + timedelta(days=dte)).isoformat(),
                bid=1.0, ask=1.5, last=1.25, volume=100, open_interest=500,
            )
            for i, dte in enumerate([5, 15, 25, 35, 55])
        ]
        chain = OptionsChain(
            underlying="TEST",
            fetch_timestamp="2026-01-01T00:00:00",
            expirations=sorted({c.expiration_date for c in contracts}),
            contracts=contracts,
        )
        filtered = chain.filter_by_dte(10, 30)
        # Only 15 and 25 DTE should remain
        assert len(filtered.contracts) == 2
        for c in filtered.contracts:
            from datetime import datetime
            exp = datetime.strptime(c.expiration_date, "%Y-%m-%d").date()
            dte = (exp - today).days
            assert 10 <= dte <= 30

    def test_filter_updates_expirations_list(self):
        today = date.today()
        exp_10 = (today + timedelta(days=10)).isoformat()
        exp_40 = (today + timedelta(days=40)).isoformat()
        contracts = [
            OptionsContract(
                symbol="A", underlying="TEST", option_type="call",
                strike=100.0, expiration_date=exp_10,
                bid=1.0, ask=1.5, last=1.25, volume=100, open_interest=500,
            ),
            OptionsContract(
                symbol="B", underlying="TEST", option_type="call",
                strike=100.0, expiration_date=exp_40,
                bid=1.0, ask=1.5, last=1.25, volume=100, open_interest=500,
            ),
        ]
        chain = OptionsChain(
            underlying="TEST",
            fetch_timestamp="2026-01-01T00:00:00",
            expirations=[exp_10, exp_40],
            contracts=contracts,
        )
        filtered = chain.filter_by_dte(5, 20)
        assert exp_10 in filtered.expirations
        assert exp_40 not in filtered.expirations


# ---------------------------------------------------------------------------
# TestVendorRegistration (DATA-08)
# ---------------------------------------------------------------------------


class TestVendorRegistration:
    """DATA-08: Tradier registered in vendor routing system."""

    def test_tradier_in_vendor_list(self):
        assert "tradier" in VENDOR_LIST

    def test_options_chain_in_tools_categories(self):
        assert "options_chain" in TOOLS_CATEGORIES
        tools = TOOLS_CATEGORIES["options_chain"]["tools"]
        assert "get_options_chain" in tools
        assert "get_options_expirations" in tools

    def test_get_options_chain_in_vendor_methods(self):
        assert "get_options_chain" in VENDOR_METHODS
        assert "tradier" in VENDOR_METHODS["get_options_chain"]

    def test_get_options_expirations_in_vendor_methods(self):
        assert "get_options_expirations" in VENDOR_METHODS
        assert "tradier" in VENDOR_METHODS["get_options_expirations"]


# ---------------------------------------------------------------------------
# TestRateLimitDetection
# ---------------------------------------------------------------------------


class TestRateLimitDetection:
    """Rate limit detection raises TradierRateLimitError."""

    @patch("tradingagents.dataflows.tradier_common.get_api_key", return_value="test-key")
    @patch("tradingagents.dataflows.tradier_common.requests.get")
    def test_http_429_raises(self, mock_get, mock_key):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_get.return_value = mock_response
        with pytest.raises(TradierRateLimitError, match="429"):
            make_tradier_request("/v1/markets/options/chains")

    @patch("tradingagents.dataflows.tradier_common.get_api_key", return_value="test-key")
    @patch("tradingagents.dataflows.tradier_common.requests.get")
    def test_ratelimit_available_zero_raises(self, mock_get, mock_key):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-Ratelimit-Available": "0",
            "X-Ratelimit-Expiry": "1700000000",
        }
        mock_get.return_value = mock_response
        with pytest.raises(TradierRateLimitError, match="exhausted"):
            make_tradier_request("/v1/markets/options/chains")


# ---------------------------------------------------------------------------
# TestSessionCache
# ---------------------------------------------------------------------------


class TestSessionCache:
    """Session cache avoids redundant API calls."""

    def setup_method(self):
        clear_options_cache()

    def teardown_method(self):
        clear_options_cache()

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_cache_hit_avoids_second_call(self, mock_request):
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            # No more responses -- second call should hit cache
        ]
        # First call
        get_options_chain_structured("AAPL")
        call_count_after_first = mock_request.call_count

        # Second call (should be cache hit)
        get_options_chain_structured("AAPL")
        assert mock_request.call_count == call_count_after_first

    @patch("tradingagents.dataflows.tradier.make_tradier_request_with_retry")
    def test_cache_clear_forces_new_call(self, mock_request):
        mock_request.side_effect = [
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
            # After cache clear:
            MOCK_SINGLE_EXPIRATION_RESPONSE,
            MOCK_CHAIN_RESPONSE,
        ]
        get_options_chain_structured("AAPL")
        call_count_before_clear = mock_request.call_count

        clear_options_cache()
        get_options_chain_structured("AAPL")
        assert mock_request.call_count > call_count_before_clear


# ---------------------------------------------------------------------------
# TestSandboxURL
# ---------------------------------------------------------------------------


class TestSandboxURL:
    """Sandbox URL configuration via TRADIER_SANDBOX env var."""

    @patch.dict("os.environ", {"TRADIER_SANDBOX": "true"})
    def test_sandbox_true_returns_sandbox_url(self):
        assert get_base_url() == "https://sandbox.tradier.com"

    @patch.dict("os.environ", {"TRADIER_SANDBOX": "false"})
    def test_sandbox_false_returns_production_url(self):
        assert get_base_url() == "https://api.tradier.com"

    @patch.dict("os.environ", {}, clear=True)
    def test_unset_returns_production_url(self):
        assert get_base_url() == "https://api.tradier.com"
