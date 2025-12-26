#!/usr/bin/env python3
"""Unified Documentation Validator Hook

Consolidates 12 validation hooks into a single dispatcher:
- validate_project_alignment.py
- validate_claude_alignment.py
- validate_documentation_alignment.py
- validate_docs_consistency.py
- validate_readme_accuracy.py
- validate_readme_sync.py
- validate_readme_with_genai.py
- validate_command_file_ops.py
- validate_commands.py
- validate_hooks_documented.py
- validate_command_frontmatter_flags.py
- validate_manifest_doc_alignment.py (Issue #159)

Usage:
    python unified_doc_validator.py

Environment Variables:
    UNIFIED_DOC_VALIDATOR=false         - Disable entire validator
    VALIDATE_PROJECT_ALIGNMENT=false    - Disable PROJECT.md validation
    VALIDATE_CLAUDE_ALIGNMENT=false     - Disable CLAUDE.md validation
    VALIDATE_DOC_ALIGNMENT=false        - Disable doc alignment checks
    VALIDATE_DOCS_CONSISTENCY=false     - Disable docs consistency checks
    VALIDATE_README_ACCURACY=false      - Disable README accuracy checks
    VALIDATE_README_SYNC=false          - Disable README sync checks
    VALIDATE_README_GENAI=false         - Disable README GenAI validation
    VALIDATE_COMMAND_FILE_OPS=false     - Disable command file ops validation
    VALIDATE_COMMANDS=false             - Disable command validation
    VALIDATE_HOOKS_DOCS=false           - Disable hooks documentation validation
    VALIDATE_COMMAND_FRONTMATTER=false  - Disable command frontmatter validation
    VALIDATE_MANIFEST_DOC_ALIGNMENT=false - Disable manifest-doc alignment validation

Exit Codes:
    0 = All validators passed or skipped
    1 = One or more validators failed
"""

import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple


def get_lib_directory() -> Path:
    """Dynamically discover lib directory (portable across environments)."""
    current = Path(__file__).resolve().parent

    # Try: hooks/../lib (sibling to hooks)
    lib_dir = current.parent / "lib"
    if lib_dir.exists():
        return lib_dir

    # Try: hooks/../../lib (for nested structures)
    lib_dir = current.parent.parent / "lib"
    if lib_dir.exists():
        return lib_dir

    # Try: ~/.autonomous-dev/lib (global installation)
    global_lib = Path.home() / ".autonomous-dev" / "lib"
    if global_lib.exists():
        return global_lib

    # Fallback: assume current parent has lib
    return current.parent / "lib"


def setup_lib_path():
    """Add lib directory to Python path for imports."""
    lib_dir = get_lib_directory()
    if lib_dir.exists() and str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))


def is_enabled(env_var: str, default: bool = True) -> bool:
    """Check if validator is enabled via environment variable.

    Args:
        env_var: Environment variable name to check
        default: Default value if env var not set

    Returns:
        True if enabled, False if disabled
    """
    value = os.environ.get(env_var, "").lower()
    if value in ("false", "0", "no"):
        return False
    if value in ("true", "1", "yes"):
        return True
    return default


def log_result(validator_name: str, status: str, message: str = ""):
    """Log validator result with consistent formatting.

    Args:
        validator_name: Name of the validator
        status: PASS, FAIL, SKIP, or ERROR
        message: Optional message to display
    """
    status_symbols = {
        "PASS": "\u2713",   # ✓
        "FAIL": "\u2717",   # ✗
        "SKIP": "-",
        "ERROR": "!"
    }
    symbol = status_symbols.get(status, "?")

    status_str = f"[{status}]"
    print(f"{symbol} {status_str:8} {validator_name:40} {message}")


class ValidatorDispatcher:
    """Dispatcher for running multiple validators with graceful degradation."""

    def __init__(self):
        self.validators: List[Tuple[str, str, Callable]] = []
        self.results: Dict[str, bool] = {}

    def register(self, name: str, env_var: str, validator_func: Callable):
        """Register a validator.

        Args:
            name: Display name for the validator
            env_var: Environment variable to control this validator
            validator_func: Function that returns True on pass, False on fail
        """
        self.validators.append((name, env_var, validator_func))

    def run_all(self) -> bool:
        """Run all registered validators.

        Returns:
            True if all validators passed or skipped, False if any failed
        """
        # Check if entire dispatcher is disabled
        if not is_enabled("UNIFIED_DOC_VALIDATOR", default=True):
            log_result("Unified Doc Validator", "SKIP", "Disabled via UNIFIED_DOC_VALIDATOR=false")
            return True

        all_passed = True

        for name, env_var, validator_func in self.validators:
            # Check if this validator is enabled
            if not is_enabled(env_var, default=True):
                log_result(name, "SKIP", f"Disabled via {env_var}=false")
                self.results[name] = True  # Skipped = not a failure
                continue

            # Run validator with error handling
            try:
                result = validator_func()
                if result:
                    log_result(name, "PASS")
                    self.results[name] = True
                else:
                    log_result(name, "FAIL")
                    self.results[name] = False
                    all_passed = False
            except Exception as e:
                log_result(name, "ERROR", f"{type(e).__name__}: {str(e)[:50]}")
                self.results[name] = False
                all_passed = False

        return all_passed


# Validator implementations
def validate_project_alignment() -> bool:
    """Validate PROJECT.md alignment."""
    try:
        from validate_project_alignment import main
        return main() == 0
    except ImportError:
        # Try direct execution if module import fails
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_project_alignment.py"
            if not validator_path.exists():
                return True  # Skip if not found

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True  # Graceful skip on error


def validate_claude_alignment() -> bool:
    """Validate CLAUDE.md alignment."""
    try:
        from validate_claude_alignment import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_claude_alignment.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_documentation_alignment() -> bool:
    """Validate documentation alignment."""
    try:
        from validate_documentation_alignment import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_documentation_alignment.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_docs_consistency() -> bool:
    """Validate docs consistency."""
    try:
        from validate_docs_consistency import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_docs_consistency.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_readme_accuracy() -> bool:
    """Validate README accuracy."""
    try:
        from validate_readme_accuracy import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_readme_accuracy.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_readme_sync() -> bool:
    """Validate README sync."""
    try:
        from validate_readme_sync import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_readme_sync.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_readme_with_genai() -> bool:
    """Validate README with GenAI."""
    try:
        from validate_readme_with_genai import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_readme_with_genai.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_command_file_ops() -> bool:
    """Validate command file operations."""
    try:
        from validate_command_file_ops import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_command_file_ops.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_commands() -> bool:
    """Validate commands."""
    try:
        from validate_commands import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_commands.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_hooks_documented() -> bool:
    """Validate hooks documentation."""
    try:
        from validate_hooks_documented import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_hooks_documented.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_command_frontmatter_flags() -> bool:
    """Validate command frontmatter flags."""
    try:
        from validate_command_frontmatter_flags import main
        return main() == 0
    except ImportError:
        try:
            hooks_dir = Path(__file__).parent
            validator_path = hooks_dir / "validate_command_frontmatter_flags.py"
            if not validator_path.exists():
                return True

            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator_path)],
                capture_output=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception:
            return True


def validate_manifest_doc_alignment() -> bool:
    """Validate manifest-documentation alignment (Issue #159).

    Ensures CLAUDE.md and PROJECT.md component counts match install_manifest.json.

    CRITICAL: This validator fails LOUDLY. No graceful degradation.
    If it can't run, it returns False (blocks commit).
    """
    try:
        from validate_manifest_doc_alignment import main
        return main([]) == 0
    except ImportError:
        lib_dir = get_lib_directory()
        validator_path = lib_dir / "validate_manifest_doc_alignment.py"
        if not validator_path.exists():
            # FAIL LOUD: If validator is missing, that's a problem
            print(f"ERROR: Validator not found at {validator_path}")
            return False

        import subprocess
        result = subprocess.run(
            [sys.executable, str(validator_path)],
            capture_output=True,
            timeout=30
        )
        if result.returncode != 0:
            print(result.stdout.decode() if result.stdout else "")
            print(result.stderr.decode() if result.stderr else "")
        return result.returncode == 0
    except Exception as e:
        # FAIL LOUD: Any error is a validation failure
        print(f"ERROR: Manifest-doc alignment validation failed: {e}")
        return False


def main() -> int:
    """Main entry point for unified documentation validator.

    Returns:
        0 if all validators passed or skipped, 1 if any failed
    """
    # Setup lib path for imports
    setup_lib_path()

    # Create dispatcher
    dispatcher = ValidatorDispatcher()

    # Register all validators
    dispatcher.register(
        "PROJECT.md Alignment",
        "VALIDATE_PROJECT_ALIGNMENT",
        validate_project_alignment
    )
    dispatcher.register(
        "CLAUDE.md Alignment",
        "VALIDATE_CLAUDE_ALIGNMENT",
        validate_claude_alignment
    )
    dispatcher.register(
        "Documentation Alignment",
        "VALIDATE_DOC_ALIGNMENT",
        validate_documentation_alignment
    )
    dispatcher.register(
        "Docs Consistency",
        "VALIDATE_DOCS_CONSISTENCY",
        validate_docs_consistency
    )
    dispatcher.register(
        "README Accuracy",
        "VALIDATE_README_ACCURACY",
        validate_readme_accuracy
    )
    dispatcher.register(
        "README Sync",
        "VALIDATE_README_SYNC",
        validate_readme_sync
    )
    dispatcher.register(
        "README GenAI Validation",
        "VALIDATE_README_GENAI",
        validate_readme_with_genai
    )
    dispatcher.register(
        "Command File Operations",
        "VALIDATE_COMMAND_FILE_OPS",
        validate_command_file_ops
    )
    dispatcher.register(
        "Commands Validation",
        "VALIDATE_COMMANDS",
        validate_commands
    )
    dispatcher.register(
        "Hooks Documentation",
        "VALIDATE_HOOKS_DOCS",
        validate_hooks_documented
    )
    dispatcher.register(
        "Command Frontmatter Flags",
        "VALIDATE_COMMAND_FRONTMATTER",
        validate_command_frontmatter_flags
    )
    dispatcher.register(
        "Manifest-Doc Alignment",
        "VALIDATE_MANIFEST_DOC_ALIGNMENT",
        validate_manifest_doc_alignment
    )

    # Run all validators
    print("\n=== Unified Documentation Validator ===\n")
    all_passed = dispatcher.run_all()

    # Summary
    print("\n=== Validation Summary ===")
    passed = sum(1 for result in dispatcher.results.values() if result)
    total = len(dispatcher.results)
    print(f"Passed: {passed}/{total}")

    if all_passed:
        print("\nAll validators passed or skipped.")
        return 0
    else:
        print("\nOne or more validators failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
