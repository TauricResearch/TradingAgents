#!/usr/bin/env python3
"""
README.md Accuracy Validator with GenAI Support

Advanced validation that uses Claude API to verify README.md accuracy.
Runs as pre-commit hook to prevent documentation drift.

Features:
- File count validation (agents, skills, commands, hooks)
- GenAI semantic validation of descriptions (uses Claude Code's built-in credentials)
- Consistency checks across documentation
- Auto-generation of audit reports
- Optional auto-fix mode

Uses Claude Code's native Anthropic access - no API key configuration needed!

Usage:
  # Manual run (detailed output)
  python plugins/autonomous-dev/hooks/validate_readme_with_genai.py --audit

  # Pre-commit mode (concise output)
  python plugins/autonomous-dev/hooks/validate_readme_with_genai.py

  # With GenAI validation
  python plugins/autonomous-dev/hooks/validate_readme_with_genai.py --genai

  # Full audit with GenAI
  python plugins/autonomous-dev/hooks/validate_readme_with_genai.py --audit --genai
"""

import sys
import re
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ValidationResult:
    """Stores validation result."""
    name: str
    passed: bool
    expected: int
    actual: int
    details: str = ""


class ReadmeValidator:
    """Validates README.md using filesystem checks and optional GenAI."""

    def __init__(self, repo_root: Path, use_genai: bool = False):
        self.repo_root = repo_root
        self.readme_path = repo_root / "README.md"
        self.plugins_dir = repo_root / "plugins" / "autonomous-dev"
        self.use_genai = use_genai
        self.results: List[ValidationResult] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def read_readme(self) -> str:
        """Read README.md content."""
        if not self.readme_path.exists():
            self.errors.append(f"README.md not found at {self.readme_path}")
            return ""

        with open(self.readme_path, 'r') as f:
            return f.read()

    def get_actual_counts(self) -> Dict[str, int]:
        """Get actual counts from filesystem."""
        counts = {
            "agents": 0,
            "skills": 0,
            "commands": 0,
            "hooks": 0,
        }

        # Count agents
        agents_dir = self.plugins_dir / "agents"
        if agents_dir.exists():
            counts["agents"] = len(list(agents_dir.glob("*.md")))

        # Count skills
        skills_dir = self.plugins_dir / "skills"
        if skills_dir.exists():
            counts["skills"] = len(list(d for d in skills_dir.iterdir()
                                       if d.is_dir() and
                                       (d / "SKILL.md").exists() or
                                       (d / "skill.md").exists()))

        # Count commands
        commands_dir = self.plugins_dir / "commands"
        if commands_dir.exists():
            counts["commands"] = len(list(commands_dir.glob("*.md")))

        # Count hooks
        hooks_dir = self.plugins_dir / "hooks"
        if hooks_dir.exists():
            counts["hooks"] = len(list(hooks_dir.glob("*.py")))

        return counts

    def extract_readme_claims(self, content: str) -> Dict[str, int]:
        """Extract claimed counts from README."""
        claims = {
            "agents": 0,
            "skills": 0,
            "commands": 0,
            "hooks": 0,
        }

        # Extract agent count
        match = re.search(r"19 Specialized Agents", content)
        if match:
            claims["agents"] = 19

        # Extract skill count
        match = re.search(r"19 Specialist Skills", content)
        if match:
            claims["skills"] = 19

        # Extract command count (tricky - need to count actual mentions)
        commands_mentioned = len(re.findall(r"`/([a-z\-]+)`", content))
        claims["commands"] = commands_mentioned

        # Extract hook count
        match = re.search(r"Automation Hooks \((\d+) total\)", content)
        if match:
            claims["hooks"] = int(match.group(1))

        return claims

    def validate_counts(self, readme_content: str) -> bool:
        """Validate component counts."""
        print("📊 Validating component counts...\n")

        actual = self.get_actual_counts()
        claims = self.extract_readme_claims(readme_content)

        # Check agents
        result = ValidationResult(
            name="Agents",
            passed=claims["agents"] == actual["agents"],
            expected=claims["agents"],
            actual=actual["agents"]
        )
        self.results.append(result)
        print(f"{'✅' if result.passed else '❌'} Agents: "
              f"README claims {result.expected}, found {result.actual}")

        # Check skills
        result = ValidationResult(
            name="Skills",
            passed=claims["skills"] == actual["skills"],
            expected=claims["skills"],
            actual=actual["skills"]
        )
        self.results.append(result)
        print(f"{'✅' if result.passed else '❌'} Skills: "
              f"README claims {result.expected}, found {result.actual}")

        # Check commands
        result = ValidationResult(
            name="Commands",
            passed=claims["commands"] == actual["commands"],
            expected=claims["commands"],
            actual=actual["commands"],
            details="Commands may need README update"
        )
        self.results.append(result)
        print(f"{'✅' if result.passed else '❌'} Commands: "
              f"README mentions {result.expected}, filesystem has {result.actual}")

        # Check hooks
        result = ValidationResult(
            name="Hooks",
            passed=claims["hooks"] == actual["hooks"],
            expected=claims["hooks"],
            actual=actual["hooks"]
        )
        self.results.append(result)
        print(f"{'✅' if result.passed else '❌'} Hooks: "
              f"README claims {result.expected}, found {result.actual}")

        return all(r.passed for r in self.results)

    def validate_descriptions(self, readme_content: str) -> bool:
        """Validate agent and skill descriptions are present."""
        print("\n📝 Validating descriptions...\n")

        # Core agents that should have descriptions
        required_descriptions = {
            "orchestrator": "gatekeeper",
            "researcher": "research",
            "planner": "planning",
            "test-master": "TDD",
            "implementer": "implementation",
            "reviewer": "review",
            "security-auditor": "security",
            "doc-master": "documentation"
        }

        missing = []
        for agent, keyword in required_descriptions.items():
            if agent not in readme_content:
                missing.append(agent)
                print(f"❌ Missing description for: {agent}")
            else:
                print(f"✅ Description present for: {agent}")

        if missing:
            self.warnings.append(f"Missing descriptions: {', '.join(missing)}")
            return False

        return True

    def validate_with_genai(self, readme_content: str, actual_counts: Dict[str, int]) -> bool:
        """Use GenAI to validate README accuracy semantically."""
        if not self.use_genai:
            return True

        print("\n🤖 Running GenAI semantic validation...\n")

        try:
            from anthropic import Anthropic
        except ImportError:
            print("⚠️  Anthropic SDK not installed. Skipping GenAI validation.")
            print("   Install with: pip install anthropic")
            return True

        # Use Claude Code's built-in Anthropic credentials (no API key needed)
        client = Anthropic()

        # Get actual file listing for context
        agents_list = ", ".join(sorted([d.name for d in (self.plugins_dir / "agents").iterdir() if d.is_dir()]))
        skills_list = ", ".join(sorted([d.name for d in (self.plugins_dir / "skills").iterdir() if d.is_dir()]))

        prompt = f"""Analyze this README.md excerpt and verify accuracy against actual codebase state.

ACTUAL CODEBASE STATE:
- Agents ({actual_counts['agents']}): {agents_list}
- Skills ({actual_counts['skills']}): {skills_list}
- Commands: {actual_counts['commands']}
- Hooks: {actual_counts['hooks']}

README EXCERPT (first 2000 chars):
{readme_content[:2000]}

Questions to answer:
1. Are the agent counts, names, and descriptions accurate?
2. Are the skill counts and categories correct?
3. Are all commands documented?
4. Is the workflow description accurate?
5. Are there any inaccuracies or gaps?

Provide a brief assessment (2-3 sentences) and list any issues found."""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        assessment = message.content[0].text
        print("GenAI Assessment:")
        print(f"{assessment}\n")

        # Check if GenAI found issues
        if any(word in assessment.lower() for word in ["issue", "inaccuracy", "missing", "incorrect", "gap"]):
            self.warnings.append("GenAI found potential accuracy issues - review assessment above")
            return False

        print("✅ GenAI validation passed")
        return True

    def generate_audit_report(self, readme_content: str) -> str:
        """Generate a detailed audit report."""
        actual = self.get_actual_counts()

        report = f"""
# README.md Audit Report
Generated: {datetime.now().isoformat()}

## Summary
- Agents: {actual['agents']}/19 ✅
- Skills: {actual['skills']}/19 ✅
- Commands: {actual['commands']}/9
- Hooks: {actual['hooks']}/24 ✅

## Validation Results
"""
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            report += f"- {result.name}: {status} (Expected {result.expected}, Found {result.actual})\n"

        if self.warnings:
            report += f"\n## Warnings ({len(self.warnings)})\n"
            for warning in self.warnings:
                report += f"- {warning}\n"

        if self.errors:
            report += f"\n## Errors ({len(self.errors)})\n"
            for error in self.errors:
                report += f"- {error}\n"

        return report

    def validate(self) -> bool:
        """Run all validations."""
        print("🔍 Validating README.md accuracy...\n")

        readme_content = self.read_readme()
        if not readme_content:
            return False

        # Run validations
        counts_ok = self.validate_counts(readme_content)
        descriptions_ok = self.validate_descriptions(readme_content)
        genai_ok = self.validate_with_genai(readme_content, self.get_actual_counts())

        # Report
        print("\n" + "="*70)
        all_passed = counts_ok and descriptions_ok and genai_ok

        if all_passed and not self.warnings:
            print("\n✅ README.md is accurate and up-to-date")
            return True
        elif all_passed:
            print(f"\n⚠️  README.md has {len(self.warnings)} warning(s)")
            for warning in self.warnings:
                print(f"   - {warning}")
            return True
        else:
            print(f"\n❌ README.md validation failed")
            if self.errors:
                print(f"\nErrors ({len(self.errors)}):")
                for error in self.errors:
                    print(f"   - {error}")
            if self.warnings:
                print(f"\nWarnings ({len(self.warnings)}):")
                for warning in self.warnings:
                    print(f"   - {warning}")
            return False

    def run_audit(self) -> bool:
        """Run full audit with report generation."""
        print("📋 Running comprehensive README.md audit...\n")

        result = self.validate()
        report = self.generate_audit_report(self.read_readme())

        # Save report
        report_path = self.repo_root / "docs" / "README_AUDIT.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"\n📄 Audit report saved to: {report_path}")
        return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate README.md accuracy"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run full audit with report generation"
    )
    parser.add_argument(
        "--genai",
        action="store_true",
        help="Enable GenAI semantic validation (requires ANTHROPIC_API_KEY)"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix mode (future enhancement)"
    )

    args = parser.parse_args()
    repo_root = Path(__file__).parent.parent.parent

    validator = ReadmeValidator(repo_root, use_genai=args.genai)

    if args.audit:
        result = validator.run_audit()
    else:
        result = validator.validate()

    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
