"""Tests for tradingagents.agents.personas."""

from tradingagents.agents.personas import get_persona_prompt, PERSONAS


class TestGetPersonaPrompt:
    def test_none_returns_empty(self):
        assert get_persona_prompt(None, "trader") == ""

    def test_default_returns_empty(self):
        assert get_persona_prompt("default", "trader") == ""

    def test_unknown_persona_returns_empty(self):
        assert get_persona_prompt("unknown_investor", "trader") == ""

    def test_unknown_role_returns_empty(self):
        assert get_persona_prompt("warren_buffett", "analyst") == ""

    def test_buffett_trader(self):
        prompt = get_persona_prompt("warren_buffett", "trader")
        assert "Warren Buffett" in prompt
        assert "margin of safety" in prompt
        assert len(prompt) > 100

    def test_buffett_research_manager(self):
        prompt = get_persona_prompt("warren_buffett", "research_manager")
        assert "Warren Buffett" in prompt
        assert "fundamental" in prompt.lower()

    def test_buffett_risk_manager(self):
        prompt = get_persona_prompt("warren_buffett", "risk_manager")
        assert "Warren Buffett" in prompt
        assert "permanent loss" in prompt.lower()

    def test_dalio_trader(self):
        prompt = get_persona_prompt("ray_dalio", "trader")
        assert "Ray Dalio" in prompt
        assert "diversif" in prompt.lower()

    def test_dalio_research_manager(self):
        prompt = get_persona_prompt("ray_dalio", "research_manager")
        assert "Ray Dalio" in prompt

    def test_lynch_trader(self):
        prompt = get_persona_prompt("peter_lynch", "trader")
        assert "Peter Lynch" in prompt
        assert "PEG" in prompt

    def test_lynch_research_manager(self):
        prompt = get_persona_prompt("peter_lynch", "research_manager")
        assert "Peter Lynch" in prompt
        assert "earnings growth" in prompt.lower()


class TestPersonasCompleteness:
    """Verify all personas define all required roles."""

    REQUIRED_ROLES = ["trader", "research_manager", "risk_manager"]

    def test_all_personas_have_all_roles(self):
        for persona_name, roles in PERSONAS.items():
            for role in self.REQUIRED_ROLES:
                assert role in roles, f"{persona_name} missing role: {role}"

    def test_all_prompt_fragments_are_nonempty(self):
        for persona_name, roles in PERSONAS.items():
            for role, prompt in roles.items():
                assert len(prompt) > 50, (
                    f"{persona_name}/{role} prompt too short: {len(prompt)} chars"
                )

    def test_expected_personas_exist(self):
        assert "warren_buffett" in PERSONAS
        assert "ray_dalio" in PERSONAS
        assert "peter_lynch" in PERSONAS
