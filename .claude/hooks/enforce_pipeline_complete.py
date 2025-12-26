#!/usr/bin/env python3
"""
Pre-commit hook: Enforce pipeline completeness for /auto-implement features

This hook ensures that features developed with /auto-implement go through
the full 7-agent pipeline before being committed.

Pipeline agents:
1. researcher
2. planner
3. test-master
4. implementer
5. reviewer
6. security-auditor
7. doc-master

If pipeline is incomplete, the commit is blocked with instructions on how to fix.

Relevant Skills:
- project-alignment-validation: Feature alignment patterns for validation
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def get_today_pipeline_file():
    """Find today's pipeline JSON file."""
    sessions_dir = Path("docs/sessions")
    if not sessions_dir.exists():
        return None

    today = datetime.now().strftime("%Y%m%d")

    # Find most recent pipeline file for today
    pipeline_files = sorted(
        sessions_dir.glob(f"{today}-*-pipeline.json"),
        reverse=True
    )

    return pipeline_files[0] if pipeline_files else None


def get_agent_count(pipeline_file):
    """Get count of agents that ran from pipeline file."""
    try:
        with open(pipeline_file) as f:
            data = json.load(f)

        agents = data.get("agents", [])
        completed_agents = [
            a for a in agents
            if a.get("status") == "completed"
        ]

        return len(completed_agents), [a.get("agent") for a in completed_agents]
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return 0, []


def get_missing_agents(completed_agents):
    """Get list of agents that didn't run."""
    expected_agents = [
        "researcher",
        "planner",
        "test-master",
        "implementer",
        "reviewer",
        "security-auditor",
        "doc-master"
    ]

    return [a for a in expected_agents if a not in completed_agents]


def is_feature_commit():
    """Check if this is a feature commit based on commit message."""
    import subprocess

    try:
        # Get the commit message
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=True
        )
        commit_msg = result.stdout.strip()

        # Check if it's a feature commit
        return commit_msg.startswith(("feat:", "feature:", "feat(", "feature("))
    except subprocess.CalledProcessError:
        return False


def is_auto_implement_commit():
    """Check if this is a commit from /auto-implement workflow."""
    # Check if pipeline file exists for today
    pipeline_file = get_today_pipeline_file()
    return pipeline_file is not None


def main():
    """Main enforcement logic."""

    # Check if this is a feature commit
    if not is_feature_commit():
        # Not a feature commit - allow it (docs, chore, fix, etc.)
        sys.exit(0)

    # This is a feature commit - enforce pipeline
    if not is_auto_implement_commit():
        # Feature commit but no pipeline file = manual implementation!
        print("=" * 70)
        print("❌ FEATURE COMMIT WITHOUT PIPELINE - COMMIT BLOCKED")
        print("=" * 70)
        print()
        print("This is a feature commit (starts with 'feat:' or 'feature:')")
        print("but no /auto-implement pipeline was detected.")
        print()
        print("=" * 70)
        print("Why this matters:")
        print("=" * 70)
        print()
        print("Feature commits MUST use /auto-implement to ensure:")
        print("  ✓ Research done (researcher)")
        print("  ✓ Architecture planned (planner)")
        print("  ✓ Tests written FIRST (test-master)")
        print("  ✓ Implementation follows TDD (implementer)")
        print("  ✓ Code reviewed (reviewer)")
        print("  ✓ Security scanned (security-auditor)")
        print("  ✓ Documentation updated (doc-master)")
        print()
        print("=" * 70)
        print("How to fix:")
        print("=" * 70)
        print()
        print("Option 1: Use /auto-implement (REQUIRED for features)")
        print("  Run: /auto-implement <your feature description>")
        print("  Wait for all 7 agents to complete")
        print("  Then commit")
        print()
        print("Option 2: Change commit type (if not a feature)")
        print("  If this is a:")
        print("    - Bug fix: Use 'fix:' instead of 'feat:'")
        print("    - Documentation: Use 'docs:' instead of 'feat:'")
        print("    - Chore: Use 'chore:' instead of 'feat:'")
        print()
        print("Option 3: Skip enforcement (STRONGLY NOT RECOMMENDED)")
        print("  git commit --no-verify")
        print("  WARNING: This bypasses ALL quality gates")
        print()
        print("=" * 70)
        sys.exit(1)

    # Pipeline file exists - check if complete
    pipeline_file = get_today_pipeline_file()
    agent_count, completed_agents = get_agent_count(pipeline_file)

    # Check if full pipeline (7 agents) completed
    if agent_count >= 7:
        # Full pipeline completed - allow commit
        print(f"✅ Pipeline complete: {agent_count}/7 agents ran")
        sys.exit(0)

    # Pipeline incomplete - block commit
    missing_agents = get_missing_agents(completed_agents)

    print("=" * 70)
    print("❌ PIPELINE INCOMPLETE - COMMIT BLOCKED")
    print("=" * 70)
    print()
    print(f"Agents that ran: {agent_count}/7")
    print(f"Completed: {', '.join(completed_agents) if completed_agents else 'none'}")
    print()
    print(f"Missing agents ({len(missing_agents)}):")
    for agent in missing_agents:
        print(f"  - {agent}")
    print()
    print("=" * 70)
    print("Why this matters:")
    print("=" * 70)
    print()
    print("The /auto-implement workflow requires ALL 7 agents to ensure:")
    print("  ✓ Tests written (test-master)")
    print("  ✓ Security scanned (security-auditor)")
    print("  ✓ Code reviewed (reviewer)")
    print("  ✓ Documentation updated (doc-master)")
    print()
    print("Skipping agents has led to shipping:")
    print("  ✗ Code without tests (0% coverage)")
    print("  ✗ CRITICAL security vulnerabilities (CVSS 7.1+)")
    print("  ✗ Inconsistent documentation")
    print()
    print("=" * 70)
    print("How to fix:")
    print("=" * 70)
    print()
    print("Option 1: Complete the pipeline (RECOMMENDED)")
    print(f"  Run: /auto-implement again with the same feature")
    print(f"  Claude will invoke the {len(missing_agents)} missing agents")
    print(f"  Then commit again")
    print()
    print("Option 2: Manual implementation (if you didn't use /auto-implement)")
    print("  If this was a manual change, the pipeline file shouldn't exist")
    print(f"  Remove: {pipeline_file}")
    print("  Then commit again (hooks will still validate)")
    print()
    print("Option 3: Skip enforcement (NOT RECOMMENDED)")
    print("  git commit --no-verify")
    print("  WARNING: This bypasses ALL quality gates")
    print()
    print("=" * 70)

    # Block the commit
    sys.exit(1)


if __name__ == "__main__":
    main()
