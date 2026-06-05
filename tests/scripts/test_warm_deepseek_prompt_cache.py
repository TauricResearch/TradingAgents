from scripts.warm_deepseek_prompt_cache import build_warmup_messages, iter_warmup_families


def test_iter_warmup_families_has_core_investment_team_prompts():
    names = [family.name for family in iter_warmup_families()]

    assert "market" in names
    assert "sentiment" in names
    assert "research_manager" in names
    assert "portfolio_manager" in names


def test_build_warmup_messages_use_static_prefix_and_tiny_tail():
    family = next(f for f in iter_warmup_families() if f.name == "sentiment")

    messages = build_warmup_messages(family)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "CACHE-WARMUP" in messages[1]["content"]
    assert "2000-01-01" in messages[1]["content"]
    assert "## Dynamic Run Context" in messages[1]["content"]
