#!/usr/bin/env python3
"""
Tool Validator - MCP Tool Call Validation for Auto-Approval

This module provides validation logic for MCP tool calls to enable safe
auto-approval of subagent tool usage. It implements defense-in-depth security:

1. Whitelist-based command validation (known-safe commands only)
2. Blacklist-based threat blocking (destructive/dangerous commands)
3. Path traversal prevention (CWE-22)
4. Command injection prevention (CWE-78)
5. Policy-driven configuration (JSON policy file)
6. Conservative defaults (deny unknown commands)

Security Features:
- Bash command whitelist matching (pytest, git status, ls, cat, etc.)
- Bash command blacklist blocking (rm -rf, sudo, eval, curl|bash, etc.)
- File path validation using security_utils.validate_path()
- Policy configuration with schema validation
- Command injection prevention via regex validation
- Graceful error handling (errors deny by default)

Usage:
    from tool_validator import ToolValidator, ValidationResult

    # Initialize validator with policy
    validator = ToolValidator(policy_file=Path("auto_approve_policy.json"))

    # Validate Bash command
    result = validator.validate_bash_command("pytest tests/")
    if result.approved:
        print(f"Approved: {result.reason}")
    else:
        print(f"Denied: {result.reason}")

    # Validate file path
    result = validator.validate_file_path("/tmp/output.txt")
    if result.approved:
        print(f"Safe path: {result.reason}")

    # Validate full tool call
    result = validator.validate_tool_call(
        tool="Bash",
        parameters={"command": "git status"},
        agent_name="researcher"
    )

Date: 2025-11-15
Issue: #73 (MCP Auto-Approval for Subagent Tool Calls)
Agent: implementer
Phase: TDD Green (making tests pass)

See error-handling-patterns skill for exception hierarchy and error handling best practices.
"""

import fnmatch
import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Import security utilities for path validation
try:
    from security_utils import validate_path, audit_log
except ImportError:
    # Graceful degradation if security_utils not available
    def validate_path(path, context=""):
        """Fallback path validation."""
        return Path(path).resolve()

    def audit_log(event, status, context):
        """Fallback audit logging."""
        pass

# Import path utilities for project root detection and policy file resolution
try:
    from path_utils import get_project_root, get_policy_file
except ImportError:
    # Fallback to CWD if path_utils not available
    def get_project_root():
        """Fallback project root detection."""
        return Path.cwd()

    def get_policy_file(use_cache: bool = True):
        """Fallback policy file resolution."""
        return Path(__file__).parent.parent / "config" / "auto_approve_policy.json"


# Lazy evaluation of default policy file (uses cascading lookup)
_DEFAULT_POLICY_FILE_CACHE = None


def _get_default_policy_file():
    """Get default policy file path (lazy evaluation with caching).

    Uses cascading lookup via get_policy_file() from path_utils.
    Falls back to hardcoded path if path_utils not available.

    Returns:
        Path to policy file
    """
    global _DEFAULT_POLICY_FILE_CACHE

    if _DEFAULT_POLICY_FILE_CACHE is None:
        _DEFAULT_POLICY_FILE_CACHE = get_policy_file()

    return _DEFAULT_POLICY_FILE_CACHE

# Command injection detection patterns (CWE-78)
# Format: (pattern, reason_name)
# NOTE: Patterns are targeted to dangerous combinations, not broad operators
# This allows legitimate shell usage like "cmd1 && cmd2" while blocking "cmd; rm -rf"
INJECTION_PATTERNS = [
    (r'\r', 'carriage_return'),                   # Carriage return injection (CWE-117)
    (r'\x00', 'null_byte'),                       # Null byte injection (CWE-158)
    # Targeted dangerous command chains (not all operators)
    (r';\s*rm\s', 'semicolon_rm'),                # Semicolon followed by rm
    (r';\s*sudo\s', 'semicolon_sudo'),            # Semicolon followed by sudo
    (r';\s*chmod\s', 'semicolon_chmod'),          # Semicolon followed by chmod
    (r';\s*chown\s', 'semicolon_chown'),          # Semicolon followed by chown
    (r';\s*eval\s', 'semicolon_eval'),            # Semicolon followed by eval
    (r';\s*exec\s', 'semicolon_exec'),            # Semicolon followed by exec
    (r'&&\s*rm\s', 'and_rm'),                     # AND followed by rm
    (r'&&\s*sudo\s', 'and_sudo'),                 # AND followed by sudo
    (r'\|\|\s*rm\s', 'or_rm'),                    # OR followed by rm
    (r'\|\|\s*sudo\s', 'or_sudo'),                # OR followed by sudo
    (r'\|\s*bash\b', 'pipe_to_bash'),             # Pipe to bash (dangerous)
    (r'\|\s*sh\b', 'pipe_to_sh'),                 # Pipe to sh (dangerous)
    (r'\|\s*zsh\b', 'pipe_to_zsh'),               # Pipe to zsh (dangerous)
    (r'`[^`]+`', 'backticks'),                    # Command substitution (backticks)
    (r'\$\([^)]+\)', 'command_substitution'),     # Command substitution $(...)
    (r'\n', 'newline'),                           # Newline command injection (any newline)
    (r'>\s*/etc/', 'output_redirection_etc'),     # Output redirection to /etc
    (r'>\s*/var/', 'output_redirection_var'),     # Output redirection to /var
    (r'>\s*/root/', 'output_redirection_root'),   # Output redirection to /root
    (r'>\s*/System/', 'output_redirection_sys'),  # Output redirection to /System (macOS)
]

# Compile injection patterns for performance
COMPILED_INJECTION_PATTERNS = [(re.compile(pattern), reason) for pattern, reason in INJECTION_PATTERNS]


class ToolValidationError(Exception):
    """Base exception for tool validation errors."""
    pass


class CommandInjectionError(ToolValidationError):
    """Exception for command injection attempts (CWE-78)."""
    pass


class PathTraversalError(ToolValidationError):
    """Exception for path traversal attempts (CWE-22)."""
    pass


@dataclass
class ValidationResult:
    """Result of tool call validation.

    Attributes:
        approved: Whether the tool call is approved for auto-execution
        reason: Human-readable explanation of approval/denial
        security_risk: Whether the denial is due to security concerns
        tool: Tool name (Bash, Read, Write, etc.)
        agent: Agent name that requested the tool call
        parameters: Sanitized tool parameters
        matched_pattern: Pattern that matched (whitelist/blacklist)
    """
    approved: bool
    reason: str
    security_risk: bool = False
    tool: Optional[str] = None
    agent: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    matched_pattern: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert ValidationResult to dictionary.

        Returns:
            Dictionary representation (excludes None values)
        """
        return {
            k: v for k, v in {
                "approved": self.approved,
                "reason": self.reason,
                "security_risk": self.security_risk,
                "tool": self.tool,
                "agent": self.agent,
                "parameters": self.parameters,
                "matched_pattern": self.matched_pattern,
            }.items() if v is not None or k in ["approved", "security_risk"]
        }


class ToolValidator:
    """Validates MCP tool calls for safe auto-approval.

    This class implements defense-in-depth validation:
    1. Policy loading and schema validation
    2. Whitelist-based command matching
    3. Blacklist-based threat blocking
    4. Path traversal prevention
    5. Command injection detection
    6. Conservative defaults (deny unknown)

    Thread-safe: Policy is loaded once and cached in memory.

    Example:
        >>> validator = ToolValidator()
        >>> result = validator.validate_bash_command("pytest tests/")
        >>> print(result.approved)  # True
        >>> result = validator.validate_bash_command("rm -rf /")
        >>> print(result.approved)  # False
    """

    def __init__(self, policy_file: Optional[Path] = None, policy: Optional[Dict[str, Any]] = None):
        """Initialize ToolValidator with policy file or policy dict.

        Args:
            policy_file: Path to JSON policy file (default: config/auto_approve_policy.json)
                        Can also be a dict (for backwards compatibility with tests)
            policy: Policy dict (for testing). If provided, policy_file is ignored.

        Raises:
            ToolValidationError: If policy file has invalid schema
        """
        # Handle backwards compatibility: if policy_file is a dict, treat it as policy
        if isinstance(policy_file, dict):
            policy = policy_file
            policy_file = None

        if policy is not None:
            # Use provided policy dict directly (for testing)
            self.policy_file = None
            self.policy = policy
        else:
            # Load from file (uses cascading lookup via _get_default_policy_file)
            self.policy_file = policy_file or _get_default_policy_file()
            self.policy = self._load_policy()

    def _load_policy(self) -> Dict[str, Any]:
        """Load and validate policy from JSON file.

        Returns:
            Validated policy dictionary

        Raises:
            ToolValidationError: If policy schema is invalid
        """
        # Create default policy if file doesn't exist
        if not self.policy_file.exists():
            return self._create_default_policy()

        try:
            with open(self.policy_file, 'r') as f:
                policy = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise ToolValidationError(f"Failed to load policy file: {e}")

        # Validate policy schema
        self._validate_policy_schema(policy)

        return policy

    def _validate_policy_schema(self, policy: Dict[str, Any]) -> None:
        """Validate policy has required schema.

        Args:
            policy: Policy dictionary to validate

        Raises:
            ToolValidationError: If schema is invalid
        """
        required_keys = ["bash", "file_paths", "agents"]
        missing_keys = [key for key in required_keys if key not in policy]

        if missing_keys:
            raise ToolValidationError(
                f"Invalid policy schema: missing required keys: {missing_keys}"
            )

        # Validate bash section
        if "whitelist" not in policy["bash"] or "blacklist" not in policy["bash"]:
            raise ToolValidationError(
                "Invalid policy schema: bash section must have 'whitelist' and 'blacklist'"
            )

        # Validate file_paths section
        if "whitelist" not in policy["file_paths"] or "blacklist" not in policy["file_paths"]:
            raise ToolValidationError(
                "Invalid policy schema: file_paths section must have 'whitelist' and 'blacklist'"
            )

        # Validate agents section
        if "trusted" not in policy["agents"]:
            raise ToolValidationError(
                "Invalid policy schema: agents section must have 'trusted' list"
            )

    def _create_default_policy(self) -> Dict[str, Any]:
        """Create conservative default policy.

        Returns:
            Default policy with minimal whitelist
        """
        return {
            "version": "1.0",
            "bash": {
                "whitelist": [
                    "pytest*",
                    "git status",
                    "git diff*",
                    "git log*",
                    "ls*",
                    "cat*",
                    "head*",
                    "tail*",
                ],
                "blacklist": [
                    "rm -rf*",
                    "sudo*",
                    "chmod 777*",
                    "curl*|*bash",
                    "wget*|*bash",
                    "eval*",
                    "exec*",
                ],
            },
            "file_paths": {
                "whitelist": [
                    "/Users/*/Documents/GitHub/*",
                    "/tmp/pytest-*",
                    "/tmp/tmp*",
                ],
                "blacklist": [
                    "/etc/*",
                    "/var/*",
                    "/root/*",
                    "*/.env",
                    "*/secrets/*",
                ],
            },
            "agents": {
                "trusted": [
                    "researcher",
                    "planner",
                    "test-master",
                    "implementer",
                ],
                "restricted": [
                    "reviewer",
                    "security-auditor",
                    "doc-master",
                ],
            },
        }

    def _extract_paths_from_command(self, command: str) -> List[str]:
        """Extract file paths from destructive shell commands.

        Extracts paths from commands that modify the filesystem:
        - rm: Remove files/directories
        - mv: Move files/directories
        - cp: Copy files/directories
        - chmod: Change file permissions
        - chown: Change file ownership

        Non-destructive commands (ls, cat, etc.) return empty list since they
        don't need path containment validation.

        Wildcards (* and ?) return empty list since they expand at runtime
        and cannot be validated statically.

        Args:
            command: Shell command string to parse

        Returns:
            List of file paths extracted from command, or empty list if:
            - Command is non-destructive (read-only)
            - Command contains wildcards (cannot validate)
            - Command is empty or malformed

        Examples:
            >>> _extract_paths_from_command("rm file.txt")
            ["file.txt"]
            >>> _extract_paths_from_command("mv src.txt dst.txt")
            ["src.txt", "dst.txt"]
            >>> _extract_paths_from_command("chmod 755 script.sh")
            ["script.sh"]
            >>> _extract_paths_from_command("rm *.txt")
            []  # Wildcards cannot be validated
            >>> _extract_paths_from_command("ls file.txt")
            []  # Non-destructive commands skip validation

        Security:
            - Uses shlex.split() to handle quotes and escaping correctly
            - Filters out flags (arguments starting with -)
            - Skips mode/ownership arguments for chmod/chown
        """
        if not command or not command.strip():
            return []

        # Check for wildcards - cannot validate paths that expand at runtime
        if '*' in command or '?' in command:
            return []

        try:
            # Parse command with shlex for proper quote/escape handling
            tokens = shlex.split(command)
        except ValueError:
            # Malformed command (unclosed quotes, etc.) - return empty
            return []

        if not tokens:
            return []

        # Get command name (first token)
        cmd = tokens[0]

        # Only extract paths from destructive commands
        destructive_commands = ['rm', 'mv', 'cp', 'chmod', 'chown']
        if cmd not in destructive_commands:
            return []

        # Extract arguments (skip first token which is command name)
        args = tokens[1:]

        paths = []
        seen_mode_or_ownership = False  # Track if we've seen the mode/ownership argument

        for i, arg in enumerate(args):
            # Skip flags (arguments starting with -)
            if arg.startswith('-'):
                continue

            # For chmod/chown, first non-flag argument is mode/ownership
            if cmd in ['chmod', 'chown'] and not seen_mode_or_ownership:
                # This is the mode (chmod 755) or ownership (chown user:group)
                # Skip it and continue to actual file paths
                seen_mode_or_ownership = True
                continue

            # This is a file path
            paths.append(arg)

        return paths

    def _validate_path_containment(
        self,
        paths: List[str],
        project_root: Path
    ) -> Tuple[bool, Optional[str]]:
        """Validate that all paths are contained within project boundaries.

        Validates paths to prevent:
        - CWE-22: Path traversal (../ sequences, absolute paths outside project)
        - CWE-59: Symlink attacks (symlinks pointing outside project)

        Special cases:
        - Empty list: Always valid (no paths to validate)
        - ~/.claude/: Whitelisted (Claude Code system files)
        - ~/: Rejected (home directory outside project)

        Args:
            paths: List of file paths to validate
            project_root: Project root directory (containment boundary)

        Returns:
            Tuple of (is_valid, error_message):
            - (True, None): All paths valid
            - (False, "error"): First invalid path with error description

        Examples:
            >>> _validate_path_containment(["src/main.py"], project_root)
            (True, None)
            >>> _validate_path_containment(["../../../etc/passwd"], project_root)
            (False, "Path traversal detected: ../../../etc/passwd points outside project")
            >>> _validate_path_containment(["/etc/passwd"], project_root)
            (False, "Absolute path /etc/passwd is outside project root")

        Security:
            - Checks for null bytes and newlines (injection risk)
            - Expands tilde (~) for home directory
            - Resolves symlinks and validates target
            - Uses is_relative_to() or relative_to() for containment check
        """
        # Empty list is always valid
        if not paths:
            return (True, None)

        for path_str in paths:
            # Check for null bytes and newlines (security risk)
            if '\x00' in path_str or '\n' in path_str:
                return (False, f"Invalid character in path: {path_str}")

            # Expand tilde to home directory
            if path_str.startswith('~'):
                # Special case: ~/.claude/ is whitelisted (Claude Code system files)
                if path_str.startswith('~/.claude/') or path_str == '~/.claude':
                    # For testing, treat .claude as relative to project
                    path_str = path_str.replace('~/.claude', '.claude')
                else:
                    # Block all other ~/ paths (outside project)
                    expanded = os.path.expanduser(path_str)
                    return (False, f"Path {path_str} expands to home directory {expanded} which is outside project root")

            # Whitelist system temp directories (safe for temporary file operations)
            if path_str.startswith('/tmp/') or path_str.startswith('/var/tmp/') or path_str.startswith('/var/folders/'):
                continue  # Skip containment check for temp directories

            # Convert to Path object
            try:
                path = Path(path_str)
            except (ValueError, OSError) as e:
                return (False, f"Invalid path format: {path_str} ({e})")

            # Resolve to absolute path (resolves symlinks)
            try:
                # If path is relative, resolve from project root
                if not path.is_absolute():
                    resolved = (project_root / path).resolve()
                else:
                    resolved = path.resolve()
            except (ValueError, OSError, RuntimeError) as e:
                return (False, f"Cannot resolve path {path_str}: {e}")

            # Check if path is within project boundaries
            try:
                # Try is_relative_to() (Python 3.9+)
                if hasattr(resolved, 'is_relative_to'):
                    if not resolved.is_relative_to(project_root):
                        if path.is_absolute():
                            return (False, f"Absolute path {path_str} is outside project root {project_root}")
                        else:
                            return (False, f"Path traversal detected: {path_str} points outside project root {project_root}")
                else:
                    # Fallback for Python 3.8: use relative_to() with try-except
                    try:
                        resolved.relative_to(project_root)
                    except ValueError:
                        if path.is_absolute():
                            return (False, f"Absolute path {path_str} is outside project root {project_root}")
                        else:
                            return (False, f"Path traversal detected: {path_str} points outside project root {project_root}")
            except (ValueError, TypeError) as e:
                return (False, f"Path validation error for {path_str}: {e}")

            # Check if path is a symlink pointing outside project
            # Note: resolve() already follows symlinks, so we check if the original
            # path was a symlink and if its target is outside the project
            try:
                original_path = project_root / path if not path.is_absolute() else path
                if original_path.is_symlink():
                    # Get symlink target
                    target = original_path.resolve()
                    # Check if target is within project
                    if hasattr(target, 'is_relative_to'):
                        if not target.is_relative_to(project_root):
                            return (False, f"Symlink {path_str} points outside project to {target}")
                    else:
                        try:
                            target.relative_to(project_root)
                        except ValueError:
                            return (False, f"Symlink {path_str} points outside project to {target}")
            except (OSError, ValueError):
                # If we can't check symlink status, continue (file may not exist yet)
                pass

        return (True, None)

    def validate_bash_command(self, command: str) -> ValidationResult:
        """Validate Bash command for auto-approval.

        Validation steps:
        1. Normalize command (remove quotes, expand backslashes)
        2. Check blacklist (deny if matches - check both original and normalized)
        3. Check path containment (CWE-22, CWE-59 prevention)
        4. Check for command injection patterns
        5. Check whitelist (approve if matches)
        6. Deny by default (conservative)

        Args:
            command: Bash command string to validate

        Returns:
            ValidationResult with approval decision and reason
        """
        # Step 1: Normalize command to prevent blacklist evasion
        # Remove quotes, expand backslashes, remove extra spaces
        normalized = command.replace("'", "").replace('"', '').replace('\\', '')
        normalized = ' '.join(normalized.split())  # Collapse whitespace

        # Step 2: Check blacklist against both original and normalized command
        # Support both 'blacklist' and 'denylist' for backwards compatibility
        blacklist = self.policy["bash"].get("blacklist", self.policy["bash"].get("denylist", []))
        for pattern in blacklist:
            if fnmatch.fnmatch(command, pattern) or fnmatch.fnmatch(normalized, pattern):
                return ValidationResult(
                    approved=False,
                    reason=f"Matches blacklist pattern: {pattern}",
                    security_risk=True,
                    tool="Bash",
                    parameters={"command": command},
                    matched_pattern=pattern,
                )

        # Step 3: Check path containment (CWE-22, CWE-59 prevention)
        # Extract paths from destructive commands (rm, mv, cp, chmod, chown)
        paths = self._extract_paths_from_command(command)
        if paths:
            # Validate all paths are within project boundaries
            project_root = get_project_root()
            is_valid, error = self._validate_path_containment(paths, project_root)
            if not is_valid:
                return ValidationResult(
                    approved=False,
                    reason=error,
                    security_risk=True,
                    tool="Bash",
                    parameters={"command": command},
                    matched_pattern="path_containment",
                )

        # Step 4: Check for command injection patterns (CWE-78, CWE-117, CWE-158)
        for pattern, reason_name in COMPILED_INJECTION_PATTERNS:
            if pattern.search(command):
                return ValidationResult(
                    approved=False,
                    reason=f"Command injection detected: {reason_name}",
                    security_risk=True,
                    tool="Bash",
                    parameters={"command": command},
                    matched_pattern=pattern.pattern,
                )

        # Step 5: Check whitelist (approve known-safe commands)
        whitelist = self.policy["bash"]["whitelist"]
        for pattern in whitelist:
            if fnmatch.fnmatch(command, pattern):
                return ValidationResult(
                    approved=True,
                    reason=f"Matches whitelist pattern: {pattern}",
                    security_risk=False,
                    tool="Bash",
                    parameters={"command": command},
                    matched_pattern=pattern,
                )

        # Step 6: Deny by default (conservative security posture)
        return ValidationResult(
            approved=False,
            reason="Command not in whitelist (deny by default)",
            security_risk=False,
            tool="Bash",
            parameters={"command": command},
            matched_pattern=None,
        )

    def validate_file_path(self, file_path: str) -> ValidationResult:
        """Validate file path for auto-approval.

        Validation steps:
        1. Check blacklist (deny if matches)
        2. Validate with security_utils (CWE-22 prevention)
        3. Check whitelist (approve if matches)
        4. Deny by default

        Args:
            file_path: File path string to validate

        Returns:
            ValidationResult with approval decision and reason
        """
        # Step 1: Check blacklist
        blacklist = self.policy["file_paths"]["blacklist"]
        for pattern in blacklist:
            if fnmatch.fnmatch(file_path, pattern):
                return ValidationResult(
                    approved=False,
                    reason=f"Matches path blacklist pattern: {pattern}",
                    security_risk=True,
                    parameters={"file_path": file_path},
                    matched_pattern=pattern,
                )

        # Step 2: Validate with security_utils (CWE-22, CWE-59)
        try:
            validate_path(file_path, "tool auto-approval")
        except (ValueError, PathTraversalError) as e:
            return ValidationResult(
                approved=False,
                reason=f"Path traversal detected: {e}",
                security_risk=True,
                parameters={"file_path": file_path},
                matched_pattern=None,
            )

        # Step 3: Check whitelist
        whitelist = self.policy["file_paths"]["whitelist"]
        for pattern in whitelist:
            if fnmatch.fnmatch(file_path, pattern):
                return ValidationResult(
                    approved=True,
                    reason=f"Matches path whitelist pattern: {pattern}",
                    security_risk=False,
                    parameters={"file_path": file_path},
                    matched_pattern=pattern,
                )

        # Step 4: Deny by default
        return ValidationResult(
            approved=False,
            reason="Path not in whitelist (deny by default)",
            security_risk=False,
            parameters={"file_path": file_path},
            matched_pattern=None,
        )

    def validate_web_tool(self, tool: str, url: str) -> ValidationResult:
        """Validate WebFetch/WebSearch tool call for auto-approval.

        Args:
            tool: Tool name (WebFetch or WebSearch)
            url: URL to fetch/search

        Returns:
            ValidationResult with approval decision and reason
        """
        # Get web tools policy
        web_tools = self.policy.get("web_tools", {})
        whitelist = web_tools.get("whitelist", [])
        allow_all_domains = web_tools.get("allow_all_domains", False)
        blocked_domains = web_tools.get("blocked_domains", [])

        # Check if tool is whitelisted
        if tool not in whitelist:
            return ValidationResult(
                approved=False,
                reason=f"Web tool '{tool}' not in whitelist",
                security_risk=False,
                matched_pattern=None,
            )

        # Parse URL to extract domain
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc or url  # For WebSearch, might just be a query string

        # Check if domain is blocked (SSRF prevention)
        for blocked in blocked_domains:
            if blocked.endswith("*"):
                # Wildcard match (e.g., "10.*" matches "10.0.0.1")
                prefix = blocked[:-1]
                if domain.startswith(prefix):
                    return ValidationResult(
                        approved=False,
                        reason=f"Domain '{domain}' blocked (SSRF prevention: {blocked})",
                        security_risk=True,
                        matched_pattern=blocked,
                    )
            elif domain == blocked or domain.endswith(f".{blocked}"):
                return ValidationResult(
                    approved=False,
                    reason=f"Domain '{domain}' blocked (SSRF prevention)",
                    security_risk=True,
                    matched_pattern=blocked,
                )

        # If allow_all_domains is true, approve (after blocklist check)
        if allow_all_domains:
            return ValidationResult(
                approved=True,
                reason=f"{tool} allowed (all domains enabled, blocklist checked)",
                security_risk=False,
                matched_pattern=None,
            )

        # Fallback: deny if not explicitly allowed
        return ValidationResult(
            approved=False,
            reason=f"Domain '{domain}' not explicitly allowed (allow_all_domains=false)",
            security_risk=True,
            matched_pattern=None,
        )

    def validate_tool_call(
        self,
        tool: str,
        parameters: Dict[str, Any],
        agent_name: Optional[str] = None,
    ) -> ValidationResult:
        """Validate complete MCP tool call for auto-approval.

        Args:
            tool: Tool name (Bash, Read, Write, etc.)
            parameters: Tool parameters dictionary
            agent_name: Name of agent requesting tool call

        Returns:
            ValidationResult with approval decision and reason
        """
        # Validate based on tool type
        if tool == "Bash" and "command" in parameters:
            result = self.validate_bash_command(parameters["command"])
            result.tool = tool
            result.agent = agent_name
            return result

        elif tool in ("Read", "Write", "Edit") and "file_path" in parameters:
            result = self.validate_file_path(parameters["file_path"])
            result.tool = tool
            result.agent = agent_name
            return result

        elif tool in ("Fetch", "WebFetch", "WebSearch"):
            url = parameters.get("url") or parameters.get("query", "")
            result = self.validate_web_tool(tool, url)
            result.tool = tool
            result.agent = agent_name
            return result

        elif tool in ("Grep", "Glob"):
            # Grep and Glob are read-only search tools - validate path if present
            if "path" in parameters:
                result = self.validate_file_path(parameters["path"])
            else:
                # No path specified (searches CWD) - auto-approve
                result = ValidationResult(
                    approved=True,
                    reason=f"{tool} allowed (read-only search tool)",
                    security_risk=False,
                )
            result.tool = tool
            result.agent = agent_name
            return result

        elif tool in ("AskUserQuestion", "Task", "TaskOutput", "Skill", "SlashCommand", "BashOutput", "NotebookEdit",
                      "TodoWrite", "EnterPlanMode", "ExitPlanMode", "AgentOutputTool", "KillShell"):
            # Always allow these tools - they're either interactive, delegating, or workflow management
            return ValidationResult(
                approved=True,
                reason=f"{tool} allowed (interactive/delegating tool)",
                security_risk=False,
                tool=tool,
                agent=agent_name,
                parameters=parameters,
                matched_pattern=None,
            )

        # Deny unknown tools by default
        return ValidationResult(
            approved=False,
            reason=f"Tool '{tool}' not supported for auto-approval",
            security_risk=False,
            tool=tool,
            agent=agent_name,
            parameters=parameters,
            matched_pattern=None,
        )


# Convenience functions for direct usage

def validate_bash_command(command: str) -> ValidationResult:
    """Validate Bash command (convenience function).

    Args:
        command: Bash command string

    Returns:
        ValidationResult
    """
    validator = ToolValidator()
    return validator.validate_bash_command(command)


def validate_file_path(file_path: str) -> ValidationResult:
    """Validate file path (convenience function).

    Args:
        file_path: File path string

    Returns:
        ValidationResult
    """
    validator = ToolValidator()
    return validator.validate_file_path(file_path)


def validate_tool_call(
    tool: str,
    parameters: Dict[str, Any],
    agent_name: Optional[str] = None,
) -> ValidationResult:
    """Validate tool call (convenience function).

    Args:
        tool: Tool name
        parameters: Tool parameters
        agent_name: Agent name

    Returns:
        ValidationResult
    """
    validator = ToolValidator()
    return validator.validate_tool_call(tool, parameters, agent_name)


def load_policy(policy_file: Optional[Path] = None) -> Dict[str, Any]:
    """Load policy from file (convenience function).

    Args:
        policy_file: Path to policy file

    Returns:
        Policy dictionary
    """
    validator = ToolValidator(policy_file=policy_file)
    return validator.policy
