"""Tests for the OpenRouter model picker's filter and sort logic.

We assert two behaviors:
* :free variants are excluded (they share an upstream rate-limit pool and
  routinely 429 mid-analysis — this is what we hit in real use).
* Stable providers (deepseek, anthropic, openai, ...) sort to the top in
  the order declared in _OPENROUTER_PRIORITY_PROVIDERS so the picker
  surfaces them first.
"""

from cli.utils import _OPENROUTER_PRIORITY_PROVIDERS, _curate_openrouter_models


SAMPLE_API_RESPONSE = [
    # Free variants that should be filtered
    ("Baidu: CoBuddy (free)", "baidu/cobuddy:free"),
    ("Mistral 7B (free)", "mistralai/mistral-7b-instruct:free"),
    # Mixed providers, some priority, some not
    ("OpenAI: GPT-5.4", "openai/gpt-5.4"),
    ("DeepSeek: V3.2", "deepseek/deepseek-v3.2"),
    ("Anthropic: Claude Sonnet 4.6", "anthropic/claude-sonnet-4-6"),
    ("Random Provider Model", "obscure-vendor/some-model"),
    ("Google: Gemini 2.5 Pro", "google/gemini-2.5-pro"),
    ("DeepSeek: Chat", "deepseek/deepseek-chat"),
    ("Meta: Llama 4 70B", "meta-llama/llama-4-70b"),
]


def test_filters_out_free_variants():
    out = _curate_openrouter_models(SAMPLE_API_RESPONSE)
    ids = [mid for _, mid in out]
    assert "baidu/cobuddy:free" not in ids
    assert "mistralai/mistral-7b-instruct:free" not in ids


def test_priority_providers_sort_first():
    """First model in the curated list comes from the highest-priority provider present."""
    out = _curate_openrouter_models(SAMPLE_API_RESPONSE)
    first_provider = out[0][1].split("/", 1)[0]
    # deepseek is rank 0 in _OPENROUTER_PRIORITY_PROVIDERS and present in the sample
    assert first_provider == "deepseek"


def test_provider_groups_in_declared_order():
    """deepseek must appear before anthropic must appear before openai, etc."""
    out = _curate_openrouter_models(SAMPLE_API_RESPONSE)
    providers_in_order = [mid.split("/", 1)[0] for _, mid in out]

    def first_index(provider: str) -> int:
        return providers_in_order.index(provider)

    # The priority list declares deepseek < anthropic < openai < google < ...
    assert first_index("deepseek") < first_index("anthropic")
    assert first_index("anthropic") < first_index("openai")
    assert first_index("openai") < first_index("google")
    assert first_index("google") < first_index("meta-llama")


def test_per_provider_limit_caps_chatty_providers():
    """A provider with many variants must not crowd out other priority providers."""
    chatty = [(f"deepseek/v{i}", f"deepseek/v{i}") for i in range(20)]
    sample = chatty + [
        ("anthropic/claude-sonnet-4-6", "anthropic/claude-sonnet-4-6"),
        ("openai/gpt-5.4", "openai/gpt-5.4"),
    ]
    out = _curate_openrouter_models(sample, per_provider_limit=2)
    # First 2 entries should be deepseek (capped), then anthropic, then openai
    providers_in_order = [mid.split("/", 1)[0] for _, mid in out]
    assert providers_in_order[:4] == ["deepseek", "deepseek", "anthropic", "openai"]


def test_per_provider_limit_does_not_apply_to_non_priority():
    """Non-priority providers all appear (no cap), sorted alphabetically at the bottom."""
    sample = [
        ("anthropic/sonnet", "anthropic/sonnet"),
        ("zzz/model-3", "zzz/model-3"),
        ("zzz/model-1", "zzz/model-1"),
        ("zzz/model-2", "zzz/model-2"),
    ]
    out = _curate_openrouter_models(sample, per_provider_limit=2)
    ids = [mid for _, mid in out]
    # All 3 zzz models present, alphabetical
    assert ids == ["anthropic/sonnet", "zzz/model-1", "zzz/model-2", "zzz/model-3"]


def test_priority_providers_preserve_api_order():
    """Within a priority provider, the API's insertion order (newest-first) is preserved.

    OpenRouter returns models newest-first. If we re-sorted alphabetically we'd
    surface "gpt-3.5-turbo" before "gpt-5" — actively misleading. This test
    locks the behavior so a future refactor can't accidentally re-introduce
    alphabetical sort within a provider.
    """
    sample = [
        # API returns newest first; this list mimics that
        ("OpenAI: GPT-5.4", "openai/gpt-5.4"),
        ("OpenAI: GPT-4.1", "openai/gpt-4.1"),
        ("OpenAI: GPT-3.5 Turbo", "openai/gpt-3.5-turbo"),
        ("DeepSeek: V3.2", "deepseek/deepseek-v3.2"),
        ("DeepSeek: V3", "deepseek/deepseek-v3"),
    ]
    out = _curate_openrouter_models(sample, per_provider_limit=2)
    # First 2 deepseek (declared rank 0), then first 2 openai
    ids = [mid for _, mid in out]
    assert ids[0] == "deepseek/deepseek-v3.2"  # newest, not alphabetical (-v3 < -v3.2 alphabetically)
    assert ids[1] == "deepseek/deepseek-v3"
    assert ids[2] == "openai/gpt-5.4"  # newest, not alphabetical (3.5-turbo < 5.4 alphabetically)
    assert ids[3] == "openai/gpt-4.1"
    # gpt-3.5-turbo dropped by per_provider_limit=2
    assert "openai/gpt-3.5-turbo" not in ids


def test_unknown_providers_appear_after_priority():
    """Models from providers not in the priority list land at the bottom."""
    out = _curate_openrouter_models(SAMPLE_API_RESPONSE)
    providers_in_order = [mid.split("/", 1)[0] for _, mid in out]
    obscure_position = providers_in_order.index("obscure-vendor")
    # Every priority provider that's present should appear before the obscure one
    for priority_provider in ("deepseek", "anthropic", "openai", "google", "meta-llama"):
        if priority_provider in providers_in_order:
            assert providers_in_order.index(priority_provider) < obscure_position, (
                f"{priority_provider} should come before obscure-vendor"
            )


def test_empty_input_returns_empty():
    assert _curate_openrouter_models([]) == []


def test_all_free_returns_empty():
    only_free = [
        ("A", "x/a:free"),
        ("B", "y/b:free"),
    ]
    assert _curate_openrouter_models(only_free) == []


def test_priority_list_invariants():
    """Sanity: the priority list itself contains the providers we expect."""
    assert "deepseek" in _OPENROUTER_PRIORITY_PROVIDERS
    assert "anthropic" in _OPENROUTER_PRIORITY_PROVIDERS
    assert "openai" in _OPENROUTER_PRIORITY_PROVIDERS
    # No duplicates
    assert len(set(_OPENROUTER_PRIORITY_PROVIDERS)) == len(_OPENROUTER_PRIORITY_PROVIDERS)
