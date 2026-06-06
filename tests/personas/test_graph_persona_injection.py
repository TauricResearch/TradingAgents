from tradingagents.personas.resolver import load_persona_from_config


def test_load_persona_from_config_loads_balanced_profile():
    persona = load_persona_from_config({"persona_id": "balanced"})
    assert persona is not None
    assert persona.id == "balanced"
    assert "Preserve material disagreement" in persona.system_prompt_fragment


def test_load_persona_from_config_returns_none_for_missing_profile():
    assert load_persona_from_config({"persona_id": "does-not-exist"}) is None
