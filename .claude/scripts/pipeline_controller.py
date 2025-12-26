#!/usr/bin/env python3
"""
Pipeline Controller - Manages progress display subprocess lifecycle

Handles starting, stopping, and monitoring the progress display process.
Ensures clean shutdown and prevents multiple concurrent displays.

Features:
- Start display subprocess in background
- Stop display gracefully or forcefully
- Track PID for process management
- Handle signals (SIGTERM, SIGINT)
- Automatic cleanup on exit
- Prevent multiple concurrent displays

Usage:
    # Start display
    controller = PipelineController(session_file=Path("session.json"))
    controller.start_display()

    # ... pipeline runs ...

    # Stop display
    controller.stop_display()
"""

import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Any


class PipelineController:
    """Controller for managing progress display subprocess."""

    def __init__(self, session_file: Path, pid_dir: Optional[Path] = None):
        """Initialize pipeline controller.

        Args:
            session_file: Path to JSON session file to display
            pid_dir: Directory for PID file (default: temp dir)
        """
        self.session_file = session_file
        self.display_process: Optional[subprocess.Popen] = None

        # Create PID file path
        if pid_dir is None:
            pid_dir = Path("/tmp")
        self.pid_file = pid_dir / f"progress_display_{os.getpid()}.pid"

        # Register cleanup on exit
        atexit.register(self.cleanup)

    def start_display(self, refresh_interval: float = 0.5) -> bool:
        """Start the progress display subprocess.

        Args:
            refresh_interval: Display refresh interval in seconds

        Returns:
            True if started successfully, False otherwise
        """
        # Check if already running
        if self.display_process and self.is_display_running():
            return False

        try:
            # Get path to progress_display.py
            script_dir = Path(__file__).parent
            display_script = script_dir / "progress_display.py"

            if not display_script.exists():
                raise FileNotFoundError(f"progress_display.py not found at {display_script}")

            # Start subprocess
            self.display_process = subprocess.Popen(
                [
                    sys.executable,
                    str(display_script),
                    str(self.session_file),
                    "--refresh",
                    str(refresh_interval)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Create new process group
            )

            # Write PID file
            self.pid_file.write_text(str(self.display_process.pid))

            return True

        except (FileNotFoundError, PermissionError):
            # Re-raise so caller can handle
            raise
        except Exception as e:
            # Other errors - log but don't crash
            print(f"Error starting display: {e}", file=sys.stderr)
            return False

    def stop_display(self, timeout: int = 5) -> bool:
        """Stop the progress display subprocess.

        Args:
            timeout: Seconds to wait for graceful shutdown

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.display_process:
            return True

        try:
            # Try graceful termination first
            self.display_process.terminate()

            try:
                self.display_process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                self.display_process.kill()
                self.display_process.wait()

            self.display_process = None

            # Clean up PID file
            if self.pid_file.exists():
                self.pid_file.unlink()

            return True

        except ProcessLookupError:
            # Process already gone
            self.display_process = None
            if self.pid_file.exists():
                self.pid_file.unlink()
            return True

        except Exception as e:
            print(f"Error stopping display: {e}", file=sys.stderr)
            return False

    def is_display_running(self) -> bool:
        """Check if display process is still running.

        Returns:
            True if running, False otherwise
        """
        if not self.display_process:
            return False

        # Check if process has exited
        return_code = self.display_process.poll()
        return return_code is None

    def get_status(self) -> Dict[str, Any]:
        """Get display process status information.

        Returns:
            Dictionary with status info
        """
        if not self.display_process:
            return {
                "running": False,
                "pid": None,
                "session_file": str(self.session_file)
            }

        return {
            "running": self.is_display_running(),
            "pid": self.display_process.pid,
            "session_file": str(self.session_file),
            "pid_file": str(self.pid_file)
        }

    def cleanup(self):
        """Cleanup on exit - stop display process."""
        if self.display_process and self.is_display_running():
            self.stop_display()

    def handle_signal(self, signum, frame):
        """Handle termination signals.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        self.cleanup()
        sys.exit(0)


def main():
    """Main entry point for CLI usage."""

    if len(sys.argv) < 2:
        print("Usage: pipeline_controller.py <session_file.json>")
        print("\nExample:")
        print("  pipeline_controller.py docs/sessions/20251104-120000-pipeline.json")
        sys.exit(1)

    session_file = Path(sys.argv[1])

    if not session_file.exists():
        print(f"Error: Session file not found: {session_file}")
        sys.exit(1)

    controller = PipelineController(session_file=session_file)

    # Register signal handlers
    signal.signal(signal.SIGTERM, controller.handle_signal)
    signal.signal(signal.SIGINT, controller.handle_signal)

    # Start display
    print(f"Starting progress display for {session_file.name}...")

    if controller.start_display():
        print(f"Display started (PID: {controller.display_process.pid})")
        print("Press Ctrl+C to stop")

        # Keep running until interrupted
        try:
            controller.display_process.wait()
        except KeyboardInterrupt:
            print("\nStopping display...")
            controller.stop_display()

    else:
        print("Failed to start display")
        sys.exit(1)


if __name__ == "__main__":
    main()
