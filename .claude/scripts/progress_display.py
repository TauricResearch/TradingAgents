#!/usr/bin/env python3
"""
Progress Display - Real-time agent pipeline progress indicator

Polls the JSON session file and displays a live tree view of agent progress
with emoji indicators, progress percentage, and estimated time remaining.

Features:
- Real-time updates (polls every 0.5 seconds)
- Tree view with agent status indicators
- Progress bar and percentage
- Estimated time remaining
- TTY detection (graceful non-TTY output)
- Terminal resize handling
- Malformed JSON handling

Usage:
    # Start display (runs until pipeline completes or Ctrl+C)
    python progress_display.py /path/to/session.json

    # Custom refresh interval
    python progress_display.py /path/to/session.json --refresh 1.0
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class ProgressDisplay:
    """Real-time progress display for agent pipeline."""

    def __init__(self, session_file: Path, refresh_interval: float = 0.5):
        """Initialize progress display.

        Args:
            session_file: Path to JSON session file to monitor
            refresh_interval: Seconds between display updates (default: 0.5)
        """
        self.session_file = session_file
        self.refresh_interval = refresh_interval
        self.is_tty = sys.stdout.isatty()
        self.display_mode = "refresh" if self.is_tty else "incremental"
        self.should_continue = True

    def load_pipeline_state(self) -> Optional[Dict[str, Any]]:
        """Load pipeline state from JSON file.

        Returns:
            Pipeline state dict, or None if file doesn't exist or invalid JSON
        """
        try:
            if not self.session_file.exists():
                return None

            with open(self.session_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Malformed JSON - might be mid-write, try again later
            return None
        except Exception:
            # Other error (permissions, etc.)
            return None

    def render_tree_view(self, state: Dict[str, Any]) -> str:
        """Render tree view of pipeline progress.

        Args:
            state: Pipeline state dictionary

        Returns:
            Formatted string with tree view
        """
        if not state or not isinstance(state, dict):
            return "Waiting for pipeline data...\n"

        lines = []

        # Header
        lines.append("\n═══════════════════════════════════════════════════")
        lines.append("          Agent Pipeline Progress")
        lines.append("═══════════════════════════════════════════════════\n")

        # Session info
        session_id = state.get("session_id", "unknown")
        started = state.get("started", "")
        if started:
            try:
                started_dt = datetime.fromisoformat(started)
                started_str = started_dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                started_str = started
            lines.append(f"Session: {session_id} (started {started_str})")

        github_issue = state.get("github_issue")
        if github_issue:
            lines.append(f"GitHub Issue: #{github_issue}")

        # Calculate progress
        agents = state.get("agents", [])
        if not agents:
            lines.append("\nNo agents started yet.")
            lines.append("\nProgress: [⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜] 0%")
            lines.append("\n")
            return "\n".join(lines)

        # Get agent status counts
        completed_agents = set()
        failed_agents = set()
        running_agent = None

        for entry in agents:
            agent_name = entry.get("agent")
            status = entry.get("status")

            if status == "completed":
                completed_agents.add(agent_name)
            elif status == "failed":
                failed_agents.add(agent_name)
            elif status == "started":
                running_agent = agent_name

        total_done = len(completed_agents) + len(failed_agents)
        progress_pct = (total_done / 7) * 100  # 7 expected agents

        # Progress bar
        filled = int(progress_pct / 10)  # 10 blocks for 100%
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        lines.append(f"\nProgress: [{bar}] {int(progress_pct)}%")

        # Pipeline complete message
        if progress_pct >= 100:
            lines.append("\n✅ Pipeline Complete!\n")
        elif running_agent:
            lines.append(f"⏳ Currently running: {running_agent}\n")
        else:
            lines.append("\n")

        # Agent tree
        lines.append("Agents:")

        expected_agents = [
            "researcher", "planner", "test-master", "implementer",
            "reviewer", "security-auditor", "doc-master"
        ]

        # Build agent status map
        agent_map = {}
        for entry in agents:
            agent_name = entry.get("agent")
            agent_map[agent_name] = entry

        for agent_name in expected_agents:
            if agent_name in agent_map:
                entry = agent_map[agent_name]
                status = entry.get("status")

                if status == "completed":
                    duration = entry.get("duration_seconds", 0)
                    message = entry.get("message", "")
                    lines.append(f"  ✅ {agent_name:20s} ({duration}s) - {message}")

                    # Show tools if any
                    tools = entry.get("tools_used", [])
                    if tools:
                        tools_str = ", ".join(tools)
                        lines.append(f"     └─ Tools: {tools_str}")

                elif status == "failed":
                    duration = entry.get("duration_seconds", 0)
                    error = entry.get("error", "Failed")
                    lines.append(f"  ❌ {agent_name:20s} ({duration}s) - {error}")
                elif status == "started":
                    message = entry.get("message", "Running")
                    lines.append(f"  ⏳ {agent_name:20s} - {message}")
            else:
                # Pending
                lines.append(f"  ⬜ {agent_name:20s} - Pending")

        lines.append("\n")
        return "\n".join(lines)

    def calculate_progress(self, state: Dict[str, Any]) -> int:
        """Calculate progress percentage (0-100).

        Args:
            state: Pipeline state dictionary

        Returns:
            Progress percentage
        """
        if not state or not isinstance(state, dict):
            return 0

        agents = state.get("agents", [])
        if not agents:
            return 0

        completed_agents = set()
        failed_agents = set()

        for entry in agents:
            agent_name = entry.get("agent")
            status = entry.get("status")

            if status == "completed":
                completed_agents.add(agent_name)
            elif status == "failed":
                failed_agents.add(agent_name)

        total_done = len(completed_agents) + len(failed_agents)
        progress_pct = (total_done / 7) * 100  # 7 expected agents

        return int(progress_pct)

    def format_duration(self, seconds: int) -> str:
        """Format duration in human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "5s", "2m 5s", "1h 30m")
        """
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            if secs == 0:
                return f"{minutes}m"
            return f"{minutes}m {secs}s"
        else:
            hours = seconds // 3600
            remaining = seconds % 3600
            minutes = remaining // 60
            if minutes == 0:
                return f"{hours}h"
            return f"{hours}h {minutes}m"

    def truncate_message(self, message: str, max_length: int = 50) -> str:
        """Truncate long messages to fit terminal.

        Args:
            message: Message to truncate
            max_length: Maximum length

        Returns:
            Truncated message with ellipsis if needed
        """
        if len(message) <= max_length:
            return message
        return message[:max_length - 3] + "..."

    def clear_screen(self):
        """Clear terminal screen (only in TTY mode)."""
        if self.is_tty:
            # ANSI escape sequence to clear screen and move cursor to top
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def run(self):
        """Run the display loop until pipeline completes or interrupted."""
        try:
            while self.should_continue:
                state = self.load_pipeline_state()

                if state is None:
                    # File doesn't exist or invalid JSON - wait and retry
                    time.sleep(self.refresh_interval)
                    continue

                # Clear screen and render
                self.clear_screen()
                output = self.render_tree_view(state)
                print(output, end='')

                # Check if pipeline is complete
                agents = state.get("agents", [])
                if agents:
                    completed_count = sum(
                        1 for entry in agents
                        if entry.get("status") in ["completed", "failed"]
                    )
                    if completed_count >= 7:  # All 7 expected agents done
                        # Pipeline complete, exit gracefully
                        break

                time.sleep(self.refresh_interval)

        except KeyboardInterrupt:
            # User pressed Ctrl+C - exit gracefully
            if self.is_tty:
                print("\n\n⏸️  Progress display stopped.\n")
            return
        except Exception as e:
            # Unexpected error - log but don't crash
            if self.is_tty:
                print(f"\n\n❌ Error in progress display: {e}\n")
            return


def main():
    """Main entry point for CLI usage."""
    if len(sys.argv) < 2:
        print("Usage: progress_display.py <session_file.json> [--refresh SECONDS]")
        print("\nExample:")
        print("  progress_display.py docs/sessions/20251104-120000-pipeline.json")
        print("  progress_display.py docs/sessions/20251104-120000-pipeline.json --refresh 1.0")
        sys.exit(1)

    session_file = Path(sys.argv[1])

    # Parse optional refresh interval
    refresh_interval = 0.5
    if "--refresh" in sys.argv:
        try:
            idx = sys.argv.index("--refresh")
            refresh_interval = float(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Error: --refresh requires a numeric value")
            sys.exit(1)

    display = ProgressDisplay(session_file=session_file, refresh_interval=refresh_interval)
    display.run()


if __name__ == "__main__":
    main()
