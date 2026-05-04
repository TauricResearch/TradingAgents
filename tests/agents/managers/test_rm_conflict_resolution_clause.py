import inspect

import tradingagents.agents.managers.research_manager as rm_module


def test_research_manager_prompt_contains_conflict_resolution():
    src = inspect.getsource(rm_module)
    assert "MANDATORY CONFLICT RESOLUTION" in src, (
        "Research Manager prompt must contain MANDATORY CONFLICT RESOLUTION clause"
    )
    assert "cannot override actual financial deterioration" in src
