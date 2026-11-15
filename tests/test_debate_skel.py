import pytest

from tradingagents.agents.utils.debate_skel import build_debate_instructions


@pytest.mark.parametrize(
    ("side", "opponent"),
    [("bull", "bear"), ("bear", "bull")],
)
def test_debate_instructions_address_the_opponent(side, opponent):
    instructions = build_debate_instructions(side, is_final_turn=False)

    assert f"Direct response to the {opponent} analyst" in instructions


def test_final_turn_requires_reverse_check():
    regular = build_debate_instructions("bull", is_final_turn=False)
    final = build_debate_instructions("bull", is_final_turn=True)

    assert "reverse_check must explain" in final
    assert "reverse_check must explain" not in regular


def test_invalid_side_is_rejected():
    with pytest.raises(ValueError):
        build_debate_instructions("neutral", is_final_turn=False)
