"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)`` while the tool takes a
``ticker``, tricking the LLM into hallucinating free-text query calls.
"""
import inspect

import pytest

import tradingagents.agents.analysts.news_analyst as na
from tradingagents.agents.utils.agent_utils import get_macro_guidance
from tradingagents.agents.utils.news_data_tools import get_news


@pytest.mark.unit
def test_get_news_takes_ticker_not_query():
    arg_names = set(get_news.args.keys())
    assert "ticker" in arg_names
    assert "query" not in arg_names


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature():
    src = inspect.getsource(na)
    assert "get_news(ticker, start_date, end_date)" in src
    assert "get_news(query" not in src


@pytest.mark.unit
class TestMacroGuidance:
    """A Bursa run must be steered to Malaysia's macro series, not the Fed's.

    The prompt previously hardcoded US aliases for every instrument, so the
    macro half of a KLSE report was grounded in the wrong economy.
    """

    def test_klse_ticker_leads_with_bnm_series(self):
        guidance = get_macro_guidance("7052.KL")
        assert "'opr'" in guidance
        assert "'usd_myr'" in guidance
        assert "Bank Negara" in guidance

    def test_klse_guidance_disambiguates_the_policy_rate(self):
        guidance = get_macro_guidance("1155.KL")
        assert "NOT the US fed funds rate" in guidance

    def test_klse_guidance_states_the_ringgit_direction(self):
        """A rising USD/MYR is a weaker ringgit — easy to read backwards."""
        guidance = get_macro_guidance("1155.KL")
        assert "WEAKER ringgit" in guidance

    def test_klse_guidance_keeps_us_series_as_backdrop(self):
        """US rates drive foreign flows into Bursa, so they stay available."""
        guidance = get_macro_guidance("7052.KL")
        assert "fed_funds_rate" in guidance
        assert "backdrop" in guidance

    def test_non_my_ticker_keeps_the_us_guidance(self):
        guidance = get_macro_guidance("SPY")
        assert "FRED" in guidance
        assert "Bank Negara" not in guidance

    def test_suffix_match_is_case_insensitive(self):
        assert "Bank Negara" in get_macro_guidance("7052.kl")

    def test_guidance_is_interpolated_into_the_prompt(self):
        src = inspect.getsource(na)
        assert "{macro_guidance}" in src
        # The hardcoded US-only list must be gone from the prompt itself.
        assert "actual data from FRED (e.g. 'cpi'" not in src
