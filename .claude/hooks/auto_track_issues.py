#!/usr/bin/env python3
"""
Automatic GitHub Issue Tracking Hook

Automatically creates GitHub Issues from testing results in the background.

Triggers:
- After test completion (UserPromptSubmit)
- Before push (pre-push hook)
- On commit (post-commit hook)

Usage:
- Runs automatically when GITHUB_AUTO_TRACK_ISSUES=true in .env
- Creates issues for:
  - Test failures (pytest)
  - GenAI validation findings (UX, architecture)
  - System performance opportunities

Configuration (.env):
GITHUB_AUTO_TRACK_ISSUES=true      # Enable auto-tracking
GITHUB_TRACK_ON_PUSH=true          # Track before push
GITHUB_TRACK_ON_COMMIT=false       # Track after commit (optional)
GITHUB_TRACK_THRESHOLD=medium      # Minimum priority (low/medium/high)
GITHUB_DRY_RUN=false               # Preview only
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Configuration from .env
AUTO_TRACK_ENABLED = os.getenv("GITHUB_AUTO_TRACK_ISSUES", "false").lower() == "true"
TRACK_ON_PUSH = os.getenv("GITHUB_TRACK_ON_PUSH", "true").lower() == "true"
TRACK_ON_COMMIT = os.getenv("GITHUB_TRACK_ON_COMMIT", "false").lower() == "true"
TRACK_THRESHOLD = os.getenv("GITHUB_TRACK_THRESHOLD", "medium").lower()
DRY_RUN = os.getenv("GITHUB_DRY_RUN", "false").lower() == "true"

# Priority thresholds
PRIORITY_LEVELS = {"low": 1, "medium": 2, "high": 3}


def log(message: str, level: str = "INFO"):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stderr)


def is_gh_authenticated() -> bool:
    """Check if GitHub CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_prerequisites() -> bool:
    """Check if all prerequisites are met."""
    if not AUTO_TRACK_ENABLED:
        log("Auto-tracking disabled (GITHUB_AUTO_TRACK_ISSUES=false)", "DEBUG")
        return False

    # Check if gh CLI is installed
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        log("GitHub CLI (gh) not installed. Install: brew install gh", "WARN")
        return False

    # Check if authenticated
    if not is_gh_authenticated():
        log("GitHub CLI not authenticated. Run: gh auth login", "WARN")
        return False

    return True


def parse_pytest_output() -> List[Dict]:
    """Parse pytest output to find test failures."""
    issues = []

    # Look for pytest cache
    pytest_cache = Path(".pytest_cache/v/cache/lastfailed")
    if not pytest_cache.exists():
        log("No pytest failures found", "DEBUG")
        return issues

    try:
        with open(pytest_cache) as f:
            failed_tests = json.load(f)

        for test_path, _ in failed_tests.items():
            # Extract test info
            parts = test_path.split("::")
            file_path = parts[0] if parts else "unknown"
            test_name = parts[-1] if len(parts) > 1 else test_path

            issues.append({
                "type": "bug",
                "layer": "layer-1",
                "title": f"{test_name} fails - test failure",
                "body": f"Test failure detected in `{test_path}`\n\nRun: `pytest {test_path} -v`",
                "labels": ["bug", "automated", "layer-1", "test-failure"],
                "priority": "high",
                "source": "pytest",
                "test_path": test_path,
                "file_path": file_path,
                "test_name": test_name
            })

    except Exception as e:
        log(f"Error parsing pytest output: {e}", "ERROR")

    return issues


def parse_genai_validation() -> List[Dict]:
    """Parse GenAI validation results for issues."""
    issues = []

    # Look for recent validation reports in docs/sessions/
    sessions_dir = Path("docs/sessions")
    if not sessions_dir.exists():
        return issues

    # Find recent validation files
    validation_files = []
    for pattern in ["uat-validation-*.md", "architecture-validation-*.md"]:
        validation_files.extend(sessions_dir.glob(pattern))

    # Sort by modification time, get most recent
    validation_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for vfile in validation_files[:5]:  # Check last 5 validation reports
        try:
            content = vfile.read_text()

            # Parse UX issues (score < 8/10)
            if "uat-validation" in vfile.name:
                # Simple heuristic: look for low scores
                if "UX Score: 6/10" in content or "UX Score: 7/10" in content:
                    issues.append({
                        "type": "enhancement",
                        "layer": "layer-2",
                        "title": "UX improvement needed",
                        "body": f"GenAI validation found UX issues\n\nSee: {vfile.name}",
                        "labels": ["enhancement", "ux", "genai-detected", "layer-2"],
                        "priority": "medium",
                        "source": "genai-uat"
                    })

            # Parse architectural drift
            if "architecture-validation" in vfile.name:
                if "DRIFT" in content or "VIOLATION" in content:
                    issues.append({
                        "type": "architecture",
                        "layer": "layer-2",
                        "title": "Architectural drift detected",
                        "body": f"GenAI validation found architectural drift\n\nSee: {vfile.name}",
                        "labels": ["architecture", "genai-detected", "layer-2"],
                        "priority": "high",
                        "source": "genai-architecture"
                    })

        except Exception as e:
            log(f"Error parsing {vfile.name}: {e}", "ERROR")

    return issues


def parse_performance_analysis() -> List[Dict]:
    """Parse system performance analysis for optimization opportunities."""
    issues = []

    # Look for performance analysis results
    # (This would parse output from /test system-performance)
    # For now, return empty - will be implemented when command exists

    return issues


def check_existing_issue(title: str) -> Optional[str]:
    """Check if issue with similar title already exists."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--search", f"{title} in:title", "--json", "number,title"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            issues = json.loads(result.stdout)
            if issues:
                return issues[0]["number"]

    except Exception as e:
        log(f"Error checking existing issues: {e}", "WARN")

    return None


def create_github_issue(issue: Dict) -> Optional[str]:
    """Create GitHub Issue using gh CLI."""
    title = issue["title"]
    body = issue["body"]
    labels = ",".join(issue["labels"])

    # Check for duplicates
    existing = check_existing_issue(title)
    if existing:
        log(f"Skipping duplicate issue: #{existing} - {title}", "DEBUG")
        return None

    # Check priority threshold
    issue_priority = PRIORITY_LEVELS.get(issue["priority"], 1)
    threshold_priority = PRIORITY_LEVELS.get(TRACK_THRESHOLD, 2)

    if issue_priority < threshold_priority:
        log(f"Skipping low priority issue: {title}", "DEBUG")
        return None

    if DRY_RUN:
        log(f"[DRY RUN] Would create issue: {title}", "INFO")
        return None

    try:
        cmd = [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
            "--label", labels
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            issue_url = result.stdout.strip()
            log(f"✅ Created issue: {issue_url}", "INFO")
            return issue_url
        else:
            log(f"Failed to create issue: {result.stderr}", "ERROR")

    except Exception as e:
        log(f"Error creating issue: {e}", "ERROR")

    return None


def collect_issues() -> List[Dict]:
    """Collect all issues from different sources."""
    all_issues = []

    log("Collecting issues from testing results...", "DEBUG")

    # Layer 1: pytest failures
    pytest_issues = parse_pytest_output()
    all_issues.extend(pytest_issues)
    if pytest_issues:
        log(f"Found {len(pytest_issues)} test failures", "INFO")

    # Layer 2: GenAI validation
    genai_issues = parse_genai_validation()
    all_issues.extend(genai_issues)
    if genai_issues:
        log(f"Found {len(genai_issues)} GenAI findings", "INFO")

    # Layer 3: Performance analysis
    perf_issues = parse_performance_analysis()
    all_issues.extend(perf_issues)
    if perf_issues:
        log(f"Found {len(perf_issues)} optimization opportunities", "INFO")

    return all_issues


def track_issues_automatically():
    """Main function - automatically track issues."""
    log("Starting automatic issue tracking...", "INFO")

    # Check prerequisites
    if not check_prerequisites():
        log("Prerequisites not met, skipping", "DEBUG")
        return

    # Collect issues
    issues = collect_issues()

    if not issues:
        log("No issues found to track", "DEBUG")
        return

    log(f"Found {len(issues)} total issues", "INFO")

    # Create GitHub Issues
    created = 0
    skipped = 0

    for issue in issues:
        url = create_github_issue(issue)
        if url:
            created += 1
        else:
            skipped += 1

    # Summary
    if created > 0:
        log(f"✅ Created {created} GitHub issues", "INFO")
        if not DRY_RUN:
            log("View: gh issue list --label automated", "INFO")

    if skipped > 0:
        log(f"⏭️  Skipped {skipped} issues (duplicates or low priority)", "DEBUG")


def main():
    """Entry point."""
    try:
        track_issues_automatically()
    except KeyboardInterrupt:
        log("Interrupted by user", "WARN")
        sys.exit(1)
    except Exception as e:
        log(f"Unexpected error: {e}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
