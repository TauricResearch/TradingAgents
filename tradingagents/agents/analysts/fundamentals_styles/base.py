"""Protocol every fundamentals-analysis style implements.

Using ``typing.Protocol`` (not an ABC) so adding a new style doesn't
require inheriting from a base class — any object with the right shape
works. Keeps tests simple and adheres to the open-closed principle:
add a style without touching shared code.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from langchain_core.tools import BaseTool


@runtime_checkable
class FundamentalStyle(Protocol):
    """One analytical lens through which the fundamentals analyst writes its report."""

    #: Stable, snake_case identifier used in config and ``STYLES`` registry.
    key: str

    #: Display name shown in the CLI picker. May include native script,
    #: e.g. ``"Buffett Value Investing (巴菲特價值投資)"``.
    label: str

    #: One-line subtitle shown under ``label`` in the picker.
    description: str

    def system_message(self) -> str:
        """Return the system-prompt text injected into the agent.

        The returned string is appended to the base scaffolding prompt
        in ``fundamentals_analyst_node`` (tool-use instructions, language
        directive, output table requirement). Styles should focus on
        the analytical framework — what lenses to apply, what numbers
        to weight, what verdict criteria to use — rather than tool
        plumbing.
        """
        ...

    def extra_tools(self) -> List[BaseTool]:
        """Return tools to expose to the LLM *in addition* to the four defaults.

        Most styles return ``[]``. Use this when a style genuinely needs
        a different data source — e.g. Buffett Value benefits from
        insider transactions to read management signaling, while a
        dividend-focused style might need dividend history.
        """
        ...
