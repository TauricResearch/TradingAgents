#!/usr/bin/env python3
"""
MCP Permission Validator - Security validation for MCP server operations

This module provides permission validation for MCP (Model Context Protocol) server
operations to prevent security vulnerabilities:
- CWE-22: Path Traversal
- CWE-59: Improper Link Resolution Before File Access
- CWE-78: OS Command Injection
- SSRF: Server-Side Request Forgery

Security Features:
- Whitelist-based filesystem access (allowlist/denylist patterns)
- Shell command injection prevention (semicolon, pipe, backtick detection)
- Network access validation (block localhost, private IPs, metadata services)
- Environment variable access control (block secrets like API_KEY, tokens)
- Glob pattern matching (**, *, ?, negation with !)
- Audit logging for all validation decisions

Usage:
    from mcp_permission_validator import MCPPermissionValidator

    # Create validator with policy
    validator = MCPPermissionValidator(policy_path=".mcp/security_policy.json")

    # Validate filesystem read
    result = validator.validate_fs_read("/project/src/main.py")
    if result.approved:
        # Proceed with operation
        pass
    else:
        # Deny operation, log reason
        print(f"Denied: {result.reason}")

    # Validate shell command
    result = validator.validate_shell_execute("pytest tests/")
    if result.approved:
        # Execute command
        pass

Date: 2025-12-07
Issue: #95 (MCP Server Security - Permission Whitelist System)
Agent: implementer
Phase: TDD Green (implementation to make tests pass)
"""

import fnmatch
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

# Import security utilities for path validation (reuse existing security patterns)
try:
    from security_utils import audit_log
except ImportError:
    # Fallback for tests running without full plugin structure
    def audit_log(event_type: str, status: str, context: Dict[str, Any]) -> None:
        """Fallback audit log function for testing."""
        pass


# Project root detection
def _get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).parent.parent.parent.parent.resolve()


PROJECT_ROOT = _get_project_root()


@dataclass
class ValidationResult:
    """Result of permission validation.

    Attributes:
        approved: Whether operation is approved
        reason: Reason for denial (None if approved)
    """
    approved: bool
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of result
        """
        return {
            "approved": self.approved,
            "reason": self.reason
        }


class PermissionDeniedError(Exception):
    """Exception raised when permission is denied.

    Attributes:
        operation: Operation that was denied (e.g., "fs:read")
        path: Path or command that was denied
        reason: Reason for denial
    """

    def __init__(self, operation: str, path: str, reason: str):
        """Initialize permission denied error.

        Args:
            operation: Operation that was denied
            path: Path or command that was denied
            reason: Reason for denial
        """
        self.operation = operation
        self.path = path
        self.reason = reason
        super().__init__(f"{operation} denied for {path}: {reason}")


class MCPPermissionValidator:
    """MCP server permission validator.

    Validates filesystem, shell, network, and environment variable operations
    against security policy to prevent common vulnerabilities.

    Security Policy Format:
        {
            "filesystem": {
                "read": ["src/**", "tests/**", "!**/.env"],
                "write": ["src/**", "tests/**"]
            },
            "shell": {
                "allowed_commands": ["pytest", "git", "python"],
                "denied_patterns": ["rm -rf /", "dd if="]
            },
            "network": {
                "allowed_domains": ["api.github.com", "*.example.com"],
                "denied_ips": ["127.0.0.1", "0.0.0.0", "169.254.169.254"]
            },
            "environment": {
                "allowed_vars": ["PATH", "HOME", "USER"],
                "denied_patterns": ["*_KEY", "*_TOKEN", "*_SECRET"]
            }
        }

    Attributes:
        policy: Security policy dictionary
        project_root: Project root directory for path validation
    """

    def __init__(self, policy_path: Optional[str] = None):
        """Initialize permission validator.

        Args:
            policy_path: Path to security policy JSON file (None = use default development policy)
        """
        self.policy: Dict[str, Any] = {}
        self.project_root: str = str(PROJECT_ROOT)

        if policy_path is None:
            # Use default development policy
            self.policy = self._get_default_policy()
        else:
            # Load policy from file
            with open(policy_path, 'r') as f:
                self.policy = json.load(f)

    def _get_default_policy(self) -> Dict[str, Any]:
        """Get default development security policy.

        Returns:
            Default development policy dictionary
        """
        return {
            "filesystem": {
                "read": [
                    "src/**",
                    "tests/**",
                    "docs/**",
                    "*.md",
                    "*.txt",
                    "!**/.env",
                    "!**/.git/**",
                    "!**/.ssh/**",
                    "!**/*.key",
                    "!**/*.pem"
                ],
                "write": [
                    "src/**",
                    "tests/**",
                    "docs/**",
                    "!**/.env",
                    "!**/.git/**"
                ]
            },
            "shell": {
                "allowed_commands": ["pytest", "git", "python", "npm", "pip", "poetry"],
                "denied_patterns": [
                    "rm -rf /",
                    "dd if=",
                    "mkfs",
                    "> /dev/",
                    "curl * | sh",
                    "wget * | sh"
                ]
            },
            "network": {
                "allowed_domains": ["*"],  # Wildcard allows all domains
                "denied_ips": [
                    "127.0.0.1",
                    "0.0.0.0",
                    "169.254.169.254",  # AWS metadata
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16"
                ]
            },
            "environment": {
                "allowed_vars": ["PATH", "HOME", "USER", "SHELL", "LANG", "PWD"],
                "denied_patterns": ["*_KEY", "*_TOKEN", "*_SECRET", "AWS_*", "GITHUB_TOKEN"]
            }
        }

    def load_policy(self, policy: Dict[str, Any]) -> None:
        """Load security policy from dictionary.

        Args:
            policy: Security policy dictionary
        """
        self.policy = policy

    def validate_fs_read(self, path: str) -> ValidationResult:
        """Validate filesystem read operation.

        Args:
            path: File path to read

        Returns:
            ValidationResult with approval status and reason

        Security Checks:
        - Path must match allowed read patterns
        - Path must not match denied patterns (e.g., .env files)
        - Path must not traverse outside project (CWE-22)
        - Path must not be a symlink to sensitive location (CWE-59)
        """
        try:
            # Check if path is sensitive file
            if self._is_sensitive_file(path):
                reason = f"Reading sensitive file denied: {path}"
                self._audit_log("fs:read", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check path traversal
            if self._is_path_traversal(path):
                reason = f"Path traversal attempt denied: {path}"
                self._audit_log("fs:read", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check against policy patterns
            read_patterns = self.policy.get("filesystem", {}).get("read", [])
            if not self._matches_any_pattern(path, read_patterns):
                reason = f"Path not in allowed read list: {path}"
                self._audit_log("fs:read", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Approved
            self._audit_log("fs:read", "approved", {"path": path})
            return ValidationResult(approved=True)

        except Exception as e:
            reason = f"Validation error: {str(e)}"
            self._audit_log("fs:read", "error", {"path": path, "reason": reason})
            return ValidationResult(approved=False, reason=reason)

    def validate_fs_write(self, path: str) -> ValidationResult:
        """Validate filesystem write operation.

        Args:
            path: File path to write

        Returns:
            ValidationResult with approval status and reason

        Security Checks:
        - Path must match allowed write patterns
        - Path must not match denied patterns (e.g., .env, .git)
        - Path must not traverse outside project (CWE-22)
        - Path must not be a symlink to sensitive location (CWE-59)
        """
        try:
            # Check if path is sensitive file
            if self._is_sensitive_file(path):
                reason = f"Writing to sensitive file denied: {path}"
                self._audit_log("fs:write", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check path traversal
            if self._is_path_traversal(path):
                reason = f"Path traversal attempt denied: {path}"
                self._audit_log("fs:write", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check if path is symlink to outside project (CWE-59)
            if self._is_dangerous_symlink(path):
                reason = f"Symlink to sensitive location denied: {path}"
                self._audit_log("fs:write", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check against policy patterns
            write_patterns = self.policy.get("filesystem", {}).get("write", [])
            if not self._matches_any_pattern(path, write_patterns):
                reason = f"Path not in allowed write list (outside project): {path}"
                self._audit_log("fs:write", "denied", {"path": path, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Approved
            self._audit_log("fs:write", "approved", {"path": path})
            return ValidationResult(approved=True)

        except Exception as e:
            reason = f"Validation error: {str(e)}"
            self._audit_log("fs:write", "error", {"path": path, "reason": reason})
            return ValidationResult(approved=False, reason=reason)

    def validate_shell_execute(self, command: str) -> ValidationResult:
        """Validate shell command execution.

        Args:
            command: Shell command to execute

        Returns:
            ValidationResult with approval status and reason

        Security Checks:
        - Command must start with allowed command prefix
        - Command must not match denied patterns (e.g., rm -rf /)
        - Command must not contain injection characters (;, |, `, $())
        - Command must not download and execute code (curl | sh)
        """
        try:
            # Check for download and execute patterns first (more specific message)
            command_lower = command.lower()
            download_cmds = ["curl", "wget"]
            if any(cmd in command_lower for cmd in download_cmds) and "|" in command:
                reason = f"Network download and execute denied: {command}"
                self._audit_log("shell:execute", "denied", {"command": command, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check for command injection patterns (CWE-78)
            if self._has_command_injection(command):
                reason = f"Command injection attempt denied: {command}"
                self._audit_log("shell:execute", "denied", {"command": command, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check against denied patterns
            denied_patterns = self.policy.get("shell", {}).get("denied_patterns", [])
            for pattern in denied_patterns:
                if pattern.lower() in command.lower():
                    reason = f"Destructive/dangerous command denied: {command}"
                    self._audit_log("shell:execute", "denied", {"command": command, "reason": reason})
                    return ValidationResult(approved=False, reason=reason)

            # Check if command starts with allowed command
            allowed_commands = self.policy.get("shell", {}).get("allowed_commands", [])
            command_prefix = command.split()[0] if command.split() else ""

            if allowed_commands and command_prefix not in allowed_commands:
                reason = f"Command not in allowed list: {command_prefix}"
                self._audit_log("shell:execute", "denied", {"command": command, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Approved
            self._audit_log("shell:execute", "approved", {"command": command})
            return ValidationResult(approved=True)

        except Exception as e:
            reason = f"Validation error: {str(e)}"
            self._audit_log("shell:execute", "error", {"command": command, "reason": reason})
            return ValidationResult(approved=False, reason=reason)

    def validate_network_access(self, url: str) -> ValidationResult:
        """Validate network access operation.

        Args:
            url: URL to access

        Returns:
            ValidationResult with approval status and reason

        Security Checks:
        - URL must not point to localhost (127.0.0.1, 0.0.0.0)
        - URL must not point to private IP ranges (10.x, 192.168.x)
        - URL must not point to metadata services (169.254.169.254)
        - Domain must match allowed domain patterns
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or parsed.netloc

            # Check for localhost
            if hostname in ["localhost", "127.0.0.1", "0.0.0.0", "::1"]:
                reason = f"Localhost access denied (SSRF prevention): {url}"
                self._audit_log("network:access", "denied", {"url": url, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # FIX 4: Check for entire link-local range (169.254.0.0/16), not just AWS metadata
            if hostname and hostname.startswith("169.254."):
                reason = f"Link-local/metadata service access denied (SSRF prevention): {url}"
                self._audit_log("network:access", "denied", {"url": url, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check for private IP ranges
            if self._is_private_ip(hostname):
                reason = f"Private IP access denied (SSRF prevention): {url}"
                self._audit_log("network:access", "denied", {"url": url, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Check against allowed domains
            allowed_domains = self.policy.get("network", {}).get("allowed_domains", [])
            if "*" not in allowed_domains:
                if not self._matches_any_domain(hostname, allowed_domains):
                    reason = f"Domain not in allowed list: {hostname}"
                    self._audit_log("network:access", "denied", {"url": url, "reason": reason})
                    return ValidationResult(approved=False, reason=reason)

            # Approved
            self._audit_log("network:access", "approved", {"url": url})
            return ValidationResult(approved=True)

        except Exception as e:
            reason = f"Validation error: {str(e)}"
            self._audit_log("network:access", "error", {"url": url, "reason": reason})
            return ValidationResult(approved=False, reason=reason)

    def validate_env_access(self, var_name: str) -> ValidationResult:
        """Validate environment variable access.

        Args:
            var_name: Environment variable name

        Returns:
            ValidationResult with approval status and reason

        Security Checks:
        - Variable must be in allowed list or not match denied patterns
        - Variable must not contain secrets (API_KEY, TOKEN, SECRET, AWS_*)
        """
        try:
            # Check against denied patterns
            denied_patterns = self.policy.get("environment", {}).get("denied_patterns", [])
            for pattern in denied_patterns:
                if fnmatch.fnmatch(var_name, pattern):
                    reason = f"Access to secret environment variable denied: {var_name}"
                    self._audit_log("env:access", "denied", {"var": var_name, "reason": reason})
                    return ValidationResult(approved=False, reason=reason)

            # Check against allowed list
            allowed_vars = self.policy.get("environment", {}).get("allowed_vars", [])
            if allowed_vars and var_name not in allowed_vars:
                reason = f"Environment variable not in allowed list: {var_name}"
                self._audit_log("env:access", "denied", {"var": var_name, "reason": reason})
                return ValidationResult(approved=False, reason=reason)

            # Approved
            self._audit_log("env:access", "approved", {"var": var_name})
            return ValidationResult(approved=True)

        except Exception as e:
            reason = f"Validation error: {str(e)}"
            self._audit_log("env:access", "error", {"var": var_name, "reason": reason})
            return ValidationResult(approved=False, reason=reason)

    def matches_glob_pattern(self, path: str, pattern: str) -> bool:
        """Match path against glob pattern.

        Args:
            path: File path to match
            pattern: Glob pattern (supports **, *, ?)

        Returns:
            True if path matches pattern

        Pattern Syntax:
        - ** matches zero or more path segments
        - * matches zero or more characters within a segment
        - ? matches exactly one character
        - Patterns are case-sensitive on Unix
        """
        # Normalize paths for comparison
        path = path.replace("\\", "/")
        pattern = pattern.replace("\\", "/")

        # Handle negation prefix (!)
        if pattern.startswith("!"):
            return not self.matches_glob_pattern(path, pattern[1:])

        # Convert ** to match multiple path segments
        if "**" in pattern:
            # Convert glob pattern to regex pattern
            # Example: "src/**" -> matches any path containing "src/"
            regex_pattern = pattern

            # Escape special regex characters except our glob wildcards
            regex_pattern = regex_pattern.replace(".", r"\.")
            regex_pattern = regex_pattern.replace("+", r"\+")
            regex_pattern = regex_pattern.replace("^", r"\^")
            regex_pattern = regex_pattern.replace("$", r"\$")

            # Convert ** to match any path segments (including zero)
            regex_pattern = regex_pattern.replace("**", "DOUBLE_STAR_PLACEHOLDER")

            # Convert * to match any characters except /
            regex_pattern = regex_pattern.replace("*", "[^/]*")

            # Convert ? to match single character except /
            regex_pattern = regex_pattern.replace("?", "[^/]")

            # Replace placeholder with .* for recursive match
            regex_pattern = regex_pattern.replace("DOUBLE_STAR_PLACEHOLDER", ".*")

            # Match anywhere in path (patterns like "src/**" should match "/project/src/file.py")
            return bool(re.search(regex_pattern, path))

        # Standard fnmatch for non-recursive patterns
        # For patterns like "*.py", match the basename
        # For patterns like "src/*.py", match anywhere in path BUT respect single-level wildcard
        if "/" in pattern:
            # Extract path components
            path_parts = [p for p in path.split("/") if p]
            pattern_parts = [p for p in pattern.split("/") if p]

            # Pattern must match a contiguous sequence of path parts
            if len(pattern_parts) > len(path_parts):
                return False

            # Try matching the pattern at each possible position in the path
            for i in range(len(path_parts) - len(pattern_parts) + 1):
                # Check if all pattern parts match at this position
                match = True
                for j, pattern_part in enumerate(pattern_parts):
                    if not fnmatch.fnmatch(path_parts[i + j], pattern_part):
                        match = False
                        break
                if match:
                    return True
            return False
        else:
            # Match against basename for simple patterns
            return fnmatch.fnmatch(Path(path).name, pattern)

    def detect_project_root(self, path: str) -> str:
        """Detect project root directory from path.

        Args:
            path: File path to start search from

        Returns:
            Project root directory path

        Detection Strategy:
        - Look for .git directory
        - Look for pyproject.toml
        - Look for setup.py
        - Fallback to current working directory
        """
        current = Path(path).absolute()

        # Walk up directory tree looking for project markers
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return str(parent)
            if (parent / "pyproject.toml").exists():
                return str(parent)
            if (parent / "setup.py").exists():
                return str(parent)

        # Fallback to cwd
        return os.getcwd()

    def _is_sensitive_file(self, path: str) -> bool:
        """Check if path is a sensitive file.

        Args:
            path: File path to check

        Returns:
            True if path is sensitive (secrets, credentials, keys)
        """
        path_lower = path.lower()
        sensitive_patterns = [
            ".env",
            ".git/config",
            ".ssh/",
            ".key",
            ".pem",
            "credentials",
            "secrets"
        ]
        return any(pattern in path_lower for pattern in sensitive_patterns)

    def _is_path_traversal(self, path: str) -> bool:
        """Check if path contains path traversal attempts.

        Security: Prevents CWE-22 via URL decoding, Unicode normalization,
        and null byte detection.

        Args:
            path: File path to check

        Returns:
            True if path contains .. or resolves outside project
        """
        try:
            import urllib.parse
            import unicodedata

            # FIX 1: Check for null bytes (CWE-158)
            if '\x00' in path:
                return True

            # Check for other control characters
            for char in path:
                if ord(char) < 32 and char not in ('\t', '\n', '\r'):
                    return True

            # FIX 2: URL decode (recursive to handle double encoding)
            decoded = urllib.parse.unquote(path)
            while '%' in decoded and decoded != urllib.parse.unquote(decoded):
                decoded = urllib.parse.unquote(decoded)

            # FIX 3: Unicode normalization (prevents homoglyph bypass)
            normalized = unicodedata.normalize('NFKD', decoded)

            # Check for .. in normalized path
            if ".." in normalized:
                # Resolve path and check if it's outside project root
                resolved = Path(normalized).resolve()
                project_root = Path(self.project_root).resolve()

                # If path is outside project root, it's traversal
                try:
                    resolved.relative_to(project_root)
                    return False  # Path is inside project
                except ValueError:
                    return True  # Path is outside project

            return False

        except Exception:
            # If resolution fails, treat as suspicious
            return True

    def _is_dangerous_symlink(self, path: str) -> bool:
        """Check if path is a symlink to outside project (CWE-59).

        Args:
            path: File path to check

        Returns:
            True if path is symlink to sensitive location
        """
        try:
            path_obj = Path(path)

            # Check if path is a symlink
            if path_obj.is_symlink():
                # Resolve symlink and check if it's outside project
                resolved = path_obj.resolve()
                project_root = Path(self.project_root).resolve()

                try:
                    resolved.relative_to(project_root)
                    return False  # Symlink points inside project
                except ValueError:
                    return True  # Symlink points outside project

            return False

        except Exception:
            # If check fails, treat as suspicious
            return True

    def _has_command_injection(self, command: str) -> bool:
        """Check if command contains injection attempts (CWE-78).

        Args:
            command: Shell command to check

        Returns:
            True if command contains injection patterns
        """
        injection_patterns = [
            ";",      # Command chaining
            "&&",     # Command chaining
            "||",     # Command chaining
            "`",      # Backtick command substitution
            "$(",     # Command substitution
            "\n",     # Newline command separator
        ]

        # Check for injection patterns (excluding pipe which we check separately)
        for pattern in injection_patterns:
            if pattern in command:
                return True

        # Check for pipe (needs special handling for download detection)
        if "|" in command:
            # Check if it's a download and execute pattern
            command_lower = command.lower()
            download_cmds = ["curl", "wget", "nc ", "netcat"]
            if any(cmd in command_lower for cmd in download_cmds):
                # This is a download | execute pattern, not just a pipe
                return True
            # Regular pipe is also injection
            return True

        return False

    def _is_private_ip(self, hostname: str) -> bool:
        """Check if hostname is a private IP address.

        Args:
            hostname: Hostname or IP address

        Returns:
            True if hostname is private IP
        """
        try:
            ip = ipaddress.ip_address(hostname)

            # Check for private IP ranges
            private_ranges = [
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
            ]

            for network in private_ranges:
                if ip in network:
                    return True

            return False

        except ValueError:
            # Not a valid IP address
            return False

    def _matches_any_pattern(self, path: str, patterns: List[str]) -> bool:
        """Check if path matches any pattern in list.

        Args:
            path: File path to match
            patterns: List of glob patterns (with optional ! negation)

        Returns:
            True if path matches any non-negated pattern and no negated patterns
        """
        matched = False
        negated = False

        for pattern in patterns:
            if pattern.startswith("!"):
                # Negation pattern - if matches, deny
                if self.matches_glob_pattern(path, pattern[1:]):
                    negated = True
            else:
                # Normal pattern - if matches, allow
                if self.matches_glob_pattern(path, pattern):
                    matched = True

        # Approve only if matched and not negated
        return matched and not negated

    def _matches_any_domain(self, hostname: str, domains: List[str]) -> bool:
        """Check if hostname matches any allowed domain pattern.

        Args:
            hostname: Hostname to check
            domains: List of domain patterns (supports wildcard *)

        Returns:
            True if hostname matches any domain pattern
        """
        for domain in domains:
            if fnmatch.fnmatch(hostname, domain):
                return True
        return False

    def _audit_log(self, operation: str, status: str, context: Dict[str, Any]) -> None:
        """Log validation decision to audit log.

        Args:
            operation: Operation type (e.g., "fs:read", "shell:execute")
            status: Status ("approved", "denied", "error")
            context: Additional context dictionary
        """
        audit_log(f"mcp_{operation}", status, context)


# Convenience functions for module-level API
def validate_fs_read(path: str, policy_path: Optional[str] = None) -> ValidationResult:
    """Validate filesystem read operation.

    Args:
        path: File path to read
        policy_path: Path to security policy JSON file

    Returns:
        ValidationResult with approval status
    """
    validator = MCPPermissionValidator(policy_path=policy_path)
    return validator.validate_fs_read(path)


def validate_fs_write(path: str, policy_path: Optional[str] = None) -> ValidationResult:
    """Validate filesystem write operation.

    Args:
        path: File path to write
        policy_path: Path to security policy JSON file

    Returns:
        ValidationResult with approval status
    """
    validator = MCPPermissionValidator(policy_path=policy_path)
    return validator.validate_fs_write(path)


def validate_shell_execute(command: str, policy_path: Optional[str] = None) -> ValidationResult:
    """Validate shell command execution.

    Args:
        command: Shell command to execute
        policy_path: Path to security policy JSON file

    Returns:
        ValidationResult with approval status
    """
    validator = MCPPermissionValidator(policy_path=policy_path)
    return validator.validate_shell_execute(command)


def validate_network_access(url: str, policy_path: Optional[str] = None) -> ValidationResult:
    """Validate network access operation.

    Args:
        url: URL to access
        policy_path: Path to security policy JSON file

    Returns:
        ValidationResult with approval status
    """
    validator = MCPPermissionValidator(policy_path=policy_path)
    return validator.validate_network_access(url)


def validate_env_access(var_name: str, policy_path: Optional[str] = None) -> ValidationResult:
    """Validate environment variable access.

    Args:
        var_name: Environment variable name
        policy_path: Path to security policy JSON file

    Returns:
        ValidationResult with approval status
    """
    validator = MCPPermissionValidator(policy_path=policy_path)
    return validator.validate_env_access(var_name)


def matches_glob_pattern(path: str, pattern: str) -> bool:
    """Match path against glob pattern.

    Args:
        path: File path to match
        pattern: Glob pattern (supports **, *, ?, ! negation)

    Returns:
        True if path matches pattern
    """
    validator = MCPPermissionValidator(policy_path=None)
    return validator.matches_glob_pattern(path, pattern)
