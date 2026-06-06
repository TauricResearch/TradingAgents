from tradingagents.personas.loader import load_persona_from_string
from tradingagents.personas.prompt_overlay import apply_fragment
from tradingagents.personas.risk_weights import format_weighted_risk_debate


BALANCED_YAML = """
id: balanced
name: Balanced IIC
description: Balanced default profile for approved full studies.
system_prompt_fragment: |
  IIC persona overlay: weigh evidence across growth, valuation, macro,
  momentum, and risk. Preserve material disagreement instead of forcing
  false consensus.
llm:
  deep_think_llm: deepseek-v4-pro
  quick_think_llm: deepseek-v4-flash
analysts:
  include: [market, news, fundamentals, derivatives, social]
  exclude: []
risk_debate:
  weights:
    aggressive: 1.0
    conservative: 1.0
    neutral: 1.0
memory_scope: hybrid
"""


def test_apply_fragment_appends_persona_fragment():
    persona = load_persona_from_string(BALANCED_YAML)
    prompt = apply_fragment("Base role prompt.", persona)
    assert prompt.startswith("Base role prompt.")
    assert "IIC persona overlay" in prompt


def test_apply_fragment_passthrough_without_persona():
    assert apply_fragment("Base role prompt.", None) == "Base role prompt."


def test_format_weighted_risk_debate_labels_all_sides():
    persona = load_persona_from_string(BALANCED_YAML)
    rendered = format_weighted_risk_debate(
        {
            "aggressive_history": "Aggressive case",
            "conservative_history": "Conservative case",
            "neutral_history": "Neutral case",
        },
        persona,
    )
    assert "Aggressive (weight 1.00)" in rendered
    assert "Conservative (weight 1.00)" in rendered
    assert "Neutral (weight 1.00)" in rendered
    assert "Aggressive case" in rendered
