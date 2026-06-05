import pytest

from tradingagents.agents.utils.prompt_cache import (
    DYNAMIC_CONTEXT_MARKER,
    get_prompt_cache_budget,
    prompt_prefix_fingerprint,
    stable_join_sections,
    trim_context_block,
)


def test_stable_join_sections_keeps_order_and_skips_empty():
    text = stable_join_sections(
        [
            ("Trade Date", "2026-06-05"),
            ("Empty", ""),
            ("Ticker", "NVDA"),
            ("None", None),
        ]
    )

    assert text == (
        f"{DYNAMIC_CONTEXT_MARKER}\n\n"
        "### Trade Date\n"
        "2026-06-05\n\n"
        "### Ticker\n"
        "NVDA"
    )


def test_trim_context_block_keeps_short_text_unchanged():
    assert trim_context_block("abc", 10, "sample") == "abc"


def test_trim_context_block_keeps_recent_tail_deterministically():
    text = "0123456789"

    assert trim_context_block(text, 4, "debate") == (
        "[truncated debate: kept most recent 4 chars]\n6789"
    )


def test_trim_context_block_rejects_non_positive_budget():
    with pytest.raises(ValueError, match="max_chars must be positive"):
        trim_context_block("abc", 0, "bad")


def test_prompt_prefix_fingerprint_ignores_dynamic_tail():
    messages_a = [
        {"role": "system", "content": "static instructions"},
        {"role": "user", "content": f"{DYNAMIC_CONTEXT_MARKER}\n\n### Ticker\nNVDA"},
    ]
    messages_b = [
        {"role": "system", "content": "static instructions"},
        {"role": "user", "content": f"{DYNAMIC_CONTEXT_MARKER}\n\n### Ticker\nAAPL"},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)


def test_prompt_prefix_fingerprint_changes_when_static_prefix_changes():
    messages_a = [{"role": "system", "content": "static instructions"}]
    messages_b = [{"role": "system", "content": "changed instructions"}]

    assert prompt_prefix_fingerprint(messages_a) != prompt_prefix_fingerprint(messages_b)


def test_get_prompt_cache_budget_reads_config(monkeypatch):
    import tradingagents.agents.utils.prompt_cache as mod

    monkeypatch.setattr(
        mod,
        "get_config",
        lambda: {"prompt_cache_report_budget_chars": "1234"},
    )

    assert get_prompt_cache_budget("prompt_cache_report_budget_chars", 5000) == 1234
