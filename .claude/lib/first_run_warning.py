#!/usr/bin/env python3
"""
First-run warning system for autonomous-dev plugin.

Interactive warning system for opt-out consent on first /auto-implement run.

Features:
- Displays first-run warning about automatic git operations
- Prompts user for consent (Y/n, defaults to yes)
- Records user choice in state file
- Skips warning in non-interactive sessions
- Graceful error handling

Date: 2025-11-11
Issue: #61 (Enable Zero Manual Git Operations by Default)
Agent: implementer

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import os
import sys
from pathlib import Path

# Import user state manager (standard pattern from project libraries)
try:
    from .user_state_manager import (
        UserStateManager,
        is_first_run,
        DEFAULT_STATE_FILE
    )
except ImportError:
    # Direct script execution - add lib dir to path
    lib_dir = Path(__file__).parent.resolve()
    sys.path.insert(0, str(lib_dir))
    from user_state_manager import (
        UserStateManager,
        is_first_run,
        DEFAULT_STATE_FILE
    )


# Exception hierarchy pattern from error-handling-patterns skill:
# BaseException -> Exception -> AutonomousDevError -> DomainError(BaseException) -> SpecificError
class FirstRunWarningError(Exception):
    """Exception raised for first-run warning errors."""
    pass


def render_warning() -> str:
    """
    Render first-run warning message.

    Returns:
        Formatted warning message with user prompt
    """
    warning = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║  🚀 Zero Manual Git Operations (NEW DEFAULT)                ║
║                                                              ║
║  Automatic git operations enabled after /auto-implement:    ║
║                                                              ║
║    ✓ automatic commit with conventional commit message      ║
║    ✓ automatic push to remote                               ║
║    ✓ automatic pull request creation                        ║
║                                                              ║
║  HOW TO OPT OUT:                                            ║
║                                                              ║
║  Add to .env file:                                          ║
║    AUTO_GIT_ENABLED=false                                   ║
║                                                              ║
║  Or disable specific operations:                            ║
║    AUTO_GIT_PUSH=false   # Disable push                     ║
║    AUTO_GIT_PR=false     # Disable PR creation              ║
║                                                              ║
║  See docs/GIT-AUTOMATION.md for details                     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Do you want to enable automatic git operations? (Y/n): """

    return warning


def parse_user_input(user_input: str) -> bool:
    """
    Parse user input for consent.

    Accepts: 'yes', 'y', 'Y', 'YES', '' (empty = yes)
    Rejects: 'no', 'n', 'N', 'NO'

    Args:
        user_input: User input string

    Returns:
        True if accepted, False if rejected

    Raises:
        FirstRunWarningError: If input is invalid
    """
    # Strip whitespace
    user_input = user_input.strip()

    # Empty input defaults to yes
    if not user_input:
        return True

    # Check for yes
    if user_input.lower() in {'yes', 'y'}:
        return True

    # Check for no
    if user_input.lower() in {'no', 'n'}:
        return False

    # Invalid input
    raise FirstRunWarningError(
        f"Invalid input: '{user_input}'. Please enter 'yes' or 'no' (or press Enter for yes)."
    )


def is_interactive_session() -> bool:
    """
    Detect if running in an interactive session.

    Returns:
        True if interactive, False otherwise
    """
    # Check if in CI environment
    if os.environ.get("CI"):
        return False

    # Check if stdin is a TTY
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def show_first_run_warning(
    state_file: Path = DEFAULT_STATE_FILE,
    max_retries: int = 3
) -> bool:
    """
    Show first-run warning and prompt user for consent.

    Args:
        state_file: Path to state file
        max_retries: Maximum number of retry attempts for invalid input

    Returns:
        True if user accepts, False if user rejects

    Raises:
        FirstRunWarningError: If max retries exceeded or interrupted
    """
    # Skip in non-interactive sessions
    if not is_interactive_session():
        # Default to True (opt-out model)
        record_user_choice(accepted=True, state_file=state_file)
        return True

    # Display warning (print to sys.stdout explicitly for tests)
    warning = render_warning()
    sys.stdout.write(warning)
    sys.stdout.flush()

    # Prompt for input with retries
    retry_count = 0
    while retry_count < max_retries:
        try:
            user_input = input()
            accepted = parse_user_input(user_input)

            # Record choice
            record_user_choice(accepted=accepted, state_file=state_file)

            return accepted

        except FirstRunWarningError as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise FirstRunWarningError(
                    f"Maximum retries exceeded. Please run /auto-implement again and enter 'yes' or 'no'."
                )
            sys.stdout.write(f"\n{e}\n")
            sys.stdout.write("Do you want to enable automatic git operations? (Y/n): ")
            sys.stdout.flush()

        except KeyboardInterrupt:
            raise FirstRunWarningError("Interrupted by user")

        except EOFError:
            # End of input - default to yes
            record_user_choice(accepted=True, state_file=state_file)
            return True

    # Should not reach here
    raise FirstRunWarningError("Unexpected error in first-run warning")


def record_user_choice(accepted: bool, state_file: Path = DEFAULT_STATE_FILE) -> None:
    """
    Record user choice in state file.

    Args:
        accepted: True if user accepted, False if rejected
        state_file: Path to state file

    Raises:
        FirstRunWarningError: If recording fails
    """
    try:
        manager = UserStateManager(state_file)
        manager.set_preference("auto_git_enabled", accepted)
        manager.record_first_run_complete()
        manager.save()
    except Exception as e:
        raise FirstRunWarningError(f"Failed to record user choice: {e}")


def should_show_warning(state_file: Path = DEFAULT_STATE_FILE) -> bool:
    """
    Determine whether to show first-run warning.

    Skips warning if:
    - Not first run (user already made a choice)
    - AUTO_GIT_ENABLED env var is set (user already configured)
    - Non-interactive session (can't prompt for input)

    Args:
        state_file: Path to state file

    Returns:
        True if warning should be shown, False otherwise
    """
    # Skip if env var is already set
    if os.environ.get("AUTO_GIT_ENABLED") is not None:
        return False

    # Skip in non-interactive sessions
    if not is_interactive_session():
        return False

    # Show if first run
    return is_first_run(state_file)


if __name__ == "__main__":
    # CLI test
    try:
        result = show_first_run_warning()
        print(f"\nUser choice: {'Accepted' if result else 'Rejected'}")
    except FirstRunWarningError as e:
        print(f"Error: {e}")
        sys.exit(1)
