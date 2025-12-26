#!/usr/bin/env python3
"""
Pipeline Verification Hook - Verify Agent Execution

This PreCommit hook verifies that the expected agents ran for feature implementations.

Hook Type: PreCommit (OPTIONAL - can be enabled for stricter enforcement)
Trigger: Before git commit completes

Purpose:
    - Detect if full SDLC pipeline was skipped
    - Warn about missing agents (researcher, test-master, etc.)
    - Ensure autonomous workflow was used for feature work

Behavior:
    - If today's pipeline file doesn't exist → PASS (not a feature commit)
    - If file exists but agents missing → WARN (shows what's missing)
    - If all expected agents ran → PASS (full pipeline executed)

Expected agents for feature implementations:
    - researcher (always)
    - planner (architecture/medium+ features)
    - test-master (TDD required)
    - implementer (always)
    - reviewer (quality gate)
    - security-auditor (security-sensitive features)
    - doc-master (always)

Configuration (add to .claude/settings.local.json):
    {
      "hooks": {
        "PreCommit": [{
          "hooks": [{
            "type": "command",
            "command": "python .claude/hooks/verify_agent_pipeline.py || exit 1"
          }]
        }]
      }
    }

Exit codes:
    0 - All checks passed
    1 - Missing agents detected (if strict mode enabled)

Note: By default, this hook WARNS but doesn't block. Set STRICT_PIPELINE=1
      environment variable to block commits when agents are missing.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path


def get_today_pipeline():
    """Get today's pipeline JSON file if it exists"""
    session_dir = Path("docs/sessions")
    if not session_dir.exists():
        return None

    today = date.today().strftime("%Y%m%d")
    pipeline_files = list(session_dir.glob(f"{today}-*-pipeline.json"))

    if not pipeline_files:
        return None

    # Return most recent file
    latest = sorted(pipeline_files)[-1]
    return json.loads(latest.read_text())


def has_feature_commits():
    """
    Check if current commit includes feature work.

    Heuristic: If code files (src/, *.py, *.js, *.ts, etc.) changed,
    likely a feature commit.
    """
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = result.stdout.strip().split("\n")

        # Check for code files
        code_extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp"}
        code_dirs = {"src/", "lib/", "app/"}

        for file in changed_files:
            # Check extension
            if any(file.endswith(ext) for ext in code_extensions):
                return True
            # Check directory
            if any(file.startswith(dir_path) for dir_path in code_dirs):
                return True

        return False
    except Exception:
        # If git command fails, assume feature commit (safe default)
        return True


def verify_pipeline():
    """Verify that expected agents ran"""
    # Get strict mode setting
    strict_mode = os.environ.get("STRICT_PIPELINE", "0") == "1"

    # Check if this is a feature commit
    if not has_feature_commits():
        print("ℹ️  No feature code changes detected, skipping pipeline verification")
        return 0

    # Get today's pipeline
    pipeline = get_today_pipeline()

    if not pipeline:
        print("⚠️  Warning: No agent pipeline file found for today")
        print("   Expected: docs/sessions/{date}-{time}-pipeline.json")
        print("   This usually means agents weren't invoked (manual implementation?)")
        print("\n   Recommendation: Use /auto-implement for feature work to ensure")
        print("   full SDLC pipeline (research → plan → test → implement → review → security → docs)")

        if strict_mode:
            print("\n❌ STRICT_PIPELINE=1: Blocking commit (no pipeline evidence)")
            return 1
        else:
            print("\n✅ Allowing commit (strict mode not enabled)")
            print("   Set STRICT_PIPELINE=1 to enforce pipeline verification")
            return 0

    # Check which agents ran
    completed_agents = {
        entry["agent"]
        for entry in pipeline["agents"]
        if entry["status"] == "completed"
    }

    # Expected agents (minimum for feature work)
    expected_minimum = {"researcher", "implementer", "doc-master"}
    expected_full = {"researcher", "planner", "test-master", "implementer",
                    "reviewer", "security-auditor", "doc-master"}

    # Check minimum requirements
    if expected_minimum.issubset(completed_agents):
        print(f"✅ Agent pipeline verification passed")
        print(f"   Agents ran: {', '.join(sorted(completed_agents))}")

        # Warn if full pipeline not run (but don't block)
        missing_from_full = expected_full - completed_agents
        if missing_from_full:
            print(f"\n   ℹ️  Note: Full pipeline not run (optional agents: {', '.join(missing_from_full)})")
            print(f"   This is OK for simple features, but consider using full pipeline for complex work")

        return 0

    # Missing minimum requirements
    missing = expected_minimum - completed_agents
    print(f"⚠️  Warning: Minimum agent pipeline not complete")
    print(f"   Missing: {', '.join(missing)}")
    print(f"   Ran: {', '.join(sorted(completed_agents)) if completed_agents else 'none'}")
    print("\n   Expected minimum agents:")
    print("   - researcher (find patterns & best practices)")
    print("   - implementer (write code)")
    print("   - doc-master (update documentation)")
    print("\n   Recommendation: Use /auto-implement to ensure full SDLC pipeline")

    if strict_mode:
        print("\n❌ STRICT_PIPELINE=1: Blocking commit (agents missing)")
        return 1
    else:
        print("\n✅ Allowing commit (strict mode not enabled)")
        print("   Set STRICT_PIPELINE=1 to enforce pipeline verification")
        return 0


def main():
    try:
        return verify_pipeline()
    except Exception as e:
        print(f"⚠️  Pipeline verification error: {e}", file=sys.stderr)
        print("   Allowing commit to proceed (verification hook failed gracefully)")
        return 0  # Don't block on errors


if __name__ == "__main__":
    sys.exit(main())
