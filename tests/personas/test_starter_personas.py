import pytest
from pathlib import Path


@pytest.mark.unit
def test_starter_personas_load_and_match_spec():
    from tradingagents.personas.loader import load_all_personas
    dir_ = Path(__file__).resolve().parents[2] / "tradingagents" / "personas"
    personas = {p.id: p for p in load_all_personas(dir_)}
    assert set(personas.keys()) == {"balanced", "macro", "value", "momentum"}

    # Default full-study persona keeps all native analyst roles enabled.
    assert set(personas["balanced"].analysts.include) == {
        "market", "news", "fundamentals", "derivatives", "social",
    }

    # Spec §5: macro = market + news + fundamentals
    assert set(personas["macro"].analysts.include) == {"market", "news", "fundamentals"}

    # Spec §5: value = fundamentals + news
    assert set(personas["value"].analysts.include) == {"fundamentals", "news"}

    # Spec §5: momentum = market + social + derivatives
    assert set(personas["momentum"].analysts.include) == {"market", "social", "derivatives"}

    # Risk lean — macro is conservative-heavy, momentum is aggressive-heavy
    assert personas["macro"].risk_debate.weights["conservative"] > \
           personas["macro"].risk_debate.weights["aggressive"]
    assert personas["momentum"].risk_debate.weights["aggressive"] > \
           personas["momentum"].risk_debate.weights["conservative"]
