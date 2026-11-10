import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from trader.prices import OFFICIAL, UNPRICED, lookup, normalise
from tradingagents.llm_clients.model_catalog import get_known_models

# openai_compatible, bedrock and chatgpt are left out: what they cost depends on the
# deployment or the plan, not on a public price list.
COVERED_PROVIDERS = (
    "openai", "anthropic", "google", "xai", "deepseek", "qwen", "qwen-cn", "glm", "glm-cn",
    "kimi", "minimax", "minimax-cn", "mistral", "groq", "nvidia", "ollama",
)


@pytest.mark.parametrize("provider", COVERED_PROVIDERS)
def test_every_catalog_model_is_priced_or_explained(provider):
    missing = [
        model_id
        for model_id in get_known_models()[provider]
        if model_id != "custom" and model_id not in OFFICIAL and model_id not in UNPRICED
    ]
    assert missing == []


def test_no_model_is_both_priced_and_unpriced():
    assert set(OFFICIAL) & set(UNPRICED) == set()


def test_every_unpriced_model_says_why():
    for model_id, reason in UNPRICED.items():
        assert reason.strip(), model_id


def test_prices_are_not_negative_and_output_is_not_cheaper_unless_explained():
    for model_id, price in OFFICIAL.items():
        assert price.input >= 0 and price.output >= 0, model_id
        assert price.output >= price.input or price.note, model_id


def test_every_price_names_its_page_and_the_day_it_was_read():
    for model_id, price in OFFICIAL.items():
        assert price.source.startswith("https://"), model_id
        read_on = date.fromisoformat(price.as_of)
        assert read_on.isoformat() == price.as_of, model_id
        assert read_on <= date.today(), model_id


def test_a_rate_with_an_end_date_names_it_after_the_day_it_was_read():
    ending = {model_id: price for model_id, price in OFFICIAL.items() if price.until}
    assert {"gpt-5.6-sol", "gpt-5.6", "gemini-3.8-flash"} <= set(ending)
    for model_id, price in ending.items():
        until = date.fromisoformat(price.until)
        assert until.isoformat() == price.until, model_id
        assert until >= date.fromisoformat(price.as_of), model_id
        assert price.note, model_id  # what applies after it, or that the page does not say


def test_lookup_finds_a_model_by_a_dotted_or_provider_prefixed_id():
    sonnet = OFFICIAL["claude-sonnet-5-5"]
    assert lookup("claude-sonnet-5.5") is sonnet
    assert lookup("anthropic/claude-sonnet-5-5") is sonnet


def test_lookup_returns_none_without_an_official_price():
    assert lookup("no-such-model") is None
    assert lookup("gemini-3.5-flash") is None


def test_no_two_priced_ids_normalise_alike():
    normalised = [normalise(model_id) for model_id in OFFICIAL]
    assert len(set(normalised)) == len(normalised)


def test_imports_without_tradingagents():
    check = "import sys, trader.prices; assert 'tradingagents' not in sys.modules"
    subprocess.run(
        [sys.executable, "-c", check], cwd=Path(__file__).resolve().parents[1], check=True
    )
