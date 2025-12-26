#!/usr/bin/env python3
"""
Documentation Consistency Validation Hook - Layer 3 Defense with GenAI Semantic Validation

This pre-commit hook validates that documentation stays in sync with code.
It's OPTIONAL - can be annoying to block commits, but catches drift early.

Features:
- Count validation (exact matches)
- GenAI semantic validation of descriptions (accuracy checking)
- Catches misleading or inaccurate documentation
- Graceful degradation with fallback heuristics

Enable via:
    .claude/settings.local.json:
    {
      "hooks": {
        "PreCommit": {
          "*": ["python .claude/hooks/validate_docs_consistency.py"]
        }
      }
    }

Or via git pre-commit hook:
    ln -s ../../.claude/hooks/validate_docs_consistency.py .git/hooks/pre-commit

What it checks:
- README.md skill/agent/command counts match reality
- GenAI validates descriptions match actual functionality
- Cross-document consistency (SYNC-STATUS, UPDATES, marketplace.json)
- No references to non-existent skills
- marketplace.json metrics match actual counts

Exit codes:
- 0: All checks passed
- 1: Documentation inconsistency detected (blocks commit)
"""

import sys
import json
import re
import os
from pathlib import Path
from typing import Tuple

from genai_utils import GenAIAnalyzer, parse_binary_response
from genai_prompts import DESCRIPTION_VALIDATION_PROMPT

# Initialize GenAI analyzer (with feature flag support)
analyzer = GenAIAnalyzer(
    use_genai=os.environ.get("GENAI_DOCS_VALIDATE", "true").lower() == "true"
)


def get_plugin_root() -> Path:
    """Find plugin root directory."""
    # First, check if we're running from .claude/hooks (dogfooding)
    hook_dir = Path(__file__).parent
    repo_root = hook_dir.parent.parent  # .claude/hooks -> .claude -> repo_root

    plugin_path = repo_root / "plugins" / "autonomous-dev"
    if plugin_path.exists():
        return plugin_path

    # Fallback: check if we're already in the plugin directory
    current = hook_dir.parent
    if (current / "agents").exists() and (current / "skills").exists():
        return current

    # Give up
    raise FileNotFoundError("Could not find plugin root directory")


def count_skills(plugin_root: Path) -> int:
    """Count actual skills in skills/ directory."""
    skills_dir = plugin_root / "skills"
    return len([
        d for d in skills_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])


def count_agents(plugin_root: Path) -> int:
    """Count actual agents in agents/ directory."""
    agents_dir = plugin_root / "agents"
    return len([
        f for f in agents_dir.iterdir()
        if f.is_file() and f.suffix == ".md" and not f.name.startswith(".")
    ])


def count_commands(plugin_root: Path) -> int:
    """Count actual commands in commands/ directory."""
    commands_dir = plugin_root / "commands"
    return len([
        f for f in commands_dir.iterdir()
        if f.is_file() and f.suffix == ".md" and not f.name.startswith(".")
    ])


def check_readme_skill_count(plugin_root: Path, actual_count: int) -> Tuple[bool, str]:
    """Check README.md skill count matches actual."""
    readme_path = plugin_root / "README.md"
    if not readme_path.exists():
        return False, "README.md not found"

    content = readme_path.read_text()
    pattern = rf"\b{actual_count}\s+[Ss]kills"

    if not re.search(pattern, content):
        return False, (
            f"README.md shows incorrect skill count (expected {actual_count})\n"
            f"Fix: Update README.md to show '{actual_count} Skills (Comprehensive SDLC Coverage)'"
        )

    return True, "✅ README.md skill count correct"


def check_readme_agent_count(plugin_root: Path, actual_count: int) -> Tuple[bool, str]:
    """Check README.md agent count matches actual."""
    readme_path = plugin_root / "README.md"
    content = readme_path.read_text()
    pattern = rf"\b{actual_count}\s+[Ss]pecialized\s+[Aa]gents|\b{actual_count}\s+[Aa]gents"

    if not re.search(pattern, content):
        return False, (
            f"README.md shows incorrect agent count (expected {actual_count})\n"
            f"Fix: Update README.md to show '{actual_count} Specialized Agents'"
        )

    return True, "✅ README.md agent count correct"


def check_readme_command_count(plugin_root: Path, actual_count: int) -> Tuple[bool, str]:
    """Check README.md command count matches actual."""
    readme_path = plugin_root / "README.md"
    content = readme_path.read_text()
    pattern = rf"\b{actual_count}\s+[Ss]lash\s+[Cc]ommands|\b{actual_count}\s+[Cc]ommands"

    if not re.search(pattern, content):
        return False, (
            f"README.md shows incorrect command count (expected {actual_count})\n"
            f"Fix: Update README.md to show '{actual_count} Slash Commands'"
        )

    return True, "✅ README.md command count correct"


def check_marketplace_json(plugin_root: Path, skill_count: int, agent_count: int, command_count: int) -> Tuple[bool, str]:
    """Check marketplace.json metrics match actual counts."""
    marketplace_path = plugin_root / ".claude-plugin" / "marketplace.json"
    if not marketplace_path.exists():
        return True, "⚠️  marketplace.json not found (skipping)"

    try:
        data = json.loads(marketplace_path.read_text())
        metrics = data.get("metrics", {})

        errors = []
        if metrics.get("skills") != skill_count:
            errors.append(f"skills: {metrics.get('skills')} (should be {skill_count})")
        if metrics.get("agents") != agent_count:
            errors.append(f"agents: {metrics.get('agents')} (should be {agent_count})")
        if metrics.get("commands") != command_count:
            errors.append(f"commands: {metrics.get('commands')} (should be {command_count})")

        if errors:
            return False, (
                f"marketplace.json metrics incorrect:\n"
                + "\n".join(f"  - {e}" for e in errors) +
                f"\nFix: Update .claude-plugin/marketplace.json metrics section"
            )

        return True, "✅ marketplace.json metrics correct"

    except json.JSONDecodeError:
        return False, "marketplace.json is invalid JSON"


def check_no_broken_skill_references(plugin_root: Path) -> Tuple[bool, str]:
    """Check for references to non-existent skills."""
    # Get actual skills
    skills_dir = plugin_root / "skills"
    actual_skills = set(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    # Known problematic skills that have been removed
    problematic_skills = ['engineering-standards']

    readme_path = plugin_root / "README.md"
    readme_content = readme_path.read_text()

    broken_references = []
    for skill in problematic_skills:
        if skill not in actual_skills and skill in readme_content:
            broken_references.append(skill)

    if broken_references:
        return False, (
            f"README.md references non-existent skills: {broken_references}\n"
            f"Fix: Remove or replace these skill references"
        )

    return True, "✅ No broken skill references"


def check_cross_document_consistency(plugin_root: Path, skill_count: int) -> Tuple[bool, str]:
    """Check all documentation files show same skill count."""
    files_to_check = [
        "README.md",
        "docs/SYNC-STATUS.md",
        "docs/UPDATES.md",
        "INSTALL_TEMPLATE.md",
    ]

    inconsistencies = []

    for file_path in files_to_check:
        full_path = plugin_root / file_path
        if not full_path.exists():
            continue

        content = full_path.read_text()
        # Look for skill count mentions
        if str(skill_count) not in content or "skills" not in content.lower():
            # Check if it mentions a different count
            skill_mentions = re.findall(r'(\d+)\s+[Ss]kills', content)
            if skill_mentions and int(skill_mentions[0]) != skill_count:
                inconsistencies.append(f"{file_path}: shows {skill_mentions[0]} skills (should be {skill_count})")

    if inconsistencies:
        return False, (
            f"Cross-document skill count inconsistency:\n"
            + "\n".join(f"  - {i}" for i in inconsistencies) +
            f"\nFix: Update all files to show {skill_count} skills"
        )

    return True, "✅ Cross-document consistency verified"


def validate_description_accuracy_with_genai(plugin_root: Path, entity_type: str) -> Tuple[bool, str]:
    """Use GenAI to validate if descriptions match actual implementation.

    Delegates to shared GenAI utility with graceful fallback.

    Args:
        plugin_root: Root directory of plugin
        entity_type: 'agents', 'skills', or 'commands'

    Returns:
        (passed, message) tuple
    """
    # Get README.md section for the entity type
    readme_path = plugin_root / "README.md"
    if not readme_path.exists():
        return True, f"⏭️  No README.md found"

    readme_content = readme_path.read_text()

    # Extract the relevant section (simplified - looks for entity type mentions)
    section_start = readme_content.lower().find(entity_type.lower())
    if section_start == -1:
        return True, f"⏭️  No {entity_type} section found in README.md"

    # Get a reasonable chunk of the section
    section_end = min(section_start + 2000, len(readme_content))
    section = readme_content[section_start:section_end]

    # Call shared GenAI analyzer
    response = analyzer.analyze(
        DESCRIPTION_VALIDATION_PROMPT,
        entity_type=entity_type,
        section=section[:1000]
    )

    # Parse response using shared utility
    if response:
        is_accurate = parse_binary_response(
            response,
            true_keywords=["ACCURATE"],
            false_keywords=["MISLEADING"]
        )
        if is_accurate is not None:
            if is_accurate:
                return True, f"✅ GenAI validated {entity_type} descriptions are accurate"
            else:
                return False, (
                    f"⚠️  GenAI found potential inaccuracies in {entity_type} descriptions\n"
                    f"Review README.md {entity_type} section for misleading or vague descriptions"
                )

    # Fallback: if GenAI unavailable or ambiguous, skip validation
    return True, "⏭️  GenAI validation skipped (call failed or ambiguous)"


def main() -> int:
    """Run all documentation consistency checks.

    Returns:
        0 if all checks pass
        1 if any check fails
    """
    use_genai = os.environ.get("GENAI_DOCS_VALIDATE", "true").lower() == "true"
    genai_status = "🤖 (with GenAI semantic validation)" if use_genai else ""
    print(f"🔍 Validating documentation consistency... {genai_status}")
    print()

    try:
        plugin_root = get_plugin_root()
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1

    # Count actual resources
    skill_count = count_skills(plugin_root)
    agent_count = count_agents(plugin_root)
    command_count = count_commands(plugin_root)

    print(f"📊 Actual counts:")
    print(f"   - Skills: {skill_count}")
    print(f"   - Agents: {agent_count}")
    print(f"   - Commands: {command_count}")
    print()

    # Run all checks
    checks = [
        ("README.md skill count", check_readme_skill_count(plugin_root, skill_count)),
        ("README.md agent count", check_readme_agent_count(plugin_root, agent_count)),
        ("README.md command count", check_readme_command_count(plugin_root, command_count)),
        ("marketplace.json metrics", check_marketplace_json(plugin_root, skill_count, agent_count, command_count)),
        ("Broken skill references", check_no_broken_skill_references(plugin_root)),
        ("Cross-document consistency", check_cross_document_consistency(plugin_root, skill_count)),
    ]

    # Add GenAI semantic validation if enabled
    if use_genai:
        checks.extend([
            ("Agent descriptions accuracy", validate_description_accuracy_with_genai(plugin_root, "agents")),
            ("Command descriptions accuracy", validate_description_accuracy_with_genai(plugin_root, "commands")),
        ])

    all_passed = True

    for check_name, (passed, message) in checks:
        if passed:
            print(f"{message}")
        else:
            print(f"❌ {check_name} FAILED:")
            print(f"   {message}")
            print()
            all_passed = False

    print()

    if all_passed:
        print("✅ All documentation consistency checks passed!")
        return 0
    else:
        print("❌ Documentation consistency checks FAILED!")
        print()
        print("Fix the issues above before committing.")
        print("Or run: pytest tests/test_documentation_consistency.py -v")
        print()
        print("To skip this hook (NOT RECOMMENDED):")
        print("  git commit --no-verify")
        return 1


if __name__ == "__main__":
    sys.exit(main())
