#!/usr/bin/env python3
"""
GitHub Issue Manager - Automatic issue creation and closure for /auto-implement

Integrates GitHub issues with the autonomous development pipeline:
- Creates issue at start of /auto-implement
- Tracks issue number in pipeline JSON
- Auto-closes issue when pipeline completes
- Gracefully degrades if gh CLI unavailable
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class GitHubIssueManager:
    """Manages GitHub issues for autonomous development pipeline."""

    def __init__(self):
        self.enabled = self._check_gh_available()

    def _check_gh_available(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        return (Path.cwd() / ".git").exists()

    def create_issue(self, title: str, session_file: Path) -> Optional[int]:
        """
        Create GitHub issue for feature implementation.

        Args:
            title: Feature description (issue title)
            session_file: Path to pipeline session JSON

        Returns:
            Issue number if created, None if skipped
        """
        if not self.enabled:
            print("⚠️  GitHub CLI not available - skipping issue creation", file=sys.stderr)
            return None

        if not self._is_git_repo():
            print("⚠️  Not a git repository - skipping issue creation", file=sys.stderr)
            return None

        # Create issue body
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = f"""Automated feature implementation via `/auto-implement`

**Session**: `{session_file.name}`
**Started**: {timestamp}

This issue tracks the autonomous development pipeline execution.
"""

        try:
            # Create issue
            result = subprocess.run(
                [
                    "gh", "issue", "create",
                    "--title", title,
                    "--body", body,
                    "--label", "automated,feature,in-progress"
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"⚠️  Failed to create issue: {result.stderr}", file=sys.stderr)
                return None

            # Extract issue number from output
            # gh CLI returns: "https://github.com/user/repo/issues/123"
            issue_url = result.stdout.strip()
            issue_number = int(issue_url.split("/")[-1])

            print(f"✅ Created GitHub issue #{issue_number}: {title}")
            return issue_number

        except subprocess.TimeoutExpired:
            print("⚠️  GitHub issue creation timed out", file=sys.stderr)
            return None
        except Exception as e:
            print(f"⚠️  Error creating issue: {e}", file=sys.stderr)
            return None

    def close_issue(
        self,
        issue_number: int,
        session_data: Dict[str, Any],
        commits: Optional[list] = None
    ) -> bool:
        """
        Close GitHub issue with summary.

        Args:
            issue_number: Issue number to close
            session_data: Pipeline session data
            commits: Optional list of commit SHAs

        Returns:
            True if closed successfully, False otherwise
        """
        if not self.enabled:
            return False

        # Build closing comment
        agents_summary = []
        for agent in session_data.get("agents", []):
            if agent.get("status") == "completed":
                name = agent["agent"]
                duration = agent.get("duration_seconds", 0)
                agents_summary.append(f"- ✅ {name} ({duration}s)")

        total_duration = sum(
            agent.get("duration_seconds", 0)
            for agent in session_data.get("agents", [])
        )

        commit_info = ""
        if commits:
            commit_info = f"\n\n**Commits**: {', '.join(commits)}"

        comment = f"""Pipeline completed successfully! 🎉

**Agents Executed**:
{chr(10).join(agents_summary)}

**Total Duration**: {total_duration // 60}m {total_duration % 60}s
**Session**: `{session_data.get('session_id', 'unknown')}`{commit_info}

All SDLC steps completed: Research → Plan → Test → Implement → Review → Security → Documentation
"""

        try:
            # Add closing comment
            subprocess.run(
                ["gh", "issue", "comment", str(issue_number), "--body", comment],
                capture_output=True,
                timeout=30,
                check=True
            )

            # Close issue and update labels
            subprocess.run(
                [
                    "gh", "issue", "close", str(issue_number),
                    "--comment", "Automated implementation complete."
                ],
                capture_output=True,
                timeout=30,
                check=True
            )

            # Remove in-progress label, add completed
            subprocess.run(
                [
                    "gh", "issue", "edit", str(issue_number),
                    "--remove-label", "in-progress",
                    "--add-label", "completed"
                ],
                capture_output=True,
                timeout=30,
                check=False  # Don't fail if labels don't exist
            )

            print(f"✅ Closed GitHub issue #{issue_number}")
            return True

        except subprocess.TimeoutExpired:
            print(f"⚠️  Timeout closing issue #{issue_number}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"⚠️  Error closing issue: {e}", file=sys.stderr)
            return False


def main():
    """CLI interface for testing."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: github_issue_manager.py <command> [args...]")
        print("\nCommands:")
        print("  create <title> <session_file>  - Create issue")
        print("  close <number> <session_file>  - Close issue")
        sys.exit(1)

    manager = GitHubIssueManager()
    command = sys.argv[1]

    if command == "create":
        title = sys.argv[2]
        session_file = Path(sys.argv[3])
        issue_number = manager.create_issue(title, session_file)
        if issue_number:
            print(f"Issue #{issue_number}")

    elif command == "close":
        issue_number = int(sys.argv[2])
        session_file = Path(sys.argv[3])
        session_data = json.loads(session_file.read_text())
        manager.close_issue(issue_number, session_data)


if __name__ == "__main__":
    main()
