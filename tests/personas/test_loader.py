import pytest


@pytest.mark.unit
def test_persona_loads_from_yaml_string():
    from tradingagents.personas.loader import load_persona_from_string
    yaml_text = """
id: macro
name: Macro
description: Top-down macro view
system_prompt_fragment: |
  You think top-down.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
  deepseek_reasoning_effort: max
analysts:
  include: [market, news, fundamentals]
  exclude: [social, derivatives]
risk_debate:
  weights:
    aggressive: 0.5
    conservative: 1.5
    neutral: 1.0
memory_scope: hybrid
"""
    persona = load_persona_from_string(yaml_text)
    assert persona.id == "macro"
    assert persona.analysts.include == ["market", "news", "fundamentals"]
    assert persona.analysts.exclude == ["social", "derivatives"]
    assert persona.risk_debate.weights["conservative"] == pytest.approx(1.5)
    assert persona.llm.deep_think_llm == "deepseek-v4-pro"


@pytest.mark.unit
def test_persona_rejects_unknown_analyst_keys():
    from tradingagents.personas.loader import load_persona_from_string
    bad = """
id: bad
name: Bad
description: Invalid persona — bogus analyst name
system_prompt_fragment: "x"
llm:
  deep_think_llm: m
  quick_think_llm: m
analysts:
  include: [market, definitely_not_a_real_analyst]
  exclude: []
risk_debate:
  weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}
memory_scope: hybrid
"""
    with pytest.raises(ValueError, match="definitely_not_a_real_analyst"):
        load_persona_from_string(bad)


@pytest.mark.unit
def test_persona_rejects_overlapping_include_exclude():
    from tradingagents.personas.loader import load_persona_from_string
    bad = """
id: bad
name: Bad
description: market is in both lists
system_prompt_fragment: "x"
llm:
  deep_think_llm: m
  quick_think_llm: m
analysts:
  include: [market, news]
  exclude: [market]
risk_debate:
  weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}
memory_scope: hybrid
"""
    with pytest.raises(ValueError, match="overlap"):
        load_persona_from_string(bad)


@pytest.mark.unit
def test_load_all_personas_from_dir(tmp_path):
    from tradingagents.personas.loader import load_all_personas
    (tmp_path / "macro.yaml").write_text("""
id: macro
name: Macro
description: x
system_prompt_fragment: y
llm: {deep_think_llm: m, quick_think_llm: m}
analysts: {include: [market], exclude: []}
risk_debate: {weights: {aggressive: 1.0, conservative: 1.0, neutral: 1.0}}
memory_scope: hybrid
""")
    personas = load_all_personas(str(tmp_path))
    assert len(personas) == 1
    assert personas[0].id == "macro"
