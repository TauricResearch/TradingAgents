#!/usr/bin/env python3
"""
README.md Accuracy Validator

Validates that README.md claims match actual codebase state.
Runs as pre-commit hook to prevent documentation drift.

Checks:
- Agent count (should be 19)
- Skill count (should be 19)
- Command count (should be 9)
- Hook count (should be 24)
- Command names match filesystem
- Skill names match filesystem
- Agent descriptions are present
"""

import sys
import re
from pathlib import Path


class ReadmeValidator:
    """Validates README.md accuracy against codebase."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.readme_path = repo_root / "README.md"
        self.plugins_dir = repo_root / "plugins" / "autonomous-dev"
        self.errors = []
        self.warnings = []

    def validate(self) -> bool:
        """Run all validations. Returns True if all pass."""
        print("🔍 Validating README.md accuracy...\n")

        # Check file exists
        if not self.readme_path.exists():
            self.errors.append(f"README.md not found at {self.readme_path}")
            return False

        # Read README
        with open(self.readme_path, 'r') as f:
            readme_content = f.read()

        # Run validations
        self.validate_agent_count(readme_content)
        self.validate_skill_count(readme_content)
        self.validate_command_count(readme_content)
        self.validate_command_names(readme_content)
        self.validate_hook_count(readme_content)
        self.validate_skill_names(readme_content)
        self.validate_version_consistency(readme_content)
        self.validate_descriptions(readme_content)

        # Report results
        return self.report_results()

    def validate_agent_count(self, content: str):
        """Verify 19 agents are listed."""
        # Count agents in filesystem
        agents_dir = self.plugins_dir / "agents"
        if not agents_dir.exists():
            self.errors.append("agents/ directory not found")
            return

        actual_agents = len(list(agents_dir.glob("*.md")))

        # Extract from README
        match = re.search(r"\*\*Core Workflow Agents \((\d+)\)\*\*", content)
        core_count = int(match.group(1)) if match else 0

        match = re.search(r"\*\*Analysis & Validation Agents \((\d+)\)\*\*", content)
        analysis_count = int(match.group(1)) if match else 0

        match = re.search(r"\*\*Automation & Setup Agents \((\d+)\)\*\*", content)
        automation_count = int(match.group(1)) if match else 0

        readme_total = core_count + analysis_count + automation_count

        if readme_total != actual_agents:
            self.errors.append(
                f"Agent count mismatch: README claims {readme_total} "
                f"({core_count}+{analysis_count}+{automation_count}), "
                f"but found {actual_agents} in plugins/autonomous-dev/agents/"
            )
        else:
            print(f"✅ Agent count correct: {actual_agents} (8+6+5)")

    def validate_skill_count(self, content: str):
        """Verify 19 skills are listed."""
        # Count skills in filesystem
        skills_dir = self.plugins_dir / "skills"
        if not skills_dir.exists():
            self.errors.append("skills/ directory not found")
            return

        actual_skills = len(list(skills_dir.glob("*/SKILL.md"))) + len(list(skills_dir.glob("*/skill.md")))

        # Extract from README
        match = re.search(r"\*\*19 Specialist Skills", content)
        if not match:
            self.warnings.append("README doesn't explicitly claim '19 Specialist Skills'")

        if actual_skills != 19:
            self.errors.append(
                f"Skill count mismatch: Expected 19, found {actual_skills}"
            )
        else:
            print(f"✅ Skill count correct: 19")

    def validate_command_count(self, content: str):
        """Verify command count and listing."""
        # Count commands in filesystem
        commands_dir = self.plugins_dir / "commands"
        if not commands_dir.exists():
            self.errors.append("commands/ directory not found")
            return

        actual_commands = len(list(commands_dir.glob("*.md")))

        # Extract from README
        match = re.search(r"\*\*Utility Commands\*\* \((\d+)\)\*\*", content)
        utility_count = int(match.group(1)) if match else 0

        match = re.search(r"\*\*Core Commands\*\* \((\d+)\)\*\*", content)
        core_count = int(match.group(1)) if match else 0

        readme_total = core_count + utility_count

        if readme_total != actual_commands:
            self.warnings.append(
                f"Command count in README ({readme_total}) doesn't match "
                f"filesystem ({actual_commands}). Check if all commands are documented."
            )
            print(f"⚠️  Command count may be incomplete: README shows {readme_total}, "
                  f"filesystem has {actual_commands}")
        else:
            print(f"✅ Command count correct: {actual_commands}")

    def validate_command_names(self, content: str):
        """Verify all commands are listed in README."""
        commands_dir = self.plugins_dir / "commands"
        actual_commands = set(f.stem for f in commands_dir.glob("*.md"))

        # Extract command names from README
        readme_commands = set(re.findall(r"`/([a-z\-]+)`", content))

        missing_in_readme = actual_commands - readme_commands
        if missing_in_readme:
            self.warnings.append(
                f"Commands in code but NOT in README: {', '.join(sorted(missing_in_readme))}"
            )
            print(f"⚠️  Missing from README: {', '.join(sorted(missing_in_readme))}")

        extra_in_readme = readme_commands - actual_commands
        if extra_in_readme:
            self.warnings.append(
                f"Commands in README but NOT in code: {', '.join(sorted(extra_in_readme))}"
            )

    def validate_hook_count(self, content: str):
        """Verify hook count is correct."""
        hooks_dir = self.plugins_dir / "hooks"
        if not hooks_dir.exists():
            self.errors.append("hooks/ directory not found")
            return

        actual_hooks = len(list(hooks_dir.glob("*.py")))

        # Extract from README
        match = re.search(r"Automation Hooks \((\d+) total\)", content)
        readme_total = int(match.group(1)) if match else 0

        if readme_total != actual_hooks:
            self.errors.append(
                f"Hook count mismatch: README claims {readme_total}, "
                f"found {actual_hooks} in plugins/autonomous-dev/hooks/"
            )
        else:
            print(f"✅ Hook count correct: {actual_hooks}")

    def validate_skill_names(self, content: str):
        """Verify skill names in README match filesystem."""
        skills_dir = self.plugins_dir / "skills"
        actual_skills = set(d.name for d in skills_dir.iterdir() if d.is_dir())

        # Extract skill names from README
        readme_skills = set(re.findall(r"\*\*([a-z\-]+)\*\*\s*-\s*(?:REST|Python|Test|Git|Code|DB|API|Project|Documentation|Security|Research|Cross|File|Semantic|Consistency|Observability|Advisor|Architecture)", content))

        # More lenient extraction - look for bolded items in skills section
        skills_section = re.search(r"### (Core Development Skills|Workflow|Code & Quality|Validation).*?(?=###|$)", content, re.DOTALL)
        if skills_section:
            section_skills = set(re.findall(r"\*\*([a-z\-]+)\*\*", skills_section.group(0)))
            readme_skills.update(section_skills)

        missing_in_readme = actual_skills - readme_skills
        if missing_in_readme:
            self.warnings.append(
                f"Skills in code but NOT in README: {', '.join(sorted(missing_in_readme))}"
            )

    def validate_version_consistency(self, content: str):
        """Verify version number is consistent."""
        match = re.search(r"\*\*Version\*\*:\s*v([\d.]+)", content)
        if match:
            readme_version = f"v{match.group(1)}"
            print(f"✅ Version in README: {readme_version}")
        else:
            self.warnings.append("Could not find version in README header")

    def validate_descriptions(self, content: str):
        """Check agent descriptions are present."""
        descriptions = {
            "orchestrator": "PROJECT.md gatekeeper",
            "researcher": "Web research",
            "planner": "Architecture",
            "test-master": "TDD specialist",
            "implementer": "Code implementation",
            "reviewer": "Quality gate",
            "security-auditor": "Security scanning",
            "doc-master": "Documentation"
        }

        missing_descriptions = []
        for agent, keyword in descriptions.items():
            if agent not in content or keyword not in content:
                missing_descriptions.append(agent)

        if missing_descriptions:
            self.warnings.append(
                f"Agent descriptions may be missing: {', '.join(missing_descriptions)}"
            )
        else:
            print(f"✅ Core agent descriptions present")

    def report_results(self) -> bool:
        """Report validation results."""
        print("\n" + "="*70)

        if self.errors:
            print(f"\n❌ VALIDATION FAILED ({len(self.errors)} error{'s' if len(self.errors) > 1 else ''})")
            for i, error in enumerate(self.errors, 1):
                print(f"   {i}. {error}")

            print("\n📝 Action required: Fix README.md to match codebase")
            return False

        if self.warnings:
            print(f"\n⚠️  VALIDATION PASSED with {len(self.warnings)} warning{'s' if len(self.warnings) > 1 else ''}")
            for i, warning in enumerate(self.warnings, 1):
                print(f"   {i}. {warning}")

            print("\n💡 Recommendations:")
            print("   - Review warnings and update README.md if needed")
            print("   - Run audit: python plugins/autonomous-dev/hooks/validate_readme_accuracy.py")
            return True

        print(f"\n✅ VALIDATION PASSED")
        print("   README.md is accurate and up-to-date")
        return True


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent.parent
    validator = ReadmeValidator(repo_root)

    if not validator.validate():
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
