import time

from tradingagents.agents.utils.agent_utils import prefetch_tools_parallel


class _FakeTool:
    def __init__(self, result: str, delay_s: float) -> None:
        self._result = result
        self._delay_s = delay_s

    def invoke(self, _args: dict) -> str:
        time.sleep(self._delay_s)
        return self._result


def test_prefetch_tools_parallel_preserves_declared_order():
    results = prefetch_tools_parallel(
        [
            {
                "tool": _FakeTool("company", delay_s=0.05),
                "args": {},
                "label": "Company-Specific News",
            },
            {
                "tool": _FakeTool("global", delay_s=0.0),
                "args": {},
                "label": "Global News",
            },
        ]
    )

    assert list(results) == ["Company-Specific News", "Global News"]
