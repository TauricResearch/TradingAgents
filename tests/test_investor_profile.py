"""Every report-producing agent must apply the shared investor profile, so the
whole pipeline rates the instrument for the same holder (horizon, objective,
what drives the rating) rather than each agent defaulting to a trading lens.
"""
import re

import pytest

from tests.test_i18n_coverage import _AGENTS_DIR, REPORT_AGENTS
from tradingagents.agents.utils.agent_utils import get_investor_profile_instruction
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def restore_profile(tmp_path):
    config = get_config()
    original = {k: config.get(k) for k in ("investor_profile", "investor_profile_file")}
    # Never read the developer's real private details file during tests.
    set_config({"investor_profile_file": str(tmp_path / "missing.txt")})
    yield
    set_config(original)


@pytest.mark.unit
class TestInvestorProfileInstruction:
    def test_default_profile_is_long_term_income(self, restore_profile):
        set_config({"investor_profile": DEFAULT_CONFIG["investor_profile"]})
        out = get_investor_profile_instruction()
        assert "long-term, income-focused" in out
        assert "Bursa Malaysia stocks" in out
        # Personal amounts belong in the private details file, not the committed default.
        assert not re.search(r"RM\s?\d", DEFAULT_CONFIG["investor_profile"])
        assert "board lots of 100 shares" in out
        assert "not to change the rating" in out

    def test_custom_profile_is_used(self, restore_profile):
        set_config({"investor_profile": "  Growth investor, 1-year horizon.  "})
        out = get_investor_profile_instruction()
        assert out.endswith("Growth investor, 1-year horizon.")

    def test_private_details_file_is_appended(self, restore_profile, tmp_path):
        details = tmp_path / "investor_profile.txt"
        details.write_text("Portfolio about RM10,000.\nBuys RM1,000 each.\n", encoding="utf-8")
        set_config({"investor_profile": "Income investor.", "investor_profile_file": str(details)})
        out = get_investor_profile_instruction()
        assert out.endswith(
            "Income investor. Investor's own details: Portfolio about RM10,000. Buys RM1,000 each."
        )

    def test_missing_or_empty_details_file_adds_nothing(self, restore_profile, tmp_path):
        empty = tmp_path / "empty.txt"
        empty.write_text("  \n", encoding="utf-8")
        for path in (str(tmp_path / "missing.txt"), str(empty), "", None):
            set_config({"investor_profile": "Income investor.", "investor_profile_file": path})
            assert get_investor_profile_instruction().endswith("Income investor.")

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
