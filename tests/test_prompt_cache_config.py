from tradingagents.default_config import DEFAULT_CONFIG


def test_prompt_cache_budget_defaults_present():
    assert DEFAULT_CONFIG["prompt_cache_dynamic_budget_chars"] == 24000
    assert DEFAULT_CONFIG["prompt_cache_report_budget_chars"] == 5000
    assert DEFAULT_CONFIG["prompt_cache_debate_budget_chars"] == 8000
    assert DEFAULT_CONFIG["prompt_cache_prior_pack_budget_chars"] == 8000
    assert DEFAULT_CONFIG["prompt_cache_memory_budget_chars"] == 6000
