"""Every report-producing agent must apply the shared investor profile, so the
whole pipeline rates the instrument for the same holder (horizon, objective,
what drives the rating) rather than each agent defaulting to a trading lens.
"""
import pytest

from tests.test_i18n_coverage import _AGENTS_DIR, REPORT_AGENTS
from tradingagents.agents.utils.agent_utils import get_investor_profile_instruction
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def restore_profile():
    original = get_config().get("investor_profile")
    yield
    set_config({"investor_profile": original})


@pytest.mark.unit
class TestInvestorProfileInstruction:
    def test_default_profile_is_long_term_income(self, restore_profile):
        set_config({"investor_profile": DEFAULT_CONFIG["investor_profile"]})
        out = get_investor_profile_instruction()
        assert "long-term, income-focused" in out
        assert "Malaysian bank stocks" in out
        assert "not to change the rating" in out

    def test_custom_profile_is_used(self, restore_profile):
        set_config({"investor_profile": "  Growth investor, 1-year horizon.  "})
        out = get_investor_profile_instruction()
        assert out.endswith("Growth investor, 1-year horizon.")

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_blank_profile_adds_no_tokens(self, restore_profile, value):
        set_config({"investor_profile": value})
        assert get_investor_profile_instruction() == ""


@pytest.mark.unit
@pytest.mark.parametrize("rel", REPORT_AGENTS)
def test_report_agent_applies_investor_profile(rel):
    src = (_AGENTS_DIR / rel).read_text(encoding="utf-8")
    assert "get_investor_profile_instruction()" in src, (
        f"{rel} does not apply get_investor_profile_instruction(); it would "
        f"ignore the configured investor_profile."
    )
