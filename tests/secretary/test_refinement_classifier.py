import json
from unittest.mock import MagicMock
import pytest


@pytest.mark.unit
def test_classify_extracts_persona_drop_and_risk_tilt():
    from tradingagents.secretary.refinement import classify_and_extract

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content=json.dumps({
        "personas": ["macro", "momentum"],
        "risk_tilt": "more_aggressive",
        "horizon": None,
        "analysts": None,
        "interpretation": "Dropping value, going more aggressive.",
    }))
    parent = {"brief_id": "b1", "scope": "AAPL",
              "refine_overrides": None, "mode": "deep_dive"}
    out = classify_and_extract(
        reply_text="drop value persona, more aggressive",
        parent_brief=parent, llm=fake_llm,
    )
    assert out["personas"] == ["macro", "momentum"]
    assert out["risk_tilt"] == "more_aggressive"
    assert out["horizon"] is None
    assert out["analysts"] is None
    assert "aggressive" in out["interpretation"]


@pytest.mark.unit
def test_classify_handles_invalid_json_gracefully():
    from tradingagents.secretary.refinement import classify_and_extract

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="not json at all")
    out = classify_and_extract(
        reply_text="???",
        parent_brief={"brief_id": "b1", "scope": "AAPL", "mode": "deep_dive"},
        llm=fake_llm,
    )
    assert out["personas"] is None
    assert out["risk_tilt"] is None
    assert out["horizon"] is None
    assert out["analysts"] is None
    assert isinstance(out["interpretation"], str)


@pytest.mark.unit
def test_classify_normalizes_extra_fields():
    from tradingagents.secretary.refinement import classify_and_extract

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content=json.dumps({
        "personas": ["macro"],
        "risk_tilt": "more_conservative",
        "horizon": "months",
        "analysts": {"include": ["fundamentals"], "exclude": ["social"]},
        "interpretation": "OK.",
        "extra_garbage": "ignore me",
    }))
    out = classify_and_extract(
        reply_text="just macro, conservative, months, focus on fundamentals not social",
        parent_brief={"brief_id": "b1", "scope": "AAPL", "mode": "deep_dive"},
        llm=fake_llm,
    )
    assert "extra_garbage" not in out
    assert out["analysts"]["include"] == ["fundamentals"]
    assert out["analysts"]["exclude"] == ["social"]
