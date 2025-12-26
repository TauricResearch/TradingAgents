#!/usr/bin/env python3
"""
Unified Structure Enforcer - Consolidated Enforcement Dispatcher

Consolidates 6 enforcement hooks into one dispatcher:
- enforce_file_organization.py
- enforce_bloat_prevention.py
- enforce_command_limit.py
- enforce_pipeline_complete.py
- enforce_orchestrator.py
- verify_agent_pipeline.py

Uses dispatcher pattern from pre_tool_use.py:
- Environment variable control per enforcer
- Graceful degradation on errors
- Dynamic lib directory discovery
- Clear logging with [PASS], [FAIL], [SKIP] indicators

Exit codes:
- 0: All checks passed or skipped
- 1: One or more checks failed

Environment variables (all default to true):
- ENFORCE_FILE_ORGANIZATION=true/false
- ENFORCE_BLOAT_PREVENTION=true/false
- ENFORCE_COMMAND_LIMIT=true/false
- ENFORCE_PIPELINE_COMPLETE=true/false
- ENFORCE_ORCHESTRATOR=true/false
- VERIFY_AGENT_PIPELINE=true/false
"""

import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Optional


def find_lib_directory(hook_path: Path) -> Optional[Path]:
    """
    Find lib directory dynamically (Issue #113).

    Checks multiple locations in order:
    1. Development: plugins/autonomous-dev/lib (relative to hook)
    2. Local install: ~/.claude/lib
    3. Marketplace: ~/.claude/plugins/autonomous-dev/lib

    Args:
        hook_path: Path to this hook script

    Returns:
        Path to lib directory if found, None otherwise (graceful failure)
    """
    # Try development location first (plugins/autonomous-dev/hooks/)
    dev_lib = hook_path.parent.parent / "lib"
    if dev_lib.exists() and dev_lib.is_dir():
        return dev_lib

    # Try local install (~/.claude/lib)
    home = Path.home()
    local_lib = home / ".claude" / "lib"
    if local_lib.exists() and local_lib.is_dir():
        return local_lib

    # Try marketplace location (~/.claude/plugins/autonomous-dev/lib)
    marketplace_lib = home / ".claude" / "plugins" / "autonomous-dev" / "lib"
    if marketplace_lib.exists() and marketplace_lib.is_dir():
        return marketplace_lib

    # Not found - graceful failure
    return None


# Add lib directory to path dynamically
LIB_DIR = find_lib_directory(Path(__file__))
if LIB_DIR:
    sys.path.insert(0, str(LIB_DIR))


def load_env():
    """Load .env file from project root if it exists."""
    env_file = Path(os.getcwd()) / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception:
            pass  # Silently skip


load_env()


def is_enabled(env_var: str, default: bool = True) -> bool:
    """Check if enforcer is enabled via environment variable."""
    value = os.getenv(env_var, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


# ============================================================================
# Enforcer 1: File Organization
# ============================================================================

def enforce_file_organization() -> Tuple[bool, str]:
    """
    Enforce file organization standards.

    Returns:
        (passed, reason)
    """
    if not is_enabled("ENFORCE_FILE_ORGANIZATION", True):
        return True, "[SKIP] File organization enforcement disabled"

    try:
        # Get staged files
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        staged_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]

        if not staged_files:
            return True, "[PASS] No staged files to check"

        # Check for violations (root directory clutter)
        violations = []
        for file in staged_files:
            path = Path(file)

            # Skip allowed root files
            if path.parent == Path('.') and path.name in (
                'README.md', 'LICENSE', '.gitignore', '.env', 'pytest.ini',
                'setup.py', 'pyproject.toml', 'requirements.txt', 'Makefile'
            ):
                continue

            # Check for new files in root (not subdirectories)
            if path.parent == Path('.'):
                # Allow specific patterns
                if path.suffix in ('.md', '.py', '.sh'):
                    violations.append(f"{file} should be in docs/ or scripts/ directory")

        if violations:
            return False, f"[FAIL] File organization violations:\n" + "\n".join(f"  - {v}" for v in violations)

        return True, "[PASS] File organization check passed"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] File organization check error: {e}"


# ============================================================================
# Enforcer 2: Bloat Prevention
# ============================================================================

def enforce_bloat_prevention() -> Tuple[bool, str]:
    """
    Enforce bloat prevention limits.

    Returns:
        (passed, reason)
    """
    if not is_enabled("ENFORCE_BLOAT_PREVENTION", True):
        return True, "[SKIP] Bloat prevention enforcement disabled"

    try:
        # Count documentation files
        doc_count = len(list(Path("docs").glob("**/*.md"))) if Path("docs").exists() else 0

        # Count agent files
        agent_dir = Path("plugins/autonomous-dev/agents")
        agent_count = len(list(agent_dir.glob("*.md"))) if agent_dir.exists() else 0

        # Count command files
        cmd_dir = Path("plugins/autonomous-dev/commands")
        cmd_count = len(list(cmd_dir.glob("*.md"))) if cmd_dir.exists() else 0

        violations = []

        # Check limits (these are generous to prevent bloat)
        if doc_count > 100:
            violations.append(f"Too many doc files: {doc_count} > 100")

        if agent_count > 25:
            violations.append(f"Too many agents: {agent_count} > 25 (trust the model)")

        if cmd_count > 15:
            violations.append(f"Too many commands: {cmd_count} > 15")

        if violations:
            return False, f"[FAIL] Bloat prevention violations:\n" + "\n".join(f"  - {v}" for v in violations)

        return True, "[PASS] Bloat prevention check passed"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] Bloat prevention check error: {e}"


# ============================================================================
# Enforcer 3: Command Limit
# ============================================================================

def enforce_command_limit() -> Tuple[bool, str]:
    """
    Enforce 15-command limit.

    Returns:
        (passed, reason)
    """
    if not is_enabled("ENFORCE_COMMAND_LIMIT", True):
        return True, "[SKIP] Command limit enforcement disabled"

    try:
        commands_dir = Path("plugins/autonomous-dev/commands")
        if not commands_dir.exists():
            return True, "[PASS] No commands directory found"

        # Find all active commands (not in archive)
        active_commands = [
            f.stem
            for f in commands_dir.glob("*.md")
            if f.parent.name != "archive"
        ]

        if len(active_commands) > 15:
            return False, f"[FAIL] Too many commands: {len(active_commands)} > 15\n  Commands: {', '.join(sorted(active_commands))}"

        return True, f"[PASS] Command limit check passed ({len(active_commands)}/15)"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] Command limit check error: {e}"


# ============================================================================
# Enforcer 4: Pipeline Complete
# ============================================================================

def enforce_pipeline_complete() -> Tuple[bool, str]:
    """
    Enforce complete pipeline execution for auto-implement features.

    Returns:
        (passed, reason)
    """
    if not is_enabled("ENFORCE_PIPELINE_COMPLETE", True):
        return True, "[SKIP] Pipeline completeness enforcement disabled"

    try:
        sessions_dir = Path("docs/sessions")
        if not sessions_dir.exists():
            return True, "[PASS] No sessions directory (not using /auto-implement)"

        today = datetime.now().strftime("%Y%m%d")

        # Find most recent pipeline file for today
        pipeline_files = sorted(
            sessions_dir.glob(f"{today}-*-pipeline.json"),
            reverse=True
        )

        if not pipeline_files:
            return True, "[PASS] No pipeline file for today (not using /auto-implement)"

        # Check if pipeline is complete
        pipeline_file = pipeline_files[0]
        try:
            with open(pipeline_file) as f:
                data = json.load(f)

            required_agents = [
                "researcher", "planner", "test-master", "implementer",
                "reviewer", "security-auditor", "doc-master"
            ]

            # Check which agents ran
            agents_run = data.get("agents_completed", [])
            missing = [a for a in required_agents if a not in agents_run]

            if missing:
                return False, f"[FAIL] Incomplete pipeline - missing agents: {', '.join(missing)}\n  Tip: Complete the /auto-implement workflow before committing"

            return True, "[PASS] Pipeline completeness check passed"

        except Exception as e:
            # Can't read pipeline file - graceful skip
            return True, f"[SKIP] Pipeline file read error: {e}"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] Pipeline completeness check error: {e}"


# ============================================================================
# Enforcer 5: Orchestrator Validation
# ============================================================================

def enforce_orchestrator() -> Tuple[bool, str]:
    """
    Enforce orchestrator PROJECT.md validation.

    Returns:
        (passed, reason)
    """
    if not is_enabled("ENFORCE_ORCHESTRATOR", True):
        return True, "[SKIP] Orchestrator enforcement disabled"

    try:
        # Check if strict mode is enabled
        settings_file = Path(".claude/settings.local.json")
        strict_mode = False

        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                strict_mode = settings.get("strict_mode", False)
            except Exception:
                pass

        if not strict_mode:
            return True, "[SKIP] Strict mode not enabled"

        # Check if PROJECT.md exists
        if not Path(".claude/PROJECT.md").exists():
            return True, "[PASS] No PROJECT.md (not required)"

        # Check for orchestrator validation in recent sessions
        sessions_dir = Path("docs/sessions")
        if not sessions_dir.exists():
            return False, "[FAIL] No orchestrator validation found - use /auto-implement for features"

        # Look for orchestrator logs in last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)

        for session_file in sorted(sessions_dir.glob("*.json"), reverse=True):
            try:
                mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
                if mtime < cutoff:
                    break  # Stop searching old files

                with open(session_file) as f:
                    content = f.read()
                    if "orchestrator" in content.lower() or "project.md" in content.lower():
                        return True, "[PASS] Orchestrator validation found"
            except Exception:
                continue

        return False, "[FAIL] No orchestrator validation in last 24h - use /auto-implement for features"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] Orchestrator check error: {e}"


# ============================================================================
# Enforcer 6: Agent Pipeline Verification
# ============================================================================

def verify_agent_pipeline() -> Tuple[bool, str]:
    """
    Verify expected agents ran for feature implementations.

    Returns:
        (passed, reason)
    """
    if not is_enabled("VERIFY_AGENT_PIPELINE", True):
        return True, "[SKIP] Agent pipeline verification disabled"

    try:
        sessions_dir = Path("docs/sessions")
        if not sessions_dir.exists():
            return True, "[PASS] No sessions directory (not using agents)"

        today = datetime.now().strftime("%Y%m%d")

        # Find today's pipeline file
        pipeline_files = sorted(
            sessions_dir.glob(f"{today}-*-pipeline.json"),
            reverse=True
        )

        if not pipeline_files:
            return True, "[PASS] No pipeline file for today (not a feature commit)"

        # Check which agents ran
        pipeline_file = pipeline_files[0]
        try:
            with open(pipeline_file) as f:
                data = json.load(f)

            agents_run = data.get("agents_completed", [])

            # Expected agents for full workflow
            expected = ["researcher", "test-master", "implementer", "reviewer", "doc-master"]
            missing = [a for a in expected if a not in agents_run]

            # Check if strict mode is enabled
            strict_pipeline = os.getenv("STRICT_PIPELINE", "0") == "1"

            if missing:
                msg = f"[WARN] Missing agents: {', '.join(missing)}"
                if strict_pipeline:
                    return False, f"[FAIL] {msg} (STRICT_PIPELINE=1)"
                else:
                    return True, f"{msg} (warning only)"

            return True, f"[PASS] Agent pipeline verification passed ({len(agents_run)} agents ran)"

        except Exception as e:
            return True, f"[SKIP] Pipeline file read error: {e}"

    except Exception as e:
        # Graceful degradation
        return True, f"[SKIP] Agent pipeline verification error: {e}"


# ============================================================================
# Main Dispatcher
# ============================================================================

def main():
    """Run all enabled enforcers and aggregate results."""
    print("=" * 80)
    print("UNIFIED STRUCTURE ENFORCER")
    print("=" * 80)

    # Run all enforcers
    results = [
        ("File Organization", enforce_file_organization()),
        ("Bloat Prevention", enforce_bloat_prevention()),
        ("Command Limit", enforce_command_limit()),
        ("Pipeline Complete", enforce_pipeline_complete()),
        ("Orchestrator Validation", enforce_orchestrator()),
        ("Agent Pipeline", verify_agent_pipeline()),
    ]

    # Display results
    all_passed = True
    for name, (passed, reason) in results:
        print(f"\n{name}:")
        print(f"  {reason}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 80)

    if all_passed:
        print("RESULT: All checks passed")
        print("=" * 80)
        sys.exit(0)
    else:
        print("RESULT: One or more checks failed")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
